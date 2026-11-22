"""
fall_eval.py — reproducible offline evaluation of the fall-alert decision logic.

    python3 fall_eval.py baseline                # the detector exactly as the live pipeline runs it
    python3 fall_eval.py compare                 # baseline vs improved on the same clips

Data: FallVision keypoint CSVs under datasets/raw/fallvision_extracted (fall clips and non-fall
clips; every clip is one labelled video). Pose keypoints are already extracted in those files, so
this evaluates the DECISION logic (BiLSTM windows + posture rules + alert merging), not YOLO.

Split: deterministic by clip name (md5), so every method sees the same clips. About 30% of clips
form the TEST set and are never used to choose thresholds; settings are chosen on the other 70%
(DEV). IMPORTANT LIMITS, repeated in docs/evaluation/FALL_DETECTION_IMPROVEMENT.md:
  * The BiLSTM was trained elsewhere (notebook not in this repo) and its training clips are not
    recorded, so its scores on these clips may be optimistic. Rule-based methods are unaffected.
  * Clip-level labels: a clip is a "fall" clip if the dataset puts it in the fall folder. A clip
    counts as alerted if the detector raises at least one alert in it.
  * Frame rate is not stored in the CSVs. Each CSV frame is treated as one analysis sample (the
    live pipeline analyses 6 samples per second), so "per hour" rates assume 6 samples/second.
  * Bed position is not in the data, so the bed-versus-floor rule cannot be evaluated here.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA_DIR = os.path.join(HERE, "..", "datasets", "raw", "fallvision_extracted")
FALL_DIR = "f_mask_b_1_keypoints_csv"
NONFALL_DIR = "nf_mask_b_1_ketpoints_csv"
FRAME_SIZE = 640.0            # CSV pixel coordinates top out at ~640
SAMPLE_HZ = 6.0               # the live pipeline analyses 6 samples per second
TEST_FRACTION_PERCENT = 30
KPT_CONF_MIN = 0.3


@dataclass
class Clip:
    name: str
    label: int                                   # 1 = fall clip, 0 = non-fall clip
    kpts: List[Optional[np.ndarray]]             # per sample: (17, 3) x, y, confidence in pixels, or None
    split: str = "dev"
    size: tuple = (FRAME_SIZE, FRAME_SIZE)       # frame (width, height) used to normalise model input

    @property
    def n(self) -> int:
        return len(self.kpts)


def split_of(name: str) -> str:
    h = int(hashlib.md5(name.encode()).hexdigest(), 16) % 100
    return "test" if h < TEST_FRACTION_PERCENT else "dev"


def _load_csv(path: str) -> List[Optional[np.ndarray]]:
    import pandas as pd
    df = pd.read_csv(path)
    out: List[Optional[np.ndarray]] = []
    for _, g in df.groupby("Frame", sort=True):
        k = g[["X", "Y", "Confidence"]].to_numpy(float)
        if len(k) >= 34:                          # two people in the frame: keep the more confident one
            first, second = k[:17], k[17:34]
            k = first if first[:, 2].mean() >= second[:, 2].mean() else second
        if len(k) < 17 or not np.any(k[:17, :2]):
            out.append(None)
        else:
            out.append(k[:17])
    return out


def load_clips(limit: Optional[int] = None) -> List[Clip]:
    clips: List[Clip] = []
    for folder, label in ((FALL_DIR, 1), (NONFALL_DIR, 0)):
        files = sorted(glob.glob(os.path.join(DATA_DIR, folder, "*.csv")))
        for f in files[:limit] if limit else files:
            name = os.path.basename(f)
            clips.append(Clip(name, label, _load_csv(f), split_of(name)))
    return clips


def to_vector(k: Optional[np.ndarray], size: tuple = (FRAME_SIZE, FRAME_SIZE)) -> np.ndarray:
    """The 34-value model input, exactly like the training/pose extractor: x/w, y/h interleaved."""
    if k is None:
        return np.zeros(34, dtype=np.float32)
    return (k[:, :2] / np.array(size, dtype=float)).reshape(-1).astype(np.float32)


# ── IKAR standing falls (videos, falls only): pose extracted once, cached ──────────────────

IKAR_DIR = os.path.join(HERE, "..", "datasets", "doi-10", "IKAR_dataset")
IKAR_CACHE = os.path.join(HERE, "..", "datasets", "processed", "ikar_keypoints.npz")


def extract_ikar() -> None:
    """Run YOLOv8n-pose at 6 samples/second over every IKAR video (like the live pipeline) and cache
    the pixel keypoints. Slow the first time; later runs read the cache."""
    import cv2
    from pose_extractor import PoseExtractor
    pose = PoseExtractor()
    out = {}
    videos = sorted(glob.glob(os.path.join(IKAR_DIR, "*", "videos", "*.mp4")))
    for n, path in enumerate(videos, 1):
        cap = cv2.VideoCapture(path)
        step = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 30.0) / SAMPLE_HZ))
        frames, idx = [], 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                _, pix = pose.extract_frame_detailed(frame)
                frames.append(np.zeros((17, 3)) if pix is None else np.asarray(pix, dtype=float))
            idx += 1
        cap.release()
        out[os.path.basename(path)] = np.stack(frames) if frames else np.zeros((0, 17, 3))
        if n % 25 == 0:
            print(f"  {n}/{len(videos)} videos", flush=True)
    os.makedirs(os.path.dirname(IKAR_CACHE), exist_ok=True)
    np.savez_compressed(IKAR_CACHE, **out)
    print(f"cached {len(out)} videos -> {IKAR_CACHE}")


def load_ikar() -> List[Clip]:
    import cv2
    data = np.load(IKAR_CACHE)
    paths = {os.path.basename(p): p for p in glob.glob(os.path.join(IKAR_DIR, "*", "videos", "*.mp4"))}
    clips = []
    for name in sorted(data.files):
        arr = data[name]
        kpts = [None if not np.any(f[:, :2]) else f for f in arr]
        size = (FRAME_SIZE, FRAME_SIZE)
        if name in paths:                               # normalise by the real frame size, like the live pipeline
            cap = cv2.VideoCapture(paths[name])
            w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            cap.release()
            if w and h:
                size = (float(w), float(h))
        clips.append(Clip(name, 1, kpts, "ikar", size))
    return clips


# ── detectors: clip -> list of alert sample indices ──────────────────────────

Detector = Callable[[Clip], List[int]]
MIN_GAP_SAMPLES = int(10.0 * SAMPLE_HZ)           # live pipeline: EVENT_MIN_GAP_S = 10 s


def merge_alerts(alerts: Sequence[int], gap: int = MIN_GAP_SAMPLES) -> List[int]:
    """The live pipeline drops any alert within 10 s of the previous one."""
    kept: List[int] = []
    for a in sorted(alerts):
        if not kept or a - kept[-1] >= gap:
            kept.append(a)
    return kept


_classifier = None


def shared_classifier():
    """The ORIGINAL checkpoint with its original threshold: part of the fixed baseline."""
    global _classifier
    if _classifier is None:
        from bilstm_model import FallClassifier
        _classifier = FallClassifier(os.path.join(HERE, "vitalyn_fall_bilstm.pt"), threshold=0.45)
    return _classifier


def baseline_detector(clip: Clip) -> List[int]:
    """The decision logic the live pipeline runs today: streaming BiLSTM OR posture-transition rule."""
    from fall_heuristic import PostureTransitionDetector, person_box
    from streaming_detector import StreamingFallDetector

    stream = StreamingFallDetector(shared_classifier())
    posture = PostureTransitionDetector()
    alerts: List[int] = []
    for i, k in enumerate(clip.kpts):
        if stream.push(to_vector(k, clip.size)) is not None:
            alerts.append(i)
        ar, h = person_box(k, KPT_CONF_MIN)
        if posture.update(ar, h)[0]:
            alerts.append(i)
    return merge_alerts(alerts)


def context_detector(cfg=None, min_score: float = 0.0) -> Detector:
    """The new context-aware detector (fall_context.py) as a clip detector."""
    from fall_context import ContextualFallDetector

    def run(clip: Clip) -> List[int]:
        det = ContextualFallDetector(cfg)
        alerts = []
        for i, k in enumerate(clip.kpts):
            sig = det.update(k)
            if sig is not None and sig.score >= min_score:
                alerts.append(i)
        return merge_alerts(alerts)

    return run


def scored_context_alerts(clip: Clip, cfg=None) -> List[float]:
    """Raw scores of every alert the context detector raises in a clip (after the 10 s merge)."""
    from fall_context import ContextualFallDetector
    det = ContextualFallDetector(cfg)
    hits = []
    for i, k in enumerate(clip.kpts):
        sig = det.update(k)
        if sig is not None:
            hits.append((i, sig.score))
    kept = set(merge_alerts([i for i, _ in hits]))
    return [sc for i, sc in hits if i in kept]


def union(*detectors: Detector) -> Detector:
    """Alert when any of the detectors alerts (the live pipeline raises on any source)."""
    return lambda clip: merge_alerts([a for d in detectors for a in d(clip)])


def bilstm_only(clip: Clip) -> List[int]:
    from streaming_detector import StreamingFallDetector
    stream = StreamingFallDetector(shared_classifier())
    return merge_alerts([i for i, k in enumerate(clip.kpts) if stream.push(to_vector(k, clip.size)) is not None])


V2_WEIGHTS = os.path.join(HERE, "vitalyn_fall_bilstm_v2.pt")
_v2 = None


def bilstm_v2_only(clip: Clip) -> List[int]:
    """The retrained BiLSTM (train_bilstm.py) with its validation-chosen threshold, live decision rules."""
    global _v2
    from streaming_detector import StreamingFallDetector
    if _v2 is None:
        from bilstm_model import FallClassifier
        summary = json.load(open(os.path.join(HERE, "training", "runs", "bilstm_v2", "summary.json")))
        _v2 = FallClassifier(V2_WEIGHTS, summary["decision_threshold"])
    stream = StreamingFallDetector(_v2)
    return merge_alerts([i for i, k in enumerate(clip.kpts) if stream.push(to_vector(k, clip.size)) is not None])


def posture_only(clip: Clip) -> List[int]:
    from fall_heuristic import PostureTransitionDetector, person_box
    posture = PostureTransitionDetector()
    out = []
    for i, k in enumerate(clip.kpts):
        ar, h = person_box(k, KPT_CONF_MIN)
        if posture.update(ar, h)[0]:
            out.append(i)
    return merge_alerts(out)


# ── metrics ──────────────────────────────────────────────────────────────────

def evaluate(clips: Sequence[Clip], detector: Detector, cache: Optional[Dict[str, List[int]]] = None) -> Dict:
    tp = fp = fn = tn = 0
    false_alerts = 0                              # every alert raised inside a non-fall clip
    nonfall_samples = 0
    for c in clips:
        if cache is not None and c.name in cache:
            alerts = cache[c.name]
        else:
            alerts = detector(c)
            if cache is not None:
                cache[c.name] = alerts
        fired = len(alerts) > 0
        if c.label == 1:
            tp, fn = tp + fired, fn + (not fired)
        else:
            fp, tn = fp + fired, tn + (not fired)
            false_alerts += len(alerts)
            nonfall_samples += c.n
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    hours = nonfall_samples / SAMPLE_HZ / 3600.0
    return {
        "clips": len(clips), "fall_clips": tp + fn, "nonfall_clips": fp + tn,
        "TP": int(tp), "FP": int(fp), "FN": int(fn), "TN": int(tn),
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "false_alert_clip_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,   # share of non-fall clips with an alert
        "false_alerts_per_hour": round(false_alerts / hours, 2) if hours else 0.0,
    }


def fmt(name: str, m: Dict) -> str:
    return (f"{name:34s} n={m['clips']:3d}  P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}  "
            f"false-alert clips={m['false_alert_clip_rate']:.3f}  false alerts/h={m['false_alerts_per_hour']:.1f}  "
            f"(TP{m['TP']} FP{m['FP']} FN{m['FN']} TN{m['TN']})")


def main(argv: List[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "baseline"
    clips = load_clips()
    dev = [c for c in clips if c.split == "dev"]
    test = [c for c in clips if c.split == "test"]
    print(f"{len(clips)} clips: dev {len(dev)} ({sum(c.label for c in dev)} fall), test {len(test)} ({sum(c.label for c in test)} fall)")
    if mode == "baseline":
        cache: Dict[str, List[int]] = {}
        for name, subset in (("dev", dev), ("TEST", test)):
            print(fmt(f"baseline [{name}]", evaluate(subset, baseline_detector, cache)))
        return 0
    if mode == "ablate":
        for label, det in (("BiLSTM only", bilstm_only), ("posture rule only", posture_only),
                           ("context (default cfg)", context_detector())):
            for name, subset in (("dev", dev), ("TEST", test)):
                print(fmt(f"{label} [{name}]", evaluate(subset, det)))
        return 0
    if mode == "tune":
        import itertools
        from dataclasses import replace
        from fall_context import ContextConfig
        base = ContextConfig()
        grid = {
            "min_drop": [0.7, 1.0, 1.3],
            "min_speed": [0.3, 0.45, 0.6, 0.8],
            "settle_samples": [4, 6, 9],
            "settle_tol": [0.3, 0.45, 0.7],
            "anchor": ["bottom", "centre"],
        }
        rows = []
        for vals in itertools.product(*grid.values()):
            cfg = replace(base, **dict(zip(grid.keys(), vals)))
            m = evaluate(dev, context_detector(cfg))
            rows.append((m["f1"], -m["false_alerts_per_hour"], dict(zip(grid.keys(), vals)), m))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        print("top settings on DEV only:")
        for f1, _, g, m in rows[:8]:
            print(f"  F1={f1:.3f} P={m['precision']:.3f} R={m['recall']:.3f} FA/h={m['false_alerts_per_hour']:.1f}  {g}")
        best = rows[0][2]
        print("chosen (dev):", json.dumps(best))
        print(fmt("context tuned [TEST]", evaluate(test, context_detector(replace(base, **best)))))
        return 0
    if mode == "extract-ikar":
        extract_ikar()
        return 0
    if mode == "report":
        # Final comparison with the settings now in ContextConfig (chosen on DEV), scored on TEST.
        for label, det in (("baseline (original live logic)", baseline_detector),
                           ("context detector", context_detector()),
                           ("context + posture rule", union(context_detector(), posture_only)),
                           ("context + original BiLSTM", union(context_detector(), bilstm_only)),
                           ("FINAL: retrained BiLSTM + context", union(bilstm_v2_only, context_detector()))):
            for name, subset in (("dev", dev), ("TEST", test)):
                print(fmt(f"{label} [{name}]", evaluate(subset, det)))
        return 0
    if mode == "v2":
        # Retrained BiLSTM vs the original checkpoint, alone and with the context rule. TEST is held out.
        ikar = load_ikar() if os.path.exists(IKAR_CACHE) else []
        for label, det in (("original BiLSTM only", bilstm_only),
                           ("retrained BiLSTM only", bilstm_v2_only),
                           ("context rule only", context_detector()),
                           ("retrained BiLSTM + context rule", union(bilstm_v2_only, context_detector())),
                           ("original BiLSTM + context rule", union(bilstm_only, context_detector()))):
            for name, subset in (("dev", dev), ("TEST", test)):
                print(fmt(f"{label} [{name}]", evaluate(subset, det)))
            if ikar:
                hits = sum(1 for c in ikar if det(c))
                print(f"{'':34s} IKAR standing-fall recall {hits}/{len(ikar)} = {hits / len(ikar):.3f}")
        return 0
    if mode == "calibrate":
        # Alert-level calibration: is an alert raised in a fall clip? Fit on DEV, check on TEST.
        from sklearn.linear_model import LogisticRegression
        def rows(subset):
            X, y = [], []
            for c in subset:
                for sc in scored_context_alerts(c):
                    X.append([sc]); y.append(c.label)
            return np.array(X), np.array(y)
        Xd, yd = rows(dev); Xt, yt = rows(test)
        lr = LogisticRegression().fit(Xd, yd)
        a, b = float(lr.coef_[0][0]), float(lr.intercept_[0])
        pt = lr.predict_proba(Xt)[:, 1]
        brier_raw = float(np.mean((Xt[:, 0] - yt) ** 2)); brier_cal = float(np.mean((pt - yt) ** 2))
        print(f"alerts: dev {len(yd)} ({yd.mean():.2f} real), test {len(yt)} ({yt.mean():.2f} real)")
        print(f"calibration fit on DEV: p = sigmoid({a:.4f} * score + {b:.4f})")
        print(f"TEST Brier score: raw score {brier_raw:.4f}  calibrated {brier_cal:.4f}  (lower is better)")
        print(f"TEST mean predicted {pt.mean():.3f} vs observed {yt.mean():.3f}")
        return 0
    print("unknown mode")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

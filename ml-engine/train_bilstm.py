"""
train_bilstm.py — reproducible training of the VITALYN BiLSTM fall classifier.

    python3 train_bilstm.py                 # trains, saves weights + config + history + plot

Same architecture as bilstm_model.BiLSTMFallClassifier (so the live pipeline can load the weights).

Data: FallVision bed keypoint CSVs (see fall_eval.py). Splits are by WHOLE CLIP (no frames of one video
in two sets):
  * TEST  (~30% of clips, fall_eval.split_of) — never touched here; used only by fall_eval.py.
  * DEV   (~70%) is split again by clip name into TRAIN (~80% of dev) and VALIDATION (~20% of dev).
Training uses TRAIN windows; early stopping and the decision threshold use VALIDATION clips.

Samples: sliding windows of 30 frames (stride 5) over each training clip, labelled with the clip's label
(weak labels: a fall clip also contains frames before the fall). Input per frame = 17 keypoints (x, y)
divided by 640, i.e. the same 34-value format as the live pipeline; frames without a person are zeros.
Augmentation (training only): horizontal mirror with left/right joints swapped, small random shift and scale.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bilstm_model import BiLSTMFallClassifier  # noqa: E402
from fall_eval import Clip, load_clips, to_vector  # noqa: E402
from streaming_detector import person_coverage  # noqa: E402

CFG = {
    "seed": 42,
    "seq_len": 30,
    "train_stride": 5,
    "eval_step": 15,                 # same window step as the live StreamingFallDetector
    "min_coverage": 0.8,             # same guard as live: windows with <80% person frames are not classified
    "min_consecutive": 2,            # same as live: two fall windows in a row
    "val_percent_of_dev": 20,
    "batch_size": 64,
    "epochs": 40,
    "learning_rate": 1e-3,
    "weight_decay": 1e-4,
    "optimizer": "Adam",
    "loss": "BCELoss (sigmoid output), positive class weighted by neg/pos ratio",
    "dropout": 0.3,
    "early_stopping_patience": 8,     # epochs without validation F1 improvement
    "augment_mirror_p": 0.5,
    "augment_shift": 0.03,            # fraction of the frame
    "augment_scale": 0.08,
}

OUT_DIR = os.path.join(HERE, "training", "runs", "bilstm_v2")
WEIGHTS_OUT = os.path.join(HERE, "vitalyn_fall_bilstm_v2.pt")

# COCO-17 left/right pairs, for mirroring
LR_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def val_split(name: str) -> bool:
    h = int(hashlib.md5(("val:" + name).encode()).hexdigest(), 16) % 100
    return h < CFG["val_percent_of_dev"]


def clip_matrix(clip: Clip) -> np.ndarray:
    return np.stack([to_vector(k) for k in clip.kpts]) if clip.kpts else np.zeros((0, 34), np.float32)


def windows(mat: np.ndarray, seq_len: int, stride: int) -> List[np.ndarray]:
    if len(mat) < seq_len:
        mat = np.vstack([np.zeros((seq_len - len(mat), 34), np.float32), mat])   # pad at the start (as in training format)
    return [mat[s:s + seq_len] for s in range(0, len(mat) - seq_len + 1, stride)]


def augment(w: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    w = w.copy()
    present = np.any(w != 0, axis=1)
    pts = w.reshape(len(w), 17, 2)
    if rng.random() < CFG["augment_mirror_p"]:
        pts[present, :, 0] = 1.0 - pts[present, :, 0]
        for a, b in LR_PAIRS:
            pts[:, [a, b]] = pts[:, [b, a]]
    scale = 1.0 + rng.uniform(-CFG["augment_scale"], CFG["augment_scale"])
    shift = rng.uniform(-CFG["augment_shift"], CFG["augment_shift"], size=2)
    pts[present] = (pts[present] - 0.5) * scale + 0.5 + shift
    return pts.reshape(len(w), 34)


def clip_probs(model: nn.Module, mat: np.ndarray, device: str) -> List[float]:
    """Window probabilities the way the live detector produces them (guarded windows -> None)."""
    ws = windows(mat, CFG["seq_len"], CFG["eval_step"])
    keep = [w for w in ws if person_coverage(w) >= CFG["min_coverage"]]
    if not keep:
        return []
    with torch.no_grad():
        x = torch.tensor(np.stack(keep), dtype=torch.float32, device=device)
        return model(x).squeeze(1).cpu().numpy().tolist()


def clip_fires(probs: List[float], thr: float) -> bool:
    need = 1 if len(probs) == 1 else CFG["min_consecutive"]
    run = 0
    for p in probs:
        run = run + 1 if p >= thr else 0
        if run >= need:
            return True
    return False


def prf(pred: List[bool], y: List[int]) -> Tuple[float, float, float]:
    tp = sum(p and t for p, t in zip(pred, y))
    fp = sum(p and not t for p, t in zip(pred, y))
    fn = sum((not p) and t for p, t in zip(pred, y))
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def best_threshold(all_probs: List[List[float]], y: List[int]) -> Tuple[float, float]:
    best = (0.5, -1.0)
    for thr in np.round(np.arange(0.2, 0.91, 0.05), 2):
        f1 = prf([clip_fires(p, thr) for p in all_probs], y)[2]
        if f1 > best[1]:
            best = (float(thr), f1)
    return best


def main() -> int:
    seed_everything(CFG["seed"])
    rng = np.random.default_rng(CFG["seed"])
    device = "cpu"          # small model; CPU keeps runs reproducible
    os.makedirs(OUT_DIR, exist_ok=True)

    clips = [c for c in load_clips() if c.split == "dev"]
    train = [c for c in clips if not val_split(c.name)]
    val = [c for c in clips if val_split(c.name)]
    print(f"dev clips {len(clips)}: train {len(train)} ({sum(c.label for c in train)} fall), "
          f"val {len(val)} ({sum(c.label for c in val)} fall); test clips are not used here")

    Xw, yw = [], []
    for c in train:
        for w in windows(clip_matrix(c), CFG["seq_len"], CFG["train_stride"]):
            if person_coverage(w) >= CFG["min_coverage"]:
                Xw.append(w)
                yw.append(c.label)
    Xw = np.stack(Xw).astype(np.float32)
    yw = np.array(yw, dtype=np.float32)
    pos, neg = float(yw.sum()), float(len(yw) - yw.sum())
    pos_weight = neg / max(pos, 1.0)
    print(f"training windows {len(yw)} ({int(pos)} fall, {int(neg)} non-fall); positive weight {pos_weight:.2f}")

    val_mats = [clip_matrix(c) for c in val]
    val_y = [c.label for c in val]

    model = BiLSTMFallClassifier(dropout=CFG["dropout"]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=CFG["learning_rate"], weight_decay=CFG["weight_decay"])
    bce = nn.BCELoss(reduction="none")

    history: List[Dict] = []
    best_f1, best_state, best_epoch, waited = -1.0, None, 0, 0
    t0 = time.time()
    for epoch in range(1, CFG["epochs"] + 1):
        model.train()
        order = rng.permutation(len(yw))
        total, seen = 0.0, 0
        for s in range(0, len(order), CFG["batch_size"]):
            idx = order[s:s + CFG["batch_size"]]
            xb = torch.tensor(np.stack([augment(Xw[i], rng) for i in idx]), dtype=torch.float32, device=device)
            yb = torch.tensor(yw[idx], dtype=torch.float32, device=device)
            p = model(xb).squeeze(1).clamp(1e-6, 1 - 1e-6)
            weights = torch.where(yb > 0.5, torch.full_like(yb, pos_weight), torch.ones_like(yb))
            loss = (bce(p, yb) * weights).mean()
            opt.zero_grad()
            loss.backward()                       # backpropagation through time
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += loss.item() * len(idx)
            seen += len(idx)

        model.eval()
        vprobs = [clip_probs(model, m, device) for m in val_mats]
        # validation loss on clip level (max window probability vs clip label)
        vmax = np.array([max(p) if p else 0.0 for p in vprobs]).clip(1e-6, 1 - 1e-6)
        vy = np.array(val_y, dtype=float)
        vloss = float(-np.mean(vy * np.log(vmax) + (1 - vy) * np.log(1 - vmax)))
        thr, vf1 = best_threshold(vprobs, val_y)
        history.append({"epoch": epoch, "train_loss": round(total / seen, 5), "val_loss": round(vloss, 5),
                        "val_f1": round(vf1, 4), "val_threshold": thr})
        print(f"epoch {epoch:2d}  train loss {total / seen:.4f}  val loss {vloss:.4f}  val F1 {vf1:.3f} @ {thr:.2f}")
        if vf1 > best_f1 + 1e-4:
            best_f1, best_epoch, waited = vf1, epoch, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            best_thr = thr
        else:
            waited += 1
            if waited >= CFG["early_stopping_patience"]:
                print(f"early stopping: no validation improvement for {waited} epochs")
                break

    model.load_state_dict(best_state)
    torch.save(model.state_dict(), WEIGHTS_OUT)
    pr, rc, f1 = prf([clip_fires(clip_probs(model, m, device), best_thr) for m in val_mats], val_y)
    summary = {
        "config": CFG, "best_epoch": best_epoch, "decision_threshold": best_thr,
        "validation": {"precision": round(pr, 4), "recall": round(rc, 4), "f1": round(f1, 4), "clips": len(val)},
        "train_clips": len(train), "train_windows": int(len(yw)), "positive_weight": round(pos_weight, 3),
        "parameters": sum(p.numel() for p in model.parameters()),
        "seconds": round(time.time() - t0, 1), "weights": os.path.relpath(WEIGHTS_OUT, HERE),
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(OUT_DIR, "history.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        w.writeheader()
        w.writerows(history)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ep = [h["epoch"] for h in history]
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        ax[0].plot(ep, [h["train_loss"] for h in history], label="train loss (weighted BCE)")
        ax[0].plot(ep, [h["val_loss"] for h in history], label="validation loss (clip level)")
        ax[0].axvline(best_epoch, color="grey", ls="--", lw=1)
        ax[0].set_xlabel("epoch"); ax[0].legend(); ax[0].set_title("Loss")
        ax[1].plot(ep, [h["val_f1"] for h in history], color="#2e5b4f")
        ax[1].axvline(best_epoch, color="grey", ls="--", lw=1)
        ax[1].set_xlabel("epoch"); ax[1].set_ylim(0, 1); ax[1].set_title("Validation F1 (clip level)")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "learning_curves.png"), dpi=130)
    except Exception as exc:  # plotting is optional
        print("plot skipped:", exc)
    print(json.dumps(summary["validation"]), "best epoch", best_epoch, "threshold", best_thr)
    print("saved", WEIGHTS_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

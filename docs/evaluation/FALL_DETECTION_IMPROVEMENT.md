# Fall detection improvement: method and measured results

Reproduce everything below with `cd ml-engine && python3 fall_eval.py report` (and `tune`, `calibrate`,
`extract-ikar`). No number here is estimated or copied from elsewhere.

## What changed
The architecture is unchanged: YOLOv8n-pose -> 17 keypoints -> streaming BiLSTM **plus** one rule-based
check, both able to raise a *potential* fall for human review. Only the rule-based check changed:

| | Before | After (default) |
|---|---|---|
| Rule | Posture transition: upright -> horizontal with height collapse (`fall_heuristic.py`) | Context detector (`fall_context.py`) |
| Posture | box aspect ratio | body height relative to its own resting level, using body-relative units (torso length) |
| Movement | upright-to-horizontal within ~2 s | descent of >= 0.3 body-lengths within 12 samples (~2 s) |
| Location | none | body must end >= 0.7 body-lengths lower than where it was resting (bed level); optional bed zone suppresses "lying in the bed" |
| Consecutive frames | 3 horizontal samples | must then stay low and still for 4 consecutive samples; a dip that recovers is ignored |
| Frame noise | none | 3-sample median smoothing, low-confidence keypoints ignored |
| Confidence | heuristic 0.5-0.9 | logistic calibration fitted on dev alerts |

`VITALYN_FALL_RULE=legacy` switches back to the old rule. The BiLSTM still runs in both modes.

## Data and protocol
* **FallVision bed subset** (keypoint CSVs, 243 fall clips, 373 non-fall clips: lying, sleeping, sitting,
  changing position on a bed). Deterministic split by clip name: **dev 407** clips (158 fall), **test 209** (85 fall).
  Settings were searched on dev only (216 combinations); test was scored after the choice.
* **IKAR** (278 standing-fall videos: trips, slips, faintings, blackouts; falls only). Poses extracted with
  the same YOLOv8n-pose at 6 samples/second. Used to check standing falls, which FallVision does not contain.
* A clip counts as detected if at least one alert is raised in it. False alerts per hour assume one CSV
  frame = one analysis sample at 6 Hz (the CSVs do not store their frame rate).

## Results on the held-out FallVision test split (209 clips)

| Method | Precision | Recall | F1 | Non-fall clips with an alert | False alerts / hour |
|---|---|---|---|---|---|
| Live logic before (BiLSTM + posture rule) | 0.289 | 0.129 | 0.179 | 21.8% | 42.8 |
| **New default (BiLSTM + context detector)** | **0.692** | **0.635** | **0.663** | **19.4%** | **38.0** |
| Context + old posture rule together | 0.567 | 0.694 | 0.624 | 36.3% | 71.3 |

The BiLSTM raised **no alerts at all** on these clips, alone or combined, so every alert above comes from
the rule-based check. Adding the old posture rule back raises recall slightly but almost doubles false alerts.

## Standing falls (IKAR, 278 videos, recall only)

| Method | Falls detected |
|---|---|
| Live logic before | 192 / 278 (69.1%) |
| Context detector, lowest-point anchor only | 51 / 278 (18.3%) |
| **New default (combined lowest-point + body-centre anchor)** | **211 / 278 (75.9%)** |

IKAR was used to choose the anchor (the lowest-point anchor misses standing falls because the feet are
already on the floor), so these figures are not a held-out estimate.

## Calibration
Fitted on 155 dev alerts: `p = sigmoid(0.1927 * score + 0.5724)`. On 81 test alerts the Brier score fell
from 0.257 (raw score) to 0.211. The slope is small: the score separates real from false alerts only
weakly, so the confidence shown to staff is close to "about 2 in 3 alerts like this were real falls in the
development data". It is not a clinical probability.

## Retrained BiLSTM (train_bilstm.py)

The original checkpoint raised no alerts on this data, so the BiLSTM was retrained with the **same
architecture** and a recorded, reproducible run (`ml-engine/training/runs/bilstm_v2/`: summary, history,
learning curves). Re-running `python3 train_bilstm.py` gives bit-identical weights (seed 42, CPU).

* Data: TRAIN = 330 dev clips (129 fall) -> 5,171 windows of 30 frames (stride 5) with >= 80% person
  frames; VALIDATION = 77 dev clips (29 fall), split by clip name; TEST clips never used.
* Adam, learning rate 1e-3, weight decay 1e-4, batch 64, max 40 epochs, early stopping on validation F1
  (patience 8, best epoch 20), dropout 0.3, gradient clipping 1.0, BCE with the fall class weighted 1.97
  (non-fall/fall ratio). Augmentation: mirror (left/right joints swapped), +-3% shift, +-8% scale.
* Decision threshold 0.65, chosen on validation clips with the live rules (two windows in a row).

Held-out TEST (209 clips) with live decision rules:

| Model | Precision | Recall | F1 | False alerts / hour | IKAR standing falls |
|---|---|---|---|---|---|
| Original BiLSTM alone | no alerts | 0 | 0 | 0 | 0/278 |
| Retrained BiLSTM alone | 0.817 | 0.577 | 0.676 | 17.4 | 0/278 |
| Context rule alone | 0.692 | 0.635 | 0.663 | 38.0 | 211/278 |
| **Default: retrained BiLSTM + context rule** | 0.660 | **0.753** | **0.703** | 55.4 | 211/278 |

**Choice of default.** On the 77 validation clips (not used for training) the BiLSTM alone had the best
F1 (0.760 vs 0.719 combined) and far fewer false alerts, but it detects **no standing falls** (IKAR clips
are short, median 23 samples against a 30-sample window, and it was trained only on bed scenes). Because
the objective puts recall first and standing falls are common, the default is BiLSTM + context rule;
`VITALYN_FALL_RULE=off` runs the BiLSTM alone when fewer false alarms matter more. The original checkpoint
remains available with `VITALYN_BILSTM_WEIGHTS=ml-engine/vitalyn_fall_bilstm.pt`.

Overfitting evidence: training loss falls steadily while validation loss is noisy and stops improving
after about epoch 5; validation F1 still rises to epoch 20, hence early stopping on F1. Validation has
only 77 clips, so its numbers are uncertain.

## Live status display, false-alert veto and speed

**Status shown on Watch Live** (`ml-engine/live_status.py`): "Normal bed activity", "Potential fall
detected" or "Uncertain — Manual verification required", with **Normal activity confidence** and
**Potential fall confidence**. Both percentages are the retrained BiLSTM's sigmoid output (fall % =
P(fall) averaged over the last two windows, normal % = 100 − fall %). When the model has no valid
prediction (first 5 seconds, or under 80% frames with a person) no percentage is shown and the status is
Uncertain. Bands chosen on the 77 validation clips: fall probability < 0.35 = Normal (84% of normal
windows, 24% of fall-clip windows); 0.35 to the 0.65 threshold = Uncertain; an alert in the last 10 s =
Potential fall, with the detector that raised it. If the movement rule sees the body below its resting
level without a confirmed fall, the status is Uncertain.

**False-alert veto:** a rule alert is held back when the BiLSTM has a valid prediction with fall
probability < 0.10 (`VITALYN_FALL_RULE_VETO`). Chosen on validation (false alerts/h 48 → 20, recall
unchanged, F1 0.72 → 0.81), then confirmed once on test:

| Test (209 clips) | Precision | Recall | F1 | Non-fall clips alerted | False alerts / hour | IKAR standing falls |
|---|---|---|---|---|---|---|
| Retrained BiLSTM + rule, no veto | 0.660 | 0.753 | 0.703 | 26.6% | 55.4 | 211/278 |
| **Shipped: + veto 0.10** | **0.759** | 0.741 | **0.750** | **16.1%** | **33.3** | 209/278 |

**Speed:** the BiLSTM now runs on CPU with `torch.inference_mode()`: 0.77 ms per window against 3.4 ms on
the Mac GPU (identical outputs, max difference 2.5e-14). YOLOv8n-pose stays on the GPU at about 11 ms per
frame; its input size was not reduced, because that could change keypoint accuracy without a way to check it.

The batch pipeline for uploaded videos does not apply the veto (its BiLSTM runs after the frame loop).

## Limitations (read before any claim)
* Not clinically validated. Every alert remains a potential event for staff review.
* The ORIGINAL BiLSTM's training record is unknown and it contributes no alerts on this data; the retrained model replaces it by default.
* False alerts per hour fell only slightly (42.8 -> 38.0). The big change is precision and recall.
* The bed-zone rule needs a bed rectangle, which the datasets do not have, so it is unit-tested only.
* "Lower in the image" means closer to the floor for side or angled cameras; it is weak for a camera
  pointing straight down.
* Timing thresholds are in samples (6 per second live). The CSV frame rate is unknown, so live timing may differ.
* Known trade-off: lowering oneself all the way to the floor slowly can still alert (tested in
  `tests/test_fall_context.py`). Slow position changes at bed level do not.
* Real-camera validation on site has not been done.

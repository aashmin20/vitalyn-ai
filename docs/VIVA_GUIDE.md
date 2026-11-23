# VITALYN: viva and presentation guide

Deep Learning, Semester V, project evaluation on **Monday 23 November 2026**:
**8 minutes demo + 4 minutes viva, solo.**

Every number in this guide comes from code in this repository that you can re-run (section 9). The only
thing not on record is how the ORIGINAL BiLSTM checkpoint was trained; the model you present is the one
retrained here, whose settings are all recorded.

---

## 0. The 30-second pitch

> Patients in hospital beds can fall, and nurses cannot watch every bed all the time. VITALYN is a hospital
> management system whose core is a camera-based fall monitor. A pretrained pose network (YOLOv8n-pose)
> turns each video frame into 17 body keypoints. A BiLSTM that I trained, plus a context-aware rule, look at
> how those keypoints move over time and raise a **potential** fall for a nurse to check. Staff see a live
> status (normal / uncertain / potential fall) with the model's own confidence. On held-out clips F1 went
> from 0.18 (earlier version) to 0.75. It is a research prototype and not clinically validated.

---

## 1. Requirement check against the evaluation guidelines

| Guideline requirement | Status | Evidence in the project | What to do before the viva |
|---|---|---|---|
| Problem, input/output, use case, dataset, measurable objective | Met | Section 2 below | Learn section 2 by heart |
| Why deep learning | Met | Pose estimation from raw pixels needs a CNN; fall is a temporal pattern (sequence model) | Section 2 |
| Dataset origin, size, labels, quality | Partly | FallVision CSVs (616 clips) and IKAR (278 videos) are real and counted in section 3 | **`docs/research/DATASET_RESEARCH.md` contains descriptions that do not match the real files (e.g. "~100 hours", "hospital recordings", "stereo depth"). Do not quote that file.** Use section 3 here |
| Preprocessing, split, leakage prevention | Met for evaluation | Normalisation, 6 fps sampling, deterministic clip-level split (section 3) | Explain clip-level split = no frames of one video in both sets |
| Augmentation | Met | Mirror with left/right joints swapped, ±3% shift, ±8% scale (training only) | Section 5.2 |
| Model layers, activations, loss | Met | BiLSTM layers read from the checkpoint (section 5) | Section 5 |
| Optimizer, learning rate, batch size, epochs | Met | `ml-engine/train_bilstm.py`, recorded run in `ml-engine/training/runs/bilstm_v2/` (section 5.2) | Learn the numbers in section 5.2 |
| Mathematical understanding | Prepare | Section 6 | Practise explaining LSTM gates, BCE loss, backprop |
| Implementation ownership, training/inference pipeline | Met | Training (`train_bilstm.py`), inference (`bilstm_model.py`, `streaming_detector.py`), evaluation (`fall_eval.py`) are all in the repo | Be able to walk through `train_bilstm.py` (section 10) |
| Metrics: precision, recall, F1, confusion matrix | Met | Section 7 (held-out test, confusion matrices) | Explain why recall matters and why accuracy would mislead |
| Baseline / alternative | Met | Old live logic vs new; ablations (BiLSTM only, rule only, combined) | Section 7 |
| Overfitting, validation, failure cases, generalization | Met (honestly) | Dev/test split, IKAR standing falls, failure list in section 8 | Section 8 |
| Reproducibility: code, dependencies, weights, data, results | Met | Seed 42; re-running training gives bit-identical weights (checked). `fall_eval.py` is deterministic | Weights and datasets are git-ignored: **keep a local copy and a USB copy** |
| Disclose pretrained models and AI tools | Do it | Section 14 | Put it on your last slide |
| Demo: real inference, not UI tour | Plan | Section 11 demo script | Rehearse with a timer |
| No dependence on internet for the only copy | **Risk** | App uses Supabase (cloud database) | Keep the evaluation script and a SQLite fallback ready (section 12) |

**The story for a Deep Learning panel:** the original BiLSTM checkpoint (trained in an earlier notebook,
no record kept) raised **no alerts** on the evaluation clips. I found this with a proper evaluation, then
**retrained the BiLSTM myself** with a recorded split, augmentation, class weighting and early stopping.
The retrained model alone reaches F1 0.676 on the held-out test (precision 0.817). Combined with the
context rule and the false-alert veto it reaches F1 0.750 (33 false alerts/h). Remaining honest weakness: the BiLSTM does not detect standing falls
(IKAR); the rule covers those. Questions 18-20 in section 13 prepare you for this.

---

## 2. Problem definition

* **Problem:** detect potential patient falls in a hospital room from a camera, quickly, without
  alarming on normal bed activity (lying, sleeping, sitting up, turning over).
* **Input:** live video from a phone or webcam registered to a patient (or an uploaded video).
* **Output:** a *potential fall* alert with patient, room, time and a confidence, shown to nurses and
  doctors, who acknowledge and resolve it (their name is recorded).
* **Use case:** a ward where one nurse covers many beds.
* **Measurable objective:** maximise recall (do not miss falls) while keeping precision and the false-alert
  rate usable. Reported as precision, recall, F1, confusion matrix and false alerts per hour.
* **Why deep learning:**
  1. Finding a body and its joints in raw pixels is a perception problem. Hand-written rules cannot do it;
     a CNN (YOLOv8n-pose) learns it from large labelled data.
  2. A fall is a pattern over time, not one frame. Sequence models (LSTM) are designed for patterns in
     time series.
  3. Using keypoints instead of raw pixels makes the temporal model small (34 numbers per frame), faster,
     and less sensitive to clothing, lighting and background, and better for privacy.

---

## 3. Data

| Dataset | What it really is (checked in the files) | Used for |
|---|---|---|
| **FallVision (bed subset)** | 616 keypoint CSV files already extracted from videos: **243 fall clips** (`B_D_*`) and **373 non-fall clips** (`B_N_*`: lying, sleeping, sitting, changing position). Each row: frame, keypoint name, x, y, confidence for 17 COCO keypoints. Median ~90 frames per clip | Evaluation (dev/test split) |
| **IKAR** (`datasets/doi-10`) | 278 short MP4 videos of simulated falls by 7 volunteers on mats: trips 92, slips 64, faintings 65, blackouts 57. Falls only. CC BY 4.0 | Standing-fall recall check |
| BiLSTM training data | FallVision **dev** clips only: 330 train clips (129 falls) → 5,171 windows; 77 validation clips (29 falls). Test clips never used | Training (`train_bilstm.py`) |

**Preprocessing (same as the BiLSTM was trained on, `ml-engine/pose_extractor.py`):**
1. Sample the video at 6 frames per second.
2. YOLOv8n-pose finds the person and 17 keypoints (x, y, confidence) per frame.
3. Normalise: x divided by frame width, y by frame height, giving 34 numbers per frame in [0, 1].
4. Group 30 consecutive samples (5 seconds) into one window of shape (30, 34). A frame with no person
   becomes all zeros.

**Split and leakage prevention (`ml-engine/fall_eval.py:58`, `split_of`):** each clip goes to dev (70%)
or test (30%) by a hash of its file name. A whole clip is in one set only, so frames from the same video
never appear in both (that would leak). Result: **dev 407 clips (158 falls), test 209 clips (85 falls)**.
All settings were chosen on dev; test was scored once at the end.

**Quality issues to admit:**
* The CSV frame rate is not stored; I treat each row as one 6 fps sample.
* Some frames contain two people; I keep the more confident one.
* Fall clips are named `B_D` and non-fall `B_N`; the recording conditions may differ between classes,
  which a model could exploit (possible bias).
* Training labels are weak: every window of a fall clip is labelled "fall", even the frames before the fall.

---

## 4. How the whole system works (workflow)

```
 Phone / webcam                 Mac (backend)                                          Browser (staff)
 ───────────────     ───────────────────────────────────────────────────────────     ─────────────────
 patient QR page ──► phone gateway (HTTPS, port 8443)
   (JPEG frames)         │
                         ▼
                  capture thread ──► latest frame
                                          │  6 times per second
                                          ▼
                        YOLOv8n-pose (pretrained CNN) → 17 keypoints (x, y, conf)
                                          │
                     ┌────────────────────┴─────────────────────┐
                     ▼                                          ▼
       normalise → 34 numbers                       pixel keypoints
       sliding window of 30                          │
       BiLSTM → P(fall) every 15 samples             ▼
       (guard: ≥80% frames with a person)     Context-aware rule:
       2 windows in a row ≥ 0.65 → signal     descent below resting level + fast + settles low
                     │                                          │
                     └──────────────┬───────────────────────────┘
                                    ▼
                    potential fall (merged, max 1 per 10 s)
                                    │
                         fall_event + alert rows in database (Supabase Postgres;
                         local outbox if the database is down)
                                    │
                         live event stream (SSE) ─────────────────────────────►  alarm on Watch Live,
                                                                                  bell, alerts page;
                                                                                  nurse acknowledges/resolves
```

The hospital part (logins with roles, admissions, transfers, discharge, ward board, appointments) is
ordinary web engineering around this core. The guidelines say UI carries little weight, so spend about 30
seconds on it at most.

---

## 5. The models

### 5.1 YOLOv8n-pose (pretrained, not trained by me)
* From Ultralytics, pretrained on COCO keypoints. File `yolov8n-pose.pt` (~6 MB), the smallest variant,
  chosen for an 8 GB Mac.
* A CNN backbone extracts image features; a head predicts person boxes and 17 keypoints with confidences
  in one pass ("you only look once").
* Used as a **frozen feature extractor** (no fine-tuning). Settings: confidence 0.25 in the extractor.

### 5.2 BiLSTM fall classifier (`ml-engine/bilstm_model.py`, trained by `ml-engine/train_bilstm.py`)
Weights `ml-engine/vitalyn_fall_bilstm_v2.pt` (**154,689 parameters**). Architecture (same as the original
checkpoint, so the live pipeline loads either):

| Layer | Shape | Notes |
|---|---|---|
| Input | (batch, 30, 34) | 30 time steps × 17 keypoints × (x, y) |
| LSTM layer 1, bidirectional | 34 → 64 per direction | weights (256, 34): 4 gates × 64 units |
| LSTM layer 2, bidirectional | 128 → 64 per direction | input 128 = 64 forward + 64 backward; dropout 0.3 between layers |
| Mean pooling over time | (batch, 30, 128) → (batch, 128) | average of all 30 outputs |
| Dense fc1 + ReLU | 128 → 32 | |
| Dense fc2 + sigmoid | 32 → 1 | probability of "fall" |

**Training (recorded in `ml-engine/training/runs/bilstm_v2/summary.json`):**

| Setting | Value | Why |
|---|---|---|
| Loss | Binary cross-entropy (`nn.BCELoss`), fall class weighted ×1.97 | Binary output with sigmoid; weighting balances 1,744 fall vs 3,427 non-fall windows |
| Optimizer | Adam, learning rate 0.001, weight decay 0.0001 | Adam adapts the step size per weight; weight decay is L2 regularisation |
| Batch size | 64 | Stable gradient estimates, fast on CPU |
| Epochs | up to 40, **early stopping** on validation F1 (patience 8); best epoch **20**; stopped at 28 | Stops before overfitting |
| Dropout | 0.3 between LSTM layers | Regularisation |
| Gradient clipping | norm 1.0 | Prevents exploding gradients in the LSTM |
| Augmentation | mirror (left/right joints swapped) p=0.5, shift ±3%, scale ±8% | More variety from a small dataset |
| Seed | 42 (CPU) | Re-running gives identical weights |
| Training time | about 1 minute on a MacBook CPU | |
| Decision threshold | **0.65**, chosen on validation clips | Best validation F1 with the live rules |

* **Decision rule (same as live):** window of 30 every 15 samples, at least 80% person frames, probability
  ≥ 0.65 in **two consecutive windows**.
* **Learning curves:** `ml-engine/training/runs/bilstm_v2/learning_curves.png`. Training loss falls steadily
  from 0.88 to 0.39. Validation loss (77 clips, so noisy) stops improving after about epoch 5, which shows
  some overfitting, while validation F1 keeps rising to 0.81 at epoch 20. That is why early stopping
  watches F1. (Training loss is per window, validation loss per clip, so the two are not directly
  comparable.)
* **The original checkpoint** `vitalyn_fall_bilstm.pt` (trained earlier in a notebook whose settings were
  not recorded) is kept for comparison only.

**Why each design choice (defend these):**
* *LSTM rather than a plain RNN:* gates avoid vanishing gradients over 30 steps.
* *Bidirectional:* the window is complete before classification, so the model can use frames after the
  event too. The cost is that it cannot classify until the window is full.
* *Two layers:* the first learns joint movements, the second learns patterns of those movements.
* *Mean pooling instead of the last hidden state:* uses the whole window, more robust to where in the
  window the fall happens.
* *Dropout 0.3:* reduces overfitting on a small dataset.
* *Keypoints as input:* small, fast, privacy-friendly; does not depend on clothes or lighting.

### 5.3 Context-aware fall rule (my design, `ml-engine/fall_context.py`)
Not learned. Its few parameters were **tuned on the dev split** (216 combinations, `fall_eval.py tune`).
Per sample:
1. **Posture/height:** from confident keypoints only, two heights: the lowest body point and the
   body centre, smoothed with a 3-sample median. The unit is torso length, so it does not matter how far
   the camera is.
2. **Location:** the person's *resting level* is the median height over the last ~8 seconds (excluding the
   newest 2 s). A fall must end **≥ 0.7 torso-lengths lower** than that level (bed → floor). Optional bed
   rectangle: ending inside it is "lying in bed", never a fall.
3. **Movement:** the descent must be fast, at least **0.3 torso-lengths within 12 samples (~2 s)**.
   Slow position changes do not qualify.
4. **Consecutive frames:** the body must then **stay low and still for 4 samples**. A dip that recovers
   (bending, sitting) is ignored.
5. **Confidence:** a heuristic score, then logistic calibration fitted on dev alerts.

Why two heights: with only the lowest point, a fall from *standing* is missed (the feet are already on the
floor). On IKAR that version caught only 18% of falls; with both heights, 76%.

---

## 6. The mathematics (be ready to explain)

**Forward pass of one LSTM cell at time t** (x_t = 34 inputs, h = hidden state, c = cell state):

```
f_t = σ(W_f·[h_{t-1}, x_t] + b_f)      forget gate: what to erase from memory
i_t = σ(W_i·[h_{t-1}, x_t] + b_i)      input gate: what new information to store
g_t = tanh(W_g·[h_{t-1}, x_t] + b_g)   candidate memory
o_t = σ(W_o·[h_{t-1}, x_t] + b_o)      output gate
c_t = f_t ⊙ c_{t-1} + i_t ⊙ g_t         new memory (⊙ = element-wise product)
h_t = o_t ⊙ tanh(c_t)                   output at time t
```
Four gates × 64 units = 256 rows: that is why the weight matrix is (256, 34).
Bidirectional = one LSTM reads t = 1→30, another reads 30→1, and their outputs are joined (64+64 = 128).

**Activations:** σ(z) = 1/(1+e^(−z)) squashes to (0, 1) (gates, final probability);
tanh to (−1, 1); ReLU(z) = max(0, z) in the dense layer (cheap, no vanishing gradient for z > 0).

**Loss (binary cross-entropy)** for label y ∈ {0, 1} and prediction p:
`L = −[ y·log(p) + (1−y)·log(1−p) ]`. It is small when p is close to y and grows sharply for confident
mistakes. Minimising it is maximum likelihood for a Bernoulli output.

**Learning:** gradient descent updates every weight w: `w ← w − η · ∂L/∂w` (η = learning rate).
Adam (if used) keeps running averages of the gradient and its square to adapt the step per weight.

**Backpropagation:** the chain rule carries ∂L/∂p back through sigmoid → fc2 → ReLU → fc1 → pooling →
each LSTM step. Through time this is *backpropagation through time (BPTT)*: the network is unrolled over
30 steps. The cell state path `c_t = f_t ⊙ c_{t-1} + …` lets gradients flow with little shrinking, which
is why LSTMs avoid the vanishing-gradient problem of plain RNNs.

**Dropout:** during training a random 30% of activations between LSTM layers are set to zero, so the
network cannot rely on single units. It is off at inference (`model.eval()`).

**Metrics:**
* Precision = TP / (TP + FP): of the alerts raised, how many were real falls.
* Recall = TP / (TP + FN): of the real falls, how many were caught.
* F1 = 2PR / (P + R): harmonic mean, high only if both are high.
* Accuracy would mislead: with many non-fall clips, "never alert" looks accurate but catches nothing.

**Calibration:** p = σ(a·score + b), fitted by logistic regression on dev alerts (a = 0.1927,
b = 0.5724). Brier score = mean (p − y)², lower is better.

---

## 7. Experiments and results

All from `cd ml-engine && python3 fall_eval.py report` and `python3 fall_eval.py v2`
(test = 209 held-out clips: 85 falls, 124 non-falls; none used for training or choosing settings).

| Method | Precision | Recall | F1 | Non-fall clips alerted | False alerts / hour |
|---|---|---|---|---|---|
| Baseline: original live logic (original BiLSTM + posture rule) | 0.289 | 0.129 | 0.179 | 21.8% | 42.8 |
| Original BiLSTM alone | no alerts | 0.000 | 0.000 | 0% | 0 |
| **Retrained BiLSTM alone** | **0.817** | 0.577 | 0.676 | **8.9%** | **17.4** |
| Context rule alone | 0.692 | 0.635 | 0.663 | 19.4% | 38.0 |
| Context rule + old posture rule | 0.567 | 0.694 | 0.624 | 36.3% | 71.3 |
| Retrained BiLSTM + context rule (no veto) | 0.660 | 0.753 | 0.703 | 26.6% | 55.4 |
| **Shipped: BiLSTM + rule + veto 0.10** | **0.759** | 0.741 | **0.750** | **16.1%** | **33.3** |

**Why this default:** on the 77 validation clips the BiLSTM alone had the best F1 (0.760 vs 0.719) and
far fewer false alerts, but it caught **0 of 278** IKAR standing falls, while the context rule caught 211.
The objective puts recall first, so the default combines both. `VITALYN_FALL_RULE=off` gives the
BiLSTM-only mode with fewer false alarms.

**Confusion matrices (test):**

| Baseline | Predicted fall | Predicted no fall |
|---|---|---|
| Real fall | TP 11 | FN 74 |
| No fall | FP 27 | TN 97 |

| Retrained BiLSTM alone | Predicted fall | Predicted no fall |
|---|---|---|
| Real fall | TP 49 | FN 36 |
| No fall | FP 11 | TN 113 |

| Shipped (BiLSTM + rule + veto) | Predicted fall | Predicted no fall |
|---|---|---|
| Real fall | TP 63 | FN 22 |
| No fall | FP 20 | TN 104 |

**Veto (false-alert reduction):** a rule alert is held back when the BiLSTM sees the person clearly and its
fall probability is below 0.10. Chosen on validation (false alerts/h 48 → 20), confirmed on test
(55.4 → 33.3 per hour, F1 0.703 → 0.750, one extra missed fall).

**Live fall-risk levels on Watch Live:** Normal (< 25%), Low risk (25–45%), Medium "Potential fall"
(45–75%) and High "FALL DETECTED" (≥ 75% or any alert), updated every sample (6 per second) and pushed to
the page instantly. Risk = the higher of the BiLSTM fall probability (sigmoid output, mean of the last two
windows) and the posture score (`ml-engine/fall_risk.py`: torso horizontal × shoulders below the person's
resting level; a heuristic, not a probability). The panel shows both and says which one drives the level.
Bed versus floor: lying at the resting (bed) level scores low; lying lower than before scores high.
Posture alerts after 2 s at High: test F1 0.750 → 0.741, false alerts 33.3 → 36.4 per hour (more
sensitive, slightly less precise; `VITALYN_POSTURE_ALERTS=off` restores the evaluated logic). Code:
`ml-engine/live_status.py`, `ml-engine/fall_risk.py`.

**Speed:** BiLSTM on CPU 0.77 ms per window (3.4 ms on the Mac GPU, same outputs); pose model ~11 ms per
frame on the GPU.

**Standing falls (IKAR, falls only, recall):** baseline 192/278 (69.1%), retrained BiLSTM 0/278, shipped
**209/278 (75.2%)**, all from the context rule. IKAR clips are short (median 23 samples, below the
30-sample window) and the BiLSTM was trained only on bed scenes. IKAR was used to choose the rule's
anchor, so this is not a held-out estimate.

**Overfitting check:** retrained BiLSTM validation F1 0.760 vs test 0.676, a drop expected from a small
validation set (77 clips). Context rule dev 0.645 vs test 0.663 (no sign of overfitting).

**Interpreting the errors:**
* The final version misses 31 of 85 test falls. Likely causes: the person is partly out of view after
  the fall, the camera looks down from above (falling does not move the body lower in the image), or the
  fall happens near the end of the clip, before the body can be confirmed as settled.
* 24 non-fall clips still alert, mostly fast large movements on the bed that end lower in the frame.
* False alerts per hour fell only slightly (42.8 → 38.0). The gain is mostly precision and recall.

---

## 8. Failure cases, limitations and honest answers

1. **The original BiLSTM raised no alerts on the evaluation data** (it also read empty windows as falls,
   ~0.96). I retrained it (section 5.2): the retrained model reaches F1 0.676 alone on test and does not
   read empty windows as falls (tested). **It still misses standing falls** (IKAR 0/278): trained only on
   bed clips, and IKAR clips are shorter than its 5-second window. The context rule covers them.
2. Not clinically validated; every alert is a *potential* fall for a person to check.
3. Camera angle matters: a camera pointing straight down weakens the "lower in the image" signal.
4. The bed-zone rule needs a bed rectangle; the datasets have none, so it is unit-tested only.
5. Lowering oneself slowly all the way to the floor can still alert (documented trade-off, tested).
6. Timing thresholds are in samples at 6 per second; the CSV frame rate is unknown.
7. Fictional patient data only; Supabase cloud database needs internet.

---

## 9. Reproducibility (commands the panel may ask you to run)

```bash
cd ml-engine
python3 fall_eval.py baseline     # earlier live logic on dev and test
python3 fall_eval.py ablate       # BiLSTM only, posture only, context only
python3 fall_eval.py report       # final comparison table (section 7)
python3 fall_eval.py v2           # original vs retrained BiLSTM, alone and combined
python3 train_bilstm.py           # retrain (about 1 minute, identical weights each time)
python3 fall_eval.py calibrate    # confidence calibration
python3 -m pytest tests -q        # 168 ML tests
```
Backend tests: `cd backend && python3 -m pytest tests -q` (365). Settings live in `ml-engine/config.py`
(environment variables, e.g. `VITALYN_FALL_THRESH`, `VITALYN_FALL_RULE=legacy`).

The evaluation is deterministic (fixed split by file-name hash). Training uses seed 42 on CPU; running it
twice produced byte-identical weights and history (checked with `shasum`).

---

## 10. Code the panel may ask you to open

| Question | File and line |
|---|---|
| "Show me your training loop" | `ml-engine/train_bilstm.py` `main`: forward pass, weighted BCE, `loss.backward()`, gradient clipping, `opt.step()`, early stopping |
| "Show me your model" | `ml-engine/bilstm_model.py:29` (class), `:52` `forward` (LSTM → mean pool → fc1 → ReLU → fc2 → sigmoid) |
| "How do you run inference?" | `ml-engine/bilstm_model.py:81` `predict` (tensor shape (1, 30, 34), `torch.no_grad()`) |
| "How do you get keypoints?" | `ml-engine/pose_extractor.py:97` `extract_frame_detailed` (YOLO, normalise x/w, y/h) |
| "How does the live sliding window work?" | `ml-engine/streaming_detector.py:85` `push`, coverage guard `:32` |
| "Explain your fall rule" | `ml-engine/fall_context.py:121` `_evaluate` (drop, settled, speed), `:156` `update` |
| "Where is the threshold?" | `ml-engine/config.py` `FALL_THRESHOLD` (0.65 for the retrained model, 0.45 for the original) |
| "How did you split the data?" | `ml-engine/fall_eval.py:58` `split_of` |
| "How are metrics computed?" | `ml-engine/fall_eval.py:237` `evaluate` |
| "What was the baseline?" | `ml-engine/fall_eval.py:167` `baseline_detector` |
| "Where does a live alert come from?" | `ml-engine/live_pipeline.py:395` `_inference_loop` → `:475` `_raise_fall` |
| "Several patients at once?" | `ml-engine/live_pipeline.py:568` `LiveManager` (shared models behind a lock) |
| "How does the phone stream?" | `backend/phone_gateway.py:405` `patient_ws` (JPEG frames over WebSocket) |
| "Who can see video?" | `backend/auth.py:242` `require_roles` |

**Changed-input test the panel may ask for:** change `VITALYN_FALL_THRESH` (e.g. 0.3 or 0.8) and explain
how precision and recall move, or switch the rule with `VITALYN_FALL_RULE=off` / `legacy` (restart the
backend afterwards for the live app).

---

## 11. 8-minute demo script

| Time | Show | Say |
|---|---|---|
| 0:00-0:45 | Title slide | The pitch (section 0) |
| 0:45-1:45 | Pipeline slide (section 4) | Pose CNN → keypoints → BiLSTM + context rule → alert → human review |
| 1:45-3:30 | **Live:** Watch Live, select a patient, phone camera on. Lie on a bed/table (no alert), then sit up (no alert), then lower to the floor quickly and stay (alert) | Point at the skeleton overlay and the status. Explain "potential fall, needs review" |
| 3:30-4:15 | Acknowledge the alert as a nurse | Name is recorded; human in the loop |
| 4:15-6:15 | Terminal: `python3 fall_eval.py report` | Data split, baseline vs final table, confusion matrix |
| 6:15-7:15 | Model + learning-curve slide | BiLSTM layers, BCE loss, Adam, early stopping at epoch 20, why bidirectional |
| 7:15-8:00 | Limitations slide | Original model failed → retrained; BiLSTM misses standing falls; false alerts; not validated |

**If the live demo fails:** go straight to the terminal evaluation (it needs no camera, no internet), and
say what failed.

## 12. Slide outline (6 slides)
1. Problem and objective (falls in wards, recall first, potential events only)
2. Data and split (FallVision 616 clips, IKAR 278 videos, clip-level 70/30 split, no augmentation)
3. Pipeline (section 4 diagram)
4. Models and training (YOLOv8n-pose frozen; BiLSTM table; training settings; learning curves; context rule)
5. Results (table + confusion matrices + IKAR recall)
6. Limitations, next steps, acknowledgements and AI disclosure

---

## 13. Likely viva questions with short answers

1. **Why a BiLSTM and not a CNN or Transformer?** A fall is a short time sequence of 34 numbers. An LSTM is
   small, works with little data and handles order; a Transformer needs far more data. A 1D-CNN would be
   a fair alternative.
2. **What does bidirectional mean, and does it allow real time?** Two LSTMs read the window forwards and
   backwards. It is real time per window: we classify every 15 samples (2.5 s) once 30 are buffered.
3. **Why 30 frames at 6 fps?** 5 seconds covers a fall and the moments after it; 6 fps keeps compute low
   on a laptop.
4. **What is the loss and why?** Binary cross-entropy: binary output with a sigmoid; it punishes confident
   wrong answers heavily.
5. **Explain backpropagation through time.** Unroll the LSTM over 30 steps and apply the chain rule from
   the loss back through every step, summing gradients for the shared weights.
6. **Why do LSTMs not vanish like RNNs?** The additive cell-state update lets gradients pass through with
   the forget gate controlling the decay, instead of repeated multiplication by the same matrix.
7. **What is mean pooling doing?** Averages the 30 outputs into one vector so the decision uses the whole
   window.
8. **Why threshold 0.45?** Slightly below 0.5 to favour recall: missing a fall costs more than a false alarm.
9. **Why two windows in a row?** One noisy window should not raise an alarm.
10. **Why keypoints instead of pixels?** Smaller input, less overfitting, privacy, independence from
    clothes and lighting. Downside: the pose model's errors become my errors.
11. **What is YOLOv8n-pose, and did you train it?** A pretrained CNN that detects people and 17 joints. I
    used it frozen as a feature extractor.
12. **Why precision/recall/F1 and not accuracy?** Classes are imbalanced and the cost of errors differs.
13. **How did you prevent leakage?** Whole clips go to dev or test, never split across; settings chosen on
    dev only.
14. **Did you overfit?** Dev F1 0.645, test 0.663: no sign. The rule has only a few parameters.
15. **What is your baseline?** The earlier live logic (BiLSTM + upright-to-horizontal rule): F1 0.179.
16. **Why did the old rule fail on bed data?** Many falls from bed start already horizontal, and sitting up
    or lying down also changes the box shape. It looked at shape, not where the body ends up.
17. **How does your rule tell bed from floor?** It compares where the body ends with where it was resting,
    in torso lengths, and can use a bed rectangle. Falling off a bed ends much lower; turning over does not.
18. **Why did you retrain the BiLSTM?** My evaluation showed the original checkpoint raised no alerts on
    held-out clips and read empty frames as falls. I retrained it with a clip-level split, class weighting,
    augmentation and early stopping. Alone it now reaches F1 0.676, precision 0.817 on test.
19. **Why does the BiLSTM miss standing falls?** It only saw bed scenes in training, and the IKAR clips are
    shorter than its 5-second window, so the windows are mostly padding. Training on standing falls (and
    shorter windows) would be the next step.
20. **Why combine it with a rule instead of using the BiLSTM alone?** On validation the BiLSTM alone had
    the best F1 and fewest false alarms, but missed every standing fall. Recall comes first in a hospital,
    so the default adds the rule; the BiLSTM-only mode is one setting away.
20b. **How did you choose the threshold 0.65?** By scanning 0.20-0.90 on the validation clips with the live
    decision rule and taking the best F1. Not on test.
20d. **Where do the percentages on screen come from?** The BiLSTM's sigmoid output, averaged over the last
    two windows; normal = 100 − fall. Not calibrated clinical probabilities; nothing is shown when the
    model has no valid window.
20e. **How did you reduce false alerts?** A rule alert is held back when the BiLSTM clearly sees the
    person and gives under 10% fall probability. Chosen on validation; test false alerts/h 55 → 33.
20f. **How did you make it faster?** Measured each step: the tiny BiLSTM was slower on the GPU because of
    data transfer, so it runs on CPU (3.4 → 0.77 ms). The pose CNN stays on the GPU (~11 ms).
20c. **Does it overfit?** Training loss keeps falling but validation loss stops improving after about epoch
    5; validation F1 peaks at epoch 20, so early stopping keeps that model. Validation F1 0.76 vs test 0.68.
21. **What is calibration and why?** Making the confidence match how often alerts are right. Brier score
    0.257 → 0.211 on test.
22. **What happens if no person is visible?** The frame becomes zeros; windows with < 80% person frames
    are not classified (the model reads zeros as falls).
23. **What is the false-alert rate and is it acceptable?** About 38 per hour of non-fall footage on this
    data: too high for real use. That is a known limitation.
24. **How do you handle several patients?** One session per patient, sharing one model in memory behind a
    lock; up to 3 cameras on this laptop.
25. **What if the database is down?** Fall events are saved in a local outbox and replayed later.
26. **What did you build yourself, and what did you use?** See section 14.

---

## 14. Acknowledgements and AI disclosure (put on the last slide)

* **Pretrained model:** YOLOv8n-pose by Ultralytics (COCO keypoints), used frozen.
* **BiLSTM:** retrained by me with `ml-engine/train_bilstm.py` (recorded run included). The original
  checkpoint came from an earlier notebook (kept for comparison only).
* **Datasets:** FallVision (bed subset, keypoint CSVs); IKAR fall dataset (CC BY 4.0, credit the authors
  as in `datasets/doi-10/00_readme.md`).
* **Libraries:** PyTorch, Ultralytics, OpenCV, NumPy, pandas, scikit-learn (calibration), FastAPI,
  SQLModel, Supabase (Postgres and Auth), Next.js, Tailwind, three.js/React Three Fiber.
* **AI assistance:** large parts of the code, the evaluation harness and these documents were written with
  an AI coding assistant (Claude Code) under my direction. I reviewed and tested it. The guidelines require
  this disclosure. Make sure you can explain every file in section 10.

---

## 15. Checklist for tonight and tomorrow morning

- [ ] Read `ml-engine/train_bilstm.py` top to bottom once; open `learning_curves.png` and explain it out loud.
- [ ] Do not quote `docs/research/DATASET_RESEARCH.md`; it does not match the real data.
- [ ] Copy the project, `ml-engine/*.pt` weights (especially `vitalyn_fall_bilstm_v2.pt`) and `datasets/` to a USB drive (weights and data are not in git; `train_bilstm.py` can recreate the v2 weights in about a minute).
- [ ] Run `python3 fall_eval.py report` once and keep the output on screen as a fallback.
- [ ] Laptop charged; phone charged; phone on the same Wi-Fi or a hotspot; regenerate the patient QR on the venue network.
- [ ] Open the app once so Supabase is awake; signed in as admin before your slot.
- [ ] Rehearse the 8-minute script with a timer twice.
- [ ] Practise questions 1-20 out loud.

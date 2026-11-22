# VITALYN: viva and presentation guide

Deep Learning, Semester V, project evaluation on **Monday 23 November 2026**:
**8 minutes demo + 4 minutes viva, solo.**

Every number in this guide comes from code in this repository that you can re-run. Where something is
not known (marked **YOU MUST FILL IN**), do not guess in front of the panel.

---

## 0. The 30-second pitch

> Patients in hospital beds can fall, and nurses cannot watch every bed all the time. VITALYN is a hospital
> management system whose core is a camera-based fall monitor. A pretrained pose network (YOLOv8n-pose)
> turns each video frame into 17 body keypoints. A deep sequence model (a BiLSTM) and a context-aware
> rule then look at how those keypoints move over time and raise a **potential** fall for a nurse to check.
> I measured it on held-out clips: F1 went from 0.18 to 0.66 against the earlier version. It is a research
> prototype and not clinically validated.

---

## 1. Requirement check against the evaluation guidelines

| Guideline requirement | Status | Evidence in the project | What to do before the viva |
|---|---|---|---|
| Problem, input/output, use case, dataset, measurable objective | Met | Section 2 below | Learn section 2 by heart |
| Why deep learning | Met | Pose estimation from raw pixels needs a CNN; fall is a temporal pattern (sequence model) | Section 2 |
| Dataset origin, size, labels, quality | Partly | FallVision CSVs (616 clips) and IKAR (278 videos) are real and counted in section 3 | **`docs/research/DATASET_RESEARCH.md` contains descriptions that do not match the real files (e.g. "~100 hours", "hospital recordings", "stereo depth"). Do not quote that file.** Use section 3 here |
| Preprocessing, split, leakage prevention | Met for evaluation | Normalisation, 6 fps sampling, deterministic clip-level split (section 3) | Explain clip-level split = no frames of one video in both sets |
| Augmentation | Not done | None used | Say so honestly |
| Model layers, activations, loss | Met | BiLSTM layers read from the checkpoint (section 5) | Section 5 |
| Optimizer, learning rate, batch size, epochs | **GAP** | Not recorded anywhere in the repo. The BiLSTM was trained in a separate notebook | **YOU MUST FILL IN from your training notebook.** If you cannot find it, say the training record was lost and offer the evaluation evidence instead |
| Mathematical understanding | Prepare | Section 6 | Practise explaining LSTM gates, BCE loss, backprop |
| Implementation ownership, training/inference pipeline | Inference: met. Training: **GAP** | Inference code, evaluation harness and context detector are in the repo. Training code is not | Bring the training notebook if you have it |
| Metrics: precision, recall, F1, confusion matrix | Met | Section 7 (held-out test, confusion matrices) | Explain why recall matters and why accuracy would mislead |
| Baseline / alternative | Met | Old live logic vs new; ablations (BiLSTM only, rule only, combined) | Section 7 |
| Overfitting, validation, failure cases, generalization | Met (honestly) | Dev/test split, IKAR standing falls, failure list in section 8 | Section 8 |
| Reproducibility: code, dependencies, weights, data, results | Mostly | `ml-engine/fall_eval.py`, `requirements.txt`, weights in `ml-engine/` | Weights and datasets are git-ignored: **keep a local copy and a USB copy**. No random seeds needed for evaluation (deterministic) |
| Disclose pretrained models and AI tools | Do it | Section 14 | Put it on your last slide |
| Demo: real inference, not UI tour | Plan | Section 11 demo script | Rehearse with a timer |
| No dependence on internet for the only copy | **Risk** | App uses Supabase (cloud database) | Keep the evaluation script and a SQLite fallback ready (section 12) |

**The single biggest risk for a Deep Learning panel:** the measured improvement comes from the
context-aware rule, while the BiLSTM raised **no alerts** on the evaluation clips. Be ready to explain
this honestly (section 8, Q&A 18-20). The guidelines warn that "wrapping a pretrained model" is not
enough. Your own work is the temporal pipeline, the evaluation methodology, the detector design and the
analysis. Present it that way.

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
| BiLSTM training data | **YOU MUST FILL IN** (from your notebook: which dataset, how many sequences, which split) | Training |

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
* No augmentation was used.

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
       2 windows in a row ≥ 0.45 → signal     descent below resting level + fast + settles low
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

### 5.2 BiLSTM fall classifier (`ml-engine/bilstm_model.py`)
Read directly from the saved checkpoint `ml-engine/vitalyn_fall_bilstm.pt` (**154,689 parameters**):

| Layer | Shape | Notes |
|---|---|---|
| Input | (batch, 30, 34) | 30 time steps × 17 keypoints × (x, y) |
| LSTM layer 1, bidirectional | 34 → 64 per direction | weights (256, 34): 4 gates × 64 units |
| LSTM layer 2, bidirectional | 128 → 64 per direction | input 128 = 64 forward + 64 backward; dropout 0.3 between layers |
| Mean pooling over time | (batch, 30, 128) → (batch, 128) | average of all 30 outputs |
| Dense fc1 + ReLU | 128 → 32 | |
| Dense fc2 + sigmoid | 32 → 1 | probability of "fall" |

* **Decision:** `prob ≥ 0.45` (`ml-engine/config.py:38`; slightly below 0.5 to favour recall), and two
  consecutive windows (window every 15 samples) before a signal.
* **Loss:** the sigmoid output implies **binary cross-entropy**. **YOU MUST FILL IN** whether the notebook
  used `BCELoss` or `BCEWithLogitsLoss`.
* **Optimizer, learning rate, batch size, epochs, early stopping:** **YOU MUST FILL IN** from the notebook.

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

All from `cd ml-engine && python3 fall_eval.py report` (test = 209 held-out clips: 85 falls, 124 non-falls).

| Method | Precision | Recall | F1 | Non-fall clips alerted | False alerts / hour |
|---|---|---|---|---|---|
| Baseline: earlier live logic (BiLSTM + posture rule) | 0.289 | 0.129 | 0.179 | 21.8% | 42.8 |
| **Final: BiLSTM + context-aware rule** | **0.692** | **0.635** | **0.663** | **19.4%** | **38.0** |
| Alternative: context rule + old posture rule | 0.567 | 0.694 | 0.624 | 36.3% | 71.3 |
| Ablation: BiLSTM alone | 0 alerts | 0.000 | 0.000 | 0% | 0 |

**Confusion matrices (test):**

| Baseline | Predicted fall | Predicted no fall |
|---|---|---|
| Real fall | TP 11 | FN 74 |
| No fall | FP 27 | TN 97 |

| Final | Predicted fall | Predicted no fall |
|---|---|---|
| Real fall | TP 54 | FN 31 |
| No fall | FP 24 | TN 100 |

**Standing falls (IKAR, falls only, recall):** baseline 192/278 (69.1%), final **211/278 (75.9%)**.
(IKAR was used to choose between two versions, so this is not a held-out estimate.)

**Dev vs test (overfitting check):** final F1 0.645 on dev vs 0.663 on test. Dev and test are close, so no
sign that the tuning overfitted the dev clips.

**Interpreting the errors:**
* The final version misses 31 of 85 test falls. Likely causes: the person is partly out of view after
  the fall, the camera looks down from above (falling does not move the body lower in the image), or the
  fall happens near the end of the clip, before the body can be confirmed as settled.
* 24 non-fall clips still alert, mostly fast large movements on the bed that end lower in the frame.
* False alerts per hour fell only slightly (42.8 → 38.0). The gain is mostly precision and recall.

---

## 8. Failure cases, limitations and honest answers

1. **The BiLSTM raises no alerts on the evaluation data.** Causes I can show: the earlier analysis found
   it outputs ~0.96 for all-zero (no-person) windows, so a guard was added (≥ 80% person frames); on real
   windows its probabilities stay below the 0.45 threshold. Possible reasons: a mismatch between training
   and evaluation data (frame rate, camera views, normalisation), or a training set too small or
   different. What would fix it: retrain with a recorded, clip-level train/val/test split on the same
   preprocessing, and report its learning curves.
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
python3 fall_eval.py calibrate    # confidence calibration
python3 -m pytest tests -q        # 168 ML tests
```
Backend tests: `cd backend && python3 -m pytest tests -q` (365). Settings live in `ml-engine/config.py`
(environment variables, e.g. `VITALYN_FALL_THRESH`, `VITALYN_FALL_RULE=legacy`).

The evaluation is deterministic (fixed split by file-name hash, no random sampling), so no seed is needed.
Training seeds: **YOU MUST FILL IN** if the notebook set any.

---

## 10. Code the panel may ask you to open

| Question | File and line |
|---|---|
| "Show me your model" | `ml-engine/bilstm_model.py:29` (class), `:52` `forward` (LSTM → mean pool → fc1 → ReLU → fc2 → sigmoid) |
| "How do you run inference?" | `ml-engine/bilstm_model.py:81` `predict` (tensor shape (1, 30, 34), `torch.no_grad()`) |
| "How do you get keypoints?" | `ml-engine/pose_extractor.py:97` `extract_frame_detailed` (YOLO, normalise x/w, y/h) |
| "How does the live sliding window work?" | `ml-engine/streaming_detector.py:85` `push`, coverage guard `:32` |
| "Explain your fall rule" | `ml-engine/fall_context.py:121` `_evaluate` (drop, settled, speed), `:156` `update` |
| "Where is the threshold?" | `ml-engine/config.py:38` `FALL_THRESHOLD = 0.45` |
| "How did you split the data?" | `ml-engine/fall_eval.py:58` `split_of` |
| "How are metrics computed?" | `ml-engine/fall_eval.py:237` `evaluate` |
| "What was the baseline?" | `ml-engine/fall_eval.py:167` `baseline_detector` |
| "Where does a live alert come from?" | `ml-engine/live_pipeline.py:395` `_inference_loop` → `:475` `_raise_fall` |
| "Several patients at once?" | `ml-engine/live_pipeline.py:568` `LiveManager` (shared models behind a lock) |
| "How does the phone stream?" | `backend/phone_gateway.py:405` `patient_ws` (JPEG frames over WebSocket) |
| "Who can see video?" | `backend/auth.py:242` `require_roles` |

**Changed-input test the panel may ask for:** change `VITALYN_FALL_THRESH` (e.g. 0.3) or run
`VITALYN_FALL_RULE=legacy python3 fall_eval.py report` and explain how precision and recall move.

---

## 11. 8-minute demo script

| Time | Show | Say |
|---|---|---|
| 0:00-0:45 | Title slide | The pitch (section 0) |
| 0:45-1:45 | Pipeline slide (section 4) | Pose CNN → keypoints → BiLSTM + context rule → alert → human review |
| 1:45-3:30 | **Live:** Watch Live, select a patient, phone camera on. Lie on a bed/table (no alert), then sit up (no alert), then lower to the floor quickly and stay (alert) | Point at the skeleton overlay and the status. Explain "potential fall, needs review" |
| 3:30-4:15 | Acknowledge the alert as a nurse | Name is recorded; human in the loop |
| 4:15-6:15 | Terminal: `python3 fall_eval.py report` | Data split, baseline vs final table, confusion matrix |
| 6:15-7:15 | Model slide | BiLSTM layers, loss, why bidirectional, why keypoints |
| 7:15-8:00 | Limitations slide | BiLSTM gives no alerts on this data; not validated; camera angle; next steps |

**If the live demo fails:** go straight to the terminal evaluation (it needs no camera, no internet), and
say what failed.

## 12. Slide outline (6 slides)
1. Problem and objective (falls in wards, recall first, potential events only)
2. Data and split (FallVision 616 clips, IKAR 278 videos, clip-level 70/30 split, no augmentation)
3. Pipeline (section 4 diagram)
4. Models (YOLOv8n-pose frozen; BiLSTM table; context rule 5 steps)
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
18. **Your deep model raises no alerts. Is this a deep learning project?** Yes. The perception is deep
    learning (pose CNN), the temporal model is a BiLSTM, and the project contains a rigorous evaluation
    that *found* the BiLSTM does not generalise to this data. I reported that instead of hiding it, and
    added a measured, explainable layer while keeping the BiLSTM in the pipeline. Next step: retrain it
    with a recorded split.
19. **Why might the BiLSTM fail here?** Distribution shift (different cameras, frame rate, normalisation
    between training data and these clips), possibly small or different training data, plus a threshold
    tuned elsewhere.
20. **How would you improve it?** Retrain on FallVision with a clip-level split, class weights for
    imbalance, augmentation (mirroring, small rotations, time stretching), early stopping on validation
    F1, then compare against the rule with the same harness.
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
* **BiLSTM:** trained in a separate notebook. **YOU MUST FILL IN:** who trained it, on what data, and
  where the notebook is.
* **Datasets:** FallVision (bed subset, keypoint CSVs); IKAR fall dataset (CC BY 4.0, credit the authors
  as in `datasets/doi-10/00_readme.md`).
* **Libraries:** PyTorch, Ultralytics, OpenCV, NumPy, pandas, scikit-learn (calibration), FastAPI,
  SQLModel, Supabase (Postgres and Auth), Next.js, Tailwind, three.js/React Three Fiber.
* **AI assistance:** large parts of the code, the evaluation harness and these documents were written with
  an AI coding assistant (Claude Code) under my direction. I reviewed and tested it. The guidelines require
  this disclosure. Make sure you can explain every file in section 10.

---

## 15. Checklist for tonight and tomorrow morning

- [ ] Find the BiLSTM training notebook; fill in every **YOU MUST FILL IN** above.
- [ ] Do not quote `docs/research/DATASET_RESEARCH.md`; it does not match the real data.
- [ ] Copy the project, `ml-engine/*.pt` weights and `datasets/` to a USB drive (weights and data are not in git).
- [ ] Run `python3 fall_eval.py report` once and keep the output on screen as a fallback.
- [ ] Laptop charged; phone charged; phone on the same Wi-Fi or a hotspot; regenerate the patient QR on the venue network.
- [ ] Open the app once so Supabase is awake; signed in as admin before your slot.
- [ ] Rehearse the 8-minute script with a timer twice.
- [ ] Practise questions 1-20 out loud.

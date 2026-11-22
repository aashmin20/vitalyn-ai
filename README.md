VITALYN

Intelligence that cares.

Hospital Management System with AI Fall Monitoring

VITALYN is a hospital management prototype (staff accounts with roles, admissions, transfers, discharge, outpatient appointments) built around an AI fall-monitoring core. The monitoring part is a deep-learning prototype designed to estimate bed occupancy and identify potential patient-fall events using computer vision and temporal analysis.

Problem Statement

Hospitals need reliable ways to monitor bed utilisation and identify potential patient-safety events. Manual monitoring can be resource-intensive, while isolated image-based detection may fail to capture movement and changes over time.

VITALYN explores how deep learning and computer vision can support these monitoring tasks.

Core Objectives

1. Detect people and beds in video frames.
2. Estimate bed occupancy using spatial relationships.
3. Analyse patient posture and movement over time.
4. Identify potential fall events.
5. Generate and manage safety alerts.
6. Evaluate model performance using appropriate metrics.

Core Features

* Staff sign-in with roles (admin, doctor, nurse, receptionist), approval and audit log
* Admission, transfer and discharge with a ward board and bed lifecycle
* Outpatient appointments, doctor schedules and an OPD queue
* Live per-patient camera monitoring with potential-fall alerts (needs human review)
* Video-based inference
* Person and bed detection
* Bed occupancy estimation
* Temporal fall-event analysis
* Safety alert management
* Model evaluation dashboard

Technology Stack

Layer	Technology
Frontend	Next.js, TypeScript
UI	Tailwind CSS, shadcn/ui, Motion
Backend	Python, FastAPI
Computer Vision	PyTorch, OpenCV
Detection	Selected pretrained or fine-tuned model
Database	Supabase Postgres (SQLite for local development and tests)
Version Control	Git, GitHub

Architecture

The application is organised into three independent components:

* Frontend: User interface and monitoring dashboard.
* Backend: API, application logic and event management.
* ML Engine: Video processing, detection, occupancy estimation and fall-event analysis.

Project Structure

Vitalyn-AI/
├── frontend/
├── backend/
├── ml-engine/
├── datasets/
├── docs/
├── scripts/
├── AGENTS.md
├── README.md
└── .gitignore

Evaluation

Model performance will be assessed using task-appropriate metrics, including:

* Precision
* Recall
* F1-score
* Confusion matrix
* Inference latency
* Occupancy MAE, where applicable

Live camera demo

1. Grant camera access once, from the same app you start the backend from (macOS ties permission to that app):
   python3 scripts/check_camera.py
2. Start the backend from that app (bind to localhost unless you need LAN access):
   cd backend && python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
3. Start the frontend (cd frontend && npm run dev), open Monitoring > Live Camera, choose a room, source 0, Start.
4. Allow sound on the first click so the alarm beep can play.

Camera sources (pick them in the Live Camera page):

* Mac webcam: the first camera in the list.
* iPhone as a camera: macOS Continuity Camera lists it as another camera (same Apple ID, Wi-Fi and Bluetooth on, phone nearby and steady).
* Any phone or IP camera: run a streaming app on the phone (e.g. "IP Webcam" on Android) and paste its http:// or rtsp:// address. Start the backend with VITALYN_LIVE_ALLOW_URLS=1; only local-network addresses are accepted.
* Phone browser link (no app): start the backend with VITALYN_PHONE_GATEWAY=1, choose Phone camera > Phone link > Create phone link, open the link on the phone (accept the one-time self-signed certificate warning), tap Start streaming. Only the small phone gateway (HTTPS, port 8443) listens on the network; the main API stays on 127.0.0.1.
* A video inside backend/uploads or datasets/ for rehearsal without a camera.

Watch Live (one page for everything)

Monitoring > Watch Live: select a patient. If a camera is registered to them, live monitoring opens straight away with their details and recent potential falls. First time only: choose "Use this Mac's webcam" or "Pair a phone" (scan the QR once; the phone then stays registered). For a phone, leave its page open with the screen on; it connects in standby and starts when you open the patient. If the phone is offline, Watch Live says so and opens the camera as soon as the phone is back. Several patients can be monitored at once (up to 3 by default; set VITALYN_MAX_SESSIONS to change it). Each needs its own camera: the Mac webcam serves one patient, phones as many as you pair. A fall alarm appears on Watch Live whichever patient you are viewing.

Patients and camera QR codes

Patients > Admit patient: enter name, age, condition, room and doctor (demo data only), then print the patient's QR card. Scanning the QR in the phone's browser (Safari, accept the one-time certificate warning) starts monitoring for that patient; alerts then show the patient, room and doctor. Start the backend with VITALYN_PHONE_GATEWAY=1.

Using Supabase instead of the local database

1. Create a Supabase project, then copy the "Session pooler" connection string (Connect button).
2. Copy backend/.env.example to backend/.env (git-ignored) and set DATABASE_URL to it.
3. pip install -r backend/requirements.txt (adds psycopg), restart the backend. Tables are created automatically with Row Level Security on.
4. Use demo data only: patient fields leave this machine for a cloud service.

Live detection limitations (measured, informal)

* The BiLSTM is not validated: it reacted to zero-filled frames rather than motion in our probes, so it is only consulted while a person is in view (VITALYN_MIN_PERSON_COVERAGE, default 0.8) and its output is shown as a raw score.
* The posture-transition rule flags upright-to-horizontal changes with a collapse in body height. On 160 IKAR standing-fall clips (thresholds tuned on the same clips) it fired on about two thirds; on the FallVision clips it did not detect falls (about 1%) and flagged about a quarter of non-fall clips. It assumes a side/front view, can miss falls onto a mat and can fire on a fast deliberate lie-down.
* All detections are potential falls needing human review. No clinical validation.

Scope and Limitations

VITALYN is an academic prototype, not a clinically validated hospital monitoring system. Fall outputs represent potential events requiring human review. The system does not diagnose medical conditions or replace healthcare professionals.

Future Scope

* LSTM-based occupancy forecasting
* RAG-based hospital knowledge assistant
* Voice interaction
* Advanced segmentation
* C++ inference integration
* Model monitoring and versioning

Project Status

Development in progress.

HMS phase 1: first-time setup

1. `python3 scripts/set_supabase_auth.py` (Supabase project URL and the public anon key; never the secret key).
2. Start the backend and frontend, open the app and create your account on the Sign up page.
3. `python3 scripts/make_admin.py you@example.com` promotes it to administrator; sign in again.
4. Approve other staff and assign roles under Administration, Staff.

Demo and academic prototype only. Use fictional patients. Not clinically validated and not a compliance claim.

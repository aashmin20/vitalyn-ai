# VITALYN — Architecture Decisions

This document captures the key architectural decisions made for VITALYN to provide consistency and clear guidelines for development.

⸻

1. Monolithic Architecture Choice

Decision: Use a modular monolithic architecture for the initial implementation.

Rationale:

* Faster initial development with separate concerns but single deployment unit
* Reduces operational complexity compared to microservices for the prototype
* Easier to test and debug interactions between components
* Suitable for the academic prototype phase with limited resources

Boundaries:

* Frontend and backend remain separate layers but can be modified together
* ML engine stays tightly coupled with backend for processing efficiency
* Database changes propagate through the entire application

2. Video Processing Strategy

Decision: Implement upload-first approach, with live camera processing planned for a future enhancement.

Rationale:

* Simpler initial implementation focused on file-based video analysis
* Better control over video quality and processing time
* Easier to test with pre-recorded datasets
* More predictable resource usage

3. Communication Architecture

Decision: All frontend communication must go through the backend APIs.

Rationale:

* Centralizes validation and security
* Allows for future real-time features (WebSocket/SSE) implementation
* Simplifies model switching without frontend changes
* Provides consistent error handling and logging

4. ML Integration Approach

Decision: Backend orchestrates ML inference, with ML engine as a processing component.

Rationale:

* Keeps ML concerns separate from business logic
* Allows for easier model switching and A/B testing
* Provides better error isolation
* Enables model versioning

5. Processing Model

Decision: Use job-based processing for long video analysis.

Rationale:

* Allows for resume on failure
* Provides progress tracking
* Enables processing of large videos
* Supports user feedback during processing

6. Database Choice

Decision: Use SQLite for the initial prototype.

Rationale:

* Zero-configuration setup
* Single file database for easy deployment
* Suitable for the projected scale
* Native Python support

7. Fall Alert Processing

Decision: Use temporal event aggregation for fall detection.

Rationale:

* Reduces false positives from frame-level noise
* Provides coherent incident timelines
* Better user experience with fewer alerts
* More accurate detection of actual fall events

8. Occupancy Tracking

Decision: Use historical observations for occupancy analytics.

Rationale:

* Provides trend analysis over time
* Allows detection of occupancy patterns
* Supports forecasting capabilities
* Historical record for auditing

9. Alert Resolution

Decision: Require human verification for fall event resolution.

Rationale:

* Prevents automatic false negatives
* Ensures patient safety verification
* Maintains audit trail
* Aligns with clinical safety requirements

10. Git Workflow

Decision: Feature branches → dev → main with no direct commits to main.

Rationale:

* Ensures code review and testing
* Provides integration testing environment
* Maintains production stability
* Supports multiple agent development

11. Dataset Management

Decision: Store datasets locally, excluded from Git.

Rationale:

* Large files bloat repository
* Prevents accidental commits of sensitive data
* Allows dataset management outside version control
* Supports dataset size and access control

12. Live Camera Detection

Decision: Run live detection in-process as two daemon threads (capture + inference) behind FastAPI, one camera session at a time. Stream annotated video to the browser as MJPEG and push fall events as Server-Sent Events.

Rationale:

* Reuses the existing YOLOv8n-pose → BiLSTM + aspect-ratio pipeline and database writers
* MJPEG and SSE need no extra dependencies and are light on an 8 GB machine (WebRTC and WebSocket rejected as heavier for no benefit at this scale)
* Capture and inference are decoupled so slow inference never freezes the video
* Raw video is not stored; only occupancy rows, fall events and alerts are persisted
* The `source` may be a webcam index, a file path or an RTSP/HTTP URL, so the same path is testable with recorded video

Limitations:

* The fall model needs 30 sampled frames (~5 s at 6 FPS) before its first decision
* Live performance on a webcam is unmeasured; every detection is a potential fall requiring human review
* macOS grants camera permission to the launching app; see scripts/check_camera.py


13. Person-Coverage Guard for the BiLSTM

Decision: The BiLSTM is only consulted when at least `MIN_PERSON_COVERAGE` (default 0.8, env `VITALYN_MIN_PERSON_COVERAGE`) of the frames in a 30-frame window contain a detected person. Windows below that are treated as "no fall" and the model is not called. Applies to both the live and the batch pipelines.

Rationale (measured, see model investigation):

* The trained model scores an all-zero (no person) window at about 0.96 and its output rises with the number of zero-filled frames, identically for fall and non-fall data, so zero padding / missed detections were being reported as falls
* An empty scene produced a 0.96-confidence "potential fall" in the live pipeline before the guard

Limitations:

* This removes a false-alarm source; it does not make the model a validated fall detector. On real, unpadded windows the model showed no measurable skill in our probe. Retraining with video-level splits and held-out metrics is required before any performance claim
* Clips shorter than ~5 s are zero-padded, so their BiLSTM windows are skipped (a warning is attached to the job)


14. Posture-Transition Heuristic and Source Allow-List

Decision: Replace the static aspect-ratio rule with a transition rule (upright -> horizontal within ~2 s with a >=35% collapse of body height) computed from pixel keypoints, shared by live and batch. Restrict live sources to camera indices, files under backend/uploads or datasets/ (plus VITALYN_LIVE_ALLOWED_DIRS) and, only when VITALYN_LIVE_ALLOW_URLS=1, rtsp/http(s) URLs.

Rationale:

* A static horizontal posture is normal for a patient lying in bed, so the old rule would alarm continuously
* The batch rule computed its aspect ratio from interleaved keypoints as if they were stored x-then-y, giving meaningless values; the pixel-based version also removes distortion from the video's own width/height
* The API has no authentication, so unrestricted file paths and URLs would let any client make the server read local files or probe the network

Measured limitations (informal, thresholds tuned on the evaluation clips, no held-out set): about 64% recall on 160 IKAR standing-fall clips; about 1% on FallVision falls; about 24% false positives on FallVision non-fall clips. Not a validated detector.


15. Camera Source Selection

Decision: The Live Camera page offers OS-reported cameras (built-in webcam, iPhone via Continuity Camera), a phone/IP camera URL, or a video file. URL sources are opt-in (VITALYN_LIVE_ALLOW_URLS=1), limited to rtsp/http(s) hosts that resolve to private, loopback or link-local addresses, and opened with a 5 s timeout.

Rationale:

* Continuity Camera needs no extra software and appears as a normal camera index
* Phone streaming apps cover Android and any IP camera without building a browser-to-server video uplink (which would need HTTPS on the phone)
* The API is unauthenticated, so URLs are restricted to the local network to avoid public-internet probing

Limitations: macOS lists the built-in camera first but OpenCV lists Continuity Camera phones first (observed on a MacBook Air with an iPhone: index 0 = iPhone, index 1 = FaceTime camera), so phones are ordered first by default. This is a heuristic validated on one machine; the page has a 'check which is which' step (in-memory snapshots, nothing stored) and remembers the user's choice in the browser. URL streams depend on Wi-Fi quality and the phone app.


16. Phone Browser Camera via Gateway

Decision: A phone can stream its camera by opening a link generated by VITALYN (browser getUserMedia -> JPEG frames over WebSocket -> in-memory PhoneSource -> the normal live pipeline). It is served by a separate, opt-in HTTPS listener (VITALYN_PHONE_GATEWAY=1) with a self-signed certificate for the Mac's LAN address; the main API stays on 127.0.0.1.

Rationale:

* Phone browsers only allow camera access on secure pages, so HTTPS is required; a self-signed certificate keeps video on the local network (tunnelling services would route patient video through a third party)
* The main API is unauthenticated, so only the minimal gateway (page + WebSocket, random 128-bit link token, one phone per link, expiring) is exposed to the LAN
* No app and no phone IP address to type; works for iPhone and Android

Limitations: the user must accept a one-time certificate warning on the phone; JPEG-over-WebSocket gives about 8-10 FPS and some latency (adequate for the 6 FPS analysis rate); the phone page must stay open with the screen on; certificate and key live in backend/certs (git-ignored). Not validated on real phones yet.


17. Supabase (Postgres) behind the FastAPI backend

Decision: The database can be Supabase Postgres via `DATABASE_URL`; FastAPI (and the ML threads) remain the only database clients. The browser never talks to Supabase directly. Local SQLite stays the default for development and tests (tests force a throwaway SQLite file even if `backend/.env` points at Supabase).

Rationale:

* One API contract and one place for validation; no database keys in the frontend
* Row Level Security is enabled with no policies, so the public Supabase API key exposes nothing
* A cloud database is a single point of failure for a safety system, so fall events fall back to a local outbox and are replayed when the database returns

Limitations: patient fields sent to a cloud service are acceptable for demo data only; real patient data needs written authorisation, a suitable plan/region and a compliance review. Supabase Auth, Realtime and Storage are not used yet. Postgres compatibility is unit-tested (DDL, types) but needs a live Supabase smoke test.

18. Per-patient camera QR

Decision: Each admitted patient gets a QR containing a random 128-bit secret; only its SHA-256 is stored. Scanning it (phone gateway, HTTPS) starts monitoring for that patient and room. One patient is monitored at a time. The QR stays valid until it is regenerated or the patient is discharged. Logs, URLs and the printed card use the patient code, never the name.

Rationale: a leaked QR could inject fake video for that patient (hiding or inventing a fall), so tokens are revocable, unrecoverable from the database, single-phone-per-link, and die on discharge or regeneration.


19. One Watch Live page and a camera registered per patient

Decision: Live Camera is merged into Watch Live. Each patient has a registered camera (a phone that connected with their QR, or the Mac webcam). Selecting a patient calls one endpoint, `POST /patients/{id}/monitor`, which opens that camera. A registered phone stays connected in standby with its camera off and starts when told; it never needs a new QR scan.

Rationale: a browser cannot switch a phone camera on remotely, so a standby page (kept open, screen awake) is the closest to "select the patient and it opens". The Mac webcam needs no standby. Monitoring another patient is never started over a live session automatically, to avoid cutting off someone's monitoring by browsing.

Limitations: the phone page must stay open and awake (iOS suspends background pages); Safari's camera permission should be set to Allow for the site or the phone shows a Tap to resume button; one patient is monitored at a time.


20. Concurrent monitoring of several patients

Decision: `LiveManager` holds one session per patient (up to `VITALYN_MAX_SESSIONS`, default 3). All sessions share one pose model and one fall classifier behind a lock; each session keeps its own capture and inference threads, detector state, stream and database job. One Server-Sent Events feed carries every patient's events. A webcam serves one patient; phones scale with the number of sessions.

Rationale: models are the memory cost on an 8 GB Mac, so they are shared; the lock keeps non-thread-safe models safe and, at 6 analysed frames per second per patient, costs little (two simulated phones used about 18% CPU). Alarms must not depend on which patient is on screen, hence the global feed.

Limits: inference is serialised, so the analysis rate per patient falls as sessions are added; the limit protects the machine. Not validated beyond two simultaneous sessions.


21. Staff sign-in through the backend (Supabase Auth) with role-based access

Decision: Staff sign in through FastAPI, which proxies Supabase Auth using only the public anon key (no service-role key anywhere). Tokens are kept in httpOnly SameSite=Lax cookies; unsafe requests need an `X-Requested-With` header. The backend verifies each JWT (JWKS, or a shared secret, or Supabase's user endpoint), loads the staff row and enforces a role matrix on every route. New accounts are `pending` until an administrator approves them and assigns a role. The first administrator is created with `scripts/make_admin.py`. Every write, sign-in and patient-record open is written to an audit log. `VITALYN_AUTH=off` gives an open demo for local use only.

Rationale: the browser, image streams and Server-Sent Events send cookies automatically and no new npm packages are needed; the server is the only place permissions are decided (the sidebar merely hides what a role cannot use).

Limitations: in-memory login rate limit (resets on restart); demo-grade, not a compliance claim; real patient use would need authorisation and a compliance review.

22. Patient stay model: one patient row plus an ADT event log

Decision: `patient` stays the person-and-current-stay record (`patient_code` is the stable record number); history lives in `adt_event`. A discharged patient can be re-admitted. Bed occupancy is derived from admitted patients; only cleaning and maintenance are stored on the bed.

Rationale: smaller change than splitting person and stay, so QR, camera and fall events keep working unchanged.

Limitations: no separate encounter ids; a re-admitted patient's earlier stays appear only in the timeline. A transfer ends the live camera session and staff reopen it (it is not restarted automatically).

23. Outpatient appointments in hospital wall-clock time

Decision: schedules and appointments use naive local date-times because clinic hours are local. Slots are generated from weekly blocks; a booking must match a slot, may not be in the past or overlap another active appointment of the doctor or patient. Status changes follow a fixed workflow with role and ownership checks.

Limitations: the server clock defines "now" and "past"; no recurring bookings, waiting-time estimates or reminders.

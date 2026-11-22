# VITALYN — API Specification

The frontend will communicate with FastAPI through REST APIs.

Base path:

/api/v1

5.1 Room APIs

Method    Endpoint              Purpose
GET        /rooms                List rooms
POST       /rooms                Create room
GET        /rooms/{room_id}      Room details
GET        /rooms/{room_id}/beds List beds

5.2 Video APIs

Method    Endpoint              Purpose
POST       /videos/upload         Upload video
GET        /jobs                 List inference jobs
GET        /jobs/{job_id}         Get job status
GET        /jobs/{job_id}/results Retrieve results

Upload response example

{
  "job_id": "JOB-001",
  "status": "queued",
  "message": "Video uploaded successfully"
}

Job status response

{
  "job_id": "JOB-001",
  "status": "processing",
  "progress": 45
}

The frontend can initially poll the job-status endpoint. Real-time updates through SSE or WebSockets can be added later.

5.3 Occupancy APIs

Method    Endpoint              Purpose
GET        /occupancy/current     Current occupancy
GET        /occupancy/history    Historical occupancy
GET        /beds/{bed_id}/occupancy Bed-specific occupancy

5.4 Fall Event APIs

Method    Endpoint              Purpose
GET        /events/falls          List fall events
GET        /events/falls/{event_id}Event details
PATCH      /events/falls/{event_id}/resolve    Resolve event

5.5 Alert APIs

Method    Endpoint              Purpose
GET        /alerts               List alerts
GET        /alerts/{alert_id}    Alert details
PATCH      /alerts/{alert_id}/acknowledge   Acknowledge alert
PATCH      /alerts/{alert_id}/resolve    Resolve alert

5.6 Dashboard API

Method    Endpoint              Purpose
GET        /dashboard/overview   Dashboard statistics
GET        /dashboard/occupancy-trends Occupancy trends
GET        /dashboard/event-summary    Fall-event statistics

## Live Camera (`/api/v1/live`)

Single session at a time. Every fall event produced here is a *potential* fall requiring human review.

| Method | Path | Description |
|---|---|---|
| GET | `/live/sources` | `{cameras:[{index,label}], urls_enabled}` (phones listed first, matching OpenCV's index order on macOS). Camera names come from the OS (macOS `system_profiler`), no camera access needed. |
| GET | `/live/snapshot?index=N` | One JPEG from camera N (not stored) to identify cameras. `409` while a live session is running, `422` if the camera can't be opened. |
| POST | `/live/phone-link` | Creates a one-session link a phone opens to stream its camera: `{token, url, expires_in}`. `422` unless the backend runs with `VITALYN_PHONE_GATEWAY=1`. Use the result as `source: "phone:<token>"` in `/live/start`. |
| GET | `/live/phone-link/{token}` | `{exists, connected, frames, last_frame_age_s, expires_in}`. |
| DELETE | `/live/phone-link/{token}` | Revokes the link. |
| POST | `/live/start` | Body `{room_id, source}` (`source` default `"0"`: webcam index, file path or RTSP/HTTP URL). Returns status. `400` bad room id, `404` room not found, `409` session already running, `422` source not allowed or cannot be opened (sources: camera index, video under backend/uploads or datasets/, or rtsp/http(s) only with VITALYN_LIVE_ALLOW_URLS=1 and only for local-network hosts), `503` ML dependencies unavailable. |
| POST | `/live/stop` | Stops the running session; returns `{stopped, ...status}`. |
| GET | `/live/status` | `state` (`idle`/`starting`/`live`/`stopped`/`error`), `capture_fps`, `inference_fps`, `person_detected`, `window_fill`/`window_required`, `last_probability` (raw BiLSTM output, `null` while guarded), `model_guarded` (true when the window lacked enough person frames and the model was not consulted), `events_count`, `last_event`, `error`. |
| GET | `/live/stream` | `multipart/x-mixed-replace` MJPEG with skeleton overlay. `409` if no session. |
| GET | `/live/events` | `text/event-stream`. Messages: `{"type":"status",...}`, `{"type":"fall_detected","id","confidence","source":"bilstm"|"heuristic","detected_at"}`; `: heartbeat` comments. Stream ends when the session stops. |

Persistence: a session creates an `InferenceJob` with `status="live"` and `video_path="camera:<source>"`; occupancy rows are written every 5 s (confidence = share of sampled frames agreeing with the status); each detection creates a `FallEvent` + `Alert` with real wall-clock times. Jobs left `live` after a backend restart are marked `failed`.

`/health` now also reports `components.camera` (`idle`/`live`/`error`...).


### Phone gateway (separate HTTPS listener, opt-in)

Enabled with `VITALYN_PHONE_GATEWAY=1` (port `VITALYN_PHONE_PORT`, default 8443; host override `VITALYN_PHONE_HOST`). Serves only `GET /p/{token}` (the phone page) and `WS /p/{token}/ws` (binary JPEG frames). Unknown/expired tokens get 404 / close code 4404; a second phone on the same link gets 4409. The link dies when the live session stops; unused links expire after 10 minutes.


## Patients and doctors (`/api/v1`)

| Method | Path | Description |
|---|---|---|
| GET / POST | `/doctors` | List / create (`name` 1-80, `department?`). |
| GET | `/patients?status=admitted\|discharged\|all` | List (default admitted). |
| POST | `/patients` | Admit: `name` (1-80), `age` (0-130), `condition` (1-200), `doctor_id`, `room_id`, `bed_id?` (must be in the room). Returns `{patient, camera_link, camera_link_note}`; `camera_link` (`{token,url}`) is shown once and is `null` unless the phone gateway is on. |
| GET / PATCH | `/patients/{id}` | Read / edit (not after discharge). |
| POST | `/patients/{id}/camera-link` | Regenerate the QR secret: the old QR stops working and that patient's live session ends. |
| POST | `/patients/{id}/discharge` | Discharge: revokes the QR and stops their session. Idempotent. |
| DELETE | `/patients/{id}` | Hard delete (demo cleanup); fall events are kept without the patient link. |
| GET | `/patients/{id}/events` | The patient's fall events. |

`POST /live/start` accepts an optional `patient_id` (admitted patients only); `GET /live/status` then includes `patient: {patient_code, room_number}` (never the name). `POST /videos/upload` accepts an optional `patient_id` form field.

### Patient camera QR (phone gateway, `https://<mac-ip>:8443`)

`GET /c/{token}` serves the phone page (shows the patient code and room, never the name); `WS /c/{token}/ws` streams JPEG frames. A valid scan starts monitoring for that patient and their room automatically. Close codes: `4404` QR invalid/revoked/discharged, `4409` another patient or camera is already being monitored / a phone is already connected / patient has no room. If the phone drops, the session waits 60 s for it to return, then stops.


## Registered cameras and one-step monitoring

| Method | Path | Description |
|---|---|---|
| PUT | `/patients/{id}/camera` | Register this Mac's webcam: `{kind:"webcam", index:0-9}`. (A phone registers itself by connecting with the patient's QR.) |
| DELETE | `/patients/{id}/camera` | Unregister; stops that patient's session and disconnects their phone. |
| POST | `/patients/{id}/monitor` | Open live monitoring with the registered camera. Webcam: starts at once. Phone: tells the standby phone to start its camera. Returns `{state:"live"\|"starting", kind}`. Errors carry `detail:{code,message}`: `no_camera` (422), `no_room` (422), `camera_unavailable` (422), `busy` (409, another patient is monitored; never stopped automatically), `phone_offline` (409), `phone_unavailable` (409), `discharged` (409). Idempotent for a patient already live. |
| POST | `/patients/{id}/monitor/stop` | Stop that patient's session (the phone returns to standby). |

Patient objects now include `camera_kind`, `camera_label`, `camera_index`, `camera_registered_at` and `phone_online`.

### Phone standby protocol (`WS /c/{token}/ws`)

Connecting means "this phone is online for the patient": it is registered and kept in **standby** (camera off). The server sends text commands: `standby`, `start` (open the camera and stream), `stop` (camera off, back to standby), `live` (resume after a reconnect), `busy:<reason>`. The phone sends binary JPEG frames, `ping`, and `start_request` (the user tapped Start). Close codes: `4404` QR invalid/revoked/replaced, `4409` another phone is already connected for this patient. If a phone drops mid-session the session waits 60 s for it to return.


## Several patients at once (multi-session)

Sessions are keyed by patient (ad-hoc sessions by room). The machine runs up to `VITALYN_MAX_SESSIONS` cameras at once (default 3, sized for an 8 GB Mac); one pose model and one fall classifier are shared by all sessions and serialised with a lock. A physical camera (webcam index) can serve only one patient.

* `GET /live/status`: `state` (`live` if any session runs), `max_sessions`, `sessions[]` (one status per patient: `patient_id`, `patient{patient_code,room_number}`, `capture_fps`, `person_detected`, `model_guarded`, `events_count`, ...). Top-level fields describe the most recent session for older callers.
* `GET /live/stream?patient_id=<id>`: MJPEG for that patient. `409` if they are not being monitored.
* `GET /live/events`: ONE Server-Sent Events feed for every patient. Each message carries `patient_id` (and `job_id`), so a fall alarm reaches the dashboard whichever patient is on screen. The feed stays open (heartbeat comments every 15 s).
* `POST /live/stop?patient_id=<id>` stops one patient; with no `patient_id` it stops every session.
* `POST /patients/{id}/monitor` errors added: `limit` (409, camera limit reached) and `camera_in_use` (409, that webcam already serves another patient). It never stops another patient's session.
* `GET /health` adds `live_sessions` (number running).

## HMS phase 1 endpoints

All endpoints except `/health`, `/api/v1/auth/*` and the token-based phone pages require a signed-in, **active** staff member (httpOnly cookie, or `Authorization: Bearer`). Writes from a browser also need the header `X-Requested-With: vitalyn`. Errors: 401 not signed in, 403 `{code: pending|disabled|forbidden}`.

Roles: admin, doctor, nurse, receptionist (matrix in `backend/permissions.py`; every endpoint x role is tested in `tests/test_rbac.py`).

| Method | Endpoint | Roles | Purpose |
|---|---|---|---|
| POST | /auth/signup, /auth/login, /auth/refresh, /auth/logout | public | Sign in via Supabase Auth; new accounts start `pending` |
| GET | /auth/me | any signed-in | Current staff member and status |
| GET / PATCH | /staff, /staff/{id} | admin | Approve, set role, disable (cannot change self or remove the last admin) |
| GET | /audit | admin | Audit log, filter `action` prefix, `actor` |
| POST | /patients/register | admin, doctor, receptionist | Register an outpatient |
| POST | /patients/{id}/admit | same | Admit a registered outpatient to a ward (returns a one-time camera QR link) |
| GET | /patients?status=&q= | any staff | Search by name, patient code or phone |
| POST | /patients/{id}/transfer | admin, doctor, nurse | Move to a free bed; ends that patient's live session |
| POST | /patients/{id}/discharge | admin, doctor | Optional body: type home/transfer/ama/other, diagnosis, instructions, follow_up_date |
| POST | /patients/{id}/readmit | admin, doctor, receptionist | New stay, new QR |
| GET | /patients/{id}/timeline | any staff | ADT history; fall events only for clinical roles |
| PATCH | /beds/{id}/status | admin, doctor, nurse | available / cleaning / maintenance (not while occupied) |
| GET | /ward-board | any staff | Rooms, beds, occupants; monitoring and alert data only for clinical roles |
| GET / PUT | /doctors/{id}/schedule | any / admin or the doctor themself | Weekly clinic hours |
| GET | /doctors/{id}/availability?date= | any staff | Slots with `free` flag |
| POST | /appointments | admin, doctor, receptionist | Book a slot (409 if taken, 422 if not a slot or in the past) |
| GET | /appointments?date=&doctor_id=&patient_id=&status= | any staff | List |
| PATCH | /appointments/{id} | by transition | scheduled to checked_in/cancelled/no_show (front desk); checked_in to in_consult (the appointment's doctor or admin); in_consult to completed (same); other changes are 409 |

Live monitoring, alerts and camera endpoints are limited to admin, doctor and nurse; alert acknowledge/resolve record the signed-in staff member.

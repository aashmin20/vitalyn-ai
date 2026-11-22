# VITALYN — Database Schema

This is one of the most important sections because it defines how the entire application stores and manages information.

4.1 Core Database Entities

We will start with seven primary tables.

Table              Purpose
rooms              Hospital room information
beds               Beds belonging to rooms
inference_jobs      Video-processing jobs
occupancy_records   Historical occupancy observations
fall_events         Potential fall incidents
alerts             Alerts generated from events
users              Application users

4.2 Entity Relationship Diagram

             USERS
               |
               |
             ROOMS
               |
          ┌────┴────┐
          |         |
         BEDS   INFERENCE_JOBS
          |         |
          |         |
   OCCUPANCY_RECORDS
          |
          |
      INFERENCE_JOBS
          |
          ▼
      FALL_EVENTS
          |
          ▼
        ALERTS

More precisely, the relationships are:

* One room has multiple beds.
* One room has multiple inference jobs.
* One bed has multiple occupancy records.
* One inference job has multiple occupancy records.
* One inference job can generate multiple fall events.
* One fall event can generate multiple alerts.
* Users can acknowledge and resolve alerts.

4.3 Database Schema

Table 1: rooms

Column          Type            Description
id              UUID            Primary key
room_number      VARCHAR         Room identifier
floor            VARCHAR         Floor number
status          VARCHAR         Active/inactive
created_at       DATETIME        Creation timestamp

Table 2: beds

Column          Type            Description
id              UUID            Primary key
room_id          UUID            Foreign key
bed_number       VARCHAR         Bed identifier
status          VARCHAR         Active/inactive
created_at       DATETIME        Creation timestamp

Table 3: inference_jobs

Column          Type            Description
id              UUID            Primary key
room_id          UUID            Associated room
video_filename   VARCHAR         Original filename
video_path       VARCHAR         Stored video location
status          VARCHAR         Job status
progress        FLOAT           Processing progress
error_message   TEXT            Failure details
started_at       DATETIME       Start time
completed_at    DATETIME       Completion time
created_at       DATETIME       Job creation

Job statuses:

queued
processing
completed
failed

Table 4: occupancy_records

Column          Type            Description
id              UUID            Primary key
bed_id          UUID            Associated bed
inference_job_id UUID            Source job
occupancy_status VARCHAR         Occupied/vacant/uncertain
confidence      FLOAT           Model confidence
observed_at     DATETIME       Observation time

Table 5: fall_events

Column          Type            Description
id              UUID            Primary key
inference_job_id UUID            Source job
room_id          UUID            Associated room
bed_id          UUID            Associated bed, nullable
event_type      VARCHAR         Potential fall
confidence      FLOAT           Detection confidence
status          VARCHAR         Active/acknowledged/resolved
started_at      DATETIME       Event start
ended_at       DATETIME       Event end, nullable
created_at      DATETIME       Record creation

Table 6: alerts

Column          Type            Description
id              UUID            Primary key
fall_event_id    UUID            Associated event
alert_type      VARCHAR         Alert category
severity        VARCHAR         Priority
status          VARCHAR         Active/acknowledged/resolved
acknowledged_by UUID            User ID, nullable
acknowledged_at DATETIME       Acknowledgement time
resolved_by     UUID            User ID, nullable
resolved_at     DATETIME       Resolution time
created_at       DATETIME       Creation time

Table 7: users

Column          Type            Description
id              UUID            Primary key
name            VARCHAR         User name
email           VARCHAR         Login email
password_hash   VARCHAR         Hashed password
role            VARCHAR         User role
created_at       DATETIME        Creation time

Passwords must never be stored as plaintext.

4.4 Important Database Rules

1. Never overwrite historical occupancy records.
2. Every occupancy observation must retain its source inference job.
3. Failed inference jobs must remain available for debugging.
4. Fall events must be traceable to their source job.
5. Bed association may be null if the bed cannot be reliably identified.
6. Acknowledging an alert must not automatically resolve the event.
7. All important timestamps should be stored in UTC.

## Patients and doctors (added for the admission flow)

DEMO DATA ONLY until real-patient use is authorised.

| Table | Columns |
|---|---|
| `doctor` | `id`, `name`, `department?`, `user_id?` (reserved for staff logins), `created_at` |
| `patient` | `id`, `patient_code` (unique, e.g. P-0001), `name`, `age`, `condition`, `doctor_id`, `room_id`, `bed_id?`, `status` (`admitted`/`discharged`), `admitted_at`, `discharged_at?`, `camera_token_hash?`, `created_at` |

`inference_job.patient_id` and `fall_event.patient_id` are nullable foreign keys to `patient`. `camera_token_hash` is the SHA-256 of the secret in the patient's camera QR; the secret itself is never stored.

## Database engines

`DATABASE_URL` selects the engine (`backend/database.py`): unset = local SQLite file; `postgresql://...` = Supabase/Postgres (driver `psycopg`). UUID columns are native `UUID` on Postgres and hyphenated `CHAR(36)` on SQLite. `backend/schema.py::ensure_schema` creates tables, adds new nullable/defaulted columns to existing tables, and on Postgres enables Row Level Security on every table with no policies and revokes `anon`/`authenticated` privileges, so Supabase's public REST key cannot read patient data. Only the backend's direct database credentials can.

Fall events that cannot be written (database unreachable) are queued in a local SQLite outbox (`ml-engine/outbox.db`) and replayed automatically; `/health` shows `alert_queue` while any are waiting.


### Registered camera columns on `patient`

`camera_kind` (`phone`/`webcam`/null), `camera_index` (webcam index), `camera_label` (e.g. "iPhone (iOS 18)"), `camera_registered_at`. Set when a phone first connects with the patient's QR, or when staff pick the Mac webcam; cleared on discharge, QR regeneration or unregistering. They hold no secrets. The backend adds these columns automatically at startup (`schema.py::ensure_schema`), on SQLite and on Supabase.

## Hospital Management System tables (HMS phase 1)

| Table | Purpose |
|---|---|
| `user` (extended) | Staff account: `auth_user_id` (Supabase user id), `status` pending/active/disabled, `role` admin/doctor/nurse/receptionist/none, `last_login_at`. Passwords live in Supabase Auth; `password_hash` is a constant placeholder |
| `audit_log` | Who did what and when: actor, role, action, entity, short detail, IP. Never passwords, tokens or clinical free text |
| `adt_event` | Admission / transfer / discharge history of a patient: kind admitted/transferred/discharged/readmitted, from/to room and bed, note, discharge summary (JSON text), acting staff member |
| `doctor_schedule` | A doctor's weekly clinic hours (weekday 0-6, "HH:MM" start/end, slot minutes) |
| `appointment` | OPD booking: patient, doctor, start/end (hospital wall-clock time, no timezone), status, short reason, booked-by |

`patient` gains `sex`, `date_of_birth`, `phone`, `emergency_contact`, `allergies`, and `status` is now `outpatient | admitted | discharged`. Outpatients have no room, bed or camera. `bed.status` is `available | cleaning | maintenance` (older rows say `active`, treated as available); "occupied" is derived from admitted patients, never stored.

Invariants (enforced in code and tested): one admitted patient per bed; transfer needs a free, ready bed; discharge sends the bed to `cleaning`, revokes the camera QR and ends that patient's live session; a doctor's slots cannot overlap and a patient cannot hold two simultaneous appointments; appointment status changes follow a fixed workflow.

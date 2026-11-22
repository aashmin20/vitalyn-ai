-- VITALYN HMS phase 1: upgrade an EXISTING Supabase database. Safe to run more than once.
-- Run in: Supabase > SQL Editor > New query. (The backend also does this itself on startup.)

-- 1. new columns on existing tables
ALTER TABLE "user"  ADD COLUMN IF NOT EXISTS auth_user_id VARCHAR;
ALTER TABLE "user"  ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'pending';
ALTER TABLE "user"  ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITHOUT TIME ZONE;
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_auth_user_id ON "user" (auth_user_id);

ALTER TABLE patient ADD COLUMN IF NOT EXISTS sex VARCHAR;
ALTER TABLE patient ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE patient ADD COLUMN IF NOT EXISTS phone VARCHAR;
ALTER TABLE patient ADD COLUMN IF NOT EXISTS emergency_contact VARCHAR;
ALTER TABLE patient ADD COLUMN IF NOT EXISTS allergies VARCHAR;

-- 2. new tables
CREATE TABLE IF NOT EXISTS audit_log (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	id UUID NOT NULL PRIMARY KEY,
	actor_id UUID REFERENCES "user" (id),
	actor_email VARCHAR, actor_role VARCHAR,
	action VARCHAR NOT NULL, entity VARCHAR, entity_id VARCHAR, detail VARCHAR, ip VARCHAR
);
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action);

CREATE TABLE IF NOT EXISTS adt_event (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	id UUID NOT NULL PRIMARY KEY,
	patient_id UUID REFERENCES patient (id),
	kind VARCHAR NOT NULL,
	by_user_id UUID REFERENCES "user" (id),
	from_room_id UUID REFERENCES room (id), from_bed_id UUID REFERENCES bed (id),
	to_room_id UUID REFERENCES room (id), to_bed_id UUID REFERENCES bed (id),
	note VARCHAR, summary VARCHAR
);

CREATE TABLE IF NOT EXISTS doctor_schedule (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	id UUID NOT NULL PRIMARY KEY,
	doctor_id UUID REFERENCES doctor (id),
	weekday INTEGER NOT NULL, start_time VARCHAR NOT NULL, end_time VARCHAR NOT NULL, slot_minutes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS appointment (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	id UUID NOT NULL PRIMARY KEY,
	patient_id UUID REFERENCES patient (id),
	doctor_id UUID REFERENCES doctor (id),
	start_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, end_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	status VARCHAR NOT NULL, reason VARCHAR,
	created_by UUID REFERENCES "user" (id)
);

-- 3. lock the new tables down (no public API access; only the backend's direct connection)
ALTER TABLE audit_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE adt_event       ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_schedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointment     ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

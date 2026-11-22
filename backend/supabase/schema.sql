-- VITALYN schema for Supabase (Postgres). Generated from backend/models.py.
-- Safe to run more than once. Run in: Supabase > SQL Editor > New query.

CREATE TABLE IF NOT EXISTS room (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	room_number VARCHAR NOT NULL, 
	floor VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_room_room_number ON room (room_number);

CREATE TABLE IF NOT EXISTS "user" (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	name VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	auth_user_id VARCHAR, 
	status VARCHAR NOT NULL, 
	last_login_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_auth_user_id ON "user" (auth_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON "user" (email);

CREATE TABLE IF NOT EXISTS audit_log (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	actor_id UUID, 
	actor_email VARCHAR, 
	actor_role VARCHAR, 
	action VARCHAR NOT NULL, 
	entity VARCHAR, 
	entity_id VARCHAR, 
	detail VARCHAR, 
	ip VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES "user" (id)
);
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action);

CREATE TABLE IF NOT EXISTS bed (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	bed_number VARCHAR NOT NULL, 
	room_id UUID, 
	status VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(room_id) REFERENCES room (id)
);
CREATE INDEX IF NOT EXISTS ix_bed_bed_number ON bed (bed_number);

CREATE TABLE IF NOT EXISTS doctor (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	name VARCHAR NOT NULL, 
	department VARCHAR, 
	user_id UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES "user" (id)
);
CREATE INDEX IF NOT EXISTS ix_doctor_name ON doctor (name);

CREATE TABLE IF NOT EXISTS doctor_schedule (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	doctor_id UUID, 
	weekday INTEGER NOT NULL, 
	start_time VARCHAR NOT NULL, 
	end_time VARCHAR NOT NULL, 
	slot_minutes INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES doctor (id)
);

CREATE TABLE IF NOT EXISTS patient (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	patient_code VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	age INTEGER NOT NULL, 
	condition VARCHAR NOT NULL, 
	doctor_id UUID, 
	room_id UUID, 
	bed_id UUID, 
	status VARCHAR NOT NULL, 
	admitted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	discharged_at TIMESTAMP WITHOUT TIME ZONE, 
	camera_token_hash VARCHAR, 
	camera_kind VARCHAR, 
	camera_index INTEGER, 
	camera_label VARCHAR, 
	camera_registered_at TIMESTAMP WITHOUT TIME ZONE, 
	sex VARCHAR, 
	date_of_birth DATE, 
	phone VARCHAR, 
	emergency_contact VARCHAR, 
	allergies VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES doctor (id), 
	FOREIGN KEY(room_id) REFERENCES room (id), 
	FOREIGN KEY(bed_id) REFERENCES bed (id)
);
CREATE INDEX IF NOT EXISTS ix_patient_camera_token_hash ON patient (camera_token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS ix_patient_patient_code ON patient (patient_code);

CREATE TABLE IF NOT EXISTS adt_event (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	patient_id UUID, 
	kind VARCHAR NOT NULL, 
	by_user_id UUID, 
	from_room_id UUID, 
	from_bed_id UUID, 
	to_room_id UUID, 
	to_bed_id UUID, 
	note VARCHAR, 
	summary VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(patient_id) REFERENCES patient (id), 
	FOREIGN KEY(by_user_id) REFERENCES "user" (id), 
	FOREIGN KEY(from_room_id) REFERENCES room (id), 
	FOREIGN KEY(from_bed_id) REFERENCES bed (id), 
	FOREIGN KEY(to_room_id) REFERENCES room (id), 
	FOREIGN KEY(to_bed_id) REFERENCES bed (id)
);

CREATE TABLE IF NOT EXISTS appointment (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	patient_id UUID, 
	doctor_id UUID, 
	start_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	end_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	status VARCHAR NOT NULL, 
	reason VARCHAR, 
	created_by UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(patient_id) REFERENCES patient (id), 
	FOREIGN KEY(doctor_id) REFERENCES doctor (id), 
	FOREIGN KEY(created_by) REFERENCES "user" (id)
);

CREATE TABLE IF NOT EXISTS inference_job (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	room_id UUID, 
	video_filename VARCHAR NOT NULL, 
	video_path VARCHAR NOT NULL, 
	patient_id UUID, 
	status VARCHAR NOT NULL, 
	progress FLOAT NOT NULL, 
	error_message VARCHAR, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(room_id) REFERENCES room (id), 
	FOREIGN KEY(patient_id) REFERENCES patient (id)
);

CREATE TABLE IF NOT EXISTS fall_event (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	inference_job_id UUID, 
	room_id UUID, 
	bed_id UUID, 
	patient_id UUID, 
	event_type VARCHAR NOT NULL, 
	confidence FLOAT NOT NULL, 
	status VARCHAR NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	ended_at TIMESTAMP WITHOUT TIME ZONE, 
	resolved_by UUID, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(inference_job_id) REFERENCES inference_job (id), 
	FOREIGN KEY(room_id) REFERENCES room (id), 
	FOREIGN KEY(bed_id) REFERENCES bed (id), 
	FOREIGN KEY(patient_id) REFERENCES patient (id), 
	FOREIGN KEY(resolved_by) REFERENCES "user" (id)
);

CREATE TABLE IF NOT EXISTS occupancy_record (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	bed_id UUID, 
	inference_job_id UUID, 
	occupancy_status VARCHAR NOT NULL, 
	confidence FLOAT NOT NULL, 
	observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(bed_id) REFERENCES bed (id), 
	FOREIGN KEY(inference_job_id) REFERENCES inference_job (id)
);

CREATE TABLE IF NOT EXISTS alert (
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id UUID NOT NULL, 
	fall_event_id UUID, 
	alert_type VARCHAR NOT NULL, 
	severity VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	acknowledged_by UUID, 
	acknowledged_at TIMESTAMP WITHOUT TIME ZONE, 
	resolved_by UUID, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(fall_event_id) REFERENCES fall_event (id), 
	FOREIGN KEY(acknowledged_by) REFERENCES "user" (id), 
	FOREIGN KEY(resolved_by) REFERENCES "user" (id)
);

-- Row Level Security: ON with NO policies, so Supabase's public (anon / authenticated)
-- API keys can read and write nothing. Only the backend's direct database login can.
ALTER TABLE "room" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "audit_log" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "bed" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "doctor" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "doctor_schedule" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "patient" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "adt_event" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "appointment" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "inference_job" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "fall_event" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "occupancy_record" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "alert" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

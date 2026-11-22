// Mirror of backend SQLModel schemas

export interface Room {
  id: string;
  room_number: string;
  floor: string;
  status: string;
  created_at: string;
}

export interface Bed {
  id: string;
  bed_number: string;
  room_id: string | null;
  status: string;
  created_at: string;
}

export interface InferenceJob {
  id: string;
  room_id: string | null;
  video_filename: string;
  video_path: string;
  status: "queued" | "processing" | "live" | "completed" | "failed";
  progress: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface OccupancyRecord {
  id: string;
  bed_id: string | null;
  inference_job_id: string | null;
  occupancy_status: "occupied" | "vacant" | "uncertain";
  confidence: number;
  observed_at: string;
  created_at: string;
}

export interface CurrentOccupancy {
  bed_id: string;
  bed_number: string;
  room_number: string;
  room_id: string;
  occupancy_status: "occupied" | "vacant" | "uncertain";
  confidence: number;
  observed_at: string;
}

export interface OccupancyTrend {
  observed_at: string;
  occupancy_status: "occupied" | "vacant" | "uncertain";
  confidence: number;
  bed_id: string;
  bed_number: string;
}

export interface FallEvent {
  id: string;
  patient_id?: string | null;
  inference_job_id: string | null;
  room_id: string | null;
  bed_id: string | null;
  event_type: string;
  confidence: number;
  status: "active" | "acknowledged" | "resolved";
  started_at: string | null;
  ended_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  fall_event_id: string | null;
  alert_type: string;
  severity: "high" | "medium" | "low";
  status: "active" | "acknowledged" | "resolved";
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface DashboardOverview {
  total_beds: number;
  occupied_beds: number;
  vacant_beds: number;
  uncertain_beds: number;          // camera could not tell (only beds with a camera)
  not_ready_beds: number;          // cleaning or maintenance
  camera_occupied_beds: number;    // camera currently sees a person
  occupied_percentage: number;
  active_fall_events: number;
  active_alerts: number;
}

export interface EventSummary {
  total_events: number;
  active_events: number;
  acknowledged_events: number;
  resolved_events: number;
}

export interface JobResults {
  job: InferenceJob;
  occupancy_records: OccupancyRecord[];
  fall_events: FallEvent[];
}

export interface UploadResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface LiveFallEvent {
  id: string;
  confidence: number;
  source: "bilstm" | "heuristic";
  detected_at: string;
}

/** Three-way status from the live session. Percentages are the BiLSTM's own output, or null when the
 *  model has no valid prediction (never estimated). */
export interface FallAssessment {
  code: "normal" | "uncertain" | "potential_fall";
  label: string;
  fall_confidence: number | null;
  normal_confidence: number | null;
  reason: string;
  source: string;
  raised_by?: string | null;
}

export interface LiveStatus {
  state: "idle" | "starting" | "live" | "stopped" | "error";
  source?: string;
  room_id?: string;
  job_id?: string | null;
  started_at?: string | null;
  capture_fps?: number;
  inference_fps?: number;
  frames_captured?: number;
  samples?: number;
  person_detected?: boolean;
  window_fill?: number;
  window_required?: number;
  last_probability?: number | null;
  model_guarded?: boolean;
  assessment?: FallAssessment;
  retrained_model?: boolean;
  alerts_held_back?: number;
  patient_id?: string | null;
  patient?: { patient_code: string; room_number: string | null };
  sessions?: LiveStatus[];
  max_sessions?: number;
  events_count?: number;
  last_event?: LiveFallEvent | null;
  error?: string | null;
}

export interface LiveSources {
  cameras: { index: number; label: string }[];
  urls_enabled: boolean;
}

export interface Doctor {
  id: string;
  name: string;
  department: string | null;
}

export interface Patient {
  id: string;
  patient_code: string;
  name: string;
  age: number;
  condition: string;
  doctor: { id: string; name: string } | null;
  room: { id: string; room_number: string } | null;
  bed_id: string | null;
  bed_number: string | null;
  sex: "female" | "male" | "other" | null;
  date_of_birth: string | null;
  phone: string | null;
  emergency_contact: string | null;
  allergies: string | null;
  status: "admitted" | "discharged" | "outpatient";
  admitted_at: string;
  discharged_at: string | null;
  has_camera_link: boolean;
  camera_kind: "phone" | "webcam" | null;
  camera_label: string | null;
  camera_index: number | null;
  camera_registered_at: string | null;
  phone_online: boolean;
}

export interface CameraLink {
  token: string;
  url: string;
}

export interface AdmitResponse {
  patient: Patient;
  camera_link: CameraLink | null;
  camera_link_note: string | null;
}

export interface NewPatient {
  name: string;
  age: number;
  condition: string;
  doctor_id: string;
  room_id: string;
  bed_id?: string | null;
  sex?: "female" | "male" | "other" | null;
  phone?: string | null;
  emergency_contact?: string | null;
  allergies?: string | null;
}

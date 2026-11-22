# VITALYN — Application Flow

This section defines how users interact with VITALYN.

3.1 Application Navigation

Proposed sidebar:

VITALYN
│
├── Command Center
│
├── Monitoring
│   ├── Monitoring Overview
│   ├── Live Monitoring Room
│   └── Video Analysis
│
├── Hospital Operations
│   ├── Rooms
│   ├── Beds
│   └── Occupancy
│
├── Alerts & Events
│   ├── Active Alerts
│   ├── Acknowledged
│   └── Resolved
│
├── Analytics
│   ├── Occupancy Trends
│   ├── Fall Events
│   └── Model Performance
│
└── Settings
    ├── System Configuration
    └── Model Information

3.2 User Journey — Video Processing

User opens dashboard
        |
        ▼
Navigates to Monitoring
        |
        ▼
Selects Video Analysis
        |
        ▼
Uploads video
        |
        ▼
Backend validates video
        |
        ▼
Inference Job Created
        |
        ▼
ML Engine Processes Video
        |
        ▼
Results Stored
        |
        ▼
Frontend Displays Results
        |
        ├───────────────┐
        |               |
        ▼               ▼
Occupancy Results   Fall Events
        |               |
        ▼               ▼
Analytics          Alert Management

3.3 User Journey — Fall Alert

Potential Fall Detected
          |
          ▼
     Event Created
          |
          ▼
     Alert Created
          |
          ▼
    Staff Notified
          |
          ▼
  Staff Acknowledges
          |
          ▼
   Monitoring Continues
          |
          ▼
 Staff Verifies Incident
          |
          ▼
    Event Resolved

Important: disappearance from the camera cannot automatically establish that a patient is safe. Resolution requires human verification.

3.4 Monitoring Room Interface

This should be one of VITALYN’s standout features.

The interface should contain:

Left panel

* Room selection.
* Bed selection.
* Monitoring status.

Centre panel

* Original video.
* Processed video.
* Bounding boxes.
* Detection labels.
* Occupancy indicators.

Right panel

* Active events.
* Detection confidence.
* Event timestamps.
* Alert status.

Bottom panel

* Processing timeline.
* Occupancy history.
* Event log.

The processed video should show actual model output, not decorative simulated detections.
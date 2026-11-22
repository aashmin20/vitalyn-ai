# VITALYN — Product Requirements Document

Product: VITALYN
Tagline: Intelligence that cares.
Project: Hospital Bed Occupancy & Patient Fall Alert System
Version: 1.0
Document status: Initial specification
Target: Academic prototype and portfolio-grade application

⸻

1. Product Overview

VITALYN is an AI-powered hospital monitoring platform that uses computer vision and deep learning to monitor hospital bed occupancy and identify potential patient fall events.

The platform processes hospital room videos, detects people and beds, estimates bed occupancy, analyses patient movement and generates alerts when potentially dangerous fall events are identified.

It provides hospital staff with a centralised dashboard to monitor rooms, manage alerts and analyse occupancy patterns.

Product vision

Build an intelligent hospital monitoring platform that improves visibility into bed occupancy and potential patient fall incidents through computer vision and data-driven insights.

1.1 Problem Statement

Hospital staff often need to manually monitor multiple patients and hospital beds.

This creates several challenges:

* Difficulty monitoring multiple rooms simultaneously.
* Delayed identification of potential patient falls.
* Inefficient visibility into bed occupancy.
* Limited historical occupancy analytics.
* Repetitive manual monitoring activities.

VITALYN aims to address these challenges through automated video analysis and centralised monitoring.

1.2 Target Users

User    Responsibilities
Hospital Administrator    Manage rooms, beds and system configuration
Nurse / Healthcare Staff    Monitor patients and manage alerts
Monitoring Operator    Observe room activity and occupancy
System Administrator    Manage application settings and access

For the initial academic prototype, we will implement an administrator/monitoring-operator experience rather than a complex multi-role enterprise permission system.

1.3 Core Product Modules

Module  Description                 Priority
Command Dashboard    Overall monitoring overview              P0
Live Monitoring Room    Video upload and processed-video visualisation    P0
Bed Occupancy    Occupied/vacant/uncertain estimates    P0
Fall Detection    Identify potential fall events              P0
Alert Management    View, acknowledge and resolve alerts      P0
Analytics    Occupancy and event statistics               P1
AI Insights    Explain structured operational information  P2
SOP Knowledge Hub    Search approved hospital documentation  P2
Occupancy Forecasting    Predict future occupancy                  P2

P0 means essential for the first working prototype.

P1 and P2 are extensions. They must not be presented as functional until implemented.

1.4 Functional Requirements

FR-01: Video Upload

The system must:

* Accept supported video formats.
* Validate file type and size.
* Generate a unique inference job ID.
* Store uploaded video metadata.
* Return the job status.

FR-02: Person Detection

The system must:

* Detect people in video frames.
* Generate bounding boxes.
* Calculate detection confidence.
* Display processed frames.

FR-03: Bed Detection

The system must:

* Identify hospital beds.
* Maintain bed-region information.
* Associate detected people with bed regions where possible.

FR-04: Bed Occupancy

The system must classify bed occupancy as:

* Occupied
* Vacant
* Uncertain

Every observation should contain a timestamp and confidence value.

FR-05: Potential Fall Detection

The system must:

* Analyse human posture and movement.
* Identify potential fall sequences.
* Aggregate consecutive detections belonging to the same incident.
* Generate one event rather than repetitive frame-level alerts.

FR-06: Alert Management

The system must support:

* Alert creation.
* Alert listing.
* Alert acknowledgement.
* Event monitoring.
* Alert resolution.
* Timestamp tracking.

Acknowledging an alert must not automatically resolve the event.

FR-07: Analytics

The system should display:

* Total beds.
* Occupied beds.
* Vacant beds.
* Occupancy percentage.
* Active potential fall events.
* Historical occupancy trends.

Only actual stored data should contribute to these metrics.

1.5 Non-Functional Requirements

Requirement    Description
Performance    Efficient processing on limited hardware
Reliability    Preserve job and event records
Security    Validate uploads and restrict access
Privacy    Avoid unnecessary patient identification
Maintainability    Modular architecture
Scalability    Allow future multi-room monitoring
Reproducibility    Record model and processing configuration
Usability    Clear, accessible monitoring interface
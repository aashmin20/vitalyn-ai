# VITALYN — System Architecture

This document defines the overall system architecture, including components, their relationships, and data flow.

⸻

1. Component Overview

The VITALYN system consists of the following core components:

Frontend (Next.js + React + TypeScript)
    * User interface for monitoring and management
    * Video visualization and analysis display
    * Real-time alert management
    * Analytics and reporting

Backend (FastAPI + SQLite)
    * API server and business logic
    * Database management and persistence
    * ML inference orchestration
    * Authentication and authorization

ML Engine (Python + OpenCV + PyTorch + YOLO)
    * Person and bed detection using YOLO
    * Pose estimation and keypoint extraction
    * Temporal analysis for fall detection
    * Occupancy classification logic

2. Data Flow

Video Processing Pipeline:

Video Upload
    ↓ (API validation and storage)
Inference Job Creation
    ↓ (Database record created)
Frame Extraction
    ↓ (OpenCV processing)
Person Detection (YOLO)
    ↓
Pose Estimation
    ↓           ↓
Bed Detection  Posture Analysis
    ↓           ↓
Occupancy Classification  Temporal Analysis
    ↓           ↓
Structured Results    Fall Event Detection
    ↓           ↓
Database Storage  Database Storage
    ↓           ↓
API Response  API Response

Alert Management Pipeline:

Fall Event Detected
    ↓ (Database record)
Alert Created
    ↓ (Database record)
Frontend Notification
    ↓ (User action)
Alert Acknowledged/Resolved
    ↓ (Database update with user info)
Event Status Updated

3. API Architecture

API Layer:
    * RESTful endpoints organized under /api/v1
    * JSON request/response formats
    * JWT-based authentication
    * Comprehensive error handling
    * API documentation via OpenAPI/Swagger

Database Layer:
    * SQLite with ACID compliance
    * Foreign key constraints for referential integrity
    * Indexes for performance optimization
    * Transactions for data consistency

4. Technology Integration Points

Integration Points:
    * Frontend ↔ Backend: REST APIs
    * Backend ↔ ML Engine: Function calls
    * Backend ↔ Database: SQL
    * ML Engine ↔ Hardware: Direct hardware access

5. Security Architecture

Security Controls:
    * Input validation and sanitization
    * File upload restrictions (type, size, location)
    * Access control based on user roles
    * HTTPS for all API communications
    * Password hashing (bcrypt)
    * No patient identification in output
    * Audit logging for all operations

6. Scalability Considerations

Scaling Plan:
    * Database: SQLite → PostgreSQL/MySQL for production
    * Caching: Redis for job status and analytics
    * Load balancing: Nginx for frontend and API
    * Horizontal scaling for ML processing
    * Monitoring and alerting infrastructure

## Live camera path

Camera/stream → capture thread (latest frame, overlay, JPEG) → `/live/stream` (MJPEG)
                         ↓ latest frame
            inference thread @ 6 FPS: YOLOv8n-pose → `StreamingFallDetector` (BiLSTM windows) + aspect-ratio heuristic
                         ↓
            `db_writer` → FallEvent + Alert / OccupancyRecord → `/live/events` (SSE) and the existing dashboard/alerts pages

Implemented in `ml-engine/live_pipeline.py`, `ml-engine/streaming_detector.py`, `backend/live_routes.py` and the `/monitoring/camera` page.

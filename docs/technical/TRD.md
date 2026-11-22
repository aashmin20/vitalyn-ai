# VITALYN — Technical Requirements Document

⸻

2. System Architecture

We will use a modular monolithic architecture.

This means the frontend, backend and ML engine have separate responsibilities, but we don't need to deploy multiple independent microservices.

Architecture diagram

                 VITALYN
                    |
          ┌─────────┴─────────┐
          |                   |
       FRONTEND             BACKEND
       Next.js              FastAPI
          |                   |
          |             ┌─────┴─────┐
          |             |           |
          |          Database    ML Engine
          |          SQLite      Python
          |             |           |
          |             |       OpenCV
          |             |       PyTorch
          |             |       YOLO
          |             |       LSTM*
          |             |           |
          |             └─────┬─────┘
          |                   |
          └──────── API ──────┘

LSTM is a future extension, not a mandatory component of the initial MVP.

2.1 Technology Stack

Layer      Technology
Frontend   Next.js
UI         React + TypeScript
Styling    Tailwind CSS
Components  shadcn/ui
Animation   Framer Motion
Charts      Recharts
Icons       Lucide
Backend    Python FastAPI
Database   SQLite
Computer Vision OpenCV
Deep Learning PyTorch
Object Detection YOLO
Temporal Analysis LSTM / sequence classifier
Version Control Git + GitHub
Testing     Pytest

Hardware considerations

The development machine has:

* Apple M3 chip.
* 8 GB RAM.
* Approximately 40 GB available storage at the last environment audit.

Therefore:

* Avoid unnecessarily large models.
* Use smaller video samples.
* Process frames selectively.
* Avoid running multiple heavy models simultaneously.
* Keep the initial database lightweight.

2.2 ML Architecture

The ML engine will consist of independent processing components.

Video Input
    |
    ▼
OpenCV Frame Extraction
    |
    ▼
Person Detection
    |
    ▼
Pose / Keypoint Extraction
    |
    ├───────────────┐
    |               |
    ▼               ▼
Bed Detection    Posture Analysis
    |               |
    ▼               ▼
Occupancy Logic  Temporal Analysis
    |               |
    ▼               ▼
Occupancy       Potential Fall
Estimation      Classification
    |               |
    └───────┬───────┘
            |
            ▼
     Structured Results

Model responsibilities

Component      Responsibility
YOLO          Person and bed detection
Pose estimation Extract body landmarks
Temporal classifier    Analyse movement sequences
Occupancy logic   Estimate bed occupancy
Event aggregation  Combine frame-level detections
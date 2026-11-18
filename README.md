VITALYN

Intelligence that cares.

AI-powered Hospital Bed Occupancy Monitoring and Patient Fall Alert System

VITALYN is a deep-learning-based hospital monitoring prototype designed to estimate bed occupancy and identify potential patient-fall events using computer vision and temporal analysis.

Problem Statement

Hospitals need reliable ways to monitor bed utilisation and identify potential patient-safety events. Manual monitoring can be resource-intensive, while isolated image-based detection may fail to capture movement and changes over time.

VITALYN explores how deep learning and computer vision can support these monitoring tasks.

Core Objectives

1. Detect people and beds in video frames.
2. Estimate bed occupancy using spatial relationships.
3. Analyse patient posture and movement over time.
4. Identify potential fall events.
5. Generate and manage safety alerts.
6. Evaluate model performance using appropriate metrics.

Core Features

* Video-based inference
* Person and bed detection
* Bed occupancy estimation
* Temporal fall-event analysis
* Safety alert management
* Model evaluation dashboard

Technology Stack

Layer	Technology
Frontend	Next.js, TypeScript
UI	Tailwind CSS, shadcn/ui, Motion
Backend	Python, FastAPI
Computer Vision	PyTorch, OpenCV
Detection	Selected pretrained or fine-tuned model
Database	SQLite initially
Version Control	Git, GitHub

Architecture

The application is organised into three independent components:

* Frontend: User interface and monitoring dashboard.
* Backend: API, application logic and event management.
* ML Engine: Video processing, detection, occupancy estimation and fall-event analysis.

Project Structure

Vitalyn-AI/
├── frontend/
├── backend/
├── ml-engine/
├── datasets/
├── docs/
├── scripts/
├── AGENTS.md
├── README.md
└── .gitignore

Evaluation

Model performance will be assessed using task-appropriate metrics, including:

* Precision
* Recall
* F1-score
* Confusion matrix
* Inference latency
* Occupancy MAE, where applicable

Scope and Limitations

VITALYN is an academic prototype, not a clinically validated hospital monitoring system. Fall outputs represent potential events requiring human review. The system does not diagnose medical conditions or replace healthcare professionals.

Future Scope

* LSTM-based occupancy forecasting
* RAG-based hospital knowledge assistant
* Voice interaction
* Advanced segmentation
* C++ inference integration
* Model monitoring and versioning

Project Status

Development in progress.
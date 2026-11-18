# VITALYN — Architecture Decision Records

## ADR-001: Hybrid Video Processing

### Decision
VITALYN will initially support upload-based video processing,
with architecture designed for future live camera integration.

### Initial Implementation
- Upload video files.
- Extract frames using OpenCV.
- Process frames through the ML inference pipeline.
- Generate occupancy estimates.
- Identify potential fall events.
- Store and display inference results.

### Future Extensions
- Webcam input.
- IP camera integration.
- Continuous video streams.
- Multi-room monitoring.

### Reasoning
Upload-based processing is reproducible, easier to test
and suitable for the initial academic prototype.

Separating frame acquisition from inference allows
future input sources without rewriting the core
computer vision pipeline.

### Status
Accepted.
## ADR-002: Backend-Orchestrated Inference

### Decision
The frontend will communicate with the ML engine through
the backend. The backend will coordinate inference jobs.

### Initial Implementation
- Frontend uploads a video to the backend.
- Backend validates the upload and creates an inference job.
- ML engine processes the video.
- Backend stores the results and updates job status.
- Frontend retrieves results and displays them.

### Job Status
- Queued
- Processing
- Completed
- Failed

### Reasoning
Direct frontend-to-ML communication would tightly couple
the user interface to the ML implementation.

The backend provides a central layer for validation,
job management, database operations and access control.

Job-based processing prevents long video inference
from blocking the upload request.

### Future Extensions
- Real-time progress updates.
- WebSocket or Server-Sent Events.
- Distributed inference workers.

### Status
Accepted.
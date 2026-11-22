# VITALYN — Dataset Research

This document provides information about the datasets used for training and evaluating the VITALYN system.

⸻

1. Available Datasets

We have access to the following datasets for fall detection and occupancy monitoring:

FallVision
    * Purpose: Bed-related fall sequences
    * Size: ~100 hours of annotated fall and normal activities
    * License: Academic research license
    * Format: Video segments with timestamps
    * Annotation: Fall/non-fall labels with bounding boxes
    * Acquisition: Hospital-controlled environment recordings

GMDCSA-24
    * Purpose: Fall and normal activity sequences
    * Size: 24 subjects, ~50 hours total
    * License: MIT for research
    * Format: Multi-camera RGB-D recordings
    * Annotation: Full body pose, activity labels
    * Source: Geriatric motion dataset

IKAR
    * Purpose: Additional fall scenarios
    * Size: ~30 hours of diverse fall incidents
    * License: Research institution permit
    * Format: Stereo video with depth information
    * Annotation: Fall type and severity classification
    * Source: IKAR fall detection dataset

Hospital-object datasets
    * Purpose: Person and bed detection
    * Size: Large-scale hospital environment footage
    * License: Hospital research partnership
    * Format: High-resolution RGB footage
    * Annotation: Person bounding boxes, bed instances
    * Source: Multiple hospital facilities

2. Dataset Organization

Raw datasets are stored in:

datasets/
├── raw/
│   ├── fallvision/
│   │   ├── fall/
│   │   └── non_fall/
│   ├── gmdcja-24/
│   │   ├── train/
│   │   └── val/
│   └── ikar/
│       ├── falls/
│       └── normal/
├── processed/
│   ├── yolo/
│   │   ├── person/
│   │   └── bed/
│   ├── pose/
│   │   ├── keypoints/
│   │   └── heatmaps/
│   └── temporal/
│       ├── sequences/
│       └── events/
├── annotations/
│   ├── fallvision/
│   ├── gmdcja-24/
│   └── ikar/
└── README.md

3. Dataset Preparation Pipeline

Data Preparation Steps:

Video Processing:
    * Frame extraction at 1-2 fps for long videos
    * Frame filtering for quality and clarity
    * Redundant frame removal

Annotation Processing:
    * Convert bounding box formats to YOLO format
    * Generate pose annotation files
    * Create temporal event annotations

Dataset Splitting:
    * Patient-level splits for GMDCSA-24
    * Video-level splits for FallVision
    * Session-based splitting for IKAR

Quality Control:
    * Manual verification of sample frames
    * Annotation completeness checks
    * Format consistency validation

4. Dataset Limitations

Known Limitations:
    * FallVision lacks diverse lighting conditions
    * GMDCSA-24 has limited demographic diversity
    * IKAR recordings are limited to controlled environments
    * All datasets focus on falls from standing position
    * Limited representation of bed-specific fall mechanisms

5. Future Dataset Acquisition

Priority Areas for Enhancement:
    * Real-world hospital footage with diverse environments
    * Pediatric and geriatric patient variations
    * Bed-specific fall scenarios (falls while getting in/out of bed)
    * Nighttime recording scenarios
    * Multi-hospital collaborative datasets

6. Data Privacy and Ethics

Data Handling:
    * No patient identity data in any dataset
    * All footage uses synthetic patient simulations
    * Dataset augmented with privacy-preserving techniques
    * Informed consent obtained for all real patient footage
    * Regular privacy audits and compliance checks
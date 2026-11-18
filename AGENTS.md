# VITALYN — AI Agent Instructions

## Project Identity
VITALYN is an AI-powered Hospital Bed Occupancy Monitoring
and Patient Fall Alert System.

## Core Principles
- Build modular, maintainable and testable software.
- Prioritise genuine functionality over visual appearance.
- Never fabricate model metrics or inference results.
- Clearly distinguish implemented features from simulations.
- Never use identifiable patient data without authorisation.
- Never claim clinical validation.

## Architecture
- frontend/: Next.js and TypeScript
- backend/: Python FastAPI
- ml-engine/: Computer vision and deep learning
- datasets/: Dataset documentation and approved data
- docs/: Architecture, research and evaluation

## Git Rules
- Never commit directly to main.
- Develop on assigned feature branches.
- Do not overwrite another agent's work.
- Use descriptive commit messages.
- Test before committing.
- Never commit API keys, credentials or .env files.

## Development Rules
- Explain significant architectural decisions.
- Avoid unnecessary dependencies.
- Prefer reusable components and services.
- Keep API contracts documented.
- Write tests for critical functionality.
- Preserve existing working functionality.

## AI and Model Integrity
- Disclose pretrained models and external code.
- Record dataset provenance and preprocessing.
- Maintain reproducible training configurations.
- Report limitations and failure cases.
- Fall alerts must be treated as potential events
  requiring human review.

## Hardware Constraints
Development machine: Apple Silicon Mac, 8 GB RAM.
- Avoid unnecessary background services.
- Do not assume local LLM availability.
- Prefer lightweight development configurations.
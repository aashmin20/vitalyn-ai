from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from sqlmodel import SQLModel
import uuid
import json
import os
import sys

from sqlalchemy import text
from sqlmodel import Session
from database import engine, describe_database
from schema import ensure_schema
from routes import router
from live_routes import router as live_router, live_state
from patient_routes import router as patient_router
from adt_routes import router as adt_router
from opd_routes import router as opd_router
from auth_routes import router as auth_router
from staff_routes import router as staff_router
from audit import router as audit_router
from models import InferenceJob
from sqlmodel import select
from contextlib import asynccontextmanager


class UUIDJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


@asynccontextmanager
async def lifespan(_app):
    # A job still marked 'live' at startup belongs to a process that no longer exists.
    with Session(engine) as session:
        for job in session.exec(select(InferenceJob).where(InferenceJob.status == "live")).all():
            job.status = "failed"
            job.error_message = "Live session ended: backend restarted."
            job.completed_at = datetime.now(timezone.utc)
            session.add(job)
        session.commit()
    # Optional phone-camera gateway (HTTPS listener for phone browsers, opt-in).
    gateway = None
    if os.getenv("VITALYN_PHONE_GATEWAY") == "1":
        try:
            from phone_gateway import get_gateway
            gateway = get_gateway()
            gateway.start()
            print(f"VITALYN phone gateway: {gateway.base_url()}")
        except Exception as exc:
            print(f"Phone gateway failed to start: {exc}")
    yield
    if gateway is not None:
        gateway.stop()
    # Graceful shutdown: end any running live session so its job is not left 'live'.
    try:
        from live_routes import _loaded_manager
        manager = _loaded_manager()
        if manager is not None:
            manager.stop()
    except Exception:
        pass


app = FastAPI(
    lifespan=lifespan,
    title="VITALYN API",
    description="AI-powered Hospital Bed Occupancy & Patient Fall Alert System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"]
    + [o.strip() for o in os.getenv("VITALYN_CORS_ORIGINS", "").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded videos as static files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(router)
app.include_router(live_router)
app.include_router(patient_router)
app.include_router(adt_router)
app.include_router(opd_router)
app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(audit_router)


ensure_schema(engine)
print(f"VITALYN database: {describe_database()}")


@app.get("/")
def root():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml-engine", "vitalyn_fall_bilstm.pt")


@app.get("/health")
def health():
    """Real component checks — the UI status indicator is driven by this."""
    components = {"api": "ok"}
    try:
        with Session(engine) as session:
            session.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception:
        components["database"] = "error"
    queued = 0
    try:
        ml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml-engine")
        if ml_path not in sys.path:
            sys.path.insert(0, ml_path)
        import outbox
        queued = outbox.pending()
    except Exception:
        pass
    components["alert_queue"] = "ok" if queued == 0 else f"{queued} queued"   # fall events waiting for the database
    components["fall_model"] = "ok" if os.path.exists(MODEL_PATH) else "missing"
    components["camera"] = live_state()          # idle | starting | live | stopped | error
    components["uploads"] = "ok" if os.access(UPLOAD_DIR, os.W_OK) else "error"

    if components["database"] != "ok":
        status = "unhealthy"
    elif any(v not in ("ok", "idle", "live", "stopped") for v in components.values()):
        status = "degraded"
    else:
        status = "healthy"
    live_sessions = 0
    try:
        from live_routes import _loaded_manager
        manager = _loaded_manager()
        live_sessions = len(manager.running_sessions()) if manager else 0
    except Exception:
        pass
    return {"status": status, "database": describe_database(), "components": components, "live_sessions": live_sessions}

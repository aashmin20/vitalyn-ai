"""Audit trail: who did what and when. Never records passwords, tokens or clinical free text."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session, select

from auth import AuthUser, require_roles
from database import get_session
from models import AuditLog

log = logging.getLogger("vitalyn.audit")

router = APIRouter(prefix="/api/v1")


def record(
    session: Session,
    user: Optional[AuthUser],
    action: str,
    entity: Optional[str] = None,
    entity_id: Any = None,
    detail: Any = None,
    request: Optional[Request] = None,
) -> None:
    """Add one audit row in the caller's transaction (committed with the change itself)."""
    ip = request.client.host if request is not None and request.client else None
    text = detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str)
    session.add(AuditLog(
        actor_id=user.uuid if user else None,
        actor_email=user.email if user else None,
        actor_role=user.role if user else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=(text or "")[:500] or None,
        ip=ip,
    ))


def record_view(session: Session, user: Optional[AuthUser], entity: str, entity_id: Any,
                request: Optional[Request] = None, window_minutes: int = 10) -> None:
    """Log that a record was opened, at most once per user and record per window (pages poll)."""
    if user is None:
        return
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    last = session.exec(
        select(AuditLog)
        .where(AuditLog.action == f"{entity}.view", AuditLog.entity_id == str(entity_id),
               AuditLog.actor_email == user.email)
        .order_by(AuditLog.created_at.desc())
    ).first()
    if last is not None:
        seen = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=timezone.utc)
        if seen > since:
            return
    record(session, user, f"{entity}.view", entity, entity_id, request=request)
    session.commit()


@router.get("/audit")
def list_audit(
    action: Optional[str] = None,
    actor: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    _admin: AuthUser = Depends(require_roles("admin")),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if actor:
        stmt = stmt.where(AuditLog.actor_email == actor.lower())
    rows = session.exec(stmt).all()
    return [
        {
            "id": str(r.id),
            "at": r.created_at.isoformat() + ("Z" if r.created_at.tzinfo is None else ""),
            "actor_email": r.actor_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "detail": r.detail,
            "ip": r.ip,
        }
        for r in rows
    ]

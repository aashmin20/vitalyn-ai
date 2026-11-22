"""Staff accounts: administrators approve sign-ups and assign roles."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

import audit
from auth import ROLES, AuthUser, require_roles
from database import get_session
from models import Doctor, User

router = APIRouter(prefix="/api/v1/staff")

STATUSES = ("pending", "active", "disabled")


class StaffUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None


def _out(u: User) -> dict:
    return {
        "id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "status": u.status,
        "created_at": u.created_at.isoformat() + ("Z" if u.created_at.tzinfo is None else ""),
        "last_login_at": (u.last_login_at.isoformat() + ("Z" if u.last_login_at.tzinfo is None else ""))
        if u.last_login_at else None,
    }


@router.get("")
def list_staff(session: Session = Depends(get_session), _admin: AuthUser = Depends(require_roles("admin"))):
    return [_out(u) for u in session.exec(select(User).order_by(User.created_at)).all()]


@router.patch("/{user_id}")
def update_staff(
    user_id: uuid.UUID,
    body: StaffUpdate,
    request: Request,
    session: Session = Depends(get_session),
    admin: AuthUser = Depends(require_roles("admin")),
):
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if body.role is not None and body.role not in ROLES + ("none",):
        raise HTTPException(status_code=422, detail=f"Role must be one of {', '.join(ROLES)}")
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of {', '.join(STATUSES)}")
    if admin.id and str(target.id) == admin.id:
        raise HTTPException(status_code=409, detail="You cannot change your own role or status.")

    new_role = body.role if body.role is not None else target.role
    new_status = body.status if body.status is not None else target.status
    if new_status == "active" and new_role not in ROLES:
        raise HTTPException(status_code=422, detail="Choose a role before approving the account.")

    loses_admin = target.role == "admin" and target.status == "active" and (new_role != "admin" or new_status != "active")
    if loses_admin:
        other_admins = session.exec(
            select(User).where(User.role == "admin", User.status == "active", User.id != target.id)
        ).all()
        if not other_admins:
            raise HTTPException(status_code=409, detail="There must always be at least one active administrator.")

    change = f"role {target.role}->{new_role}, status {target.status}->{new_status}"
    target.role, target.status = new_role, new_status
    session.add(target)
    if new_role == "doctor" and session.exec(select(Doctor).where(Doctor.user_id == target.id)).first() is None:
        session.add(Doctor(name=target.name, user_id=target.id))            # doctors show up in dropdowns
    audit.record(session, admin, "staff.update", "user", target.id, change, request)
    session.commit()
    session.refresh(target)
    return _out(target)

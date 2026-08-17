"""Append-only recruitment audit logger."""

from __future__ import annotations

from flask import Request, has_request_context, request as flask_request
from flask_login import current_user

from recruitment.extensions import db
from recruitment.models import RecruitmentAuditLog, utcnow
from recruitment.tracking import request_context


def write_audit(
    event_type: str,
    event_name: str,
    *,
    request: Request | None = None,
    payload: dict | None = None,
    candidate_id: int | None = None,
    application_id: int | None = None,
    details: str | None = None,
    actor_type: str | None = None,
    actor_name: str | None = None,
    visitor_id: str | None = None,
    session_id: str | None = None,
) -> RecruitmentAuditLog:
    req = request
    if req is None and has_request_context():
        req = flask_request
    ctx = request_context(req, payload) if req is not None else {
        "visitor_id": visitor_id or "",
        "session_id": session_id or "",
        "ip_address": None,
        "user_agent": "",
        "device_type": "",
        "browser": "",
        "operating_system": "",
        "referrer": "",
        "page_url": "",
    }
    if visitor_id:
        ctx["visitor_id"] = visitor_id
    if session_id:
        ctx["session_id"] = session_id

    if actor_type is None:
        if has_request_context() and current_user.is_authenticated:
            actor_type = "admin"
            actor_name = actor_name or f"{current_user.name} <{current_user.email}>"
        else:
            actor_type = "visitor"

    row = RecruitmentAuditLog(
        event_type=event_type,
        event_name=event_name,
        candidate_id=candidate_id,
        application_id=application_id,
        session_id=ctx.get("session_id") or None,
        visitor_id=ctx.get("visitor_id") or None,
        ip_address=ctx.get("ip_address"),
        user_agent=ctx.get("user_agent") or None,
        device_type=ctx.get("device_type") or None,
        browser=ctx.get("browser") or None,
        operating_system=ctx.get("operating_system") or None,
        referrer=ctx.get("referrer") or None,
        page_url=ctx.get("page_url") or None,
        actor_type=actor_type,
        actor_name=actor_name,
        details=(details or "")[:4000] or None,
        event_timestamp=utcnow(),
    )
    db.session.add(row)
    return row

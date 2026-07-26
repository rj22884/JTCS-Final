"""Database session helpers for SQLAlchemy 2.x + Flask-SQLAlchemy."""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError

from app.extensions import db

logger = logging.getLogger(__name__)


def map_db_exception(exc: Exception) -> str:
    if isinstance(exc, IntegrityError):
        return "A record with these details already exists."
    if isinstance(exc, OperationalError):
        return "Database is temporarily unavailable. Please try again."
    if isinstance(exc, InvalidRequestError):
        return "Database session error. Please try again."
    return "An unexpected database error occurred. Please try again."


def persist(callable_write):
    """
    Single transaction per write: flush, commit, rollback on error, always close session.
    Never uses db.session.begin() — compatible with SQLAlchemy 2.x autobegin on reads.
    """
    try:
        result = callable_write()
        db.session.flush()
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.remove()


def reset_session() -> None:
    try:
        db.session.rollback()
    except Exception:
        logger.exception("Failed to rollback database session")
    finally:
        db.session.remove()

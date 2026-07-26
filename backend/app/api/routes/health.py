from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services import system

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    system.check_database(db)
    info = system.get_app_info(db)
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": info["version"],
    }

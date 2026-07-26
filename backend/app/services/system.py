from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings


def seed_defaults(db: Session) -> None:
    from app.models import AppSetting

    existing = db.scalar(select(AppSetting).where(AppSetting.key == "app_version"))
    if existing is None:
        db.add(AppSetting(key="app_version", value="0.1.0"))
        db.commit()


def check_database(db: Session) -> bool:
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return True


def get_app_info(db: Session) -> dict[str, str]:
    from app.models import AppSetting

    version = db.scalar(select(AppSetting).where(AppSetting.key == "app_version"))
    return {
        "app_name": settings.app_name,
        "version": version.value if version else "unknown",
    }

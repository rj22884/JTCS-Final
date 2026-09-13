"""Uttarakhand FPS login against existing PdsFpsMaster (no duplicate master)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime

from flask import session
from sqlalchemy import func, or_, select, text

from app.extensions import db
from app.models.auth import User
from app.models.ration_card import (
    PdsAroMaster,
    PdsDistrictMaster,
    PdsDsoMaster,
    PdsFpsMaster,
    PdsStateMaster,
)
from app.repositories.pds_master_repository import PdsMasterRepository
from app.repositories.user_repository import UserRepository
from app.services.login_activity_service import STATUS_FAILED, STATUS_SUCCESS, LoginActivityService
from app.utils.db_session import persist
from app.utils.fps_access import (
    FPS_INACTIVE_MESSAGE,
    FPS_LOGIN_ERROR,
    is_fps_session,
    session_fps_row_id,
)
from app.utils.roles import FPS_USER_ROLE
from app.utils.security import hash_password

logger = logging.getLogger(__name__)

_SCHEMA_READY = False
PAGE_SIZE = 40


class FpsLoginService:
    def __init__(self):
        self.users = UserRepository()
        self.login_activity = LoginActivityService()

    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        PdsMasterRepository().ensure_schema()
        statements = (
            """
            IF COL_LENGTH(N'dbo.Users', N'FpsRowID') IS NULL
                ALTER TABLE dbo.Users ADD FpsRowID INT NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
            AND OBJECT_ID(N'dbo.PdsFpsMaster', N'U') IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM sys.foreign_keys
                WHERE name = N'FK_Users_FpsRowID'
                  AND parent_object_id = OBJECT_ID(N'dbo.Users')
            )
                ALTER TABLE dbo.Users
                    ADD CONSTRAINT FK_Users_FpsRowID
                    FOREIGN KEY (FpsRowID) REFERENCES dbo.PdsFpsMaster (FpsRowID);
            """,
            """
            IF COL_LENGTH(N'dbo.Users', N'FpsRowID') IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'UX_Users_FpsRowID'
                  AND object_id = OBJECT_ID(N'dbo.Users')
            )
                CREATE UNIQUE INDEX UX_Users_FpsRowID
                    ON dbo.Users (FpsRowID)
                    WHERE FpsRowID IS NOT NULL;
            """,
        )
        try:
            for sql in statements:
                db.session.execute(text(sql))
            db.session.commit()
            _SCHEMA_READY = True
        except Exception:
            db.session.rollback()
            logger.exception("FPS user schema ensure failed")
            raise

    def serialize_fps(
        self,
        fps: PdsFpsMaster,
        *,
        district_name: str | None = None,
        state_name: str | None = None,
        dso_name: str | None = None,
        aro_name: str | None = None,
    ) -> dict:
        district = district_name
        if district is None:
            district = ""
            if fps.DistrictID:
                row = db.session.get(PdsDistrictMaster, fps.DistrictID)
                district = (row.DistrictName if row else "") or ""
        return {
            "fps_row_id": fps.FpsRowID,
            "shop_name": fps.FpsName or "",
            "dealer_name": fps.DealerName or "",
            "fps_id": fps.FpsCode or "",
            "existing_fps_id": fps.ExistingFpsId or "",
            "state_name": state_name or "",
            "district_name": district or "",
            "dso_name": dso_name or "",
            "aro_name": aro_name or "",
            "tehsil_name": fps.TehsilName or "",
            "mobile_number": fps.MobileNumber or "",
            "address": fps.Address or "",
            "active_status": bool(fps.ActiveStatus),
            "status_label": "Active" if fps.ActiveStatus else "Inactive",
        }

    @staticmethod
    def _option_label(name, code) -> str:
        title = (name or "").strip()
        extra = (code or "").strip()
        if title and extra and extra.lower() not in title.lower():
            return f"{title} ({extra})"
        return title or extra or "—"

    @staticmethod
    def _login_fps_filters():
        """Only active FPS rows that already have the full office chain."""
        return (
            PdsFpsMaster.ActiveStatus == True,  # noqa: E712
            PdsFpsMaster.DsoID.isnot(None),
            PdsFpsMaster.AroID.isnot(None),
        )

    def cascade_options(self, level: str, *, parent_id: int | None = None) -> list[dict]:
        """Active offices that actually have an active FPS under them."""
        self.ensure_schema()
        step = (level or "").strip().lower()
        parent = int(parent_id or 0)
        active_fps = self._login_fps_filters()
        if step == "state":
            stmt = (
                select(PdsStateMaster.StateID, PdsStateMaster.StateName, PdsStateMaster.StateCode)
                .join(PdsDistrictMaster, PdsDistrictMaster.StateID == PdsStateMaster.StateID)
                .join(PdsFpsMaster, PdsFpsMaster.DistrictID == PdsDistrictMaster.DistrictID)
                .where(PdsStateMaster.ActiveStatus == True, PdsDistrictMaster.ActiveStatus == True, *active_fps)  # noqa: E712
                .distinct()
                .order_by(PdsStateMaster.StateName, PdsStateMaster.StateID)
            )
        elif step == "district":
            if parent <= 0:
                return []
            stmt = (
                select(PdsDistrictMaster.DistrictID, PdsDistrictMaster.DistrictName, PdsDistrictMaster.DistrictCode)
                .join(PdsFpsMaster, PdsFpsMaster.DistrictID == PdsDistrictMaster.DistrictID)
                .where(
                    PdsDistrictMaster.StateID == parent,
                    PdsDistrictMaster.ActiveStatus == True,  # noqa: E712
                    *active_fps,
                )
                .distinct()
                .order_by(PdsDistrictMaster.DistrictName, PdsDistrictMaster.DistrictID)
            )
        elif step == "dso":
            if parent <= 0:
                return []
            stmt = (
                select(PdsDsoMaster.DsoID, PdsDsoMaster.DsoName, PdsDsoMaster.DsoCode)
                .join(PdsFpsMaster, PdsFpsMaster.DsoID == PdsDsoMaster.DsoID)
                .where(
                    PdsDsoMaster.DistrictID == parent,
                    PdsFpsMaster.DistrictID == parent,
                    PdsDsoMaster.ActiveStatus == True,  # noqa: E712
                    *active_fps,
                )
                .distinct()
                .order_by(PdsDsoMaster.DsoName, PdsDsoMaster.DsoID)
            )
        elif step == "aro":
            if parent <= 0:
                return []
            stmt = (
                select(PdsAroMaster.AroID, PdsAroMaster.AroName, PdsAroMaster.AroCode)
                .join(PdsFpsMaster, PdsFpsMaster.AroID == PdsAroMaster.AroID)
                .where(
                    PdsAroMaster.DsoID == parent,
                    PdsFpsMaster.DsoID == parent,
                    PdsAroMaster.ActiveStatus == True,  # noqa: E712
                    *active_fps,
                )
                .distinct()
                .order_by(PdsAroMaster.AroName, PdsAroMaster.AroID)
            )
        else:
            raise ValueError("Unknown selection step.")
        rows = db.session.execute(stmt).all()
        return [{"id": int(row[0]), "label": self._option_label(row[1], row[2])} for row in rows]

    def search_active(
        self,
        term: str | None = None,
        *,
        page: int = 1,
        per_page: int = PAGE_SIZE,
        state_id: int | None = None,
        district_id: int | None = None,
        dso_id: int | None = None,
        aro_id: int | None = None,
    ) -> dict:
        self.ensure_schema()
        per_page = max(1, min(int(per_page or PAGE_SIZE), 100))
        page = max(1, int(page or 1))
        empty = {
            "rows": [],
            "count": 0,
            "total": 0,
            "page": page,
            "per_page": per_page,
            "has_more": False,
            "query": (term or "").strip(),
            "requires_aro": True,
        }
        if not int(aro_id or 0):
            return empty
        stmt = (
            select(
                PdsFpsMaster,
                PdsDistrictMaster.DistrictName,
                PdsStateMaster.StateName,
                PdsDsoMaster.DsoName,
                PdsAroMaster.AroName,
            )
            .outerjoin(PdsDistrictMaster, PdsFpsMaster.DistrictID == PdsDistrictMaster.DistrictID)
            .outerjoin(PdsStateMaster, PdsDistrictMaster.StateID == PdsStateMaster.StateID)
            .outerjoin(PdsDsoMaster, PdsFpsMaster.DsoID == PdsDsoMaster.DsoID)
            .outerjoin(PdsAroMaster, PdsFpsMaster.AroID == PdsAroMaster.AroID)
            .where(PdsFpsMaster.ActiveStatus == True)  # noqa: E712
            .where(PdsFpsMaster.AroID == int(aro_id))
        )
        count_stmt = (
            select(func.count(PdsFpsMaster.FpsRowID))
            .select_from(PdsFpsMaster)
            .outerjoin(PdsDistrictMaster, PdsFpsMaster.DistrictID == PdsDistrictMaster.DistrictID)
            .where(PdsFpsMaster.ActiveStatus == True)  # noqa: E712
            .where(PdsFpsMaster.AroID == int(aro_id))
        )
        if int(dso_id or 0):
            stmt = stmt.where(PdsFpsMaster.DsoID == int(dso_id))
            count_stmt = count_stmt.where(PdsFpsMaster.DsoID == int(dso_id))
        if int(district_id or 0):
            stmt = stmt.where(PdsFpsMaster.DistrictID == int(district_id))
            count_stmt = count_stmt.where(PdsFpsMaster.DistrictID == int(district_id))
        if int(state_id or 0):
            stmt = stmt.where(PdsDistrictMaster.StateID == int(state_id))
            count_stmt = count_stmt.where(PdsDistrictMaster.StateID == int(state_id))
        cleaned = (term or "").strip()
        if cleaned:
            needle = f"%{cleaned.lower()}%"
            search_filter = or_(
                func.lower(PdsFpsMaster.FpsName).like(needle),
                func.lower(PdsFpsMaster.DealerName).like(needle),
                func.lower(PdsFpsMaster.FpsCode).like(needle),
                func.lower(PdsFpsMaster.ExistingFpsId).like(needle),
                func.lower(PdsFpsMaster.TehsilName).like(needle),
                func.lower(PdsDistrictMaster.DistrictName).like(needle),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)
        total = int(db.session.scalar(count_stmt) or 0)
        rows = list(
            db.session.execute(
                stmt.order_by(
                    PdsFpsMaster.FpsName,
                    PdsFpsMaster.FpsCode,
                    PdsFpsMaster.FpsRowID,
                )
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).all()
        )
        return {
            "rows": [
                self.serialize_fps(
                    fps,
                    district_name=district or "",
                    state_name=state or "",
                    dso_name=dso or "",
                    aro_name=aro or "",
                )
                for fps, district, state, dso, aro in rows
            ],
            "count": len(rows),
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": (page * per_page) < total,
            "query": cleaned,
            "requires_aro": False,
        }

    def get_active(self, fps_row_id: int) -> PdsFpsMaster | None:
        self.ensure_schema()
        if not fps_row_id:
            return None
        fps = db.session.get(PdsFpsMaster, int(fps_row_id))
        if fps is None or not fps.ActiveStatus:
            return None
        return fps

    def get_any(self, fps_row_id: int) -> PdsFpsMaster | None:
        self.ensure_schema()
        if not fps_row_id:
            return None
        return db.session.get(PdsFpsMaster, int(fps_row_id))

    def _find_user_for_fps(self, fps_row_id: int) -> User | None:
        stmt = select(User).where(User.FpsRowID == int(fps_row_id))
        return db.session.scalars(stmt).first()

    def _ensure_user(self, fps: PdsFpsMaster) -> User:
        found = self._find_user_for_fps(fps.FpsRowID)
        display = (fps.FpsName or fps.DealerName or fps.FpsCode or "FPS").strip()[:200]
        mobile = (fps.MobileNumber or "").strip()[:15] or "0000000000"
        email = f"fps.{fps.FpsRowID}@fps.jtcs.internal"
        now = datetime.utcnow()
        if found is not None:
            found.FullName = display
            found.Role = FPS_USER_ROLE
            found.FpsRowID = fps.FpsRowID
            found.IsActive = True
            found.UserStatus = "Active"
            found.AdminApproved = True
            found.EmailVerified = True
            found.LastLoginDate = now
            found.ModifiedDate = now
            if fps.MobileNumber:
                found.MobileNumber = mobile
            return found
        by_email = self.users.get_by_email(email)
        if by_email is not None:
            by_email.FullName = display
            by_email.Role = FPS_USER_ROLE
            by_email.FpsRowID = fps.FpsRowID
            by_email.IsActive = True
            by_email.UserStatus = "Active"
            by_email.AdminApproved = True
            by_email.EmailVerified = True
            by_email.LastLoginDate = now
            by_email.ModifiedDate = now
            return by_email
        return self.users.create(
            {
                "FullName": display,
                "EmailID": email,
                "MobileNumber": mobile,
                "PasswordHash": hash_password(secrets.token_urlsafe(32)),
                "IsPasswordSet": True,
                "Role": FPS_USER_ROLE,
                "IsActive": True,
                "Department": "FPS",
                "Designation": "FPS User",
                "UserStatus": "Active",
                "EmailVerified": True,
                "AdminApproved": True,
                "FpsRowID": fps.FpsRowID,
                "LastLoginDate": now,
            }
        )

    def _audit(self, action: str, status: str, *, fps_row_id: int | None = None, detail: str | None = None):
        try:
            from app.services.server_audit_service import ServerAuditService

            ServerAuditService().log(
                action=action,
                module="FPSLogin",
                record_id=fps_row_id,
                status=status,
                new_value=detail,
            )
        except Exception:
            logger.exception("FPS login audit skipped")

    def login(self, fps_row_id: int) -> tuple[bool, str, dict]:
        self.ensure_schema()
        self._audit("FPS login attempt", STATUS_SUCCESS, fps_row_id=fps_row_id)
        fps = self.get_any(int(fps_row_id or 0))
        if fps is None:
            self.login_activity.log_login_activity("fps-unknown", STATUS_FAILED)
            self._audit("FPS login failed", STATUS_FAILED, fps_row_id=fps_row_id, detail="not found")
            return False, FPS_LOGIN_ERROR, {}
        if not fps.ActiveStatus:
            self.login_activity.log_login_activity(
                fps.FpsCode or f"fps-{fps.FpsRowID}",
                STATUS_FAILED,
            )
            self._audit(
                "Inactive FPS login attempt",
                STATUS_FAILED,
                fps_row_id=fps.FpsRowID,
                detail="inactive",
            )
            return False, FPS_INACTIVE_MESSAGE, {"reason": "inactive"}

        shop = self.serialize_fps(fps)
        fps_pk = int(fps.FpsRowID)

        def _write():
            user = self._ensure_user(fps)
            return user.UserID, user.FullName

        try:
            user_id, user_name = persist(_write)
        except Exception:
            logger.exception("FPS login persist failed")
            self._audit("FPS login failed", STATUS_FAILED, fps_row_id=fps_pk, detail="persist")
            return False, FPS_LOGIN_ERROR, {}

        session_id = None
        try:
            session_id = self.login_activity.log_login_activity(
                shop["fps_id"] or f"fps-{fps_pk}",
                STATUS_SUCCESS,
                user_pk=user_id,
            )
        except Exception:
            logger.exception("FPS login activity skipped")
        self._audit("Successful FPS login", STATUS_SUCCESS, fps_row_id=fps_pk, detail=shop["fps_id"])
        return True, "Logged in.", {
            "user_id": user_id,
            "user_name": user_name,
            "role": FPS_USER_ROLE,
            "fps_row_id": fps_pk,
            "fps_id": shop["fps_id"],
            "shop": shop,
            "login_session_id": session_id,
        }

    def scoped_shop(self) -> dict | None:
        fps_row_id = session_fps_row_id()
        if not fps_row_id:
            return None
        fps = self.get_any(fps_row_id)
        if fps is None:
            return None
        return self.serialize_fps(fps)

    def scoped_dealer(self) -> dict | None:
        """Resolve the authenticated FPS to the existing ration-dealer report row."""
        if not is_fps_session():
            return None
        fps_row_id = session_fps_row_id()
        fps = self.get_any(fps_row_id or 0)
        if fps is None:
            return None
        from app.services.ration_card_report_service import RationCardReportService

        def _load():
            service = RationCardReportService()
            dealer = service._ensure_dealer_for_fps(fps)
            return service._serialize_fps_shop(dealer, fps)

        return persist(_load)

    def resolve_dealer_id(self, requested: int | None) -> int:
        """FPS_USER always uses the session FPS; admin uses the requested dealer."""
        if is_fps_session():
            scoped = self.scoped_dealer()
            if not scoped or not scoped.get("dealer_id"):
                raise ValueError(FPS_LOGIN_ERROR)
            return int(scoped["dealer_id"])
        if not requested:
            raise ValueError("Select a ration dealer first.")
        return int(requested)

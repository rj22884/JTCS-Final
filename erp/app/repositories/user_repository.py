from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.auth import AuthToken, CompanyProfile, User


class UserRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str, *, include_rejected: bool = True) -> User | None:
        normalized = (email or "").strip().lower()
        stmt = select(User).where(func.lower(User.EmailID) == normalized)
        if not include_rejected:
            stmt = stmt.where(User.UserStatus != "Rejected")
        return self.session.scalars(stmt).first()

    def get_active_by_email(self, email: str) -> User | None:
        return self.get_by_email(email, include_rejected=False)

    def get_active_by_mobile(self, mobile: str) -> list[User]:
        normalized = (mobile or "").strip()
        stmt = (
            select(User)
            .where(User.MobileNumber == normalized)
            .where(User.UserStatus != "Rejected")
            .order_by(User.FullName)
        )
        return list(self.session.scalars(stmt).all())

    def get_active_by_full_name(self, full_name: str) -> User | None:
        normalized = (full_name or "").strip().lower()
        stmt = (
            select(User)
            .where(func.lower(User.FullName) == normalized)
            .where(User.UserStatus != "Rejected")
        )
        return self.session.scalars(stmt).first()

    def get_primary_administrator(self) -> User | None:
        stmt = (
            select(User)
            .where(User.Role.in_(["Administrator", "Admin"]))
            .where(User.IsActive == True)  # noqa: E712
            .order_by(User.CreatedDate)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_by_mobile(self, mobile: str) -> list[User]:
        normalized = (mobile or "").strip()
        stmt = select(User).where(User.MobileNumber == normalized).order_by(User.FullName)
        return list(self.session.scalars(stmt).all())

    def administrator_exists(self) -> bool:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.Role.in_(["Administrator", "Admin"]))
            .where(User.IsActive == True)  # noqa: E712
            .where(User.UserStatus == "Active")
        )
        return self.session.scalar(stmt) > 0

    def list_pending_users(self) -> list[User]:
        stmt = (
            select(User)
            .where(User.UserStatus == "Pending")
            .order_by(User.CreatedDate.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_active_non_admin_users(self) -> list[User]:
        stmt = (
            select(User)
            .where(User.UserStatus == "Active")
            .where(User.IsActive == True)  # noqa: E712
            .where(~User.Role.in_(["Administrator", "Admin"]))
            .order_by(User.FullName)
        )
        return list(self.session.scalars(stmt).all())

    def list_all_for_admin(self) -> list[User]:
        """All users for Admin Role → Users grid (excludes rejected)."""
        stmt = select(User).where(User.UserStatus != "Rejected")
        rows = list(self.session.scalars(stmt).all())
        rows.sort(
            key=lambda u: (
                0 if (u.UserStatus or "") == "Pending" else 1,
                0 if u.IsActive else 2,
                -(u.CreatedDate.timestamp() if u.CreatedDate else 0),
            )
        )
        return rows

    def create(self, data: dict) -> User:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        user = User(**data)
        self.session.add(user)
        self.session.flush()
        return user

    def update(self, user: User, data: dict) -> User:
        for key, value in data.items():
            setattr(user, key, value)
        user.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return user


class CompanyRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def get_profile(self) -> CompanyProfile | None:
        stmt = select(CompanyProfile).order_by(CompanyProfile.CompanyID).limit(1)
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> CompanyProfile:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        company = CompanyProfile(**data)
        self.session.add(company)
        self.session.flush()
        return company

    def update(self, company: CompanyProfile, data: dict) -> CompanyProfile:
        for key, value in data.items():
            setattr(company, key, value)
        company.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return company


class AuthTokenRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> AuthToken:
        token = AuthToken(**data)
        self.session.add(token)
        self.session.flush()
        return token

    def find_valid(self, token_type: str, email: str | None = None, mobile: str | None = None) -> list[AuthToken]:
        stmt = select(AuthToken).where(
            AuthToken.TokenType == token_type,
            AuthToken.IsUsed == False,  # noqa: E712
            AuthToken.ExpiresAt > datetime.utcnow(),
        )
        if email:
            stmt = stmt.where(AuthToken.Email == email.lower())
        if mobile:
            stmt = stmt.where(AuthToken.MobileNumber == mobile)
        stmt = stmt.order_by(AuthToken.CreatedDate.desc())
        return list(self.session.scalars(stmt).all())

    def mark_used(self, token: AuthToken) -> None:
        token.IsUsed = True
        self.session.flush()

    def invalidate_active(
        self,
        token_type: str,
        *,
        user_id: int | None = None,
        email: str | None = None,
        mobile: str | None = None,
    ) -> None:
        stmt = select(AuthToken).where(
            AuthToken.TokenType == token_type,
            AuthToken.IsUsed == False,  # noqa: E712
        )
        if user_id is not None:
            stmt = stmt.where(AuthToken.UserID == user_id)
        if email:
            stmt = stmt.where(AuthToken.Email == email.lower())
        if mobile:
            stmt = stmt.where(AuthToken.MobileNumber == mobile)
        for token in self.session.scalars(stmt).all():
            token.IsUsed = True
        self.session.flush()

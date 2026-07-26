from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.auth import PasswordResetOTP

PASSWORD_RESET_PURPOSE = "PASSWORD_RESET"
OTP_VALID_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


class PasswordResetOTPRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def invalidate_active(self, user_id: int, email: str, purpose: str = PASSWORD_RESET_PURPOSE) -> None:
        stmt = select(PasswordResetOTP).where(
            PasswordResetOTP.UserID == user_id,
            PasswordResetOTP.Email == email.lower(),
            PasswordResetOTP.Purpose == purpose,
            PasswordResetOTP.IsUsed == False,  # noqa: E712
        )
        for row in self.session.scalars(stmt).all():
            row.IsUsed = True
        self.session.flush()

    def create(self, user_id: int, email: str, otp_hash: str, purpose: str = PASSWORD_RESET_PURPOSE) -> PasswordResetOTP:
        now = datetime.utcnow()
        row = PasswordResetOTP(
            UserID=user_id,
            Email=email.lower(),
            OTP=otp_hash,
            Purpose=purpose,
            CreatedOn=now,
            ExpiresOn=now + timedelta(minutes=OTP_VALID_MINUTES),
            Verified=False,
            AttemptCount=0,
            IsUsed=False,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_active_for_email(self, email: str, purpose: str = PASSWORD_RESET_PURPOSE) -> PasswordResetOTP | None:
        stmt = (
            select(PasswordResetOTP)
            .where(
                func.lower(PasswordResetOTP.Email) == email.lower(),
                PasswordResetOTP.Purpose == purpose,
                PasswordResetOTP.IsUsed == False,  # noqa: E712
                PasswordResetOTP.ExpiresOn > datetime.utcnow(),
            )
            .order_by(PasswordResetOTP.CreatedOn.desc())
        )
        return self.session.scalars(stmt).first()

    def get_by_id(self, otp_id: int) -> PasswordResetOTP | None:
        return self.session.get(PasswordResetOTP, otp_id)

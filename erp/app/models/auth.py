from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class User(db.Model):
    __tablename__ = "Users"

    UserID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FullName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    EmailID: Mapped[str] = mapped_column(Unicode(254), nullable=False)
    MobileNumber: Mapped[str] = mapped_column(Unicode(15), nullable=False)
    PasswordHash: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    IsPasswordSet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    Role: Mapped[str] = mapped_column(Unicode(200), nullable=False, default="Operator")
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    Department: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    Designation: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    UserStatus: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="Pending")
    EmailVerified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    AdminApproved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    VerificationDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    VerificationIP: Mapped[str | None] = mapped_column(Unicode(45), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    LastLoginDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CompanyProfile(db.Model):
    __tablename__ = "CompanyProfile"

    CompanyID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    CompanyName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    OwnerName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    LogoPath: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    SetupCompleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthToken(db.Model):
    __tablename__ = "AuthToken"

    AuthTokenID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    Email: Mapped[str | None] = mapped_column(Unicode(254), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)
    TokenType: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    TokenHash: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    ExpiresAt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    IsUsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PasswordResetOTP(db.Model):
    __tablename__ = "PasswordResetOTP"

    OTPID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserID: Mapped[int] = mapped_column(Integer, nullable=False)
    Email: Mapped[str] = mapped_column(Unicode(254), nullable=False)
    OTP: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    Purpose: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="PASSWORD_RESET")
    CreatedOn: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ExpiresOn: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    Verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    AttemptCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsUsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

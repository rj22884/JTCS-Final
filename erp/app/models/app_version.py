"""Application version history (deployments / change log)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class AppVersionHistory(db.Model):
    __tablename__ = "AppVersionHistory"

    VersionID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ApplicationVersion: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    BuildNumber: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    DatabaseVersion: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    GitCommitID: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    GitBranch: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    DeveloperName: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    ReleaseNotes: Mapped[str | None] = mapped_column(Text, nullable=True)
    WhatsNew: Mapped[str | None] = mapped_column(Text, nullable=True)
    BugFixes: Mapped[str | None] = mapped_column(Text, nullable=True)
    NewFeatures: Mapped[str | None] = mapped_column(Text, nullable=True)
    DatabaseChanges: Mapped[str | None] = mapped_column(Text, nullable=True)
    SecurityUpdates: Mapped[str | None] = mapped_column(Text, nullable=True)
    PerformanceImprovements: Mapped[str | None] = mapped_column(Text, nullable=True)
    DeploymentStatus: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="Success")
    BackupPath: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    DeployedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    IsCurrent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AppVersionHistory {self.ApplicationVersion} build={self.BuildNumber}>"

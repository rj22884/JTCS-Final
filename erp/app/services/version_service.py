"""Enterprise version / change-log service for JTCS ERP."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from app.extensions import db
from app.models.app_version import AppVersionHistory


class VersionService:
    def get_current(self) -> AppVersionHistory | None:
        try:
            return db.session.scalars(
                select(AppVersionHistory)
                .where(AppVersionHistory.IsCurrent == True)  # noqa: E712
                .order_by(AppVersionHistory.VersionID.desc())
                .limit(1)
            ).first()
        except Exception:
            # Table may not exist until migration 066 is applied.
            db.session.rollback()
            return None

    def get_display_version(self, fallback: str = "1.0.0") -> str:
        current = self.get_current()
        if current and current.ApplicationVersion:
            return current.ApplicationVersion
        return fallback

    def list_history(self, *, limit: int = 50) -> list[AppVersionHistory]:
        try:
            return list(
                db.session.scalars(
                    select(AppVersionHistory)
                    .order_by(AppVersionHistory.VersionID.desc())
                    .limit(limit)
                ).all()
            )
        except Exception:
            db.session.rollback()
            return []

    def get_by_id(self, version_id: int) -> AppVersionHistory | None:
        return db.session.get(AppVersionHistory, version_id)

    def get_by_version_string(self, application_version: str) -> AppVersionHistory | None:
        needle = (application_version or "").strip()
        if not needle:
            return None
        return db.session.scalars(
            select(AppVersionHistory)
            .where(AppVersionHistory.ApplicationVersion == needle)
            .order_by(AppVersionHistory.VersionID.desc())
            .limit(1)
        ).first()

    def record_deployment(
        self,
        *,
        application_version: str,
        build_number: int,
        database_version: str | None = None,
        git_commit_id: str | None = None,
        git_branch: str | None = None,
        developer_name: str | None = None,
        release_notes: str | None = None,
        whats_new: str | None = None,
        bug_fixes: str | None = None,
        new_features: str | None = None,
        database_changes: str | None = None,
        security_updates: str | None = None,
        performance_improvements: str | None = None,
        deployment_status: str = "Success",
        backup_path: str | None = None,
        mark_current: bool | None = None,
    ) -> AppVersionHistory:
        status = (deployment_status or "Success").strip() or "Success"
        if mark_current is None:
            mark_current = status == "Success"

        if mark_current:
            db.session.execute(
                update(AppVersionHistory).values(IsCurrent=False).where(
                    AppVersionHistory.IsCurrent == True  # noqa: E712
                )
            )

        row = AppVersionHistory(
            ApplicationVersion=application_version.strip(),
            BuildNumber=int(build_number),
            DatabaseVersion=(database_version or application_version).strip() or None,
            GitCommitID=(git_commit_id or "").strip() or None,
            GitBranch=(git_branch or "").strip() or None,
            DeveloperName=(developer_name or "").strip() or None,
            ReleaseNotes=(release_notes or "").strip() or None,
            WhatsNew=(whats_new or "").strip() or None,
            BugFixes=(bug_fixes or "").strip() or None,
            NewFeatures=(new_features or "").strip() or None,
            DatabaseChanges=(database_changes or "").strip() or None,
            SecurityUpdates=(security_updates or "").strip() or None,
            PerformanceImprovements=(performance_improvements or "").strip() or None,
            DeploymentStatus=status,
            BackupPath=(backup_path or "").strip() or None,
            DeployedAt=datetime.utcnow(),
            IsCurrent=bool(mark_current),
            CreatedDate=datetime.utcnow(),
        )
        db.session.add(row)
        db.session.flush()
        return row

    def history_as_dicts(self, *, limit: int = 50) -> list[dict]:
        rows = self.list_history(limit=limit)
        return [self.to_dict(row) for row in rows]

    @staticmethod
    def to_dict(row: AppVersionHistory) -> dict:
        return {
            "version_id": row.VersionID,
            "application_version": row.ApplicationVersion,
            "build_number": row.BuildNumber,
            "database_version": row.DatabaseVersion or "",
            "git_commit_id": row.GitCommitID or "",
            "git_branch": row.GitBranch or "",
            "developer_name": row.DeveloperName or "",
            "release_notes": row.ReleaseNotes or "",
            "whats_new": row.WhatsNew or "",
            "bug_fixes": row.BugFixes or "",
            "new_features": row.NewFeatures or "",
            "database_changes": row.DatabaseChanges or "",
            "security_updates": row.SecurityUpdates or "",
            "performance_improvements": row.PerformanceImprovements or "",
            "deployment_status": row.DeploymentStatus,
            "backup_path": row.BackupPath or "",
            "deployed_at": row.DeployedAt.isoformat() if row.DeployedAt else "",
            "is_current": bool(row.IsCurrent),
        }

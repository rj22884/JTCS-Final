"""Provider-based cloud backup upload (Google Drive first; OneDrive/Dropbox later)."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.modules.settings.google_drive_client import GoogleDriveClient, GoogleDriveError
from app.modules.settings.google_drive_oauth_service import (
    FOLDER_NAME,
    PROVIDER as GDRIVE_PROVIDER,
    STATUS_CONNECTED,
    GoogleDriveOAuthService,
)
from app.modules.settings.services import IntegrationSettingsService
from app.services.backup_service import BackupService

logger = logging.getLogger(__name__)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_SCHEMA_READY = False


def _job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _job_update(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")


class CloudBackupUploadService:
    """Facade so OneDrive / Dropbox providers can plug in later."""

    SUPPORTED_PROVIDERS = ("google_drive",)

    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.BackupCloudUpload', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.BackupCloudUpload (
                        UploadID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        Provider NVARCHAR(50) NOT NULL,
                        BackupKind NVARCHAR(20) NOT NULL,
                        FileName NVARCHAR(260) NOT NULL,
                        RemoteFileId NVARCHAR(200) NULL,
                        UploadStatus NVARCHAR(40) NOT NULL,
                        ProgressPercent INT NOT NULL CONSTRAINT DF_BackupCloudUpload_Progress DEFAULT (0),
                        ErrorMessage NVARCHAR(1000) NULL,
                        UploadedBy NVARCHAR(120) NULL,
                        UploadedAt DATETIME2 NULL,
                        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_BackupCloudUpload_Created DEFAULT (SYSUTCDATETIME()),
                        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_BackupCloudUpload_Updated DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE INDEX IX_BackupCloudUpload_File
                        ON dbo.BackupCloudUpload (BackupKind, FileName, Provider);
                END
                """
            )
        )
        db.session.commit()
        _SCHEMA_READY = True

    def provider_status(self, provider: str = GDRIVE_PROVIDER, *, return_to: str | None = None) -> dict[str, Any]:
        provider = (provider or GDRIVE_PROVIDER).strip().lower()
        if provider != GDRIVE_PROVIDER:
            return {
                "ok": False,
                "provider": provider,
                "connected": False,
                "error": f"Cloud provider '{provider}' is not implemented yet.",
            }
        return GoogleDriveOAuthService().connection_info(return_to=return_to)

    def latest_upload_map(self, *, kind: str = "database", provider: str = GDRIVE_PROVIDER) -> dict[str, dict]:
        self.ensure_schema()
        rows = db.session.execute(
            text(
                """
                SELECT FileName, RemoteFileId, UploadStatus, ProgressPercent, ErrorMessage, UploadedAt
                FROM (
                    SELECT
                        FileName, RemoteFileId, UploadStatus, ProgressPercent, ErrorMessage, UploadedAt,
                        ROW_NUMBER() OVER (
                            PARTITION BY FileName ORDER BY ISNULL(UploadedAt, CreatedAt) DESC, UploadID DESC
                        ) AS rn
                    FROM dbo.BackupCloudUpload
                    WHERE BackupKind = :kind AND Provider = :provider
                ) x
                WHERE rn = 1
                """
            ),
            {"kind": kind, "provider": provider},
        ).mappings().all()
        result: dict[str, dict] = {}
        for row in rows:
            result[str(row["FileName"])] = {
                "remote_file_id": row["RemoteFileId"] or "",
                "upload_status": row["UploadStatus"] or "",
                "progress_percent": int(row["ProgressPercent"] or 0),
                "error_message": row["ErrorMessage"] or "",
                "uploaded_at": row["UploadedAt"].isoformat(timespec="seconds")
                if row["UploadedAt"]
                else "",
            }
        return result

    def start_upload(
        self,
        *,
        kind: str,
        file_name: str,
        provider: str = GDRIVE_PROVIDER,
        uploaded_by: str = "System",
        return_to: str | None = None,
    ) -> dict[str, Any]:
        provider = (provider or GDRIVE_PROVIDER).strip().lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Cloud provider '{provider}' is not supported yet.")
        kind = (kind or "").strip().lower()
        if kind != "database":
            raise ValueError("Only Data Backup (.bak) files can be uploaded to Google Drive.")

        path = BackupService().resolve_download(kind, file_name)
        if path.suffix.lower() != ".bak":
            raise ValueError("Only .bak backup files can be uploaded to Google Drive.")

        status = self.provider_status(provider, return_to=return_to)
        if not status.get("connected"):
            return {
                "ok": False,
                "needs_oauth": True,
                "provider": provider,
                "authorize_url": status.get("authorize_url"),
                "connect_error": status.get("connect_error"),
                "error": status.get("connect_error")
                or "Connect Google Drive first, then retry upload.",
            }

        self.ensure_schema()
        job_id = uuid.uuid4().hex
        upload_id = self._insert_row(
            provider=provider,
            kind=kind,
            file_name=path.name,
            status="queued",
            uploaded_by=uploaded_by,
        )
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "job_id": job_id,
                "upload_id": upload_id,
                "provider": provider,
                "kind": kind,
                "file_name": path.name,
                "status": "queued",
                "progress": 0,
                "message": "Queued…",
                "error": "",
                "remote_file_id": "",
                "web_view_link": "",
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
            }

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=self._run_job,
            args=(app, job_id, upload_id, provider, kind, path, uploaded_by),
            daemon=True,
            name=f"gdrive-upload-{job_id[:8]}",
        )
        thread.start()
        return {"ok": True, "job_id": job_id, "provider": provider, "file_name": path.name}

    def job_status(self, job_id: str) -> dict[str, Any]:
        job = _job_snapshot(job_id)
        if not job:
            return {"ok": False, "error": "Upload job not found."}
        return {"ok": True, **job}

    def _run_job(
        self,
        app,
        job_id: str,
        upload_id: int,
        provider: str,
        kind: str,
        path: Path,
        uploaded_by: str,
    ) -> None:
        with app.app_context():
            try:
                _job_update(job_id, status="uploading", progress=0, message="Uploading…")
                self._update_row(upload_id, status="uploading", progress=0, error="")
                result = self._upload_google_drive(
                    path,
                    progress_cb=lambda done, total: self._on_progress(job_id, upload_id, done, total),
                )
                _job_update(
                    job_id,
                    status="success",
                    progress=100,
                    message="Upload successful ✅",
                    remote_file_id=result.get("id") or "",
                    web_view_link=result.get("webViewLink") or "",
                    error="",
                )
                self._update_row(
                    upload_id,
                    status="success",
                    progress=100,
                    remote_file_id=result.get("id") or "",
                    error="",
                    uploaded_at=datetime.utcnow(),
                )
            except Exception as exc:
                # Never log secrets; exception messages are sanitized in Drive client.
                logger.exception("Cloud backup upload failed for %s", path.name)
                message = str(exc) or "Upload failed."
                _job_update(
                    job_id,
                    status="failed",
                    message="Upload failed ❌",
                    error=message[:900],
                )
                self._update_row(
                    upload_id,
                    status="failed",
                    error=message[:900],
                )

    def _on_progress(self, job_id: str, upload_id: int, done: int, total: int) -> None:
        pct = int(min(99, max(0, (done * 100) // max(total, 1))))
        _job_update(job_id, status="uploading", progress=pct, message=f"Uploading… {pct}%")
        try:
            self._update_row(upload_id, status="uploading", progress=pct)
        except Exception:
            db.session.rollback()

    def _upload_google_drive(
        self,
        path: Path,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        oauth = GoogleDriveOAuthService()
        settings = IntegrationSettingsService()
        cfg = settings.get_provider_config_decrypted(GDRIVE_PROVIDER)
        client_id, client_secret = oauth.resolve_oauth_client()
        refresh_token = (cfg.get("refresh_token") or "").strip()
        if not refresh_token:
            raise GoogleDriveError("Google Drive is not connected.")

        token_payload = GoogleDriveClient.refresh_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
        access_token = (token_payload.get("access_token") or "").strip()
        if not access_token:
            raise GoogleDriveError("Could not refresh Google Drive access token.")

        # Persist short-lived access token encrypted; never return it to callers.
        try:
            oauth._upsert_secret("access_token", access_token)
            expires_in = int(token_payload.get("expires_in") or 3600)
            from datetime import timedelta

            oauth._upsert_plain(
                "token_expires_at",
                (datetime.utcnow() + timedelta(seconds=max(expires_in - 60, 60))).isoformat(
                    timespec="seconds"
                ),
            )
            oauth._upsert_plain("connection_status", STATUS_CONNECTED)
        except Exception:
            logger.exception("Failed to persist refreshed Google Drive access token")

        client = GoogleDriveClient(access_token=access_token)
        folder_id = client.ensure_folder(
            (cfg.get("folder_name") or FOLDER_NAME).strip() or FOLDER_NAME,
            existing_id=(cfg.get("folder_id") or "").strip(),
        )
        try:
            oauth._upsert_plain("folder_id", folder_id)
            oauth._upsert_plain("folder_name", FOLDER_NAME)
        except Exception:
            logger.exception("Failed to persist Google Drive folder id")

        return client.resumable_upload(path, folder_id=folder_id, progress_cb=progress_cb)

    def _insert_row(
        self,
        *,
        provider: str,
        kind: str,
        file_name: str,
        status: str,
        uploaded_by: str,
    ) -> int:
        self.ensure_schema()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.BackupCloudUpload (
                    Provider, BackupKind, FileName, UploadStatus, ProgressPercent,
                    UploadedBy, CreatedAt, UpdatedAt
                )
                OUTPUT INSERTED.UploadID
                VALUES (
                    :provider, :kind, :file_name, :status, 0,
                    :uploaded_by, SYSUTCDATETIME(), SYSUTCDATETIME()
                )
                """
            ),
            {
                "provider": provider,
                "kind": kind,
                "file_name": file_name,
                "status": status,
                "uploaded_by": (uploaded_by or "System")[:120],
            },
        ).scalar()
        db.session.commit()
        return int(row)

    def _update_row(
        self,
        upload_id: int,
        *,
        status: str | None = None,
        progress: int | None = None,
        remote_file_id: str | None = None,
        error: str | None = None,
        uploaded_at: datetime | None = None,
    ) -> None:
        sets = ["UpdatedAt = SYSUTCDATETIME()"]
        params: dict[str, Any] = {"id": int(upload_id)}
        if status is not None:
            sets.append("UploadStatus = :status")
            params["status"] = status
        if progress is not None:
            sets.append("ProgressPercent = :progress")
            params["progress"] = int(progress)
        if remote_file_id is not None:
            sets.append("RemoteFileId = :remote_file_id")
            params["remote_file_id"] = remote_file_id[:200]
        if error is not None:
            sets.append("ErrorMessage = :error")
            params["error"] = (error or "")[:1000] or None
        if uploaded_at is not None:
            sets.append("UploadedAt = :uploaded_at")
            params["uploaded_at"] = uploaded_at
        db.session.execute(
            text(f"UPDATE dbo.BackupCloudUpload SET {', '.join(sets)} WHERE UploadID = :id"),
            params,
        )
        db.session.commit()

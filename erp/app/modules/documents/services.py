"""CRM document upload, versioning, and soft delete."""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import text
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config import Config
from app.extensions import db
from app.modules.notification.services import NotificationService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService


class DocumentService:
    FOLDERS = (
        "PAN",
        "Aadhaar",
        "GST",
        "TDS",
        "ITR",
        "Bank",
        "Salary",
        "Notice",
        "Appeal",
        "Others",
    )
    ALLOWED_EXTENSIONS = frozenset(
        {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx", "xls", "xlsx"}
    )

    def __init__(
        self,
        *,
        timeline: TimelineService | None = None,
        notifications: NotificationService | None = None,
    ):
        self.timeline = timeline or TimelineService()
        self.notifications = notifications or NotificationService()

    @classmethod
    def _allowed_file(cls, filename: str) -> bool:
        ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
        return ext in cls.ALLOWED_EXTENSIONS

    @classmethod
    def _customer_dir(cls, customer_id: int) -> Path:
        base = Config.UPLOAD_FOLDER / "crm_documents" / str(customer_id)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def upload(
        self,
        *,
        customer_id: int,
        folder_type: str,
        title: str,
        file: FileStorage,
        remarks: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        folder = (folder_type or "Others").strip()
        if folder not in self.FOLDERS:
            raise ValueError(f"Folder type must be one of: {', '.join(self.FOLDERS)}")

        if not file or not file.filename:
            raise ValueError("File is required.")

        safe_name = secure_filename(file.filename)
        if not safe_name or not self._allowed_file(safe_name):
            raise ValueError(
                f"Allowed extensions: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

        max_size = current_app.config.get("MAX_CONTENT_LENGTH", Config.MAX_CONTENT_LENGTH)
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > max_size:
            raise ValueError("File exceeds maximum upload size.")

        ext = safe_name.rsplit(".", 1)[-1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        dest_dir = self._customer_dir(customer_id)
        stored_path = dest_dir / stored_name
        file.save(stored_path)

        rel_path = str(stored_path.relative_to(Config.UPLOAD_FOLDER)).replace("\\", "/")
        mime = file.mimetype or mimetypes.guess_type(safe_name)[0]
        now = datetime.utcnow()

        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmDocument
                    (CustomerID, FolderType, Title, FileName, StoredPath, MimeType, FileSizeBytes,
                     CurrentVersion, Remarks, UploadedByUserID, UploadedByName, CreatedDate)
                OUTPUT INSERTED.DocumentID
                VALUES
                    (:customer_id, :folder, :title, :filename, :path, :mime, :size,
                     1, :remarks, :user_id, :user_name, :now)
                """
            ),
            {
                "customer_id": customer_id,
                "folder": folder[:50],
                "title": (title or safe_name)[:255],
                "filename": safe_name[:255],
                "path": rel_path[:500],
                "mime": (mime or "")[:100] or None,
                "size": size,
                "remarks": (remarks or "")[:500] or None,
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
                "now": now,
            },
        ).first()
        document_id = int(row[0])

        db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmDocumentVersion
                    (DocumentID, VersionNumber, FileName, StoredPath, MimeType, FileSizeBytes,
                     UploadedByUserID, UploadedByName)
                VALUES
                    (:doc_id, 1, :filename, :path, :mime, :size, :user_id, :user_name)
                """
            ),
            {
                "doc_id": document_id,
                "filename": safe_name[:255],
                "path": rel_path[:500],
                "mime": (mime or "")[:100] or None,
                "size": size,
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
            },
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="DocumentUploaded",
            title=f"Document uploaded: {title or safe_name}",
            description=folder,
            customer_id=customer_id,
            entity_type="CrmDocument",
            entity_id=document_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.notifications.notify_roles_or_all(
            notification_type="Document",
            title=f"Document uploaded for customer #{customer_id}",
            message=title or safe_name,
            link_url=f"/crm/documents?customer_id={customer_id}",
            customer_id=customer_id,
            entity_type="CrmDocument",
            entity_id=document_id,
        )

        return self.get_document(document_id) or {}

    def list_documents(
        self,
        *,
        customer_id: int,
        folder_type: str | None = None,
    ) -> list[dict]:
        ensure_crm_schema()
        clauses = ["CustomerID = :cid", "IsActive = 1"]
        params: dict = {"cid": customer_id}
        if folder_type:
            clauses.append("FolderType = :folder")
            params["folder"] = folder_type
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT DocumentID, CustomerID, FolderType, Title, FileName, StoredPath,
                       MimeType, FileSizeBytes, CurrentVersion, Remarks,
                       UploadedByUserID, UploadedByName, CreatedDate, ModifiedDate
                FROM dbo.CrmDocument
                WHERE {where}
                ORDER BY FolderType, CreatedDate DESC
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_document(self, document_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT DocumentID, CustomerID, FolderType, Title, FileName, StoredPath,
                       MimeType, FileSizeBytes, CurrentVersion, Remarks,
                       UploadedByUserID, UploadedByName, CreatedDate, ModifiedDate
                FROM dbo.CrmDocument
                WHERE DocumentID = :id AND IsActive = 1
                """
            ),
            {"id": document_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_versions(self, document_id: int) -> list[dict]:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT VersionID, DocumentID, VersionNumber, FileName, StoredPath,
                       MimeType, FileSizeBytes, UploadedByUserID, UploadedByName, CreatedDate
                FROM dbo.CrmDocumentVersion
                WHERE DocumentID = :id
                ORDER BY VersionNumber DESC
                """
            ),
            {"id": document_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def soft_delete(
        self,
        document_id: int,
        *,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> None:
        ensure_crm_schema()
        doc = self.get_document(document_id)
        if not doc:
            raise ValueError("Document not found.")

        db.session.execute(
            text(
                """
                UPDATE dbo.CrmDocument
                SET IsActive = 0, ModifiedDate = :now
                WHERE DocumentID = :id
                """
            ),
            {"id": document_id, "now": datetime.utcnow()},
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="DocumentDeleted",
            title=f"Document removed: {doc.get('Title')}",
            customer_id=doc.get("CustomerID"),
            entity_type="CrmDocument",
            entity_id=document_id,
            user_id=user_id,
            user_name=user_name,
        )

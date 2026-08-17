"""Secure resume upload handling. Physical paths are never exposed to clients."""

from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

from werkzeug.datastructures import FileStorage

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
ALLOWED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-pdf",
}
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".js", ".jar",
    ".php", ".phtml", ".asp", ".aspx", ".jsp", ".html", ".htm", ".svg",
    ".sh", ".py", ".rb", ".dll", ".vbs", ".wsf",
}
PDF_MAGIC = b"%PDF"
DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"


class UploadError(ValueError):
    pass


def _ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def validate_resume(file: FileStorage, max_mb: int = 5) -> bytes:
    if not file or not file.filename:
        raise UploadError("Please upload your resume.")
    original = file.filename
    ext = _ext(original)
    if ext in BLOCKED_EXTENSIONS:
        raise UploadError("This file type is not allowed.")
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError("Resume must be a PDF, DOC or DOCX file.")

    payload = file.read()
    file.stream.seek(0)
    if not payload:
        raise UploadError("The uploaded file is empty.")
    if len(payload) > max_mb * 1024 * 1024:
        raise UploadError(f"Resume must be {max_mb} MB or smaller.")

    mime = (file.mimetype or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_MIMES and mime != "application/octet-stream":
        raise UploadError("Resume MIME type is not allowed.")

    if ext == ".pdf":
        if not payload.startswith(PDF_MAGIC):
            raise UploadError("The file does not look like a valid PDF.")
    elif ext == ".doc":
        if not payload.startswith(DOC_MAGIC):
            raise UploadError("The file does not look like a valid DOC document.")
    elif ext == ".docx":
        if not payload.startswith(ZIP_MAGIC):
            raise UploadError("The file does not look like a valid DOCX document.")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile as exc:
            raise UploadError("The DOCX file could not be read.") from exc
        if not any(name.startswith("word/") for name in names):
            raise UploadError("The file is not a valid Word document.")
        if any(name.lower().endswith(tuple(BLOCKED_EXTENSIONS)) for name in names):
            raise UploadError("The document contains disallowed content.")
    return payload


def store_resume(payload: bytes, original_name: str, upload_dir: Path) -> dict:
    ext = _ext(original_name)
    reference = uuid.uuid4().hex
    stored_name = f"{reference}{ext}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / stored_name
    dest.write_bytes(payload)
    try:
        dest.chmod(0o640)
    except OSError:
        pass
    return {
        "resume_original_name": Path(original_name).name[:255],
        "resume_stored_name": stored_name,
        "resume_file_reference": reference,
        "resume_file_type": {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(ext, "application/octet-stream"),
        "resume_file_size": len(payload),
    }


def resolve_resume_path(upload_dir: Path, stored_name: str) -> Path | None:
    if not stored_name or "/" in stored_name or "\\" in stored_name or ".." in stored_name:
        return None
    path = (upload_dir / stored_name).resolve()
    try:
        path.relative_to(upload_dir.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None

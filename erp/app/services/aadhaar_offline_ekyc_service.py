"""Aadhaar Offline eKYC — watch Downloads ZIP, extract, parse XML (Customer Master only)."""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

OFFLINE_EKYC_URL = "https://myaadhaar.uidai.gov.in/offline-ekyc"

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

_ZIP_NAME_HINTS = ("offlineaadhaar", "offline-aadhaar", "aadhaar", "ekyc", "uidai")


def _downloads_dir() -> Path:
    home = Path.home()
    candidates = [
        home / "Downloads",
        home / "Download",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
        Path(os.environ.get("HOME", "")) / "Downloads",
    ]
    for path in candidates:
        if path and path.is_dir():
            return path
    return home


def _photo_dir() -> Path:
    root = Path(__file__).resolve().parents[2]  # erp/
    dest = root / "app" / "static" / "uploads" / "customer_photos"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _is_aadhaar_zip(name: str) -> bool:
    lower = (name or "").lower()
    if not lower.endswith(".zip"):
        return False
    if lower.endswith(".crdownload") or lower.endswith(".tmp") or lower.endswith(".part"):
        return False
    return any(h in lower for h in _ZIP_NAME_HINTS)


def _snapshot_zips(folder: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if not _is_aadhaar_zip(entry.name):
                continue
            try:
                out[str(entry.resolve())] = entry.stat().st_mtime
            except OSError:
                continue
    except OSError:
        pass
    return out


def _local(tag: str) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr(el: ET.Element | None, *names: str) -> str:
    if el is None:
        return ""
    for name in names:
        for key, val in el.attrib.items():
            if _local(key).lower() == name.lower() and val:
                return str(val).strip()
    return ""


def _find_child(parent: ET.Element | None, *names: str) -> ET.Element | None:
    if parent is None:
        return None
    wanted = {n.lower() for n in names}
    for child in list(parent):
        if _local(child.tag).lower() in wanted:
            return child
    for child in parent.iter():
        if _local(child.tag).lower() in wanted:
            return child
    return None


def _normalize_gender(raw: str) -> str:
    token = (raw or "").strip().upper()
    if token in {"M", "MALE"}:
        return "Male"
    if token in {"F", "FEMALE"}:
        return "Female"
    if token in {"T", "O", "OTHER", "TRANSGENDER"}:
        return "Other"
    return ""


def _normalize_dob(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _join_parts(*parts: str) -> str:
    return ", ".join(p for p in (x.strip() for x in parts if x and str(x).strip()) if p)


def _parse_offline_xml(xml_bytes: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("Corrupt or unsupported Aadhaar XML.") from exc

    reference_id = _attr(root, "referenceId", "referenceid") or ""
    uid = _find_child(root, "UidData", "uiddata")
    poi = _find_child(uid or root, "Poi", "poi")
    poa = _find_child(uid or root, "Poa", "poa")
    pht = _find_child(uid or root, "Pht", "pht")

    if poi is None and poa is None:
        raise ValueError("Missing mandatory tags in Aadhaar XML (Poi/Poa).")

    name = _attr(poi, "name")
    dob = _normalize_dob(_attr(poi, "dob", "dateOfBirth"))
    gender = _normalize_gender(_attr(poi, "gender"))

    care_of = _attr(poa, "careof", "co", "careOf")
    house = _attr(poa, "house")
    street = _attr(poa, "street")
    landmark = _attr(poa, "lm", "landmark")
    locality = _attr(poa, "loc", "locality")
    vtc = _attr(poa, "vtc", "village", "villageTownCity")
    subdist = _attr(poa, "subdist", "subDistrict", "city")
    district = _attr(poa, "dist", "district")
    state = _attr(poa, "state")
    country = _attr(poa, "country") or "India"
    pincode = re.sub(r"\D", "", _attr(poa, "pc", "pincode", "pin"))[:6]

    photo_b64 = ""
    if pht is not None and (pht.text or "").strip():
        photo_b64 = re.sub(r"\s+", "", pht.text.strip())

    if not name and not district and not pincode:
        raise ValueError("Aadhaar XML has no usable demographic fields.")

    return {
        "reference_id": reference_id,
        "customer_name": name,
        "date_of_birth": dob,
        "gender": gender,
        "father_husband_name": care_of,
        "address_line1": _join_parts(house, street)[:300],
        "address_line2": _join_parts(landmark, locality)[:300],
        "village": vtc or "",
        "area": locality or "",
        "city": subdist or vtc or "",
        "district": district,
        "state": state,
        "country": country or "India",
        "pincode": pincode,
        "photo_base64": photo_b64,
    }


def _extract_xml_from_zip(zip_path: Path, password: str) -> bytes:
    pwd = (password or "").encode("utf-8")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise ValueError("ZIP does not contain an Aadhaar XML file.")
            # Prefer offlineaadhaar xml
            names.sort(key=lambda n: (0 if "offline" in n.lower() else 1, len(n)))
            target = names[0]
            try:
                return zf.read(target, pwd=pwd if password else None)
            except RuntimeError as exc:
                # Wrong password / encrypted
                msg = str(exc).lower()
                if "password" in msg or "encrypted" in msg or "bad password" in msg:
                    raise ValueError("Wrong ZIP password (Share Code).") from exc
                raise ValueError("Unable to extract ZIP. Check password and try again.") from exc
            except zipfile.BadZipFile as exc:
                raise ValueError("Invalid ZIP file.") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid ZIP file.") from exc


def _save_photo(photo_b64: str) -> str | None:
    if not photo_b64:
        return None
    raw = photo_b64
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Aadhaar photo decode failed: %s", exc)
        return None
    if not data or len(data) < 50:
        return None
    name = f"aadhaar_{uuid.uuid4().hex}.jpg"
    path = _photo_dir() / name
    path.write_bytes(data)
    # URL path relative to static
    return f"uploads/customer_photos/{name}"


def _set_job(job_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id) or {"job_id": job_id}
        job.update(fields)
        job["updated_at"] = time.time()
        _JOBS[job_id] = job
        return dict(job)


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _watch_loop(job_id: str, baseline: dict[str, float], folder: Path, started_at: float) -> None:
    deadline = time.time() + 15 * 60  # 15 minutes
    try:
        while time.time() < deadline:
            job = _get_job(job_id)
            if not job or job.get("status") in {"cancelled", "done", "error", "need_password"}:
                if job and job.get("status") == "need_password":
                    return
                if job and job.get("status") in {"done", "error", "cancelled"}:
                    return
            current = _snapshot_zips(folder)
            for path, mtime in current.items():
                if path in baseline and mtime <= baseline[path] + 0.01:
                    continue
                if mtime < started_at - 2:
                    continue
                # Prefer newest file still growing? wait until size stable
                p = Path(path)
                try:
                    size1 = p.stat().st_size
                    time.sleep(0.6)
                    size2 = p.stat().st_size
                    if size1 != size2 or size2 < 100:
                        continue
                except OSError:
                    continue
                _set_job(
                    job_id,
                    status="need_password",
                    message="Aadhaar ZIP download detected. Enter ZIP password (Share Code).",
                    zip_path=path,
                    zip_name=p.name,
                )
                return
            time.sleep(1.0)
        _set_job(
            job_id,
            status="error",
            message="Timed out waiting for Aadhaar ZIP download. Complete Download on UIDAI portal and try again.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Aadhaar ZIP watch failed")
        _set_job(job_id, status="error", message=f"Download watch failed: {exc}")


class AadhaarOfflineEkycService:
    """Customer Master — Import Aadhaar Portal offline eKYC."""

    @staticmethod
    def portal_url() -> str:
        return OFFLINE_EKYC_URL

    def start_watch(self) -> dict[str, Any]:
        folder = _downloads_dir()
        if not folder.is_dir():
            raise ValueError("Downloads folder not found on this computer.")
        job_id = uuid.uuid4().hex
        started_at = time.time()
        baseline = _snapshot_zips(folder)
        _set_job(
            job_id,
            status="watching",
            message="Waiting for Offline Aadhaar ZIP download… Complete captcha/OTP on UIDAI, then Download.",
            downloads_dir=str(folder),
            zip_path=None,
            data=None,
        )
        thread = threading.Thread(
            target=_watch_loop,
            args=(job_id, baseline, folder, started_at),
            daemon=True,
            name=f"aadhaar-ekyc-{job_id[:8]}",
        )
        thread.start()
        return {
            "ok": True,
            "job_id": job_id,
            "portal_url": OFFLINE_EKYC_URL,
            "downloads_dir": str(folder),
            "message": "Portal ready. Waiting for ZIP download.",
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = _get_job(job_id)
        if not job:
            return None
        # Never expose full zip path to UI beyond file name
        safe = {
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "message": job.get("message"),
            "zip_name": job.get("zip_name"),
            "data": job.get("data"),
            "photo_url": job.get("photo_url"),
        }
        return safe

    def unlock_and_parse(self, job_id: str, password: str) -> dict[str, Any]:
        job = _get_job(job_id)
        if not job:
            raise ValueError("Aadhaar import job not found. Start Import Aadhaar again.")
        if job.get("status") not in {"need_password", "error"}:
            # allow retry from need_password; also if watching but zip already set
            if not job.get("zip_path"):
                raise ValueError("ZIP not detected yet. Finish Download on the UIDAI portal first.")
        zip_path = job.get("zip_path")
        if not zip_path or not Path(zip_path).is_file():
            raise ValueError("Downloaded ZIP not found. Download again from UIDAI portal.")

        pwd = (password or "").strip()
        if not pwd:
            raise ValueError("ZIP password (Share Code) is required.")

        _set_job(job_id, status="processing", message="Extracting and reading Aadhaar XML…")
        tmp_dir = Path(tempfile.mkdtemp(prefix="aadhaar_ekyc_"))
        try:
            xml_bytes = _extract_xml_from_zip(Path(zip_path), pwd)
            parsed = _parse_offline_xml(xml_bytes)
            photo_rel = _save_photo(parsed.pop("photo_base64", "") or "")
            # Do not keep full Aadhaar; reference_id only (last4+timestamp).
            form_data = {
                "customer_name": parsed.get("customer_name") or "",
                "date_of_birth": parsed.get("date_of_birth") or "",
                "gender": parsed.get("gender") or "",
                "father_husband_name": parsed.get("father_husband_name") or "",
                "address_line1": parsed.get("address_line1") or "",
                "address_line2": parsed.get("address_line2") or "",
                "village": parsed.get("village") or "",
                "area": parsed.get("area") or "",
                "city": parsed.get("city") or "",
                "district": parsed.get("district") or "",
                "state": parsed.get("state") or "",
                "country": parsed.get("country") or "India",
                "pincode": parsed.get("pincode") or "",
                "aadhaar_reference_id": parsed.get("reference_id") or "",
                "photo_path": photo_rel or "",
            }
            # Drop empties for overwrite-only mapping
            form_data = {k: v for k, v in form_data.items() if v not in (None, "")}

            photo_url = None
            if photo_rel:
                photo_url = "/static/" + photo_rel.replace("\\", "/")

            _set_job(
                job_id,
                status="done",
                message="Aadhaar Offline eKYC data ready. Review fields, then Save Customer.",
                data=form_data,
                photo_url=photo_url,
            )
            return {
                "ok": True,
                "job_id": job_id,
                "status": "done",
                "message": "Aadhaar data parsed successfully.",
                "data": form_data,
                "photo_url": photo_url,
            }
        except ValueError:
            _set_job(
                job_id,
                status="need_password",
                message="Could not open ZIP. Check Share Code and try again.",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Aadhaar unlock/parse failed")
            _set_job(job_id, status="error", message="Unable to process Aadhaar ZIP.")
            raise ValueError("Unable to process Aadhaar ZIP.") from exc
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def cancel(self, job_id: str) -> None:
        _set_job(job_id, status="cancelled", message="Cancelled.")

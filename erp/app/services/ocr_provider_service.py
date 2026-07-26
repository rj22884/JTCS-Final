"""
OCR provider detection, startup probe, and installation helpers.

Priority: EasyOCR → PaddleOCR → Tesseract
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TESSERACT_CANDIDATE_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

EASYOCR_STACK = (
    "easyocr",
    "torch",
    "torchvision",
    "opencv-python-headless",
    "Pillow",
    "numpy",
)

INSTALL_GUIDE = [
    "Open PowerShell in the ERP folder (erp).",
    "Activate virtual environment: .\\.venv\\Scripts\\Activate.ps1",
    "Run: python scripts/install_ocr.py",
    "Or click Install OCR Engine on Stamp Activity page (Administrator).",
    "Restart the ERP server after installation completes.",
]


@dataclass
class ProviderProbe:
    name: str
    available: bool
    reason: str = ""
    detail: str = ""


@dataclass
class OcrStartupStatus:
    ready: bool = False
    active_provider: str | None = None
    providers: list[ProviderProbe] = field(default_factory=list)
    tesseract_path: str | None = None
    install_guide: list[str] = field(default_factory=lambda: list(INSTALL_GUIDE))

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "active_provider": self.active_provider,
            "providers": [
                {
                    "name": p.name,
                    "available": p.available,
                    "reason": p.reason,
                    "detail": p.detail,
                }
                for p in self.providers
            ],
            "tesseract_path": self.tesseract_path,
            "install_guide": self.install_guide,
            "message": (
                f"OCR ready — {self.active_provider}"
                if self.ready
                else "OCR Engine Not Installed. Administrator Contact Required."
            ),
        }


_STATUS: OcrStartupStatus | None = None


def _importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def configure_tesseract() -> str | None:
    """Configure pytesseract executable from standard Windows path or PATH."""
    if not _importable("pytesseract"):
        return None

    import pytesseract

    for path in TESSERACT_CANDIDATE_PATHS:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return path

    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return found
    return None


def probe_easyocr() -> ProviderProbe:
    modules = {"easyocr": "easyocr", "torch": "torch", "Pillow": "PIL", "numpy": "numpy"}
    missing = [label for label, mod in modules.items() if not _importable(mod)]
    if missing:
        return ProviderProbe(
            name="EasyOCR",
            available=False,
            reason="Python packages missing",
            detail=", ".join(missing),
        )
    try:
        import easyocr  # noqa: F401

        return ProviderProbe(name="EasyOCR", available=True, reason="Packages installed")
    except Exception as exc:
        return ProviderProbe(name="EasyOCR", available=False, reason="Import failed", detail=str(exc))


def probe_paddleocr() -> ProviderProbe:
    if not _importable("paddleocr"):
        return ProviderProbe(name="PaddleOCR", available=False, reason="paddleocr not installed")
    try:
        import paddleocr  # noqa: F401

        return ProviderProbe(name="PaddleOCR", available=True, reason="Package installed")
    except Exception as exc:
        return ProviderProbe(name="PaddleOCR", available=False, reason="Import failed", detail=str(exc))


def probe_tesseract() -> ProviderProbe:
    if not _importable("pytesseract"):
        return ProviderProbe(name="Tesseract", available=False, reason="pytesseract not installed")

    tess_path = configure_tesseract()
    if not tess_path:
        return ProviderProbe(
            name="Tesseract",
            available=False,
            reason="tesseract.exe not found",
            detail="Install Tesseract or add to PATH (C:\\Program Files\\Tesseract-OCR\\tesseract.exe)",
        )
    try:
        import pytesseract

        version = pytesseract.get_tesseract_version()
        return ProviderProbe(
            name="Tesseract",
            available=True,
            reason=f"Found at {tess_path}",
            detail=f"version {version}",
        )
    except Exception as exc:
        return ProviderProbe(name="Tesseract", available=False, reason="Execution failed", detail=str(exc))


class OcrProviderService:
    @classmethod
    def initialize(cls, *, force: bool = False) -> OcrStartupStatus:
        global _STATUS
        if _STATUS is not None and not force:
            return _STATUS

        providers = [probe_easyocr(), probe_paddleocr(), probe_tesseract()]
        tess_path = configure_tesseract()
        active: str | None = None

        try:
            from app.services.ocr_engine import get_ocr_engine

            name, _ = get_ocr_engine(force_refresh=True)
            active = name
            logger.info("OCR startup probe: active provider = %s", active)
        except Exception as exc:
            logger.warning("OCR startup probe: provider init failed — %s", exc)
            active = None

        _STATUS = OcrStartupStatus(
            ready=bool(active),
            active_provider=active,
            providers=providers,
            tesseract_path=tess_path,
        )

        if _STATUS.ready:
            logger.info("===== OCR STARTUP: READY (%s) =====", _STATUS.active_provider)
        else:
            logger.warning("===== OCR STARTUP: NOT INSTALLED =====")
            for probe in providers:
                logger.warning("  %s — %s (%s)", probe.name, probe.reason, probe.detail)

        return _STATUS

    @classmethod
    def get_status(cls) -> OcrStartupStatus:
        if _STATUS is None:
            return cls.initialize()
        return _STATUS

    @classmethod
    def install_easyocr_stack(cls) -> dict:
        """Install EasyOCR and dependencies into the current Python environment."""
        logger.info("OCR install started: %s", EASYOCR_STACK)
        cmd = [sys.executable, "-m", "pip", "install", *EASYOCR_STACK]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Installation timed out after 15 minutes."}

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "pip install failed").strip()
            logger.error("OCR install failed: %s", detail[-2000:])
            return {"ok": False, "error": detail[-500:]}

        cls.initialize(force=True)
        status = cls.get_status()
        logger.info("OCR install completed. Ready=%s Provider=%s", status.ready, status.active_provider)
        return {
            "ok": status.ready,
            "status": status.to_dict(),
            "message": status.to_dict()["message"],
            "output": (completed.stdout or "")[-1000:],
        }

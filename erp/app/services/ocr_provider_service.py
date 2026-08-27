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
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/snap/bin/tesseract",
)

# EasyOCR 1.7 is built for OpenCV 4.x. Unpinned >=4.8 pulls OpenCV 5, which can
# import as a stub namespace without cvtColor.
OPENCV_PIN = "opencv-python-headless>=4.8.0,<4.12.0"

EASYOCR_STACK = (
    "easyocr",
    "torch",
    "torchvision",
    OPENCV_PIN,
    "Pillow",
    "numpy",
)

LINUX_OCR_APT_PACKAGES = (
    "libgl1",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender1",
    "libgomp1",
    "tesseract-ocr",
    "tesseract-ocr-eng",
)

INSTALL_GUIDE_WINDOWS = [
    "Open PowerShell in the ERP folder (erp).",
    "Activate virtual environment: .\\.venv\\Scripts\\Activate.ps1",
    "Run: python scripts/install_ocr.py",
    "Or click Install OCR Engine on Stamp Activity page (Administrator).",
    "Restart the ERP server after installation completes.",
]

INSTALL_GUIDE_LINUX = [
    "On the VPS run: sudo bash deployment/fix_vps_ocr.sh",
    "Or: sudo apt-get update && sudo apt-get install -y libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-eng",
    "Then in the ERP venv: pip uninstall -y opencv-python opencv-contrib-python && pip install \"" + OPENCV_PIN + "\"",
    "Or click Install OCR Engine on Stamp Activity (Administrator).",
    "Restart the ERP service after installation completes.",
]


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def install_guide() -> list[str]:
    return list(INSTALL_GUIDE_LINUX if _is_linux() else INSTALL_GUIDE_WINDOWS)


INSTALL_GUIDE = INSTALL_GUIDE_WINDOWS


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
    install_guide: list[str] = field(default_factory=install_guide)

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
            "install_guide": self.install_guide or install_guide(),
            "message": (
                f"OCR ready — {self.active_provider}"
                if self.ready
                else "OCR Engine Not Installed. Administrator Contact Required."
            ),
        }


_STATUS: OcrStartupStatus | None = None
_OPENCV_HEADLESS_ATTEMPTED = False


def _importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _libgl_missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "libgl.so" in text or "libopengl.so" in text


def _purge_cv2_modules() -> None:
    for name in list(sys.modules):
        if name == "cv2" or name.startswith("cv2."):
            sys.modules.pop(name, None)


def force_opencv_headless() -> tuple[bool, str]:
    """Drop GUI OpenCV (needs libGL) and install the headless wheel."""
    uninstall = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "opencv-python", "opencv-contrib-python"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            OPENCV_PIN,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    _purge_cv2_modules()
    detail = ((install.stdout or "") + "\n" + (install.stderr or uninstall.stderr or "")).strip()
    return install.returncode == 0, detail[-800:]


def _hydrate_cv2(mod) -> None:
    """Copy native OpenCV symbols onto the cv2 package if the loader left them off."""
    if callable(getattr(mod, "cvtColor", None)):
        return
    native = getattr(mod, "cv2", None)
    if native is None or native is mod:
        try:
            native = importlib.import_module("cv2.cv2")
        except Exception:  # noqa: BLE001
            native = None
    if native is None:
        return
    for key in dir(native):
        if key.startswith("_") or hasattr(mod, key):
            continue
        try:
            setattr(mod, key, getattr(native, key))
        except Exception:  # noqa: BLE001
            continue


def rebind_easyocr_cv2() -> None:
    """Point EasyOCR's cached `cv2` imports at a hydrated OpenCV module."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return
    _hydrate_cv2(cv2)
    for name in (
        "easyocr.utils",
        "easyocr.imgproc",
        "easyocr.detection",
        "easyocr.recognition",
        "easyocr.craft_utils",
    ):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "cv2", None) is not None:
            try:
                mod.cv2 = cv2
            except Exception:  # noqa: BLE001
                continue


def _try_import_cv2() -> Exception | None:
    try:
        import numpy as np
        import cv2

        _hydrate_cv2(cv2)
        if not callable(getattr(cv2, "cvtColor", None)):
            return AttributeError("module 'cv2' has no attribute 'cvtColor'")
        sample = np.zeros((4, 4, 3), dtype=np.uint8)
        cv2.cvtColor(sample, getattr(cv2, "COLOR_RGB2BGR", 4))
        return None
    except Exception as exc:  # noqa: BLE001
        return exc


def _needs_opencv_repair(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    text = str(exc).lower()
    return _libgl_missing(exc) or "cvtcolor" in text or "libgl" in text


def prepare_opencv_for_ocr(*, allow_install: bool = False) -> None:
    """Make OpenCV importable and ensure cvtColor exists (EasyOCR requirement)."""
    global _OPENCV_HEADLESS_ATTEMPTED
    err = _try_import_cv2()
    if err is None:
        rebind_easyocr_cv2()
        return
    logger.warning("OpenCV is not ready for OCR (%s)", err)
    if not allow_install or _OPENCV_HEADLESS_ATTEMPTED or not _needs_opencv_repair(err):
        return
    _OPENCV_HEADLESS_ATTEMPTED = True
    logger.warning("Switching to pinned opencv-python-headless")
    ok, detail = force_opencv_headless()
    if ok:
        err2 = _try_import_cv2()
        if err2 is None:
            rebind_easyocr_cv2()
            logger.info("OpenCV headless import succeeded")
            return
        logger.warning("OpenCV still failing after headless swap: %s", err2)
    else:
        logger.warning("opencv-python-headless install failed: %s", detail)


def _run_apt(cmd: list[str]) -> subprocess.CompletedProcess | None:
    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        return subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def install_linux_ocr_system_packages() -> tuple[bool, str]:
    if not _is_linux():
        return True, ""
    packages = list(LINUX_OCR_APT_PACKAGES)
    update_cmds = (["apt-get", "update"], ["sudo", "apt-get", "update"])
    updated = False
    for cmd in update_cmds:
        result = _run_apt(cmd)
        if result is not None and result.returncode == 0:
            updated = True
            break
    notes: list[str] = []
    if not updated:
        notes.append("apt-get update did not run (need root/sudo).")
    install_cmds = (
        ["apt-get", "install", "-y", *packages],
        ["sudo", "apt-get", "install", "-y", *packages],
        ["apt-get", "install", "-y", "libgl1-mesa-glx", "libglib2.0-0", "tesseract-ocr", "tesseract-ocr-eng"],
        ["sudo", "apt-get", "install", "-y", "libgl1-mesa-glx", "libglib2.0-0", "tesseract-ocr", "tesseract-ocr-eng"],
    )
    for cmd in install_cmds:
        result = _run_apt(cmd)
        if result is None:
            continue
        if result.returncode == 0:
            return True, "Installed Linux OCR system libraries."
        notes.append((result.stderr or result.stdout or "apt install failed").strip()[-400:])
    return False, " ".join(notes)[-800:]


def configure_tesseract() -> str | None:
    """Configure pytesseract from Windows, Linux, env, or PATH."""
    if not _importable("pytesseract"):
        return None

    import pytesseract

    env_path = (os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH") or "").strip()
    candidates = ((env_path,) if env_path else ()) + TESSERACT_CANDIDATE_PATHS
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        if _is_linux() and not os.access(path, os.X_OK):
            continue
        pytesseract.pytesseract.tesseract_cmd = path
        return path

    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return found
    return None


def probe_easyocr() -> ProviderProbe:
    prepare_opencv_for_ocr()
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

        rebind_easyocr_cv2()
        cv2_err = _try_import_cv2()
        if cv2_err is not None:
            return ProviderProbe(
                name="EasyOCR",
                available=False,
                reason="OpenCV cvtColor unavailable",
                detail=str(cv2_err),
            )
        return ProviderProbe(name="EasyOCR", available=True, reason="Packages installed")
    except Exception as exc:
        hint = ""
        if _libgl_missing(exc):
            hint = (
                " Missing libGL.so.1 — install libgl1 or use opencv-python-headless "
                "(see Linux install guide)."
            )
        return ProviderProbe(name="EasyOCR", available=False, reason="Import failed", detail=str(exc) + hint)


def probe_paddleocr() -> ProviderProbe:
    prepare_opencv_for_ocr()
    if not _importable("paddleocr"):
        return ProviderProbe(name="PaddleOCR", available=False, reason="paddleocr not installed")
    try:
        import paddleocr  # noqa: F401

        return ProviderProbe(name="PaddleOCR", available=True, reason="Package installed")
    except Exception as exc:
        hint = ""
        if _libgl_missing(exc):
            hint = " Missing libGL.so.1 — install libgl1 or use opencv-python-headless."
        return ProviderProbe(name="PaddleOCR", available=False, reason="Import failed", detail=str(exc) + hint)


def probe_tesseract() -> ProviderProbe:
    if not _importable("pytesseract"):
        return ProviderProbe(name="Tesseract", available=False, reason="pytesseract not installed")

    tess_path = configure_tesseract()
    if not tess_path:
        linux_hint = "sudo apt-get install -y tesseract-ocr tesseract-ocr-eng"
        win_hint = r"Install Tesseract or add to PATH (C:\Program Files\Tesseract-OCR\tesseract.exe)"
        return ProviderProbe(
            name="Tesseract",
            available=False,
            reason="Tesseract binary not found",
            detail=linux_hint if _is_linux() else win_hint,
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

        prepare_opencv_for_ocr()
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
            install_guide=install_guide(),
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
        """Install EasyOCR stack and Linux system OCR libraries when possible."""
        notes: list[str] = []
        if _is_linux():
            ok, detail = install_linux_ocr_system_packages()
            notes.append(detail or ("Linux OCR packages installed." if ok else "Linux OCR packages skipped."))
            prepare_opencv_for_ocr(allow_install=True)

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

        headless_ok, headless_detail = force_opencv_headless()
        if not headless_ok:
            notes.append("opencv-python-headless swap failed: " + headless_detail)
        else:
            notes.append("Pinned opencv-python-headless (no libGL).")

        cls.initialize(force=True)
        status = cls.get_status()
        logger.info("OCR install completed. Ready=%s Provider=%s", status.ready, status.active_provider)
        return {
            "ok": status.ready,
            "status": status.to_dict(),
            "message": status.to_dict()["message"],
            "output": ((completed.stdout or "") + "\n" + " ".join(notes))[-1500:],
        }

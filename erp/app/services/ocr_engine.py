"""
OCR engine abstraction for JTCS ERP.

Priority: EasyOCR → PaddleOCR → Tesseract (first available wins).
Reusable across SHCIL, Court Fee, DSC, PAN, Aadhaar, GST modules.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from typing import Callable

from PIL import Image

from app.services.ocr_provider_service import (
    configure_tesseract,
    prepare_opencv_for_ocr,
    rebind_easyocr_cv2,
)

logger = logging.getLogger(__name__)

prepare_opencv_for_ocr()
configure_tesseract()


class OcrEngineNotAvailableError(RuntimeError):
    """Raised when no OCR backend is installed."""


@dataclass
class OcrResult:
    provider: str
    text: str
    confidence: float


class OcrBackend(ABC):
    @abstractmethod
    def extract(self, image: Image.Image) -> OcrResult:
        raise NotImplementedError


class EasyOcrBackend(OcrBackend):
    def __init__(self):
        prepare_opencv_for_ocr()
        import cv2
        import easyocr

        rebind_easyocr_cv2()
        if not callable(getattr(cv2, "cvtColor", None)):
            raise OcrEngineNotAvailableError("OpenCV cvtColor is unavailable for EasyOCR.")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                rebind_easyocr_cv2()
                return
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) == 32 or "being used by another process" in str(exc).lower():
                    import time

                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error

    def extract(self, image: Image.Image) -> OcrResult:
        import numpy as np

        rebind_easyocr_cv2()
        rgb = image.convert("RGB")
        results = self._reader.readtext(np.array(rgb), detail=1, paragraph=False)
        lines: list[str] = []
        scores: list[float] = []
        for item in results:
            if len(item) >= 3:
                lines.append(str(item[1]).strip())
                scores.append(float(item[2]))
        text = "\n".join(line for line in lines if line)
        confidence = (sum(scores) / len(scores) * 100) if scores else 0.0
        return OcrResult(provider="EasyOCR", text=text, confidence=round(confidence, 2))


class PaddleOcrBackend(OcrBackend):
    def __init__(self):
        prepare_opencv_for_ocr()
        from paddleocr import PaddleOCR

        try:
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except TypeError:
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en")

    def extract(self, image: Image.Image) -> OcrResult:
        import numpy as np

        rgb = image.convert("RGB")
        result = self._ocr.ocr(np.array(rgb), cls=True)
        lines: list[str] = []
        scores: list[float] = []
        if result:
            for page in result:
                if not page:
                    continue
                for item in page:
                    if item and len(item) >= 2 and item[1]:
                        lines.append(str(item[1][0]).strip())
                        if len(item[1]) > 1:
                            scores.append(float(item[1][1]))
        text = "\n".join(line for line in lines if line)
        confidence = (sum(scores) / len(scores) * 100) if scores else 0.0
        return OcrResult(provider="PaddleOCR", text=text, confidence=round(confidence, 2))


def _prepare_tesseract_image(image: Image.Image) -> Image.Image:
    """Upscale and contrast-boost small scans (WhatsApp / phone photos) for Tesseract."""
    from PIL import ImageEnhance, ImageFilter, ImageOps

    rgb = image.convert("RGB")
    width, height = rgb.size
    min_width = 1800
    if width < min_width:
        scale = min_width / float(width)
        rgb = rgb.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(rgb)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Contrast(gray).enhance(1.55)
    gray = gray.filter(ImageFilter.SHARPEN)
    return gray


def _tesseract_text_score(text: str) -> int:
    import re

    blob = (text or "").lower()
    hints = (
        r"in[\s\-]?uk",
        r"subin",
        r"certif",
        r"issued",
        r"purchas",
        r"first\s*part",
        r"second\s*part",
        r"stamp\s*dut",
        r"account\s*ref",
        r"unique",
    )
    hits = sum(1 for pattern in hints if re.search(pattern, blob))
    return hits * 200 + min(len(blob.strip()), 2500)


class TesseractBackend(OcrBackend):
    def __init__(self):
        import pytesseract

        tess_path = configure_tesseract()
        if not tess_path:
            raise OcrEngineNotAvailableError(
                "Tesseract binary not found. On Linux: sudo apt-get install -y tesseract-ocr. "
                r"On Windows: install Tesseract or add C:\Program Files\Tesseract-OCR\tesseract.exe to PATH."
            )
        pytesseract.get_tesseract_version()

    def extract(self, image: Image.Image) -> OcrResult:
        import pytesseract

        configure_tesseract()
        prepared = _prepare_tesseract_image(image)
        configs = ("--oem 3 --psm 4", "--oem 3 --psm 6", "--oem 3 --psm 11")
        best_text = ""
        best_score = -1
        best_config = configs[0]
        for config in configs:
            text = pytesseract.image_to_string(prepared, lang="eng", config=config) or ""
            score = _tesseract_text_score(text)
            logger.info("Tesseract candidate %s score=%s chars=%s", config, score, len(text))
            if score > best_score:
                best_score = score
                best_text = text
                best_config = config
        data = pytesseract.image_to_data(prepared, output_type=pytesseract.Output.DICT, config=best_config)
        scores = [
            float(conf)
            for conf in data.get("conf", [])
            if conf not in (-1, "-1") and str(conf).replace(".", "", 1).isdigit() and float(conf) >= 0
        ]
        confidence = (sum(scores) / len(scores)) if scores else 72.0
        return OcrResult(provider="Tesseract", text=best_text, confidence=round(confidence, 2))


_ENGINE_CACHE: tuple[str, OcrBackend] | None = None
_LAST_INIT_ERROR: str | None = None

_ENGINE_FACTORIES: list[tuple[str, Callable[[], OcrBackend]]] = [
    ("EasyOCR", EasyOcrBackend),
    ("PaddleOCR", PaddleOcrBackend),
    ("Tesseract", TesseractBackend),
]


def get_last_init_error() -> str | None:
    return _LAST_INIT_ERROR


def peek_ocr_engine() -> str | None:
    if _ENGINE_CACHE is None:
        return None
    return _ENGINE_CACHE[0]


def _is_recoverable_ocr_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "cvtcolor" in text or ("has no attribute" in text and "cv2" in text) or "libgl" in text


def get_ocr_engine(force_refresh: bool = False, exclude: set[str] | None = None) -> tuple[str, OcrBackend]:
    global _ENGINE_CACHE, _LAST_INIT_ERROR
    skip = exclude or set()
    if _ENGINE_CACHE is not None and not force_refresh and _ENGINE_CACHE[0] not in skip:
        return _ENGINE_CACHE

    errors: list[str] = []
    for name, factory in _ENGINE_FACTORIES:
        if name in skip:
            continue
        try:
            backend = factory()
            _ENGINE_CACHE = (name, backend)
            _LAST_INIT_ERROR = None
            logger.info("OCR Provider selected: %s", name)
            return _ENGINE_CACHE
        except Exception as exc:
            msg = f"{name}: {exc}"
            errors.append(msg)
            logger.warning("OCR Provider unavailable — %s", msg)

    _LAST_INIT_ERROR = "; ".join(errors) if errors else "No OCR provider packages found."
    raise OcrEngineNotAvailableError(
        "OCR Engine Not Installed. Administrator Contact Required. "
        f"Details: {_LAST_INIT_ERROR}"
    )


def _prepare_image(raw: bytes) -> Image.Image:
    image = Image.open(BytesIO(raw))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    width, height = image.size
    min_width = 1400
    if width < min_width:
        scale = min_width / float(width)
        image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
        logger.info("OCR: upscaled image from %sx%s to %sx%s", width, height, image.size[0], image.size[1])
    return image


def _extract_with_fallback(image: Image.Image) -> OcrResult:
    tried: list[str] = []
    retried: set[str] = set()
    last_exc: Exception | None = None
    while True:
        try:
            provider_name, engine = get_ocr_engine(force_refresh=bool(tried), exclude=set(tried))
        except OcrEngineNotAvailableError:
            if last_exc is not None:
                raise last_exc
            raise
        logger.info("OCR Provider: %s", provider_name)
        logger.info("OCR Started")
        try:
            result = engine.extract(image)
            logger.info("OCR Text:\n%s", result.text)
            logger.info("OCR Completed — provider=%s confidence=%s", result.provider, result.confidence)
            return result
        except Exception as exc:
            last_exc = exc
            logger.error("OCR Failed Reason (%s): %s", provider_name, exc)
            if _is_recoverable_ocr_error(exc) and provider_name not in retried:
                retried.add(provider_name)
                rebind_easyocr_cv2()
                logger.warning("Retrying %s after OpenCV repair", provider_name)
                continue
            tried.append(provider_name)
            global _ENGINE_CACHE
            _ENGINE_CACHE = None
            logger.warning("Falling back from %s to the next OCR provider", provider_name)
            continue


def ocr_image_bytes(raw: bytes) -> OcrResult:
    logger.info("OCR: Image Loaded (%s bytes)", len(raw))
    return _extract_with_fallback(_prepare_image(raw))


def ocr_pdf_bytes(raw: bytes) -> OcrResult:
    from pdf2image import convert_from_bytes

    logger.info("OCR: PDF Loaded (%s bytes)", len(raw))
    pages = convert_from_bytes(raw, dpi=200)
    texts: list[str] = []
    confidences: list[float] = []
    provider = "Unknown"
    try:
        for page in pages:
            if page.mode not in ("RGB", "L"):
                page = page.convert("RGB")
            result = _extract_with_fallback(page)
            provider = result.provider
            texts.append(result.text)
            confidences.append(result.confidence)
        combined = "\n".join(texts)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        logger.info("OCR Text:\n%s", combined)
        logger.info("OCR Completed — provider=%s confidence=%s", provider, avg_conf)
        return OcrResult(provider=provider, text=combined, confidence=round(avg_conf, 2))
    except Exception as exc:
        logger.error("OCR Failed Reason: %s", exc)
        raise

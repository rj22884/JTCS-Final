"""
Install OCR engine stack for JTCS ERP (EasyOCR priority).

Run:
    cd erp
    .\\.venv\\Scripts\\Activate.ps1
    python scripts/install_ocr.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PACKAGES = [
    "easyocr",
    "torch",
    "torchvision",
    "opencv-python-headless",
    "Pillow",
    "numpy",
    "pytesseract",
    "pdf2image",
]


def main() -> int:
    print("Installing OCR stack:", ", ".join(PACKAGES))
    cmd = [sys.executable, "-m", "pip", "install", *PACKAGES]
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        print("Installation failed.")
        return completed.returncode

    print("\nProbing OCR providers...")
    from app import create_app
    from app.services.ocr_provider_service import OcrProviderService

    app = create_app()
    with app.app_context():
        status = OcrProviderService.initialize(force=True)
        print(status.to_dict()["message"])
        for probe in status.providers:
            print(f"  {probe.name}: {probe.reason} {probe.detail}".strip())

    if status.ready:
        print("\nOCR installation successful. Restart the ERP server.")
        return 0

    print("\nOCR still not ready.")
    if sys.platform.startswith("linux"):
        print("  sudo bash deployment/fix_vps_ocr.sh")
        print("  sudo apt-get install -y libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-eng")
        print("  pip uninstall -y opencv-python opencv-contrib-python && pip install opencv-python-headless")
    else:
        print("  Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("  Default path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

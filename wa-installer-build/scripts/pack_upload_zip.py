"""Build a deploy zip with forward-slash paths (Windows Compress-Archive / tar can break Linux extract)."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", ".git", "data"}
SKIP_FILES = {
    "deploy_vps.env",
    "deploy_admin.env",
    ".env",
    ".env.local",
    ".env.production",
}


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: pack_upload_zip.py <project_root> <zip_path>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    if out.exists():
        out.unlink()
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name in SKIP_FILES:
                continue
            if not path.is_file():
                continue
            zf.write(path, path.relative_to(root).as_posix())
            count += 1
    print(f"Packed {count} files -> {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

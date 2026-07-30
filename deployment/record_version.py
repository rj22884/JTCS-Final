#!/usr/bin/env python3
"""
JTCS ERP — record deployment into dbo.AppVersionHistory / ChangeLog.

Runs on the VPS inside the app virtualenv (preferred) or any env with
Flask app dependencies. Safe to call multiple times for the same commit
(creates a new history row; marks prior IsCurrent=0).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def _bootstrap_app():
    """Add erp/ to path and create Flask app context."""
    here = Path(__file__).resolve().parent
    repo = here.parent
    erp = Path(os.environ.get("VPS_ERP_DIR_ABS") or (repo / "erp")).resolve()
    if str(erp) not in sys.path:
        sys.path.insert(0, str(erp))
    os.chdir(erp)
    from wsgi import app  # type: ignore

    return app


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record JTCS ERP deployment version")
    p.add_argument("--version", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--developer", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--branch", default="")
    p.add_argument("--backup", default="")
    p.add_argument("--status", default="Success")
    p.add_argument("--whats-new", default="")
    p.add_argument("--bug-fixes", default="")
    p.add_argument("--features", default="")
    p.add_argument("--db-changes", default="")
    p.add_argument("--security", default="")
    p.add_argument("--performance", default="")
    p.add_argument("--database-version", default="")
    return p.parse_args()


def bump_build(existing_build: int | None) -> int:
    return int(existing_build or 0) + 1


def main() -> int:
    args = parse_args()
    app = _bootstrap_app()
    with app.app_context():
        from app.extensions import db
        from app.services.version_service import VersionService

        svc = VersionService()
        current = svc.get_current()
        version = (args.version or "").strip()
        if not version:
            # Auto patch bump from current, or start at 1.0.0
            if current and current.ApplicationVersion:
                parts = current.ApplicationVersion.split(".")
                while len(parts) < 3:
                    parts.append("0")
                try:
                    parts[2] = str(int(parts[2]) + 1)
                except ValueError:
                    parts = ["1", "0", "0"]
                version = ".".join(parts[:3])
            else:
                version = "1.0.0"

        build = bump_build(current.BuildNumber if current else None)
        row = svc.record_deployment(
            application_version=version,
            build_number=build,
            database_version=(args.database_version or version).strip() or version,
            git_commit_id=args.commit.strip() or None,
            git_branch=args.branch.strip() or None,
            developer_name=args.developer.strip() or None,
            release_notes=args.notes.strip() or None,
            whats_new=args.whats_new.strip() or None,
            bug_fixes=args.bug_fixes.strip() or None,
            new_features=args.features.strip() or None,
            database_changes=args.db_changes.strip() or None,
            security_updates=args.security.strip() or None,
            performance_improvements=args.performance.strip() or None,
            deployment_status=args.status.strip() or "Success",
            backup_path=args.backup.strip() or None,
        )
        db.session.commit()
        print(
            f"Recorded Version {row.ApplicationVersion} "
            f"build={row.BuildNumber} status={row.DeploymentStatus} "
            f"at {datetime.utcnow().isoformat()}Z"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"record_version failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

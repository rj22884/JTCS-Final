"""JTCS Xpert recruitment application factory — standalone service."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, redirect
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from recruitment.config import VAR_DIR, Config
from recruitment.extensions import csrf, db, limiter, login_manager, migrate

logging.basicConfig(level=logging.INFO)


def create_app(config_class=Config) -> Flask:
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/recruitment/static",
    )
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    upload_dir: Path = app.config["UPLOAD_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / ".htaccess").write_text("Require all denied\n", encoding="utf-8")
    pdf_dir = Path(app.config.get("APPLICATION_PDF_DIR") or (upload_dir.parent / "application_pdfs"))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / ".htaccess").write_text("Require all denied\n", encoding="utf-8")
    for extra in ("HR_LETTER_DIR", "EMPLOYEE_DOC_DIR"):
        extra_dir = Path(app.config.get(extra) or (upload_dir.parent / extra.lower().replace("_dir", "")))
        extra_dir.mkdir(parents=True, exist_ok=True)
        (extra_dir / ".htaccess").write_text("Require all denied\n", encoding="utf-8")

    if app.config.get("TESTING"):
        app.config["RATELIMIT_ENABLED"] = False
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).parent / "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r"/api/recruitment/*": {"origins": app.config["CORS_ORIGINS"]}})

    login_manager.login_view = "admin.login"
    login_manager.login_message = "Please sign in to access recruitment admin."

    from recruitment import models  # noqa: F401
    from recruitment.views_admin import admin_bp
    from recruitment.views_api import api_bp
    from recruitment.views_hr import hr_bp
    from recruitment.views_public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(hr_bp)

    @app.before_request
    def _ensure_schema_once():
        if app.config.get("_schema_ready") or app.config.get("TESTING"):
            return
        from recruitment.schema import ensure_admin_schema

        try:
            ensure_admin_schema()
            app.config["_schema_ready"] = True
        except Exception:
            logging.exception("Could not ensure recruitment admin schema")

    @app.get("/")
    def service_home():
        return redirect("/careers/apply/sales-executive")

    @app.cli.command("init-db")
    def init_db_command():
        """Create tables, run seed data, and stamp migrations."""
        from recruitment.seed import seed_defaults

        db.create_all()
        seed_defaults()
        print("Recruitment database ready.")

    @app.context_processor
    def inject_globals():
        from flask_login import current_user

        return {
            "current_user": current_user,
            "website_url": (app.config.get("PUBLIC_SITE_URL") or "https://jtcsxpert.com").rstrip("/"),
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return ("Access denied.", 403)

    @app.errorhandler(404)
    def not_found(_e):
        return ("Not found.", 404)

    @app.errorhandler(413)
    def too_large(_e):
        return (
            "The uploaded file is too large. Please upload a resume of 5 MB or smaller, then submit again.",
            413,
        )

    @app.errorhandler(429)
    def too_many(_e):
        return (
            "Too many attempts. Please wait a few minutes and try again.",
            429,
        )

    return app

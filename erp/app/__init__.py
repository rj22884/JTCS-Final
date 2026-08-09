from datetime import date, datetime

from flask import Flask, has_request_context, redirect, request, session, url_for
from app.config import Config
from app.extensions import db, mail, csrf
from app.routes.auth import bp as auth_bp
from app.routes.dashboard import bp as dashboard_bp
from app.routes.menu_admin import bp as menu_admin_bp
from app.routes.pages import bp as pages_bp
from app.routes.reports import bp as reports_bp
from app.routes.setup import bp as setup_bp
from app.routes.transactions import bp as transactions_bp
from app.routes.stamp import bp as stamp_bp
from app.routes.ecourt import bp as ecourt_bp
from app.routes.bank_master import bp as bank_master_bp
from app.routes.masters_account_type import bp as masters_account_type_bp
from app.routes.masters_chart_account import bp as masters_chart_account_bp
from app.routes.masters_chart_group import bp as masters_chart_group_bp
from app.routes.masters_item import bp as masters_item_bp
from app.routes.accounting_invoice import bp as accounting_invoice_bp
from app.routes.masters_sub_work import bp as masters_sub_work_bp
from app.routes.masters_work import (
    bp as masters_work_bp,
    legacy_expense_bp as masters_expense_legacy_bp,
    legacy_income_bp as masters_income_legacy_bp,
)
from app.routes.printing_scanning import bp as printing_scanning_bp, expense_bp as printing_scan_expense_bp
from app.routes.others_income_expense import bp as others_income_expense_bp
from app.routes.others_bank_cash import bp as others_bank_cash_bp
from app.routes.purpose_master import bp as purpose_master_bp
from app.routes.credentials_master import bp as credentials_master_bp
from app.routes.followup import (
    api_itr_bp,
    dsc_followup_bp,
    gst_followup_bp,
    itr_followup_bp,
    tds_followup_bp,
)
from app.routes.masters_followup import bp as masters_followup_bp
from app.routes.masters_customer import bp as masters_customer_bp
from app.routes.customer_portal import bp as customer_portal_bp
from app.routes.masters_group import bp as masters_group_bp
from app.routes.exceptional_report import bp as exceptional_report_bp
from app.routes.backup import bp as backup_bp
from app.routes.admin_dashboard import bp as admin_dashboard_bp
from app.routes.customer_activity import bp as customer_activity_bp
from app.routes.admin_import_export import bp as admin_import_export_bp
from app.routes.menu_customization import bp as menu_customization_bp
from app.routes.ledger_report import bp as ledger_report_bp
from app.routes.financial_statements import bp as financial_statements_bp
from app.routes.software_update import bp as software_update_bp
from app.routes.utility import bp as utility_bp
from app.modules.crm.routes import (
    crm_api_bp,
    crm_bp,
    notification_api_bp,
    public_intake_bp,
    search_api_bp,
)
from app.modules.settings.routes import bp as integration_settings_bp
from app.modules.system_health.routes import bp as system_health_bp
from app.services.auth_service import AuthService
from app.services.menu_service import MenuService
from app.utils.date_format import (
    DISPLAY_DATE_FORMAT,
    format_display_date,
    format_display_datetime,
    format_display_value,
)

SETUP_PUBLIC_ENDPOINTS = {
    "setup.index",
    "auth.login",
    "auth.register",
    "auth.forgot_password",
    "auth.forgot_user_id",
    "auth.reset_password",
    "auth.verify_email",
    "auth.verify_token",
    "auth.verify_email_link",
    "auth.verify_success",
    "dashboard.health",
    "public_intake.website_intake",
    "customer_portal.login_page",
    "customer_portal.login_api",
    "customer_portal.reset_password_api",
    "customer_portal.profile_api_legacy",
}


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    app.register_blueprint(setup_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(stamp_bp)
    app.register_blueprint(ecourt_bp)
    app.register_blueprint(printing_scanning_bp)
    app.register_blueprint(printing_scan_expense_bp)
    app.register_blueprint(others_income_expense_bp)
    app.register_blueprint(others_bank_cash_bp)
    app.register_blueprint(purpose_master_bp)
    app.register_blueprint(credentials_master_bp)
    app.register_blueprint(bank_master_bp)
    app.register_blueprint(masters_work_bp)
    app.register_blueprint(masters_sub_work_bp)
    app.register_blueprint(masters_account_type_bp)
    app.register_blueprint(masters_chart_group_bp)
    app.register_blueprint(masters_chart_account_bp)
    app.register_blueprint(masters_item_bp)
    app.register_blueprint(accounting_invoice_bp)
    app.register_blueprint(masters_income_legacy_bp)
    app.register_blueprint(masters_expense_legacy_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(menu_admin_bp)
    app.register_blueprint(itr_followup_bp)
    app.register_blueprint(api_itr_bp)
    app.register_blueprint(dsc_followup_bp)
    app.register_blueprint(tds_followup_bp)
    app.register_blueprint(gst_followup_bp)
    app.register_blueprint(masters_followup_bp)
    app.register_blueprint(masters_customer_bp)
    app.register_blueprint(customer_portal_bp)
    app.register_blueprint(masters_group_bp)
    app.register_blueprint(exceptional_report_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(admin_dashboard_bp)
    from app.routes.admin_dashboard import activity_bp as admin_activity_bp

    app.register_blueprint(admin_activity_bp)
    app.register_blueprint(customer_activity_bp)
    app.register_blueprint(admin_import_export_bp)
    app.register_blueprint(menu_customization_bp)
    app.register_blueprint(ledger_report_bp)
    app.register_blueprint(financial_statements_bp)
    app.register_blueprint(software_update_bp)
    app.register_blueprint(utility_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(crm_api_bp)
    app.register_blueprint(notification_api_bp)
    app.register_blueprint(search_api_bp)
    app.register_blueprint(public_intake_bp)
    app.register_blueprint(integration_settings_bp)
    app.register_blueprint(system_health_bp)
    app.register_blueprint(pages_bp)

    # Website intake uses API key auth (no session CSRF token).
    csrf.exempt(public_intake_bp)

    # Integration Settings (and JSON clients): CSRF failures as JSON, not HTML.
    from app.modules.settings.routes import register_integration_csrf_json_handler

    register_integration_csrf_json_handler(app)

    with app.app_context():
        from app.services.ocr_provider_service import OcrProviderService

        OcrProviderService.initialize()

        try:
            from app.modules.shared.schema import (
                ensure_activities_shcil_menus,
                ensure_crm_menus,
                ensure_crm_schema,
                ensure_erp_core_nav_menus,
            )

            ensure_crm_schema()
            ensure_crm_menus()
            ensure_erp_core_nav_menus()
            ensure_activities_shcil_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("CRM/core nav menu ensure skipped: %s", exc)

        try:
            from app.modules.settings.routes import ensure_integration_settings_bootstrap

            ensure_integration_settings_bootstrap()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Integration Settings bootstrap skipped: %s", exc)

        try:
            from app.services.login_activity_service import LoginActivityService

            LoginActivityService().ensure_schema()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Login activity schema ensure skipped: %s", exc)

        from app.utils.smtp_health import check_smtp_from_config, log_mail_config

        log_mail_config(app.config, app.logger)

        if app.config.get("SMTP_HEALTH_CHECK_ON_STARTUP") and app.config.get("MAIL_PASSWORD"):
            import threading

            def _smtp_health_bg() -> None:
                try:
                    smtp_ok, smtp_detail = check_smtp_from_config(app.config)
                    if smtp_ok:
                        app.logger.info(smtp_detail)
                    else:
                        app.logger.warning("SMTP startup health check failed: %s", smtp_detail)
                except Exception as exc:  # pragma: no cover - defensive
                    app.logger.warning("SMTP startup health check error: %s", exc)

            threading.Thread(
                target=_smtp_health_bg,
                name="jtcs-smtp-health",
                daemon=True,
            ).start()
            app.logger.info("SMTP startup health check running in background…")

        try:
            from app.routes.backup import ensure_backup_menus

            ensure_backup_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Backup menu ensure skipped: %s", exc)

        try:
            from app.routes.utility import ensure_utility_menus

            ensure_utility_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Utility menus ensure skipped: %s", exc)

        try:
            from app.modules.system_health.routes import ensure_system_health_menus

            ensure_system_health_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("System Health menus ensure skipped: %s", exc)

        try:
            from app.routes.admin_dashboard import ensure_admin_dashboard_menu

            ensure_admin_dashboard_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Admin Dashboard menu ensure skipped: %s", exc)

        try:
            from app.routes.customer_activity import ensure_customer_activity_menu

            ensure_customer_activity_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Client/Customer Activity menu ensure skipped: %s", exc)

        try:
            from app.routes.menu_customization import ensure_menu_customization_menu

            ensure_menu_customization_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Menu Customization menu ensure skipped: %s", exc)

        try:
            from app.routes.auth import ensure_admin_users_menu

            ensure_admin_users_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Admin Users menu ensure skipped: %s", exc)

        try:
            from app.routes.admin_import_export import ensure_import_export_menus

            ensure_import_export_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Import/Export menu ensure skipped: %s", exc)

        try:
            from app.routes.masters_work import _ensure_menu as ensure_work_category_menu

            ensure_work_category_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Work/Category Master menu ensure skipped: %s", exc)

        try:
            from app.routes.masters_chart_group import _ensure_menu as ensure_chart_group_menu

            ensure_chart_group_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Chart of Group Master menu ensure skipped: %s", exc)

        try:
            from app.routes.masters_chart_account import _ensure_menu as ensure_chart_account_menu

            ensure_chart_account_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Chart of Account Master menu ensure skipped: %s", exc)

        try:
            from app.routes.ledger_report import ensure_ledger_report_menu

            ensure_ledger_report_menu()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Ledger Report menu ensure skipped: %s", exc)

        try:
            from app.routes.financial_statements import ensure_financial_statements_menus

            ensure_financial_statements_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Financial Statements menus ensure skipped: %s", exc)

        try:
            from app.repositories.customer_repository import CustomerRepository

            CustomerRepository().ensure_schema()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Customer Master / portal schema ensure skipped: %s", exc)

        # After Ledger Report so Stamp / e-Court Exception sit after it under Reports.
        try:
            from app.routes.exceptional_report import _ensure_exceptional_report_menus

            _ensure_exceptional_report_menus()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Exception report menus ensure skipped: %s", exc)

    @app.before_request
    def enforce_initial_setup():
        if request.endpoint in (None, "static"):
            return None
        if request.endpoint in SETUP_PUBLIC_ENDPOINTS:
            auth = AuthService()
            if auth.administrator_exists() and request.endpoint == "setup.index":
                return redirect(url_for("auth.login"))
            return None

        auth = AuthService()
        if not auth.administrator_exists():
            return redirect(url_for("setup.index"))
        return None

    @app.context_processor
    def inject_globals():
        navigation = []
        company = AuthService().get_company()
        company_name = company.CompanyName if company else app.config["APP_NAME"]
        company_logo = company.LogoPath if company else None
        company_display_name = company_name if company_name not in (None, "", "JTCS ERP", "JTCS") else app.config.get(
            "COMPANY_DISPLAY_NAME", "Joshi Tax Consultancy & Services"
        )
        today = date.today()
        if today.month >= 4:
            financial_year = f"FY {today.year}-{today.year + 1}"
        else:
            financial_year = f"FY {today.year - 1}-{today.year}"

        from app.utils.roles import has_admin_role

        pending_user_notifications = []
        pending_user_count = 0
        crm_notifications = []
        crm_unread_count = 0
        is_admin_user = False
        if has_request_context() and session.get("user_id"):
            menu_service = MenuService()
            navigation = menu_service.get_navigation(session.get("role"))
            is_admin_user = has_admin_role(session.get("role"))
            if is_admin_user:
                try:
                    pending_users = AuthService().list_pending_users()
                    pending_user_count = len(pending_users)
                    pending_user_notifications = [
                        {
                            "user_id": u.UserID,
                            "name": u.FullName,
                            "email": u.EmailID,
                            "verified": bool(u.EmailVerified),
                            "status": "Pending Approval",
                        }
                        for u in pending_users[:8]
                    ]
                except Exception:
                    pending_user_count = 0
                    pending_user_notifications = []
            try:
                from app.modules.notification.services import NotificationService

                notif_data = NotificationService().list_for_user(
                    session.get("user_id"),
                    page=1,
                    page_size=8,
                )
                crm_unread_count = int(notif_data.get("unread_count") or 0)
                crm_notifications = notif_data.get("rows") or []
            except Exception:
                crm_unread_count = 0
                crm_notifications = []

        db_server = app.config.get("DB_SERVER_DISPLAY", r"JTCS\JTCS")
        db_name = app.config.get("DB_NAME_DISPLAY", "JTCSS")
        db_connection = app.config.get("DB_CONNECTION_DISPLAY", f"{db_server}\\{db_name}")

        login_id = ""
        if has_request_context() and session.get("user_id"):
            try:
                from app.utils.delete_auth import current_login_id

                login_id = current_login_id()
            except Exception:
                login_id = ""

        display_version = app.config["APP_VERSION"]
        try:
            from app.services.version_service import VersionService

            display_version = VersionService().get_display_version(app.config["APP_VERSION"])
        except Exception:
            display_version = app.config["APP_VERSION"]

        now = datetime.now()
        return {
            "app_name": app.config["APP_NAME"],
            "app_version": display_version,
            "company_name": company_name,
            "company_display_name": company_display_name,
            "company_tagline": app.config.get("COMPANY_TAGLINE", "Income Tax | GST | Compliance Services"),
            "company_logo": company_logo,
            "navigation": navigation,
            "financial_year": financial_year,
            "current_date": format_display_date(today, empty=""),
            "server_time": format_display_datetime(now, empty=""),
            "server_time_iso": now.isoformat(timespec="seconds"),
            "display_date_format": DISPLAY_DATE_FORMAT,
            "display_date_format_label": "dd/mm/yyyy",
            "db_server_display": db_server,
            "db_name_display": db_name,
            "db_connection_display": db_connection,
            "pending_user_count": pending_user_count,
            "pending_user_notifications": pending_user_notifications,
            "crm_unread_count": crm_unread_count,
            "crm_notifications": crm_notifications,
            "notification_poll_seconds": app.config.get("NOTIFICATION_POLL_SECONDS", 15),
            "is_admin_user": is_admin_user,
            "current_login_id": login_id,
        }
    @app.template_filter("menu_active")
    def menu_active(menu_url: str | None) -> bool:
        from urllib.parse import parse_qs, urlparse

        from flask import request
        from app.services.menu_service import MenuService

        menu_url = MenuService.normalize_menu_url(menu_url)
        if not menu_url:
            return False

        parsed = urlparse(menu_url)
        if request.path != parsed.path and not request.path.startswith(f"{parsed.path}/"):
            return False

        if not parsed.query:
            if parsed.path == "/transactions/new":
                return not request.args.get("work_type")
            return request.path == parsed.path

        menu_params = parse_qs(parsed.query)
        for key, values in menu_params.items():
            if request.args.get(key) != values[0]:
                return False
        return True

    @app.template_filter("display_date")
    def display_date_filter(value):
        return format_display_date(value)

    @app.template_filter("display_datetime")
    def display_datetime_filter(value):
        return format_display_datetime(value)

    @app.template_filter("display_value")
    def display_value_filter(value):
        return format_display_value(value)

    @app.template_filter("menu_href")
    def menu_href_filter(menu_url: str | None):
        from app.services.menu_service import MenuService

        return MenuService.normalize_menu_url(menu_url)

    return app

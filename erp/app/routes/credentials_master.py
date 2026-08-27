from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import text

from app.decorators import login_required, require_delete_reauth
from app.extensions import db
from app.services.credentials_master_service import CredentialsMasterService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response
from app.whats_new import publish_whats_new

bp = Blueprint("credentials_master", __name__, url_prefix="/masters/credentials")

MENU_PATH = "/masters/credentials"


def _ensure_schema_and_menu() -> None:
    db.session.execute(
        text(
            """
            IF OBJECT_ID(N'dbo.CredentialsMaster', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.CredentialsMaster (
                    CredentialID   INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CredentialsMaster PRIMARY KEY,
                    Activity       NVARCHAR(200) NOT NULL,
                    URL            NVARCHAR(500) NULL,
                    UserID         NVARCHAR(150) NULL,
                    Password       NVARCHAR(200) NULL,
                    EmailID        NVARCHAR(200) NULL,
                    MobileNumber   NVARCHAR(20) NULL,
                    ActiveStatus   BIT NOT NULL CONSTRAINT DF_CredentialsMaster_Active DEFAULT (1),
                    CreatedBy      NVARCHAR(100) NULL,
                    CreatedDate    DATETIME NOT NULL CONSTRAINT DF_CredentialsMaster_Created DEFAULT (GETUTCDATE()),
                    ModifiedDate   DATETIME NULL
                );
            END

            DECLARE @MastersID INT;
            SELECT TOP 1 @MastersID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @MastersID IS NOT NULL
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Credentials Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/credentials',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-key'),
                        Description = N'Activity portal credentials vault',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Credentials Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID, N'Credentials Master', N'bi-key', N'/masters/credentials',
                        18, N'Activity portal credentials vault', 1, NULL
                    );
            END
            """
        )
    )
    db.session.commit()
    try:
        # Idempotent — shows once under Dashboard → What's New.
        publish_whats_new(
            "feature:credentials_master",
            "Credentials Master",
            detail="Masters → store Activity, URL, User ID, Password, Email & Mobile with Add / Edit / Delete.",
            url=MENU_PATH,
            badge="New",
        )
    except Exception:
        db.session.rollback()


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    try:
        _ensure_schema_and_menu()
    except Exception:
        db.session.rollback()

    menu_service = MenuService()
    try:
        rows = CredentialsMasterService().list_records()
    except Exception:
        rows = []
    return render_template(
        "credentials_master/index.html",
        page_title="Credentials Master",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records")
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    rows = CredentialsMasterService().list_records(search=search, active_only=active_only)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:credential_id>")
@login_required
def get_record(credential_id: int):
    try:
        record = CredentialsMasterService().get_record(credential_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"])
@login_required
def create_record():
    try:
        record = CredentialsMasterService().create_record(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        return jsonify({"ok": True, "record": record, "message": "Credential added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:credential_id>", methods=["POST"])
@login_required
def update_record(credential_id: int):
    try:
        record = CredentialsMasterService().update_record(credential_id, request.form)
        return jsonify({"ok": True, "record": record, "message": "Credential updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:credential_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_record(credential_id: int):
    try:
        message = CredentialsMasterService().delete_record(credential_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))

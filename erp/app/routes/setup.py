from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services.auth_service import AuthService

bp = Blueprint("setup", __name__)


@bp.route("/setup", methods=["GET", "POST"])
def index():
    auth = AuthService()
    if auth.administrator_exists():
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        logo = request.files.get("company_logo")
        success, message, _ = auth.complete_setup(request.form, logo_file=logo)
        if not success:
            flash(message, "danger")
        else:
            flash(message or "Setup completed successfully. Please sign in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("setup/index.html", page_title="Initial Setup")

"""Public Meta WhatsApp webhook. Meta calls this URL; it is not a login page."""

from flask import Blueprint

from app.extensions import csrf
from app.modules.settings.routes import api_whatsapp_webhook

bp = Blueprint("whatsapp_webhook", __name__, url_prefix="/webhooks")


@bp.route("/whatsapp", methods=["GET", "POST"])
@csrf.exempt
def whatsapp():
    return api_whatsapp_webhook()

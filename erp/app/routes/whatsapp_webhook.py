"""Public Meta WhatsApp webhook entry on the ERP host.

Meta may still call this path until the Meta Callback URL is switched to
wa.ukdscwala.com. The handler forwards to the dedicated WhatsApp app and does
not store messages in the ERP CRM inbox.
"""

from flask import Blueprint

from app.extensions import csrf
from app.modules.settings.routes import api_whatsapp_webhook

bp = Blueprint("whatsapp_webhook", __name__, url_prefix="/webhooks")


@bp.route("/whatsapp", methods=["GET", "POST"])
@csrf.exempt
def whatsapp():
    return api_whatsapp_webhook()

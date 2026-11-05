"""Public DSC Resume Applications page (no login). Prefills from query params."""

from __future__ import annotations

import base64
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, render_template, request

from app.services.followup_service import FollowupService

logger = logging.getLogger(__name__)

bp = Blueprint("public_resume", __name__)

# Same ID-Sign signup host already used by DSC Followup status sync.
_IDSIGN_SIGNUP = "https://dsc.idsignca.com/ekycadmin/signup/"


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.after_request
def public_resume_cors(response):
    return _cors(response)


def index():
    return render_template("public/resume.html", page_title="Resume Applications")


@bp.route("/resume/config", methods=["GET", "OPTIONS"], strict_slashes=False)
def config():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        values = FollowupService("DSC").get_dsc_assist()
    except Exception:
        logger.exception("resume config failed")
        values = {}
    return jsonify(
        {
            "ok": True,
            "video_base": (values.get("customer_video_link") or "").strip(),
        }
    )


def _b64(value: str) -> str:
    return base64.b64encode(str(value or "").encode("utf-8")).decode("ascii")


def _idsign_post(path: str, payload: dict) -> str:
    data = urlencode(payload).encode("utf-8")
    req = Request(
        _IDSIGN_SIGNUP + path,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/plain, */*",
            "User-Agent": "JTCS-Resume/1.0",
        },
    )
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


@bp.route("/resume/vkyc", methods=["POST", "OPTIONS"], strict_slashes=False)
def vkyc():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    ref = "".join(ch for ch in str(body.get("applicationId") or body.get("refno") or "") if ch.isdigit())
    mobile = "".join(ch for ch in str(body.get("mobile") or "") if ch.isdigit())[-10:]
    mode = str(body.get("mode") or "").strip()
    if mode == "app_mobile" and len(ref) < 7:
        return jsonify({"ok": False, "error": "Please enter a valid Reference Number."}), 400
    if len(mobile) != 10:
        return jsonify({"ok": False, "error": "Please enter a valid Mobile Number."}), 400
    try:
        raw = _idsign_post(
            "vkyc",
            {"recordId": _b64(ref), "mobNo": _b64(mobile), "isVoice": "N"},
        )
        parts = [part.strip() for part in raw.split("|")]
        code = parts[0] if parts else ""
        message = parts[1] if len(parts) > 1 else raw
        if code != "1000":
            return jsonify({"ok": False, "error": message or "Unable to send OTP."}), 400
        return jsonify(
            {
                "ok": True,
                "message": message,
                "otp_ref": parts[2] if len(parts) > 2 else "",
                "session_id": parts[3] if len(parts) > 3 else "",
                "record_id": parts[4] if len(parts) > 4 else "",
                "continue_url": _IDSIGN_SIGNUP + "incprodapp",
            }
        )
    except Exception:
        logger.exception("resume vkyc failed")
        return jsonify({"ok": False, "error": "Unable to start validation. Try again."}), 500


@bp.route("/resume/otp", methods=["POST", "OPTIONS"], strict_slashes=False)
def otp():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    otp_value = "".join(ch for ch in str(body.get("otp") or "") if ch.isdigit())
    otp_ref = str(body.get("otp_ref") or "").strip()
    if not otp_value or not otp_ref:
        return jsonify({"ok": False, "error": "Enter the OTP received on mobile."}), 400
    try:
        raw = _idsign_post(
            "otpValidate",
            {"emailOtp": otp_value, "emailotprefid": otp_ref, "verflag": "M"},
        )
        parts = [part.strip() for part in raw.split("|")]
        code = parts[0] if parts else ""
        message = parts[1] if len(parts) > 1 else raw
        if code != "1000":
            return jsonify({"ok": False, "error": message or "OTP verification failed."}), 400
        return jsonify({"ok": True, "message": message or "OTP verified."})
    except Exception:
        logger.exception("resume otp failed")
        return jsonify({"ok": False, "error": "Unable to verify OTP. Try again."}), 500

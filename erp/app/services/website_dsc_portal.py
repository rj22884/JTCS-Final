"""Token login + DSC documents for the public website popup (no new browser tab)."""

from __future__ import annotations

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.services import dsc_documents
from app.services.customer_portal_service import CustomerPortalService

SALT = "jtcs-dsc-website-portal"
SESSION_MAX_AGE = 8 * 3600
SETUP_MAX_AGE = 30 * 60
DOC_KINDS = (
    ("pan", "PAN"),
    ("aadhaar", "Aadhaar"),
    ("org_id", "Organization ID"),
    ("auth_letter", "Authorization Letter"),
)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=SALT)


def _client_meta() -> tuple[str | None, str | None]:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = forwarded or request.remote_addr
    return ip, request.headers.get("User-Agent")


def issue_token(payload: dict, *, max_age: int = SESSION_MAX_AGE) -> str:
    data = dict(payload)
    data["max_age"] = max_age
    return _serializer().dumps(data)


def read_token(token: str, *, max_age: int | None = None) -> dict:
    raw = (token or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        raise ValueError("Please login again.")
    try:
        data = _serializer().loads(raw, max_age=max_age or SESSION_MAX_AGE)
    except SignatureExpired as exc:
        raise ValueError("Login expired. Please login again.") from exc
    except BadSignature as exc:
        raise ValueError("Invalid login. Please login again.") from exc
    if not isinstance(data, dict):
        raise ValueError("Invalid login. Please login again.")
    return data


def token_from_request() -> str:
    header = request.headers.get("Authorization") or ""
    if header:
        return header
    return (
        request.args.get("token")
        or (request.get_json(silent=True) or {}).get("token")
        or request.form.get("token")
        or ""
    )


def require_session() -> dict:
    data = read_token(token_from_request())
    if data.get("stage") != "session" or not data.get("cid"):
        raise ValueError("Please login again.")
    return data


class WebsiteDscPortalService:
    def __init__(self) -> None:
        self.portal = CustomerPortalService()

    def login_start(self, user_id: str, *, for_reset: bool = False) -> dict:
        ip, ua = _client_meta()
        result = self.portal.begin_login(user_id, ip_address=ip, user_agent=ua, for_reset=for_reset)
        if not result.get("ok"):
            return result
        if result.get("next") == "verify_identity":
            setup = issue_token(
                {
                    "stage": "setup",
                    "cid": result["customer_id"],
                    "uid": user_id,
                    "detected": result.get("detected_type"),
                    "verified": False,
                    "for_reset": bool(result.get("for_reset")),
                },
                max_age=SETUP_MAX_AGE,
            )
            result["setup_token"] = setup
        return result

    def login_verify(self, user_id: str, verify_value: str, setup_token: str) -> dict:
        setup = read_token(setup_token, max_age=SETUP_MAX_AGE)
        if setup.get("stage") != "setup":
            return {"ok": False, "error": "Please start login again.", "status_code": 400}
        ip, ua = _client_meta()
        result = self.portal.verify_identity(
            user_id or setup.get("uid") or "",
            verify_value,
            customer_id=int(setup["cid"]),
            ip_address=ip,
            user_agent=ua,
        )
        if not result.get("ok"):
            return result
        result["setup_token"] = issue_token(
            {
                "stage": "setup",
                "cid": result["customer_id"],
                "uid": user_id or setup.get("uid") or "",
                "detected": result.get("detected_type") or setup.get("detected"),
                "verified": True,
                "for_reset": bool(setup.get("for_reset")),
            },
            max_age=SETUP_MAX_AGE,
        )
        return result

    def login_set_password(self, new_password: str, confirm_password: str, setup_token: str) -> dict:
        setup = read_token(setup_token, max_age=SETUP_MAX_AGE)
        if setup.get("stage") != "setup" or not setup.get("verified"):
            return {"ok": False, "error": "Please verify your identity first.", "status_code": 403}
        ip, ua = _client_meta()
        result = self.portal.set_first_password(
            int(setup["cid"]),
            new_password,
            confirm_password,
            user_id_input=setup.get("uid"),
            detected_type=setup.get("detected"),
            ip_address=ip,
            user_agent=ua,
        )
        if not result.get("ok"):
            return result
        return self._session_ok(result)

    def login_password(self, user_id: str, password: str) -> dict:
        ip, ua = _client_meta()
        result = self.portal.login(user_id, password, ip_address=ip, user_agent=ua)
        if not result.get("ok"):
            return result
        return self._session_ok(result)

    def reset_password(self, user_id: str) -> dict:
        return self.login_start(user_id, for_reset=True)

    def _session_ok(self, result: dict) -> dict:
        token = issue_token(
            {
                "stage": "session",
                "cid": result["customer_id"],
                "name": result.get("customer_name") or "",
            }
        )
        return {
            "ok": True,
            "token": token,
            "customer_id": result["customer_id"],
            "customer_name": result.get("customer_name") or "",
            "message": result.get("message") or "Login successful.",
        }

    def docs(self, session: dict) -> dict:
        cid = int(session["cid"])
        rows = dsc_documents.customer_doc_status(cid)
        token = token_from_request()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        docs = []
        for kind, label in DOC_KINDS:
            item = next((row for row in rows if row.get("kind") == kind), None) or {
                "kind": kind,
                "label": label,
                "file_name": "",
                "has_file": False,
            }
            item["label"] = label
            name = str(item.get("file_name") or "")
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            item["preview_kind"] = "image" if ext in {"jpg", "jpeg", "png", "gif", "webp"} else ("pdf" if ext == "pdf" else "file")
            item["preview_url"] = (
                f"/api/dsc/portal/docs/{kind}?token={token}&inline=1" if item.get("has_file") else ""
            )
            docs.append(item)
        return {
            "ok": True,
            "customer_name": session.get("name") or "",
            "docs": docs,
        }

    def doc_file(self, session: dict, kind: str):
        return dsc_documents.customer_doc_file(int(session["cid"]), kind)

    def save_doc(self, session: dict, kind: str, file_storage) -> dict:
        result = dsc_documents.save_customer_doc(
            int(session["cid"]),
            kind,
            file_storage,
            actor=session.get("name") or f"Customer:{session.get('cid')}",
        )
        return result

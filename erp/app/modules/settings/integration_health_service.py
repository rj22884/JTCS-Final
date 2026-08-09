"""Integration Health Dashboard — scans all catalog providers from existing settings."""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import has_request_context, session

from app.modules.settings.audit_service import IntegrationSettingsAuditService
from app.modules.settings.crypto import encrypt_value, mask_access_token, mask_secret
from app.modules.settings.provider_catalog import PROVIDER_CATALOG, provider_meta
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.services import IntegrationSettingsService

logger = logging.getLogger(__name__)

# Re-scan when admin opens dashboard if last global scan older than this.
AUTO_SCAN_MINUTES = 30

# Secret-ish keys used for token / key presence checks across providers.
TOKEN_KEYS = (
    "access_token",
    "api_key",
    "api_secret",
    "refresh_token",
    "client_secret",
    "app_secret",
    "password",
    "webhook_verify_token",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def _score_label(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 40:
        return "Warning"
    return "Critical"


def _status_from_score(score: int, configured: bool, connected: bool) -> tuple[str, str]:
    """Return (status_code, display label) for card coloring."""
    if not configured:
        return "not_configured", "Not Configured"
    if score >= 80 and connected:
        return "connected", "Connected"
    if score >= 55:
        return "warning", "Warning"
    if score >= 35:
        return "token_expiring", "Token Expiring"
    return "disconnected", "Disconnected"


class IntegrationHealthService:
    """Central health console — reuses IntegrationSettings; no duplicate config tables."""

    def __init__(
        self,
        settings: IntegrationSettingsService | None = None,
        repository: IntegrationSettingsRepository | None = None,
    ):
        self.settings = settings or IntegrationSettingsService()
        self.repository = repository or IntegrationSettingsRepository()
        self.audit = IntegrationSettingsAuditService(self.repository)

    # ------------------------------------------------------------------ scan
    def scan_all(self, *, force: bool = False, user_id: int | None = None) -> dict[str, Any]:
        """Run health checks for every catalog provider. Persists history + alerts."""
        self.repository.ensure_health_schema()
        if user_id is None and has_request_context():
            user_id = session.get("user_id")

        if not force and not self._scan_is_stale():
            return self.dashboard(run_scan=False)

        cards: list[dict[str, Any]] = []
        for meta in PROVIDER_CATALOG:
            code = meta["code"]
            try:
                card = self._evaluate_provider(code, meta, live_probe=True)
            except Exception as exc:
                logger.exception("Health scan failed for %s", code)
                card = self._fallback_card(code, meta, str(exc))
            self._persist_check(card, user_id=user_id)
            self._sync_alerts(card)
            cards.append(card)

        return self._assemble_dashboard(cards, scanned=True)

    def dashboard(self, *, run_scan: bool = True, force: bool = False) -> dict[str, Any]:
        """Payload for Integration Health tab. Auto-scans when stale or forced."""
        self.repository.ensure_health_schema()
        if run_scan and (force or self._scan_is_stale()):
            return self.scan_all(force=True)

        latest = self.repository.latest_health_by_provider()
        cards: list[dict[str, Any]] = []
        for meta in PROVIDER_CATALOG:
            code = meta["code"]
            row = latest.get(code)
            if row:
                cards.append(self._card_from_row(row, meta))
            else:
                # No history yet — lightweight evaluate without live probes
                cards.append(self._evaluate_provider(code, meta, live_probe=False))
        return self._assemble_dashboard(cards, scanned=False)

    def provider_detail(self, provider: str) -> dict[str, Any]:
        meta = provider_meta(provider)
        card = self._evaluate_provider(provider, meta, live_probe=False)
        history = self.repository.list_health_history(provider, limit=30)
        audit_rows = self.audit.list_recent(provider=provider, limit=40)
        cfg_masked = self.settings.get_provider_settings_masked(provider)
        plain = self.settings.get_provider_config_decrypted(provider)

        # Mask secrets for detail panel
        config_safe = {}
        for k, v in plain.items():
            if any(s in k.lower() for s in ("token", "secret", "password", "key", "cert")):
                config_safe[k] = mask_secret(v) if v else ""
            else:
                config_safe[k] = v

        usage = self._usage_stats_from_history(history)
        return {
            "ok": True,
            "provider": provider,
            "meta": meta,
            "card": card,
            "configuration": config_safe,
            "field_values_masked": cfg_masked.get("field_values") or {},
            "token_expiry": plain.get("token_expires_at") or plain.get("certificate_expires_at") or "",
            "webhook_url": plain.get("webhook_url") or "",
            "permissions": self._permissions_hint(provider, plain),
            "last_api_response": card.get("details", {}).get("last_api_response"),
            "last_success": card.get("last_sync_at") or card.get("details", {}).get("last_success"),
            "last_failure": card.get("last_error"),
            "error_history": [
                {
                    "checked_on": self._iso(h.get("CheckedOn")),
                    "status": h.get("StatusCode"),
                    "score": h.get("HealthScore"),
                    "error": h.get("LastError"),
                }
                for h in history
                if h.get("LastError")
            ][:20],
            "usage": usage,
            "history": [
                {
                    "checked_on": self._iso(h.get("CheckedOn")),
                    "score": h.get("HealthScore"),
                    "status": h.get("StatusCode"),
                    "avg_ms": h.get("AvgResponseMs"),
                }
                for h in history
            ],
            "audit": [
                {
                    "key": a.get("SettingKey"),
                    "old": a.get("OldValueMasked"),
                    "new": a.get("NewValueMasked"),
                    "user": a.get("ChangedByUserName"),
                    "ip": a.get("IPAddress"),
                    "at": self._iso(a.get("CreatedOn")),
                }
                for a in audit_rows
            ],
        }

    def refresh_provider(self, provider: str) -> dict[str, Any]:
        meta = provider_meta(provider)
        user_id = session.get("user_id") if has_request_context() else None
        card = self._evaluate_provider(provider, meta, live_probe=True)
        self._persist_check(card, user_id=user_id)
        self._sync_alerts(card)
        self._audit_action(provider, "health_refresh", "Refreshed integration health")
        return {"ok": True, "card": card}

    def test_provider(self, provider: str) -> dict[str, Any]:
        """Test connection — deep probe for WhatsApp; config presence for others."""
        meta = provider_meta(provider)
        user_id = session.get("user_id") if has_request_context() else None
        started = time.perf_counter()
        probe: dict[str, Any] = {"ok": False, "message": ""}

        if provider == "whatsapp_meta":
            try:
                from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

                probe = WhatsAppHealthService(self.settings, self.repository).token_health()
            except Exception as exc:
                probe = {"ok": False, "message": str(exc)}
        elif provider == "smtp":
            try:
                probe = self.settings.test_smtp_connection({})
            except Exception as exc:
                probe = {"ok": False, "message": "SMTP test failed."}
                logger.exception("Health SMTP probe failed: %s", exc)
        else:
            cfg = self.settings.get_provider_config_decrypted(provider)
            configured = self._is_configured(cfg)
            status = (cfg.get("connection_status") or "").strip()
            if configured and status.lower().startswith("connected"):
                probe = {"ok": True, "message": "Credentials present; marked Connected."}
            elif configured:
                probe = {
                    "ok": True,
                    "message": "Credentials stored. Live API probe not enabled for this provider yet.",
                    "partial": True,
                }
            else:
                probe = {"ok": False, "message": "Not configured — add credentials first."}

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        card = self._evaluate_provider(provider, meta, live_probe=True)
        card["avg_response_ms"] = elapsed_ms
        card["details"] = dict(card.get("details") or {})
        card["details"]["last_api_response"] = probe
        if not probe.get("ok"):
            card["last_error"] = probe.get("message") or card.get("last_error")
            card["health_score"] = min(int(card["health_score"]), 35)
            card["status_code"], card["connection_status"] = _status_from_score(
                card["health_score"], True, False
            )
            card["status_label"] = _score_label(card["health_score"])
        self._persist_check(card, user_id=user_id)
        self._sync_alerts(card)
        self._audit_action(provider, "test_connection", probe.get("message") or "Test connection")
        return {"ok": bool(probe.get("ok")), "card": card, "probe": probe, "message": probe.get("message")}

    def list_alerts(self) -> dict[str, Any]:
        rows = self.repository.list_open_alerts(limit=50)
        return {
            "ok": True,
            "alerts": [
                {
                    "id": r.get("AlertID"),
                    "provider": r.get("Provider"),
                    "type": r.get("AlertType"),
                    "severity": r.get("Severity"),
                    "title": r.get("Title"),
                    "message": r.get("Message"),
                    "created_on": self._iso(r.get("CreatedOn")),
                }
                for r in rows
            ],
        }

    def login_alerts(self) -> list[dict[str, str]]:
        """Compact alerts for admin login / ERP dashboard flash."""
        try:
            rows = self.repository.list_open_alerts(limit=8)
        except Exception:
            return []
        out = []
        for r in rows:
            if (r.get("Severity") or "").lower() in {"critical", "error", "high"}:
                out.append(
                    {
                        "provider": r.get("Provider") or "",
                        "title": r.get("Title") or "Integration alert",
                        "message": r.get("Message") or "",
                    }
                )
        return out

    def export_report(self, fmt: str = "csv") -> tuple[str, str, str]:
        """Return (filename, mimetype, body) for CSV/Excel-friendly export."""
        data = self.dashboard(run_scan=False)
        cards = data.get("integrations") or []
        fmt = (fmt or "csv").lower()
        if fmt == "json":
            body = json.dumps(data, indent=2, default=str)
            return "integration_health_report.json", "application/json", body

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Provider",
                "Label",
                "Status",
                "HealthScore",
                "TokenStatus",
                "WebhookStatus",
                "ApiVersion",
                "LastSync",
                "AvgResponseMs",
                "LastError",
            ]
        )
        for c in cards:
            writer.writerow(
                [
                    c.get("code"),
                    c.get("label"),
                    c.get("connection_status"),
                    c.get("health_score"),
                    c.get("token_status"),
                    c.get("webhook_status"),
                    c.get("api_version"),
                    c.get("last_sync_at"),
                    c.get("avg_response_ms"),
                    c.get("last_error"),
                ]
            )
        body = buf.getvalue()
        if fmt in {"xlsx", "excel"}:
            # Excel opens CSV; dedicated xlsx deferred without extra deps
            return "integration_health_report.csv", "text/csv; charset=utf-8", body
        if fmt == "pdf":
            # Lightweight text report (browser can print to PDF)
            lines = ["JTCS ERP — Integration Health Report", f"Generated: {_utcnow().isoformat()}Z", ""]
            for c in cards:
                lines.append(
                    f"{c.get('label')}: {c.get('connection_status')} | "
                    f"Score {c.get('health_score')}% | Token {c.get('token_status')}"
                )
            return (
                "integration_health_report.txt",
                "text/plain; charset=utf-8",
                "\n".join(lines),
            )
        return "integration_health_report.csv", "text/csv; charset=utf-8", body

    def history_series(self, period: str = "daily") -> dict[str, Any]:
        rows = self.repository.list_health_history(None, limit=200)
        # Aggregate by day for charts
        buckets: dict[str, dict[str, float]] = {}
        for r in rows:
            checked = r.get("CheckedOn")
            if not checked:
                continue
            if isinstance(checked, datetime):
                key = checked.strftime("%Y-%m-%d")
            else:
                key = str(checked)[:10]
            b = buckets.setdefault(key, {"score_sum": 0.0, "n": 0.0, "errors": 0.0})
            b["score_sum"] += float(r.get("HealthScore") or 0)
            b["n"] += 1
            if r.get("LastError"):
                b["errors"] += 1
        labels = sorted(buckets.keys())
        if period == "weekly":
            labels = labels[-7:]
        elif period == "monthly":
            labels = labels[-30:]
        else:
            labels = labels[-14:]
        return {
            "ok": True,
            "period": period,
            "labels": labels,
            "availability": [
                round(buckets[d]["score_sum"] / buckets[d]["n"], 1) if buckets[d]["n"] else 0
                for d in labels
            ],
            "errors": [int(buckets[d]["errors"]) for d in labels],
        }

    # -------------------------------------------------------------- evaluate
    def _evaluate_provider(
        self, code: str, meta: dict[str, str], *, live_probe: bool
    ) -> dict[str, Any]:
        cfg = self.settings.get_provider_config_decrypted(code)
        configured = self._is_configured(cfg)
        status_text = (cfg.get("connection_status") or "").strip()
        connected = bool(status_text) and status_text.lower().startswith("connected")

        score = 0
        token_status = "N/A"
        webhook_status = "N/A"
        api_version = cfg.get("graph_api_version") or cfg.get("api_version") or "—"
        last_error = ""
        avg_ms: int | None = None
        last_sync = cfg.get("last_sync_at") or ""
        details: dict[str, Any] = {}
        next_check = (_utcnow() + timedelta(minutes=AUTO_SCAN_MINUTES)).isoformat() + "Z"

        if not configured:
            score = 0
            token_status = "Not Configured"
            status_code, connection_status = "not_configured", "Not Configured"
        else:
            score = 40  # base for having credentials
            has_token = any((cfg.get(k) or "").strip() for k in TOKEN_KEYS)
            if has_token:
                score += 20
                token_status = "Present"
            else:
                token_status = "Missing"

            # Expiry monitoring
            exp = _parse_dt(cfg.get("token_expires_at") or cfg.get("certificate_expires_at"))
            if exp:
                details["token_expires_at"] = exp.isoformat() + "Z"
                days = (exp - _utcnow()).total_seconds() / 86400
                if days < 0:
                    token_status = "Expired"
                    score -= 35
                elif days <= 7:
                    token_status = "Expiring Soon"
                    score -= 15
                else:
                    token_status = "Valid"
                    score += 15

            if connected:
                score += 25
            elif status_text:
                score += 5

            # Webhook (primarily WhatsApp)
            wh_url = (cfg.get("webhook_url") or "").strip()
            verify = (cfg.get("webhook_verify_token") or "").strip()
            if wh_url or verify or code == "whatsapp_meta":
                if wh_url and verify:
                    webhook_status = "Configured"
                    score += 10
                elif verify or wh_url:
                    webhook_status = "Partial"
                    score -= 5
                else:
                    webhook_status = "Missing"
                    score -= 10
                fields = (cfg.get("webhook_subscribed_fields") or "").strip()
                details["subscribed_events"] = [x.strip() for x in fields.split(",") if x.strip()]
                details["webhook_url"] = wh_url

            if live_probe and code == "whatsapp_meta":
                try:
                    from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

                    t0 = time.perf_counter()
                    th = WhatsAppHealthService(self.settings, self.repository).token_health()
                    avg_ms = int((time.perf_counter() - t0) * 1000)
                    details["last_api_response"] = {
                        "ok": th.get("ok"),
                        "status": th.get("status"),
                        "message": th.get("message"),
                        "token_display": th.get("token_display") or mask_access_token(cfg.get("access_token")),
                    }
                    if th.get("ok") and not th.get("expired"):
                        score = max(score, 88)
                        connected = True
                        token_status = "Valid"
                        status_text = th.get("status") or "Connected"
                    elif th.get("expired"):
                        token_status = "Expired"
                        score = min(score, 20)
                        last_error = th.get("message") or "Token expired"
                    else:
                        score = min(score, 45)
                        last_error = th.get("message") or "Token health check failed"
                except Exception as exc:
                    last_error = str(exc)
                    score = min(score, 30)

            # Status text heuristics
            low = status_text.lower()
            if "expired" in low:
                score = min(score, 15)
                token_status = "Expired"
            elif "invalid" in low or "auth" in low:
                score = min(score, 25)
            elif "webhook" in low and "fail" in low:
                webhook_status = "Failed"
                score = min(score, 40)

            score = max(0, min(100, score))
            status_code, connection_status = _status_from_score(score, True, connected)
            if status_text and connected:
                connection_status = status_text if status_text else connection_status

        return {
            "code": code,
            "label": meta.get("label") or code,
            "icon": meta.get("icon") or "bi-plugin",
            "category": meta.get("category") or "Other",
            "connection_status": connection_status,
            "status_code": status_code,
            "health_score": int(score),
            "status_label": _score_label(int(score)),
            "token_status": token_status,
            "api_version": api_version,
            "webhook_status": webhook_status,
            "last_sync_at": last_sync or None,
            "next_auto_check": next_check,
            "avg_response_ms": avg_ms,
            "last_error": last_error or None,
            "configured": configured,
            "details": details,
        }

    def _fallback_card(self, code: str, meta: dict[str, str], error: str) -> dict[str, Any]:
        return {
            "code": code,
            "label": meta.get("label") or code,
            "icon": meta.get("icon") or "bi-plugin",
            "category": meta.get("category") or "Other",
            "connection_status": "Warning",
            "status_code": "warning",
            "health_score": 25,
            "status_label": "Critical",
            "token_status": "Unknown",
            "api_version": "—",
            "webhook_status": "N/A",
            "last_sync_at": None,
            "next_auto_check": (_utcnow() + timedelta(minutes=AUTO_SCAN_MINUTES)).isoformat() + "Z",
            "avg_response_ms": None,
            "last_error": error[:1000],
            "configured": False,
            "details": {},
        }

    def _card_from_row(self, row: dict, meta: dict[str, str]) -> dict[str, Any]:
        details = {}
        raw = row.get("DetailsJson")
        if raw:
            try:
                details = json.loads(raw)
            except Exception:
                details = {}
        score = int(row.get("HealthScore") or 0)
        return {
            "code": meta["code"],
            "label": meta.get("label") or meta["code"],
            "icon": meta.get("icon") or "bi-plugin",
            "category": meta.get("category") or "Other",
            "connection_status": row.get("StatusLabel") or row.get("StatusCode") or "Unknown",
            "status_code": row.get("StatusCode") or "not_configured",
            "health_score": score,
            "status_label": _score_label(score),
            "token_status": row.get("TokenStatus") or "N/A",
            "api_version": row.get("ApiVersion") or "—",
            "webhook_status": row.get("WebhookStatus") or "N/A",
            "last_sync_at": details.get("last_sync_at") or self._iso(row.get("CheckedOn")),
            "next_auto_check": (_utcnow() + timedelta(minutes=AUTO_SCAN_MINUTES)).isoformat() + "Z",
            "avg_response_ms": row.get("AvgResponseMs"),
            "last_error": row.get("LastError"),
            "configured": (row.get("StatusCode") or "") != "not_configured",
            "details": details,
            "checked_on": self._iso(row.get("CheckedOn")),
        }

    def _assemble_dashboard(self, cards: list[dict], *, scanned: bool) -> dict[str, Any]:
        summary = {
            "total": len(cards),
            "connected": 0,
            "disconnected": 0,
            "warning": 0,
            "failed": 0,
            "expiring_soon": 0,
            "not_configured": 0,
            "last_health_scan": None,
            "global_health_score": 0,
        }
        score_sum = 0
        configured_n = 0
        for c in cards:
            code = c.get("status_code") or ""
            if code == "connected":
                summary["connected"] += 1
            elif code == "disconnected":
                summary["disconnected"] += 1
            elif code == "warning":
                summary["warning"] += 1
            elif code == "token_expiring":
                summary["expiring_soon"] += 1
                summary["warning"] += 1
            elif code == "not_configured":
                summary["not_configured"] += 1
            else:
                summary["failed"] += 1
            # Critical health on a configured integration counts as Failed
            if c.get("configured") and int(c.get("health_score") or 0) <= 20 and code != "not_configured":
                if code != "disconnected":
                    summary["failed"] += 1
            tok = (c.get("token_status") or "").lower()
            if "expir" in tok and code != "token_expiring":
                summary["expiring_soon"] += 1
            if c.get("configured"):
                configured_n += 1
                score_sum += int(c.get("health_score") or 0)
            checked = c.get("checked_on") or c.get("last_sync_at")
            if checked and (
                not summary["last_health_scan"] or str(checked) > str(summary["last_health_scan"])
            ):
                summary["last_health_scan"] = checked

        if configured_n:
            summary["global_health_score"] = round(score_sum / configured_n)
        elif cards:
            summary["global_health_score"] = round(
                sum(int(c.get("health_score") or 0) for c in cards) / len(cards)
            )

        if scanned and not summary["last_health_scan"]:
            summary["last_health_scan"] = _utcnow().isoformat() + "Z"

        alerts = self.list_alerts().get("alerts") or []
        return {
            "ok": True,
            "scanned": scanned,
            "auto_scan_minutes": AUTO_SCAN_MINUTES,
            "summary": summary,
            "integrations": cards,
            "alerts": alerts,
            "global_health_score": summary["global_health_score"],
            "global_label": _score_label(int(summary["global_health_score"])),
        }

    def _persist_check(self, card: dict[str, Any], *, user_id: int | None) -> None:
        details = dict(card.get("details") or {})
        if card.get("last_sync_at"):
            details["last_sync_at"] = card["last_sync_at"]
        self.repository.insert_health_check(
            provider=card["code"],
            status_code=card.get("status_code") or "unknown",
            health_score=int(card.get("health_score") or 0),
            status_label=card.get("connection_status"),
            token_status=card.get("token_status"),
            webhook_status=card.get("webhook_status"),
            api_version=str(card.get("api_version") or "")[:40] or None,
            avg_response_ms=card.get("avg_response_ms"),
            last_error=card.get("last_error"),
            details_json=json.dumps(details, default=str) if details else None,
            user_id=user_id,
        )
        card["checked_on"] = _utcnow().isoformat() + "Z"

    def _sync_alerts(self, card: dict[str, Any]) -> None:
        code = card["code"]
        token = (card.get("token_status") or "").lower()
        status = card.get("status_code") or ""
        score = int(card.get("health_score") or 0)

        if token == "expired":
            self.repository.upsert_open_alert(
                provider=code,
                alert_type="token_expired",
                severity="Critical",
                title=f"{card['label']}: Token expired",
                message=card.get("last_error") or "Access token or certificate has expired.",
            )
        else:
            self.repository.resolve_alerts(code, "token_expired")

        if "expir" in token and "soon" in token:
            self.repository.upsert_open_alert(
                provider=code,
                alert_type="token_expiring",
                severity="Warning",
                title=f"{card['label']}: Token expiring soon",
                message="Renew credentials before expiry to avoid downtime.",
            )
        else:
            self.repository.resolve_alerts(code, "token_expiring")

        if status == "disconnected" and card.get("configured"):
            self.repository.upsert_open_alert(
                provider=code,
                alert_type="api_down",
                severity="Critical",
                title=f"{card['label']}: Disconnected",
                message=card.get("last_error") or "Integration is disconnected.",
            )
        else:
            self.repository.resolve_alerts(code, "api_down")

        if (card.get("webhook_status") or "").lower() == "failed":
            self.repository.upsert_open_alert(
                provider=code,
                alert_type="webhook_failed",
                severity="Error",
                title=f"{card['label']}: Webhook failed",
                message="Webhook verification or delivery is failing.",
            )
        else:
            self.repository.resolve_alerts(code, "webhook_failed")

        if score <= 20 and card.get("configured") and "auth" in (card.get("last_error") or "").lower():
            self.repository.upsert_open_alert(
                provider=code,
                alert_type="auth_failed",
                severity="Critical",
                title=f"{card['label']}: Authentication failed",
                message=card.get("last_error"),
            )

        if score >= 80 and card.get("configured"):
            # Healthy — clear soft alerts
            for at in ("api_down", "auth_failed", "webhook_failed"):
                self.repository.resolve_alerts(code, at)

    def _scan_is_stale(self) -> bool:
        latest = self.repository.latest_health_by_provider()
        if not latest:
            return True
        newest: datetime | None = None
        for row in latest.values():
            checked = row.get("CheckedOn")
            if isinstance(checked, datetime):
                if newest is None or checked > newest:
                    newest = checked
        if newest is None:
            return True
        return (_utcnow() - newest) > timedelta(minutes=AUTO_SCAN_MINUTES)

    def _is_configured(self, cfg: dict[str, str]) -> bool:
        if not cfg:
            return False
        for k, v in cfg.items():
            if k == "connection_status" or k == "notes":
                continue
            if (v or "").strip():
                return True
        return False

    def _permissions_hint(self, provider: str, cfg: dict[str, str]) -> list[str]:
        if provider == "whatsapp_meta":
            raw = (cfg.get("webhook_subscribed_fields") or "").strip()
            if raw:
                return [x.strip() for x in raw.split(",") if x.strip()]
            return ["whatsapp_business_messaging", "whatsapp_business_management"]
        scopes = (cfg.get("scopes") or cfg.get("permissions") or "").strip()
        if scopes:
            return [x.strip() for x in scopes.replace(" ", ",").split(",") if x.strip()]
        return []

    def _usage_stats_from_history(self, history: list[dict]) -> dict[str, Any]:
        today = _utcnow().strftime("%Y-%m-%d")
        today_rows = [
            h
            for h in history
            if self._iso(h.get("CheckedOn")).startswith(today)
        ]
        ms_vals = [int(h["AvgResponseMs"]) for h in history if h.get("AvgResponseMs") is not None]
        ok_n = sum(1 for h in today_rows if int(h.get("HealthScore") or 0) >= 70)
        fail_n = sum(1 for h in today_rows if h.get("LastError"))
        return {
            "avg_response_ms": int(sum(ms_vals) / len(ms_vals)) if ms_vals else None,
            "slowest_ms": max(ms_vals) if ms_vals else None,
            "fastest_ms": min(ms_vals) if ms_vals else None,
            "total_requests_today": len(today_rows),
            "successful_today": ok_n,
            "failed_today": fail_n,
            "rate_limit": "N/A",
        }

    def _audit_action(self, provider: str, action: str, message: str) -> None:
        try:
            self.audit.log_change(
                provider=provider,
                setting_key=f"__action__:{action}",
                old_cipher=None,
                new_cipher=encrypt_value(message[:200]),
            )
        except Exception:
            logger.exception("Health audit log failed")

    @staticmethod
    def _iso(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, datetime):
            return val.isoformat() + ("Z" if val.tzinfo is None else "")
        return str(val)

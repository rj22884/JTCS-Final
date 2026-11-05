"""Plan WhatsApp Inbox merge-and-link. Customer merges use CustomerMergeService."""

from __future__ import annotations

from app.extensions import db
from app.modules.communication.customer_link_service import CustomerLinkService
from app.modules.communication.services import CommunicationService
from app.modules.shared.audit_service import AuditService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService
from app.services.customer_merge_service import CustomerMergeService, _phone_key
from app.utils.db_session import persist


def match_card(row: dict) -> dict:
    """Public customer fields for the Merge & Link dialog. No secrets."""
    customer_id = int(row.get("customer_id") or row.get("CustomerID") or 0)
    mobile_number = (row.get("mobile_number") or row.get("MobileNumber") or "").strip()
    whatsapp_number = (row.get("whatsapp_number") or row.get("WhatsAppNumber") or "").strip()
    alternate_mobile = (row.get("alternate_mobile") or row.get("AlternateMobile") or "").strip()
    shown = mobile_number or whatsapp_number or alternate_mobile or (row.get("mobile") or "")
    return {
        "customer_id": customer_id,
        "customer_name": (row.get("customer_name") or row.get("CustomerName") or "").strip(),
        "mobile": str(shown).strip(),
        "mobile_number": mobile_number,
        "whatsapp_number": whatsapp_number,
        "alternate_mobile": alternate_mobile,
        "email": (row.get("email") or row.get("EmailID") or "").strip(),
        "city": (row.get("city") or row.get("City") or "").strip(),
        "customer_group": (row.get("customer_group") or row.get("CustomerGroup") or "").strip(),
        "customer_status": (row.get("customer_status") or row.get("CustomerStatus") or "").strip(),
    }


def load_matches(conversation: dict) -> list[dict]:
    """Read matching Customer Master rows. Does not link or merge."""
    if (conversation.get("Channel") or "") != "WhatsApp":
        return []
    mobile = conversation.get("ContactMobile") or conversation.get("LeadMobile") or ""
    email = conversation.get("ContactEmail")
    rows = CustomerLinkService().match_customers(mobile=mobile, email=email)
    return [match_card(row) for row in rows if int(row.get("customer_id") or row.get("CustomerID") or 0)]


def _optional_int(value, error: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(error) from None


def decide_merge_link(matches, main_customer_id=None, merge_customer_ids=None) -> dict:
    """Choose the main customer. Does not write.

    One match is ready immediately. Several matches stay on ``choose`` until
    exactly one main customer is supplied. Merge ids must be other matches.
    """
    rows = [match_card(row) for row in (matches or []) if match_card(row)["customer_id"]]
    ids = [row["customer_id"] for row in rows]
    if not ids:
        return {
            "outcome": "none",
            "auto": False,
            "main_customer_id": None,
            "merge_customer_ids": [],
            "matches": [],
            "error": "",
        }
    if merge_customer_ids is None:
        requested = []
    elif isinstance(merge_customer_ids, (str, int)):
        requested = [merge_customer_ids]
    elif isinstance(merge_customer_ids, list):
        requested = merge_customer_ids
    else:
        raise ValueError("Select the duplicate customers to merge.")

    if len(ids) == 1:
        only = ids[0]
        chosen = _optional_int(main_customer_id, "Selected customer does not match this WhatsApp number.")
        if chosen not in (None, only):
            raise ValueError("Selected customer does not match this WhatsApp number.")
        if requested:
            raise ValueError("There is only one matching customer. Nothing else can be merged.")
        return {
            "outcome": "ready",
            "auto": True,
            "main_customer_id": only,
            "merge_customer_ids": [],
            "matches": rows,
            "error": "",
        }

    chosen = _optional_int(main_customer_id, "Select one main customer.")
    if chosen is None:
        return {
            "outcome": "choose",
            "auto": False,
            "main_customer_id": None,
            "merge_customer_ids": [],
            "matches": rows,
            "error": "Select one main customer.",
        }
    if chosen not in ids:
        raise ValueError("Selected customer does not match this WhatsApp number.")
    sources: list[int] = []
    for raw in requested:
        cid = _optional_int(raw, "A selected duplicate is not a matching customer.")
        if cid is None or cid == chosen:
            continue
        if cid not in ids:
            raise ValueError("A selected duplicate is not a matching customer.")
        if cid not in sources:
            sources.append(cid)
    return {
        "outcome": "ready",
        "auto": False,
        "main_customer_id": chosen,
        "merge_customer_ids": sources,
        "matches": rows,
        "error": "",
    }


def assert_existing_phone_duplicates(matches, main_customer_id: int, merge_customer_ids: list[int]) -> None:
    """Reuse the Customer Master phone-duplicate rule. MobileNumber only."""
    if not merge_customer_ids:
        return
    by_id = {int(row["customer_id"]): row for row in matches}
    main = by_id.get(int(main_customer_id))
    if not main:
        raise ValueError("Selected customer does not match this WhatsApp number.")
    phone = _phone_key(main.get("mobile_number") or "")
    for raw in merge_customer_ids:
        other = by_id.get(int(raw))
        if not other:
            raise ValueError("A selected duplicate is not a matching customer.")
        if not phone or _phone_key(other.get("mobile_number") or "") != phone:
            raise ValueError("Selected customers are not duplicates for this option.")


def result_message(*, name: str, mobile: str, merged_count: int, auto: bool) -> str:
    label = (name or "Customer").strip() or "Customer"
    phone = (mobile or "").strip()
    who = f"{label} ({phone})" if phone else label
    if merged_count:
        noun = "record" if int(merged_count) == 1 else "records"
        return (
            f"Main customer {who} is linked to this WhatsApp contact. "
            f"{int(merged_count)} duplicate {noun} merged into that customer."
        )
    if auto:
        return f"One Customer Master match: {who}. Linked this WhatsApp contact to that main customer."
    return f"Linked this WhatsApp contact to main customer {who}."


def cancel_merge_link() -> dict:
    """Cancel leaves every customer and link unchanged."""
    return {"changed": False, "main_customer_id": None, "merge_customer_ids": []}


def execute_merge_and_link(decision: dict, merge_fn, link_fn) -> dict:
    """Merge selected duplicates first, then link. A merge error skips the link."""
    if decision.get("outcome") != "ready":
        raise ValueError(decision.get("error") or "Select one main customer.")
    main_id = int(decision["main_customer_id"])
    sources = [int(item) for item in (decision.get("merge_customer_ids") or [])]
    merged = None
    if sources:
        merged = merge_fn(main_id, sources, "phone")
    linked = link_fn(main_id)
    return {"merged": merged, "linked": linked}


def isolated_merge_and_link(decision: dict, merge_fn, link_fn, rollback) -> dict:
    """Run merge then link. On failure, roll back so nothing stays half-applied."""
    try:
        return execute_merge_and_link(decision, merge_fn, link_fn)
    except Exception:
        rollback()
        raise


def commit_whatsapp_merge_link(
    *,
    conversation: dict,
    main_customer_id,
    merge_customer_ids,
    user_id: int | None,
    user_name: str | None,
) -> dict:
    """Link the WhatsApp conversation to one main customer and merge chosen duplicates.

    Matching rows are read again here. The customer merge, conversation link,
    mapping, timeline, and audit commit together. A failure rolls them back.
    """
    if (conversation.get("Channel") or "") != "WhatsApp":
        raise ValueError("Merge & Link is only for WhatsApp contacts.")
    matches = load_matches(conversation)
    decision = decide_merge_link(matches, main_customer_id, merge_customer_ids)
    if decision["outcome"] == "none":
        raise ValueError("No Customer Master record matches this WhatsApp contact.")
    if decision["outcome"] != "ready":
        raise ValueError(decision.get("error") or "Select one main customer.")
    sources = decision["merge_customer_ids"]
    if sources:
        assert_existing_phone_duplicates(decision["matches"], decision["main_customer_id"], sources)

    main = next(row for row in decision["matches"] if row["customer_id"] == decision["main_customer_id"])
    ensure_crm_schema()
    conversation_id = int(conversation["ConversationID"])
    mobile = conversation.get("ContactMobile") or conversation.get("LeadMobile") or ""
    previous = int(conversation["CustomerID"]) if conversation.get("CustomerID") else None
    subject = (main.get("customer_name") or "").strip() or "Customer"

    def merge_fn(main_id, merge_ids, mode):
        return CustomerMergeService().merge(main_id, merge_ids, mode, commit=False)

    def link_fn(main_id):
        CommunicationService().update_conversation(
            conversation_id,
            customer_id=int(main_id),
            customer_set=True,
            match_status="Linked",
            subject=subject[:255],
            assigned_by_user_id=user_id,
            assigned_by_name=user_name,
            commit=False,
        )
        CustomerLinkService().upsert_whatsapp_mapping(
            mobile,
            customer_id=int(main_id),
            conversation_id=conversation_id,
            confirmed=True,
            user_id=user_id,
            overwrite=True,
            commit=False,
        )
        TimelineService().reassign_conversation(
            conversation_id,
            customer_id=int(main_id),
            commit=False,
        )
        AuditService().log(
            action_name="CustomerLinkedFromWhatsApp" if previous else "CustomerCreatedFromWhatsApp",
            entity_type="CustomerMaster",
            entity_id=int(main_id),
            old_value=previous,
            new_value=int(main_id),
            user_id=user_id,
            user_name=user_name,
            commit=False,
        )
        TimelineService().add_event(
            event_type="CustomerLinked",
            title="Customer linked from WhatsApp",
            customer_id=int(main_id),
            entity_type="CrmConversation",
            entity_id=conversation_id,
            user_id=user_id,
            user_name=user_name,
            commit=False,
        )
        return {"customer_id": int(main_id)}

    def _write():
        nested = db.session.begin_nested()
        try:
            outcome = execute_merge_and_link(decision, merge_fn, link_fn)
            nested.commit()
            return outcome
        except Exception:
            nested.rollback()
            raise

    outcome = persist(_write)
    merged = outcome.get("merged") or {}
    count = int(merged.get("merged_count") or 0) if isinstance(merged, dict) else 0
    name = ""
    if isinstance(merged, dict):
        name = (merged.get("main_customer_name") or "").strip()
    name = name or main.get("customer_name") or ""
    phone = main.get("mobile") or ""
    auto = bool(decision.get("auto"))
    return {
        "customer_id": decision["main_customer_id"],
        "customer_name": name,
        "mobile": phone,
        "merged_count": count,
        "merged_customer_ids": sources,
        "auto": auto,
        "message": result_message(name=name, mobile=phone, merged_count=count, auto=auto),
    }

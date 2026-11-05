"""WhatsApp Inbox merge-and-link planning tests. No customer writes and no VPS."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.communication.whatsapp_merge_link import (  # noqa: E402
    assert_existing_phone_duplicates,
    cancel_merge_link,
    decide_merge_link,
    execute_merge_and_link,
    isolated_merge_and_link,
    result_message,
)


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


def customer(customer_id: int, name: str, mobile: str, **extra) -> dict:
    row = {
        "customer_id": customer_id,
        "customer_name": name,
        "mobile_number": mobile,
        "whatsapp_number": extra.get("whatsapp_number", ""),
        "alternate_mobile": extra.get("alternate_mobile", ""),
        "email": extra.get("email", ""),
        "city": extra.get("city", ""),
        "customer_group": extra.get("customer_group", ""),
    }
    return row


def main() -> None:
    none = decide_merge_link([])
    check("no match stays empty", none["outcome"] == "none" and none["main_customer_id"] is None)

    one = decide_merge_link([customer(7, "Ravi Sharma", "9876543210", city="Jaipur")])
    check("single match auto-selects that customer", one["outcome"] == "ready" and one["auto"] and one["main_customer_id"] == 7)
    check("single match merges nobody", one["merge_customer_ids"] == [])
    check(
        "single match result names the customer",
        "Ravi Sharma" in result_message(name="Ravi Sharma", mobile="9876543210", merged_count=0, auto=True),
    )

    try:
        decide_merge_link([customer(7, "Ravi", "9876543210")], main_customer_id=8)
        check("single match rejects a different customer", False)
    except ValueError:
        check("single match rejects a different customer", True)

    many = [
        customer(1, "Asha", "9876543210", city="Ajmer", customer_group="GST"),
        customer(2, "Asha Stores", "919876543210", email="asha@example.com"),
        customer(3, "Other Asha", "9876543210", city="Kota"),
    ]
    waiting = decide_merge_link(many)
    check("multiple matches wait for a main customer", waiting["outcome"] == "choose" and waiting["main_customer_id"] is None)

    ready = decide_merge_link(many, main_customer_id=2, merge_customer_ids=[1, 3])
    check("selected main is kept", ready["outcome"] == "ready" and ready["main_customer_id"] == 2 and not ready["auto"])
    check("selected duplicates are included", ready["merge_customer_ids"] == [1, 3])

    main_only = decide_merge_link(many, main_customer_id=1, merge_customer_ids=[])
    check("unselected duplicates stay out", main_only["merge_customer_ids"] == [])

    skipped = decide_merge_link(many, main_customer_id=2, merge_customer_ids=[2, 1])
    check("main customer is not merged into itself", skipped["merge_customer_ids"] == [1])

    try:
        decide_merge_link(many, main_customer_id=9, merge_customer_ids=[1])
        check("unknown main is rejected", False)
    except ValueError as exc:
        check("unknown main is rejected", "does not match" in str(exc))

    try:
        decide_merge_link(many, main_customer_id=1, merge_customer_ids=[99])
        check("unknown duplicate is rejected", False)
    except ValueError as exc:
        check("unknown duplicate is rejected", "not a matching customer" in str(exc))

    calls = []

    def merge_fn(main_id, merge_ids, mode):
        calls.append(("merge", main_id, list(merge_ids), mode))
        return {"merged_count": len(merge_ids), "main_customer_name": "Asha Stores"}

    def link_fn(main_id):
        calls.append(("link", main_id))
        return {"customer_id": main_id}

    done = execute_merge_and_link(ready, merge_fn, link_fn)
    check("merge uses the existing phone mode", calls[0] == ("merge", 2, [1, 3], "phone"))
    check("link runs after the merge", calls[1] == ("link", 2) and done["linked"]["customer_id"] == 2)
    check("merged count comes from the existing merge", done["merged"]["merged_count"] == 2)

    link_only_calls = []

    def no_merge(main_id, merge_ids, mode):
        link_only_calls.append("merge")
        return {}

    def link_only(main_id):
        link_only_calls.append(("link", main_id))
        return {"customer_id": main_id}

    execute_merge_and_link(one, no_merge, link_only)
    check("single match links without calling merge", link_only_calls == [("link", 7)])

    failed = []

    def boom(main_id, merge_ids, mode):
        failed.append("merge")
        raise ValueError("Selected customers are not duplicates for this option.")

    def should_not_link(main_id):
        failed.append("link")
        return {"customer_id": main_id}

    try:
        execute_merge_and_link(ready, boom, should_not_link)
        check("merge failure does not link", False)
    except ValueError as exc:
        check("merge failure does not link", failed == ["merge"] and "not duplicates" in str(exc))

    state = {"customers": [1, 2, 3]}

    def mutating_merge(main_id, merge_ids, mode):
        state["customers"] = [main_id]
        return {"merged_count": len(merge_ids)}

    def failing_link(main_id):
        raise RuntimeError("link failed")

    def rollback():
        state["customers"] = [1, 2, 3]

    try:
        isolated_merge_and_link(ready, mutating_merge, failing_link, rollback)
        check("link failure rolls back the merge", False)
    except RuntimeError:
        check("link failure rolls back the merge", state["customers"] == [1, 2, 3])

    assert_existing_phone_duplicates(many, 2, [1, 3])
    check("same mobile number passes the existing phone rule", True)
    try:
        assert_existing_phone_duplicates(
            [
                customer(1, "Asha", "9876543210"),
                customer(4, "Asha WA", "1111111111", whatsapp_number="9876543210"),
            ],
            1,
            [4],
        )
        check("whatsapp-only match is not a phone duplicate", False)
    except ValueError as exc:
        check("whatsapp-only match is not a phone duplicate", str(exc) == "Selected customers are not duplicates for this option.")

    cancelled = cancel_merge_link()
    check("cancel changes nothing", cancelled == {"changed": False, "main_customer_id": None, "merge_customer_ids": []})
    print("ALL PASS")


if __name__ == "__main__":
    main()

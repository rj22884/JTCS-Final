"""Parse the NFSA FPS CSV and smoke-test Public Report routes."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re
import sys
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ERP_ROOT))

from app.services.pds_master_service import parse_wikipedia_districts
from app.services.ration_card_report_service import RationCardReportService, to_hindi_name, to_proper_case

SAMPLE = Path(r"C:\Users\USER\Downloads\ramesh chandra pinaro.csv")

WIKI_SAMPLE = """
{| class="wikitable sortable"
|-
! S.No. !! Code !! District !! Headquarters !! Division
|-
| 1 || AL || [[Almora district|Almora]] || [[Almora]] || [[Kumaon division|Kumaon]]
|-
| 2 || NA || [[Nainital district|Nainital]] || [[Nainital]] || [[Kumaon division|Kumaon]]
|-
| DD || [[Dehradun district|Dehradun]] || [[Dehradun]] || [[Garhwal division|Garhwal]]
|}
"""


def test_wiki_parse() -> None:
    rows = parse_wikipedia_districts(WIKI_SAMPLE)
    codes = {row["district_code"] for row in rows}
    print("WIKI PARSE", sorted(codes))
    assert codes == {"AL", "NA", "DD"}
    names = {row["district_name"] for row in rows}
    assert "Almora" in names and "Nainital" in names and "Dehradun" in names
    print("WIKI PARSE OK")


def test_parse() -> None:
    raw = SAMPLE.read_bytes()
    rows = RationCardReportService.parse_csv(raw, file_name=SAMPLE.name)
    report = RationCardReportService.build_report(rows)
    schemes = {group["scheme_name"] for group in report["groups"]}
    keys = {(g["scheme_name"], g["rc_number"]) for g in report["groups"]}
    print("ROWS", len(rows))
    print("GROUPS", len(report["groups"]), "UNIQUE KEYS", len(keys))
    print("SCHEMES", sorted(schemes))
    print("CARDS", report["totals"]["card_count"], "MEMBERS", report["totals"]["member_count"])
    print("FPS", report["fps_ids"])
    print("TEHSIL", report["tehsils"])
    assert rows, "CSV produced no rows"
    assert report["groups"], "Report produced no groups"
    assert report["grid_rows"], "Grid rows missing"
    assert all(g["scheme_name"] and g["rc_number"] for g in report["groups"])
    for group in report["groups"]:
        hof_rows = [member for member in group["members"] if member.get("is_hof")]
        if hof_rows:
            assert group["members"][0]["is_hof"], f"HOF is not first for {group['rc_number']}"
    group_keys = [
        ((g["scheme_name"] or "").upper(), (g["rc_number"] or "").upper())
        for g in report["groups"]
    ]
    assert group_keys == sorted(
        group_keys,
        key=lambda item: ({"AAY": 0, "PHH": 1, "SFY": 2, "NER": 3, "NPHH": 4}.get(item[0], 99), item[0], item[1]),
    )
    grid_groups = [row for row in report["grid_rows"] if row.get("group_first")]
    assert grid_groups
    assert all(row.get("is_hof") for row in grid_groups)
    first = rows[0]
    assert not str(first.get("existing_fps_id") or "").startswith("'")
    assert first.get("fps_id", "").startswith("FPS")
    display = report["grid_rows"][0].get("full_name_display") or ""
    print("NAME SAMPLE", display)
    assert "(" in display and ")" in display, "Hindi name in brackets is missing"
    first_row = report["grid_rows"][0]
    assert first_row.get("full_name_hi"), "Hindi name part is missing"
    assert to_proper_case("kamala DEVI") == "Kamala Devi"
    assert to_proper_case("ROHIT palariya") == "Rohit Palariya"
    assert to_proper_case("ASHA PANDEY") == "Asha Pandey"
    assert first_row.get("full_name_en") == to_proper_case(first_row.get("full_name_en") or "")
    assert to_hindi_name("Omprakash trilochan joshi") == "ओमप्रकाश त्रिलोचन जोशी"
    assert to_hindi_name("TEJPRAKASH OMPRAKASH JOSHI") == "तेजप्रकाश ओमप्रकाश जोशी"
    assert to_hindi_name("Girish Chandra") == "गिरीश चन्द्र"
    assert "परकश" not in to_hindi_name("Omprakash")
    first_group = report["groups"][0]
    assert "male_count" in first_group and "age_lt_10" in first_group
    print("PARSE OK")


def test_pdf_layouts() -> None:
    raw = SAMPLE.read_bytes()
    rows = RationCardReportService.parse_csv(raw, file_name=SAMPLE.name)
    report = RationCardReportService.build_report(rows)
    report["dealer"] = {"dealer_name": "TARA DURR", "fps_id": "FPS2026030500000011931"}
    desktop, desktop_name = RationCardReportService.build_pdf(report, layout="desktop")
    mobile, mobile_name = RationCardReportService.build_pdf(report, layout="mobile")
    print("PDF DESKTOP", desktop_name, len(desktop))
    print("PDF MOBILE", mobile_name, len(mobile))
    assert desktop.startswith(b"%PDF"), "Desktop A4 portrait PDF missing"
    assert mobile.startswith(b"%PDF"), "Mobile A4 portrait PDF missing"
    assert "Portrait" in desktop_name and "Desktop" in desktop_name
    assert "Portrait" in mobile_name and "Mobile" in mobile_name
    # Visible PDF chrome: page count left, no A4/layout label, no dealer/FPS/group footer.
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(desktop)
    first_page = pdf[0].get_textpage().get_text_bounded()
    pages_text = "\n".join(pdf[i].get_textpage().get_text_bounded() for i in range(len(pdf)))
    assert "A4 Portrait" not in pages_text
    assert "Group: Scheme Name" not in pages_text
    assert re.search(r"Page\s+1\s+of\s+\d+", first_page), first_page[-400:]
    assert not re.search(r"[\u0900-\u097F]", pages_text), "Hindi names must not appear in the PDF"
    sample_en = (report["grid_rows"][0].get("full_name_en") or "").strip()
    if sample_en:
        assert sample_en in pages_text, sample_en
        assert sample_en == to_proper_case(sample_en)
    print("PDF LAYOUTS OK")


def test_merge_and_fps() -> None:
    old = [
        {
            "member_id": "M1",
            "scheme_name": "PHH",
            "rc_number": "RC1",
            "full_name": "Old Name",
            "is_hof": True,
            "age": 40,
            "fps_id": "FPS1",
        },
        {
            "member_id": "M2",
            "scheme_name": "PHH",
            "rc_number": "RC1",
            "full_name": "Gone Person",
            "is_hof": False,
            "age": 12,
            "fps_id": "FPS1",
        },
    ]
    new = [
        {
            "member_id": "M1",
            "scheme_name": "PHH",
            "rc_number": "RC1",
            "full_name": "New Name",
            "is_hof": True,
            "age": 41,
            "fps_id": "FPS1",
        },
        {
            "member_id": "M3",
            "scheme_name": "AAY",
            "rc_number": "RC2",
            "full_name": "Fresh Person",
            "is_hof": True,
            "age": 30,
            "fps_id": "FPS1",
        },
    ]
    merged = RationCardReportService.apply_import(old, new, mode="update")
    by_id = {row["member_id"]: row for row in merged}
    assert by_id["M1"]["change_status"] == "updated"
    assert "Full Name" in (by_id["M1"]["change_detail"] or "")
    assert by_id["M2"]["change_status"] == "deleted"
    assert by_id["M3"]["change_status"] == "added"
    report = RationCardReportService.build_report(merged)
    assert report["totals"]["added_count"] == 1
    assert report["totals"]["deleted_count"] == 1
    assert report["totals"]["updated_count"] == 1

    class Dealer:
        FPSID = "FPS1"
        ExistingFPSID = "E1"

    service = RationCardReportService
    assert service.assert_csv_fps_matches_dealer(Dealer(), new) == "FPS1"
    try:
        service.assert_csv_fps_matches_dealer(Dealer(), [{**new[0], "fps_id": "OTHER"}])
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise SystemExit("FPS mismatch was not blocked")
    print("MERGE OK")


def test_app() -> None:
    from app import create_app
    from app.models.menu_master import MenuMaster

    app = create_app()
    client = app.test_client()
    with app.app_context():
        public = MenuMaster.query.filter(
            MenuMaster.MenuName == "Public Report",
            MenuMaster.ParentMenuID.is_(None),
        ).first()
        leaf = MenuMaster.query.filter(
            MenuMaster.MenuURL == "/public-report/ration-card/fps-detail"
        ).first()
        print("MENU Public Report:", "OK" if public and public.IsActive else "MISSING")
        print("MENU FPS detail:", "OK" if leaf and leaf.IsActive else "MISSING")
        master_urls = [
            "/public-report/ration-card/state-master",
            "/public-report/ration-card/district-master",
            "/public-report/ration-card/dso-master",
            "/public-report/ration-card/aro-master",
            "/public-report/ration-card/fps-master",
            "/public-report/ration-card/ration-card-master",
        ]
        for url in master_urls:
            item = MenuMaster.query.filter(MenuMaster.MenuURL == url).first()
            print("MENU", url.rsplit("/", 1)[-1], "OK" if item and item.IsActive else "MISSING")
            if not item:
                raise SystemExit(f"Missing menu {url}")
        from app.models.ration_card import PdsDistrictMaster, PdsDsoMaster, PdsStateMaster

        state = PdsStateMaster.query.filter(PdsStateMaster.StateName == "Uttarakhand").first()
        districts = PdsDistrictMaster.query.all()
        dsos = PdsDsoMaster.query.all()
        print("STATE", state.StateName if state else "MISSING", "DISTRICTS", len(districts), "DSO", len(dsos))
        if not state or len(districts) < 13 or len(dsos) < 13:
            raise SystemExit("Uttarakhand geography was not imported")
        if not public or not leaf:
            raise SystemExit("Public Report menus were not created")

    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "Administrator"
        sess["user_name"] = "Admin"
        sess["server_user_id"] = 1
        sess["server_auth_at"] = datetime.now(timezone.utc).isoformat()
    page = client.get("/public-report/ration-card/fps-detail")
    print("PAGE", page.status_code)
    if page.status_code != 200:
        raise SystemExit("FPS detail page did not load")
    state_page = client.get("/public-report/ration-card/state-master")
    print("STATE PAGE", state_page.status_code)
    if state_page.status_code != 200:
        raise SystemExit("State Master page did not load")
    district_api = client.get("/public-report/api/pds/district", headers={"Accept": "application/json"})
    district_payload = district_api.get_json(silent=True) or {}
    print("DISTRICT API", district_api.status_code, district_payload.get("count"))
    if district_api.status_code != 200 or (district_payload.get("count") or 0) < 13:
        raise SystemExit("District master API did not return Uttarakhand districts")
    fps_api = client.get("/public-report/api/pds/fps", headers={"Accept": "application/json"})
    fps_payload = fps_api.get_json(silent=True) or {}
    fps_rows = fps_payload.get("rows") or []
    tara_fps = [
        row
        for row in fps_rows
        if "TARA" in f"{row.get('fps_name') or ''} {row.get('dealer_name') or ''}".upper()
    ]
    tara = client.get("/public-report/api/dealers?q=tara", headers={"Accept": "application/json"})
    tara_payload = tara.get_json(silent=True) or {}
    tara_names = " ".join(
        f"{row.get('dealer_name') or ''} {row.get('shop_name') or ''}"
        for row in (tara_payload.get("rows") or [])
    ).upper()
    print("TARA SEARCH", tara.status_code, tara_payload.get("count"), tara_names or tara_payload.get("error"))
    if tara_fps and "TARA" not in tara_names:
        raise SystemExit("FPS Master shop TARA was not found in dealer search")
    html = page.get_data(as_text=True)
    if 'id="rcDealerGrid"' not in html:
        raise SystemExit("FPS detail page is missing the dealer grid")
    grid_api = client.get("/public-report/api/dealers", headers={"Accept": "application/json"})
    grid_payload = grid_api.get_json(silent=True) or {}
    print("DEALER GRID", grid_api.status_code, grid_payload.get("count"))
    if grid_api.status_code != 200 or (grid_payload.get("count") or 0) < 1:
        raise SystemExit("Dealer grid API did not return FPS shops")
    with app.app_context():
        svc = RationCardReportService()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        created = svc.create_dealer(
            {
                "DealerName": f"Grid Delete Test {stamp}",
                "FPSID": f"FPSGRIDTEST{stamp}",
                "ActiveStatus": "1",
            },
            created_by="test",
        )
        deleted = svc.delete_dealer(created["dealer_id"])
        print("DELETE DEALER", created["dealer_id"], deleted)
        try:
            svc.get_dealer(created["dealer_id"])
            raise SystemExit("Deleted dealer is still available")
        except ValueError:
            pass
    token = ""
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if match:
        token = match.group(1)
    dealer_id = None
    for row in (tara_payload.get("rows") or []):
        if (row.get("fps_id") or "") == "FPS2026030500000011931":
            dealer_id = row.get("dealer_id")
            print("DEALER FROM FPS MASTER", dealer_id, row.get("dealer_name"))
            break
    if not dealer_id:
        create = client.post(
            "/public-report/api/dealers",
            data={
                "csrf_token": token,
                "DealerName": "Ramesh Chandra Pinaro",
                "FPSID": "FPS2026030500000011931",
                "ExistingFPSID": "106600400005",
                "DistrictName": "NAINITAL",
                "TehsilName": "Nainital",
                "ActiveStatus": "1",
            },
            headers={"X-CSRFToken": token, "Accept": "application/json"},
        )
        payload = create.get_json(silent=True) or {}
        print("DEALER SAVE", create.status_code, payload.get("message") or payload.get("error"))
        dealer_id = (payload.get("record") or {}).get("dealer_id")
    if not dealer_id:
        search = client.get(
            "/public-report/api/dealers?q=FPS2026030500000011931",
            headers={"Accept": "application/json"},
        )
        rows = (search.get_json(silent=True) or {}).get("rows") or []
        dealer_id = rows[0]["dealer_id"] if rows else None
        print("DEALER SEARCH", search.status_code, "id", dealer_id)
    if not dealer_id:
        raise SystemExit("Could not save or find ration dealer")
    with SAMPLE.open("rb") as handle:
        generate = client.post(
            "/public-report/api/ration-card/fps-detail/generate",
            data={
                "csrf_token": token,
                "dealer_id": str(dealer_id),
                "fps_id": "FPS2026030500000011931",
                "import_mode": "update",
                "csv_file": (handle, SAMPLE.name),
            },
            headers={"X-CSRFToken": token, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
    result = generate.get_json(silent=True) or {}
    print("GENERATE", generate.status_code, result.get("error") or result.get("totals"))
    if generate.status_code != 200 or not result.get("ok"):
        raise SystemExit(result.get("error") or "Generate failed")
    first_batch = result.get("batch_id")
    groups = result.get("groups") or []
    print("GENERATE GROUPS", len(groups), "schemes", sorted({g.get("scheme_name") for g in groups}))
    if not result.get("grid_rows"):
        raise SystemExit("Import did not return grid rows")
    master_sync = result.get("master_sync") or {}
    print("MASTER SYNC", master_sync)
    if (master_sync.get("added") or 0) + (master_sync.get("updated") or 0) != 227:
        raise SystemExit("Ration Card Master was not upserted from the CSV")
    with app.app_context():
        from app.models.ration_card import PdsFpsMaster, PdsRationCardMaster

        fps = PdsFpsMaster.query.filter(PdsFpsMaster.FpsCode == "FPS2026030500000011931").first()
        if fps is None:
            raise SystemExit("FPS Master shop missing for Ration Card Master sync")
        cards = PdsRationCardMaster.query.filter(PdsRationCardMaster.FpsRowID == fps.FpsRowID).all()
        print("RATION CARD MASTER", len(cards), "members sample", cards[0].MemberCount if cards else None)
        if len(cards) != 227:
            raise SystemExit(f"Ration Card Master expected 227 cards, got {len(cards)}")
        if any(not card.MemberCount for card in cards):
            raise SystemExit("Ration Card Master members were not stored")
    wrong = client.post(
        "/public-report/api/ration-card/fps-detail/generate",
        data={
            "csrf_token": token,
            "dealer_id": str(dealer_id),
            "fps_id": "FPS2026030500000011931",
            "csv_file": (
                BytesIO(
                    b"Tehsil Name,Scheme Name,FPS ID,RC Number,Member ID,Full Name,Is HOF\n"
                    b"Nainital,PHH,WRONGFPS,RC1,M1,Test Person,Yes\n"
                ),
                "wrong-fps.csv",
            ),
        },
        headers={"X-CSRFToken": token, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    wrong_payload = wrong.get_json(silent=True) or {}
    print("FPS MISMATCH", wrong.status_code, wrong_payload.get("error"))
    if wrong.status_code == 200:
        raise SystemExit("CSV with a different FPS ID was imported")
    pdf = client.get(
        f"/public-report/api/ration-card/fps-detail/pdf?dealer_id={dealer_id}&layout=desktop",
        headers={"Accept": "application/pdf"},
    )
    print("PDF", pdf.status_code, pdf.mimetype, len(pdf.data))
    if pdf.status_code != 200 or not (pdf.data or b"").startswith(b"%PDF"):
        raise SystemExit("A4 portrait PDF was not created")
    with SAMPLE.open("rb") as handle:
        missing_mode = client.post(
            "/public-report/api/ration-card/fps-detail/generate",
            data={
                "csrf_token": token,
                "dealer_id": str(dealer_id),
                "fps_id": "FPS2026030500000011931",
                "csv_file": (handle, SAMPLE.name),
            },
            headers={"X-CSRFToken": token, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
    missing_payload = missing_mode.get_json(silent=True) or {}
    print("NEED MODE", missing_mode.status_code, missing_payload.get("error"))
    if missing_mode.status_code == 200:
        raise SystemExit("Second import did not ask for Update or Overwrite")
    with SAMPLE.open("rb") as handle:
        again = client.post(
            "/public-report/api/ration-card/fps-detail/generate",
            data={
                "csrf_token": token,
                "dealer_id": str(dealer_id),
                "fps_id": "FPS2026030500000011931",
                "import_mode": "update",
                "csv_file": (handle, SAMPLE.name),
            },
            headers={"X-CSRFToken": token, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
    again_payload = again.get_json(silent=True) or {}
    print("UPDATE", again.status_code, again_payload.get("import_mode"), again_payload.get("totals"))
    if again.status_code != 200 or again_payload.get("import_mode") != "update":
        raise SystemExit(again_payload.get("error") or "Update import failed")
    if (again_payload.get("totals") or {}).get("card_count") != 227:
        raise SystemExit("Update changed the card count for the same CSV")
    if again_payload.get("batch_id") == first_batch:
        raise SystemExit("Previous import batch was replaced instead of kept")
    if (again_payload.get("totals") or {}).get("deleted_count"):
        raise SystemExit("Same CSV marked members deleted")
    again_sync = again_payload.get("master_sync") or {}
    print("MASTER UPDATE", again_sync)
    if again_sync.get("updated") != 227 or again_sync.get("added"):
        raise SystemExit("Second import did not overwrite matching FPS ID + RC Number rows")
    with app.app_context():
        from app.models.ration_card import PdsFpsMaster, PdsRationCardMaster

        fps = PdsFpsMaster.query.filter(PdsFpsMaster.FpsCode == "FPS2026030500000011931").first()
        cards = PdsRationCardMaster.query.filter(PdsRationCardMaster.FpsRowID == fps.FpsRowID).all()
        if len(cards) != 227:
            raise SystemExit("Overwrite created extra Ration Card Master rows")
        if any(card.ExistingRcNumber for card in cards):
            raise SystemExit("Overwrite did not clear Existing RC Number")


def main() -> int:
    test_wiki_parse()
    test_parse()
    test_pdf_layouts()
    test_merge_and_fps()
    test_app()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

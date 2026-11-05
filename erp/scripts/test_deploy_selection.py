"""Selective Upload VPS manifest tests. No git writes, no SSH, no VPS deploy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.deploy_selection import (  # noqa: E402
    added_python_symbols,
    build_manifest,
    classify_changes,
    parse_porcelain_lines,
    parse_porcelain_z,
    selective_commit_args,
    text_calls_symbol,
)

SAMPLE = "\n".join(
    [
        " M erp/app/routes/utility.py",
        "M  erp/app/static/css/utility.css",
        "MM erp/app/services/dashboard_service.py",
        "?? erp/app/templates/crm/inbox.html",
        " M erp/app/modules/crm/routes.py",
        " M erp/app/__init__.py",
        "?? notes.txt",
        " D erp/app/static/js/old_utility.js",
        "R  erp/app/routes/old_dash.py -> erp/app/routes/dashboard.py",
    ]
)


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


def report():
    rows = parse_porcelain_lines(SAMPLE, repo="app")
    return classify_changes(rows, target="app")


def keys(manifest) -> list[str]:
    return [item["path"] for item in manifest["files"]]


def main() -> None:
    data = report()
    by_path = {item["path"]: item for item in data["files"]}
    check("unstaged utility route", by_path["erp/app/routes/utility.py"]["status"] == "unstaged")
    check("staged utility css", by_path["erp/app/static/css/utility.css"]["status"] == "staged")
    check("staged and unstaged dashboard service", by_path["erp/app/services/dashboard_service.py"]["status"] == "staged+unstaged")
    check("untracked inbox template", by_path["erp/app/templates/crm/inbox.html"]["status"] == "untracked")
    check("inbox files group as whatsapp", by_path["erp/app/templates/crm/inbox.html"]["module_label"] == "whatsapp")
    check("crm routes group as whatsapp", by_path["erp/app/modules/crm/routes.py"]["module_label"] == "whatsapp")
    check("shared init is review", by_path["erp/app/__init__.py"]["group"] == "shared" and by_path["erp/app/__init__.py"]["review"])
    check("unmapped notes", by_path["notes.txt"]["group"] == "unmapped")
    check("delete is its own group", by_path["erp/app/static/js/old_utility.js"]["group"] == "deletes_renames")
    check("rename is its own group", by_path["erp/app/routes/dashboard.py"]["group"] == "deletes_renames")
    check("rename keeps old path", by_path["erp/app/routes/dashboard.py"]["old_path"] == "erp/app/routes/old_dash.py")

    utility = next(item for item in data["modules"] if item["label"] == "utility")
    whatsapp = next(item for item in data["modules"] if item["label"] == "whatsapp")
    check("utility module count", utility["count"] == 2 and set(utility["files"]) == {
        "erp/app/routes/utility.py",
        "erp/app/static/css/utility.css",
    })
    check("whatsapp module count", whatsapp["count"] == 2 and set(whatsapp["files"]) == {
        "erp/app/templates/crm/inbox.html",
        "erp/app/modules/crm/routes.py",
    })

    one = build_manifest(data, [utility["id"]], {})
    check("one module manifest", keys(one) == [
        "erp/app/static/css/utility.css",
        "erp/app/routes/utility.py",
    ] or set(keys(one)) == {
        "erp/app/static/css/utility.css",
        "erp/app/routes/utility.py",
    })
    check("one module excludes whatsapp", "erp/app/modules/crm/routes.py" not in keys(one))
    check("one module blocked on review files", not one["ready"] and any(item["path"] == "notes.txt" for item in one["blocked"]))

    both = build_manifest(data, [utility["id"], whatsapp["id"]], {
        "app:erp/app/__init__.py": "skip",
        "app:notes.txt": "skip",
        "app:erp/app/static/js/old_utility.js": "skip",
        "app:erp/app/routes/dashboard.py": "skip",
    })
    both_paths = set(keys(both))
    check("two modules ready", both["ready"])
    check("two modules include union", both_paths == {
        "erp/app/routes/utility.py",
        "erp/app/static/css/utility.css",
        "erp/app/templates/crm/inbox.html",
        "erp/app/modules/crm/routes.py",
    })
    scattered = parse_porcelain_lines(
        "\n".join(
            [
                " M erp/app/modules/communication/whatsapp_template_catalog.py",
                " M erp/app/modules/communication/template_service.py",
                " M erp/app/modules/settings/whatsapp_meta_client.py",
                " M erp/app/static/css/crm/inbox_whatsapp.css",
                " M erp/app/static/js/crm/inbox.js",
                "?? erp/scripts/test_whatsapp_inbox_templates.py",
            ]
        ),
        repo="app",
    )
    grouped = classify_changes(scattered, target="app")
    check(
        "scattered whatsapp files are one module",
        len(grouped["modules"]) == 1 and grouped["modules"][0]["label"] == "whatsapp" and grouped["modules"][0]["count"] == 6,
    )
    check("unselected dashboard service excluded", "erp/app/services/dashboard_service.py" not in both_paths)
    check("target preserved", both["target"] == "app")

    web_rows = parse_porcelain_lines(" M css/site.css\n M index.html\n", repo="web")
    web = classify_changes(web_rows, target="web")
    web_manifest = build_manifest(web, [web["modules"][0]["id"]], {"web:index.html": "skip"})
    check("web target preserved", web_manifest["target"] == "web")
    check("web module file only", keys(web_manifest) == ["css/site.css"])

    both_target = classify_changes(
        parse_porcelain_lines(" M erp/app/routes/utility.py\n", repo="app")
        + parse_porcelain_lines(" M css/site.css\n", repo="web"),
        target="both",
    )
    check("both target preserved", both_target["target"] == "both")
    selected = [item["id"] for item in both_target["modules"] if item["label"] == "utility"]
    app_only = build_manifest(both_target, selected, {})
    check("both target can limit to app module", keys(app_only) == ["erp/app/routes/utility.py"])
    check("web file excluded when its module is not selected", "css/site.css" not in keys(app_only))

    forced = build_manifest(data, [utility["id"]], {
        "app:erp/app/__init__.py": "include",
        "app:notes.txt": "skip",
        "app:erp/app/static/js/old_utility.js": "skip",
        "app:erp/app/routes/dashboard.py": "skip",
    })
    check("explicit include adds shared file", "erp/app/__init__.py" in keys(forced) and forced["ready"])
    check("skip keeps unmapped out", "notes.txt" not in keys(forced))

    undecided = build_manifest(data, [utility["id"]], {"app:notes.txt": "skip"})
    check("missing review choice blocks deploy", not undecided["ready"])
    check("blocked file is not in the manifest", "erp/app/__init__.py" not in keys(undecided))

    args = selective_commit_args(
        ["erp/app/routes/utility.py", "erp/app/static/css/utility.css"],
        "deploy utility",
    )
    flat = " ".join(" ".join(part) for part in args)
    check("commit plan is path limited", args[0][:2] == ["add", "--"] and args[1][:3] == ["commit", "-m", "deploy utility"])
    check("commit plan has no add-all reset or clean", "-A" not in flat and "--all" not in flat and "reset" not in flat and "clean" not in flat)
    check("empty selection does not stage", selective_commit_args([], "deploy") == [])

    try:
        selective_commit_args(["../secrets.env"], "x")
        check("rejects parent path", False)
    except ValueError:
        check("rejects parent path", True)

    z_blob = " M erp/app/routes/utility.py\0R  erp/app/routes/old.py\0erp/app/routes/new.py\0"
    z_rows = parse_porcelain_z(z_blob, repo="app")
    z_paths = {(item["status"], item["path"], item["old_path"]) for item in z_rows}
    check("nul status parses rename", ("renamed", "erp/app/routes/new.py", "erp/app/routes/old.py") in z_paths)
    check("nul status parses unstaged", any(item["path"] == "erp/app/routes/utility.py" and item["status"] == "unstaged" for item in z_rows))

    check("new method is an added symbol", added_python_symbols("class Repo:\n    pass\n", "class Repo:\n    def ensure_gst_month_column(self):\n        return None\n") == {"ensure_gst_month_column"})
    check("sql bind is not a call", not text_calls_symbol("UPPER(BillNo) = :bill_key", "bill_key"))
    check("method call counts", text_calls_symbol("FollowupRepository().ensure_gst_month_column()", "ensure_gst_month_column"))

    locked = report()
    review_skips = {
        item["key"]: "skip"
        for item in locked["files"]
        if item["review"]
    }
    follow = next(item for item in locked["modules"] if item["label"] == "utility")
    follow["mandatory"] = True
    follow["requires"] = []
    auto = build_manifest(locked, [], review_skips)
    check("mandatory module is included without a click", set(follow["files"]).issubset(set(keys(auto))) and auto["ready"])
    check("mandatory module id is selected", follow["id"] in auto["selected_modules"])
    print("ALL PASS")


if __name__ == "__main__":
    main()

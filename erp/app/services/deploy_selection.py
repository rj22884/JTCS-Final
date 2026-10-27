"""Map local git changes to deploy modules and build a selective manifest.

Pure helpers: no git writes, no SSH, no VPS deploy.
"""

from __future__ import annotations

import re
from typing import Any

DEPLOY_TARGETS = ("app", "web", "both")

SHARED_EXACT = frozenset(
    {
        ".env",
        ".gitignore",
        "deploy_vps.env",
        "deploy_vps.env.example",
        "requirements.txt",
        "erp/.env",
        "erp/requirements.txt",
        "erp/run.py",
        "erp/wsgi.py",
        "erp/app/__init__.py",
        "erp/app/config.py",
        "erp/app/decorators.py",
        "erp/app/extensions.py",
        "erp/app/static/css/erp.css",
        "erp/app/static/js/jtcs_page_windows.js",
    }
)
SHARED_PREFIXES = (
    "erp/app/templates/layouts/",
    "erp/app/templates/partials/",
    "erp/app/utils/",
)

# Inbox template work spans CRM, communication, and settings. Keep it as one module.
WHATSAPP_EXACT = frozenset(
    {
        "erp/app/modules/communication/template_service.py",
        "erp/app/modules/crm/routes.py",
        "erp/app/static/js/crm/inbox.js",
        "erp/app/static/js/crm/inbox_templates.js",
        "erp/app/templates/crm/inbox.html",
    }
)

_DIR_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^erp/app/modules/([^/]+)/"), "dir"),
    (re.compile(r"^erp/app/templates/([^/]+)/"), "dir"),
    (re.compile(r"^erp/app/static/js/([^/]+)/"), "dir"),
    (re.compile(r"^erp/app/static/css/([^/]+)/"), "dir"),
    (re.compile(r"^erp/app/services/([^/]+)/"), "dir"),
    (re.compile(r"^erp/app/customer_portal/"), "customer-portal"),
    (re.compile(r"^erp/app/customer_master/"), "customer-master"),
    (re.compile(r"^erp/database/"), "database"),
    (re.compile(r"^deployment/"), "deployment"),
    (re.compile(r"^recruitment/"), "recruitment"),
    (re.compile(r"^frontend/"), "frontend"),
    (re.compile(r"^backend/"), "backend"),
    (re.compile(r"^scripts/"), "scripts"),
    (re.compile(r"^erp/scripts/"), "erp-scripts"),
    (re.compile(r"^erp/app/routes/([^/]+)\.py$"), "file"),
    (re.compile(r"^erp/app/services/([^/]+)\.py$"), "service"),
    (re.compile(r"^erp/app/repositories/([^/]+)\.py$"), "repository"),
    (re.compile(r"^erp/app/models/([^/]+)\.py$"), "file"),
    (re.compile(r"^erp/app/static/js/([^/]+)\.js$"), "file"),
    (re.compile(r"^erp/app/static/css/([^/]+)\.css$"), "file"),
)

_WEB_SHARED_EXACT = frozenset({".env", "deploy.config.bat", "web.config"})
_WEB_SHARED_PREFIXES = (".env",)


def normalize_rel_path(path: str) -> str:
    text = (path or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ValueError("Unsafe deploy path.")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError("Unsafe deploy path.")
    return "/".join(parts)


def describe_status(xy: str) -> str:
    code = ((xy or "  ") + "  ")[:2]
    if code == "??":
        return "untracked"
    if "R" in code:
        return "renamed"
    if "C" in code:
        return "copied"
    if "D" in code:
        return "deleted"
    staged = code[0] not in " ?"
    unstaged = code[1] not in " ?"
    if staged and unstaged:
        return "staged+unstaged"
    if staged:
        return "staged"
    if unstaged:
        return "unstaged"
    return "changed"


def _stem(name: str, *, kind: str) -> str:
    if name in {"__init__", "__main__"}:
        return ""
    if kind == "service" and name.endswith("_service") and name != "_service":
        name = name[: -len("_service")]
    elif kind == "repository" and name.endswith("_repository") and name != "_repository":
        name = name[: -len("_repository")]
    return name


def _mapping(module_id: str, *, kind: str) -> dict[str, str]:
    return {
        "module_id": module_id,
        "module_label": module_id,
        "map_kind": kind,
    }


def _is_whatsapp_feature(norm: str) -> bool:
    if norm in WHATSAPP_EXACT:
        return True
    lower = norm.lower()
    return "whatsapp" in lower or "inbox_templates" in lower


def map_app_path(path: str) -> dict[str, str]:
    norm = normalize_rel_path(path)
    if norm in SHARED_EXACT or any(norm.startswith(prefix) for prefix in SHARED_PREFIXES):
        return _mapping("shared", kind="shared")
    if _is_whatsapp_feature(norm):
        return _mapping("whatsapp", kind="module")
    for pattern, kind in _DIR_RULES:
        match = pattern.search(norm)
        if not match:
            continue
        if kind in {"dir", "file", "service", "repository"}:
            module_id = _stem(match.group(1), kind=kind)
            if not module_id:
                return _mapping("uncertain", kind="uncertain")
            return _mapping(module_id, kind="module")
        return _mapping(kind, kind="module")
    if norm.endswith("/__init__.py") or norm.endswith("__init__.py"):
        return _mapping("uncertain", kind="uncertain")
    return _mapping("unmapped", kind="unmapped")


def map_web_path(path: str) -> dict[str, str]:
    norm = normalize_rel_path(path)
    name = norm.split("/")[-1]
    if norm in _WEB_SHARED_EXACT or name in _WEB_SHARED_EXACT or name.startswith(".env"):
        return _mapping("shared", kind="shared")
    parts = norm.split("/")
    if len(parts) < 2:
        return _mapping("unmapped", kind="unmapped")
    return _mapping(parts[0], kind="module")


def map_path(repo: str, path: str) -> dict[str, str]:
    if repo == "web":
        return map_web_path(path)
    return map_app_path(path)


def parse_porcelain_z(blob: str, *, repo: str) -> list[dict[str, Any]]:
    """Parse `git status --porcelain=v1 -z` output. Rename records use two paths."""
    if not blob:
        return []
    parts = blob.split("\0")
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            continue
        xy = record[:2]
        path = record[3:]
        old_path = ""
        if "R" in xy or "C" in xy:
            if index >= len(parts):
                break
            old_path = path
            path = parts[index]
            index += 1
        rows.append(_raw_change(repo, xy, path, old_path))
    return rows


def parse_porcelain_lines(text: str, *, repo: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:]
        old_path = ""
        if " -> " in path and ("R" in xy or "C" in xy):
            old_path, path = path.split(" -> ", 1)
        rows.append(_raw_change(repo, xy, path, old_path))
    return rows


def _raw_change(repo: str, xy: str, path: str, old_path: str) -> dict[str, Any]:
    clean = normalize_rel_path(path)
    old = normalize_rel_path(old_path) if old_path else ""
    status = describe_status(xy)
    mapping = map_path(repo, clean)
    structural = status in {"deleted", "renamed", "copied"}
    if structural:
        group = "deletes_renames"
    else:
        group = {
            "shared": "shared",
            "unmapped": "unmapped",
            "uncertain": "uncertain",
        }.get(mapping["map_kind"], "module")
    review = group != "module"
    commit_paths = [clean]
    if old and old not in commit_paths:
        commit_paths.insert(0, old)
    return {
        "key": f"{repo}:{clean}",
        "repo": repo,
        "path": clean,
        "old_path": old,
        "xy": xy,
        "status": status,
        "module_id": "" if review else mapping["module_id"],
        "module_label": mapping["module_label"],
        "suggested_module": mapping["module_label"],
        "group": group,
        "review": review,
        "commit_paths": commit_paths,
    }


def classify_changes(rows: list[dict[str, Any]], *, target: str) -> dict[str, Any]:
    if target not in DEPLOY_TARGETS:
        raise ValueError("Invalid upload target. Use app, web, or both.")
    files = sorted(rows, key=lambda item: (item.get("repo") or "", item.get("path") or ""))
    modules: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = {
        "shared": [],
        "unmapped": [],
        "deletes_renames": [],
        "uncertain": [],
    }
    for item in files:
        if item["review"]:
            groups[item["group"]].append(item)
            continue
        module_key = f"{item['repo']}:{item['module_id']}"
        item["module_id"] = module_key
        bucket = modules.setdefault(
            module_key,
            {
                "id": module_key,
                "label": item["module_label"],
                "repo": item["repo"],
                "files": [],
                "related_review": [],
            },
        )
        bucket["files"].append(item)
    for item in files:
        if not item["review"]:
            continue
        suggested_key = f"{item.get('repo') or ''}:{item.get('suggested_module') or ''}"
        if suggested_key in modules:
            modules[suggested_key]["related_review"].append(item["key"])
    module_rows = []
    for module in modules.values():
        module_rows.append(
            {
                "id": module["id"],
                "label": module["label"],
                "repo": module["repo"],
                "count": len(module["files"]),
                "files": [entry["path"] for entry in module["files"]],
                "related_review_count": len(module["related_review"]),
            }
        )
    module_rows.sort(key=lambda item: (item["repo"], item["label"]))
    return {
        "target": target,
        "files": files,
        "modules": module_rows,
        "groups": {
            name: [
                {
                    "key": item["key"],
                    "repo": item["repo"],
                    "path": item["path"],
                    "old_path": item["old_path"],
                    "status": item["status"],
                    "suggested_module": item["suggested_module"],
                }
                for item in group_files
            ]
            for name, group_files in groups.items()
        },
    }


_SYMBOL_RE = re.compile(
    r"^[ \t]*(?:async[ \t]+def|def|class)[ \t]+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)


def added_python_symbols(before: str, after: str) -> set[str]:
    """Names defined in the working copy that are not in the published copy."""
    added = set(_SYMBOL_RE.findall(after or "")) - set(_SYMBOL_RE.findall(before or ""))
    kept: set[str] = set()
    for name in added:
        if name.startswith("_") or len(name) < 6:
            continue
        if "_" in name or name[:1].isupper():
            kept.add(name)
    return kept


def text_calls_symbol(text: str, name: str) -> bool:
    """True when text calls the symbol. SQL binds like :name do not count."""
    if not name:
        return False
    return re.search(rf"(?<![:A-Za-z0-9_]){re.escape(name)}\s*\(", text or "") is not None


def expand_selected_modules(report: dict[str, Any], selected_module_ids: set[str]) -> set[str]:
    """Keep mandatory modules, then modules required by the current selection."""
    chosen = set(selected_module_ids)
    modules = report.get("modules") or []
    requires = {
        str(module.get("id") or ""): [str(item) for item in (module.get("requires") or [])]
        for module in modules
    }
    for module in modules:
        if module.get("mandatory") and module.get("id"):
            chosen.add(str(module["id"]))
    guard = 0
    changed = True
    while changed and guard < 30:
        guard += 1
        changed = False
        for module_id in list(chosen):
            for dep in requires.get(module_id) or []:
                if dep and dep not in chosen:
                    chosen.add(dep)
                    changed = True
    return chosen


def build_manifest(
    report: dict[str, Any],
    selected_module_ids: list[str] | None,
    decisions: dict[str, str] | None,
) -> dict[str, Any]:
    """Module files follow the selection. Review files need include or skip."""
    selected = expand_selected_modules(
        report,
        {str(item) for item in (selected_module_ids or []) if str(item).strip()},
    )
    choices = decisions or {}
    included: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in report.get("files") or []:
        if item.get("review"):
            choice = str(choices.get(item["key"]) or "").strip().lower()
            if choice not in {"include", "skip"}:
                blocked.append(item)
            elif choice == "include":
                included.append(item)
            continue
        if item.get("module_id") in selected:
            included.append(item)
    commit_paths = {"app": [], "web": []}
    seen = {"app": set(), "web": set()}
    for item in included:
        repo = item.get("repo") or "app"
        if repo not in commit_paths:
            continue
        for path in item.get("commit_paths") or []:
            safe = normalize_rel_path(path)
            if safe in seen[repo]:
                continue
            seen[repo].add(safe)
            commit_paths[repo].append(safe)
    return {
        "ready": not blocked,
        "target": report.get("target"),
        "selected_modules": sorted(selected),
        "files": included,
        "blocked": blocked,
        "commit_paths": commit_paths,
        "file_keys": [item["key"] for item in included],
    }


def selective_commit_args(paths: list[str], message: str) -> list[list[str]]:
    """Git argv for a path-limited commit. Never stages the whole tree."""
    safe = [normalize_rel_path(path) for path in paths]
    if not safe:
        return []
    if any(arg in {"-A", "--all", "reset", "clean"} for arg in safe):
        raise ValueError("Unsafe deploy path.")
    return [
        ["add", "--", *safe],
        ["commit", "-m", message, "--", *safe],
    ]

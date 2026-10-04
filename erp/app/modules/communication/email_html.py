"""Turn a received email into the same HTML Outlook shows, without scripts."""

from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import unquote

_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "center", "div", "em", "font", "h1", "h2", "h3", "h4",
    "hr", "i", "img", "li", "ol", "p", "pre", "span", "strong", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "u", "ul",
}
_VOID_TAGS = {"br", "hr", "img"}
_SKIP_TAGS = {"script", "style", "iframe", "object", "embed", "form", "title"}
_SAFE_STYLE = re.compile(
    r"^(color|background-color|background|font-size|font-family|font-weight|font-style|"
    r"text-align|text-decoration|vertical-align|line-height|margin|margin-top|margin-bottom|"
    r"margin-left|margin-right|padding|padding-top|padding-bottom|padding-left|padding-right|"
    r"border|border-top|border-bottom|border-left|border-right|border-collapse|border-spacing|"
    r"width|height|max-width|display|white-space)$",
    re.I,
)
_UNSAFE_STYLE_VALUE = re.compile(r"expression|javascript:|@import|url\s*\(", re.I)


def html_to_plain(html: str) -> str:
    """Readable text for the conversation preview. Tables stay on separate rows."""
    text = html or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|h[1-6]|li|table|blockquote)>", "\n", text)
    text = re.sub(r"(?i)<t[dh][^>]*>", "\t", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_style(value: str) -> str:
    kept: list[str] = []
    for chunk in (value or "").split(";"):
        if ":" not in chunk:
            continue
        name, raw = chunk.split(":", 1)
        name = name.strip().lower()
        raw = raw.strip()
        if not _SAFE_STYLE.match(name) or not raw or _UNSAFE_STYLE_VALUE.search(raw):
            continue
        kept.append(f"{name}: {raw}")
    return "; ".join(kept)


def _safe_url(value: str, *, image: bool, cid_map: dict[str, str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower.startswith("cid:"):
        key = unquote(raw[4:]).strip().strip("<>").lower()
        return cid_map.get(key, "")
    if image and lower.startswith("data:image/") and ";base64," in lower:
        kind = lower.split(";", 1)[0].split("/", 1)[-1]
        if kind in {"png", "jpeg", "jpg", "gif", "webp"}:
            return raw
        return ""
    if lower.startswith(("http://", "https://", "mailto:")):
        return raw
    return ""


class _Sanitizer(HTMLParser):
    def __init__(self, cid_map: dict[str, str]):
        super().__init__(convert_charrefs=True)
        self.cid_map = cid_map
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, close=True)

    def _start(self, tag: str, attrs, *, close: bool) -> None:
        tag = (tag or "").lower()
        if tag in _SKIP_TAGS:
            self.skip += 0 if close else 1
            return
        if self.skip or tag not in _ALLOWED_TAGS:
            return
        clean: list[str] = []
        for key, value in attrs:
            name = (key or "").lower()
            value = value or ""
            if name == "style":
                style = _safe_style(value)
                if style:
                    clean.append(f'style="{escape(style, quote=True)}"')
            elif name == "href" and tag == "a":
                url = _safe_url(value, image=False, cid_map=self.cid_map)
                if url:
                    clean.append(f'href="{escape(url, quote=True)}"')
            elif name == "src" and tag == "img":
                url = _safe_url(value, image=True, cid_map=self.cid_map)
                if url:
                    clean.append(f'src="{escape(url, quote=True)}"')
            elif name in {"alt", "title", "face", "color", "align", "valign", "bgcolor"}:
                clean.append(f'{name}="{escape(value, quote=True)}"')
            elif name in {"width", "height", "border", "cellpadding", "cellspacing", "colspan", "rowspan", "size"}:
                if re.fullmatch(r"[0-9.%]{1,8}", value.strip()):
                    clean.append(f'{name}="{escape(value.strip(), quote=True)}"')
        if tag == "img" and not any(item.startswith("src=") for item in clean):
            return
        if tag == "a":
            clean.append('rel="noopener noreferrer"')
            if any(item.startswith("href=") for item in clean):
                clean.append('target="_blank"')
        attr = (" " + " ".join(clean)) if clean else ""
        if tag in _VOID_TAGS:
            self.parts.append(f"<{tag}{attr}>")
        else:
            self.parts.append(f"<{tag}{attr}>")

    def handle_endtag(self, tag):
        tag = (tag or "").lower()
        if tag in _SKIP_TAGS:
            if self.skip:
                self.skip -= 1
            return
        if self.skip or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip or not data:
            return
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        if not self.skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.parts.append(f"&#{name};")


def sanitize_email_html(html: str, *, cid_map: dict[str, str] | None = None) -> str:
    parser = _Sanitizer(cid_map or {})
    parser.feed(html or "")
    parser.close()
    return "".join(parser.parts).strip()

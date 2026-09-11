from __future__ import annotations

import csv
import io
import re
from collections import OrderedDict
from xml.sax.saxutils import escape as xml_escape

from pathlib import Path

from sqlalchemy import func, or_, select

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.ration_card import PdsDistrictMaster, PdsFpsMaster, RationCardMember
from app.repositories.pds_master_repository import PdsMasterRepository
from app.repositories.ration_dealer_repository import RationDealerRepository
from app.services.pds_master_service import PdsMasterService
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused
from app.utils.timezone import now_app

HEADER_MAP = {
    "district name": "district_name",
    "tehsil name": "tehsil_name",
    "scheme name": "scheme_name",
    "existing fps id": "existing_fps_id",
    "fps id": "fps_id",
    "rc number": "rc_number",
    "existing rc number": "existing_rc_number",
    "member id": "member_id",
    "existing member id": "existing_member_id",
    "full name": "full_name",
    "father name": "father_name",
    "mother name": "mother_name",
    "gender": "gender",
    "mobile number": "mobile_number",
    "age": "age",
    "is hof": "is_hof",
    "ekyc": "ekyc",
    "uid status": "uid_status",
}

REQUIRED_HEADERS = ("tehsil name", "scheme name", "fps id")
SCHEME_ORDER = {"AAY": 0, "PHH": 1, "SFY": 2, "NER": 3, "NPHH": 4}
SCHEME_LABELS = {
    "AAY": "Antyodaya Anna Yojana (AAY)",
    "PHH": "Priority Household (PHH)",
    "SFY": "SFY",
    "NER": "NER",
    "NPHH": "Non-Priority Household (NPHH)",
}
SCHEME_HINDI_COLORS = {
    "AAY": "#9F1853",
    "SFY": "#A16207",
    "PHH": "#A8A29E",
    "NER": "#166534",
}
EMPTY_TOKENS = {"", "null", "na", "n/a", "none", "-", "nil"}
MEMBER_DATA_KEYS = (
    "district_name",
    "tehsil_name",
    "scheme_name",
    "existing_fps_id",
    "fps_id",
    "rc_number",
    "existing_rc_number",
    "member_id",
    "existing_member_id",
    "full_name",
    "father_name",
    "mother_name",
    "gender",
    "mobile_number",
    "age",
    "is_hof",
    "ekyc",
    "uid_status",
    "row_number",
    "change_status",
    "change_detail",
)
COMPARE_FIELDS = (
    ("scheme_name", "Scheme"),
    ("rc_number", "RC Number"),
    ("existing_rc_number", "Existing RC"),
    ("member_id", "Member ID"),
    ("full_name", "Full Name"),
    ("father_name", "Father Name"),
    ("mother_name", "Mother Name"),
    ("gender", "Gender"),
    ("age", "Age"),
    ("is_hof", "HOF"),
    ("mobile_number", "Mobile"),
    ("tehsil_name", "Tehsil"),
    ("district_name", "District"),
)
CHANGE_LABELS = {
    "added": "Added",
    "updated": "Updated",
    "deleted": "Deleted",
    "unchanged": "",
}
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_HINDI_FONT_REGISTERED = False
_HINDI_FONT = "Helvetica"
_HINDI_FONT_BOLD = "Helvetica-Bold"

KNOWN_HINDI_WORDS = {
    "om": "ओम",
    "omprakash": "ओमप्रकाश",
    "prakash": "प्रकाश",
    "tejprakash": "तेजप्रकाश",
    "girish": "गिरीश",
    "kamlesh": "कमलेश",
    "mohini": "मोहिनी",
    "janki": "जांकी",
    "jankee": "जांकी",
    "devi": "देवी",
    "singh": "सिंह",
    "kumar": "कुमार",
    "kumari": "कुमारी",
    "chandra": "चन्द्र",
    "chand": "चन्द",
    "prasad": "प्रसाद",
    "lal": "लाल",
    "das": "दास",
    "ram": "राम",
    "sharma": "शर्मा",
    "verma": "वर्मा",
    "gupta": "गुप्ता",
    "mishra": "मिश्रा",
    "joshi": "जोशी",
    "pant": "पंत",
    "rawat": "रावत",
    "bisht": "बिष्ट",
    "negi": "नेगी",
    "mehra": "मेहरा",
    "tiwari": "तिवारी",
    "tivari": "तिवारी",
    "pandey": "पाण्डेय",
    "bhatt": "भट्ट",
    "dutt": "दत्त",
    "dutta": "दत्ता",
    "nath": "नाथ",
    "pal": "पाल",
    "rana": "राणा",
    "mohan": "मोहन",
    "lalit": "ललित",
    "laxmi": "लक्ष्मी",
    "lakshmi": "लक्ष्मी",
    "kailash": "कैलाश",
    "jagdish": "जगदीश",
    "krishna": "कृष्ण",
    "ramesh": "रमेश",
    "suresh": "सुरेश",
    "mahesh": "महेश",
    "ganesh": "गणेश",
    "harish": "हरीश",
    "manoj": "मनोज",
    "sanjay": "संजय",
    "vijay": "विजय",
    "ajay": "अजय",
    "jai": "जय",
    "rekha": "रेखा",
    "mamta": "ममता",
    "manju": "मंजू",
    "geeta": "गीता",
    "gita": "गीता",
    "sita": "सीता",
    "radha": "राधा",
    "pooja": "पूजा",
    "puja": "पूजा",
    "priya": "प्रिया",
    "neha": "नेहा",
    "kavita": "कविता",
    "sunita": "सुनीता",
    "anita": "अनिता",
    "lalita": "ललिता",
    "madhavi": "माधवी",
    "madhvi": "माधवी",
    "ganga": "गंगा",
    "yamuna": "यमुना",
    "neeraj": "नीरज",
    "deepak": "दीपक",
    "dinesh": "दिनेश",
    "naresh": "नरेश",
    "mukesh": "मुकेश",
    "rajesh": "राजेश",
    "kamla": "कमला",
    "kamala": "कमला",
    "palariya": "पलारिया",
    "khimuli": "खिमूली",
    "haruli": "हरूली",
    "leeladhar": "लीलाधर",
    "triloshan": "त्रिलोचन",
    "trilochan": "त्रिलोचन",
    "bhuvan": "भुवन",
    "roht": "रोहत",
    "kheemanand": "खीमानन्द",
    "krishnanand": "कृष्णानन्द",
    "dhananand": "धनानन्द",
    "madhavanand": "माधवानन्द",
    "khushbu": "खुशबू",
    "bhairav": "भैरव",
    "bharav": "भैरव",
}

_CONS = (
    ("ksh", "क्ष"),
    ("shr", "श्र"),
    ("pr", "प्र"),
    ("kr", "क्र"),
    ("tr", "त्र"),
    ("dr", "द्र"),
    ("br", "ब्र"),
    ("gr", "ग्र"),
    ("mr", "म्र"),
    ("gy", "ज्ञ"),
    ("chh", "छ"),
    ("kh", "ख"),
    ("gh", "घ"),
    ("ch", "च"),
    ("jh", "झ"),
    ("th", "थ"),
    ("dh", "ध"),
    ("ph", "फ"),
    ("bh", "भ"),
    ("sh", "श"),
    ("k", "क"),
    ("q", "क"),
    ("g", "ग"),
    ("c", "क"),
    ("j", "ज"),
    ("z", "ज"),
    ("t", "त"),
    ("d", "द"),
    ("n", "न"),
    ("p", "प"),
    ("f", "फ"),
    ("b", "ब"),
    ("m", "म"),
    ("y", "य"),
    ("r", "र"),
    ("l", "ल"),
    ("v", "व"),
    ("w", "व"),
    ("s", "स"),
    ("h", "ह"),
    ("x", "क्स"),
)
_VOWELS = (
    ("aa", "आ", "ा"),
    ("ee", "ई", "ी"),
    ("ii", "ई", "ी"),
    ("oo", "ऊ", "ू"),
    ("uu", "ऊ", "ू"),
    ("ai", "ऐ", "ै"),
    ("au", "औ", "ौ"),
    ("a", "अ", ""),
    ("i", "इ", "ि"),
    ("u", "उ", "ु"),
    ("e", "ए", "े"),
    ("o", "ओ", "ो"),
)
_ANUSVARA_NEXT = {"k", "kh", "g", "gh", "ch", "chh", "j", "jh", "t", "th", "d", "dh", "p", "ph", "b", "bh"}


def _match_token(text: str, index: int, tokens: tuple) -> tuple | None:
    for item in tokens:
        token = item[0]
        if text.startswith(token, index):
            return item
    return None


def _roman_to_devanagari(word: str) -> str:
    text = re.sub(r"[^A-Za-z]", "", word or "").lower()
    if not text:
        return ""
    out: list[str] = []
    index = 0
    after_cons = False
    length = len(text)
    while index < length:
        cons = _match_token(text, index, _CONS)
        vowel = _match_token(text, index, _VOWELS)
        if cons and (vowel is None or len(cons[0]) >= len(vowel[0])):
            token, glyph = cons[0], cons[1]
            if token == "n":
                nxt = _match_token(text, index + 1, _CONS)
                if nxt and nxt[0] in _ANUSVARA_NEXT:
                    out.append("ं")
                    index += 1
                    after_cons = False
                    continue
            out.append(glyph)
            index += len(token)
            after_cons = True
            continue
        if vowel:
            token, independent, matra = vowel
            at_end = index + len(token) >= length
            rest = text[index + len(token):]
            rest_cons = _match_token(rest, 0, _CONS) if rest else None
            rest_is_final_cons = bool(
                rest_cons and index + len(token) + len(rest_cons[0]) >= length
            )
            if after_cons:
                if token == "a" and rest_is_final_cons and rest_cons[0] in {"sh", "ksh", "s", "h"}:
                    out.append("ा")
                elif token == "i" and (
                    at_end or (rest_is_final_cons and rest_cons[0] in {"sh", "s"})
                ):
                    out.append("ी")
                elif at_end and token == "u":
                    out.append("ू")
                else:
                    out.append(matra)
            else:
                if at_end and token == "i":
                    out.append("ई")
                elif at_end and token == "u":
                    out.append("ऊ")
                else:
                    out.append(independent)
            index += len(token)
            after_cons = False
            continue
        index += 1
    return "".join(out)


def to_hindi_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    if DEVANAGARI_RE.search(text) and not re.search(r"[A-Za-z]", text):
        return text
    parts = []
    for word in text.split():
        key = re.sub(r"[^A-Za-z]", "", word).lower()
        if not key:
            continue
        parts.append(KNOWN_HINDI_WORDS.get(key) or _roman_to_devanagari(word))
    return " ".join(part for part in parts if part)


class _RcNumberedCanvas(Canvas):
    def __init__(self, *args, left_margin=10 * mm, right_x=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._left_margin = left_margin
        self._right_x = right_x

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_states = self._saved_page_states[:]
        page_count = len(page_states)
        for state in page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_page_number(self, page_count):
        self.setFillColor(colors.HexColor("#445566"))
        self.setFont("Helvetica", 8)
        self.drawString(self._left_margin, 4.5 * mm, f"Page {self._pageNumber} of {page_count}")
        if self._right_x:
            self.drawRightString(self._right_x, 4.5 * mm, "Generated by JTCS +919412040614")


def split_full_name(name: str) -> tuple[str, str]:
    text = " ".join(str(name or "").split())
    english = text
    extracted = ""
    match = re.search(r"^(.*)\((.*)\)\s*$", text)
    if match:
        english = match.group(1).strip() or text
        inner = match.group(2).strip()
        if DEVANAGARI_RE.search(inner):
            extracted = inner
    hindi = extracted or to_hindi_name(english)
    if english and hindi and hindi != english:
        return english, hindi
    return english or hindi, ""


def format_full_name(name: str) -> str:
    english, hindi = split_full_name(name)
    if english and hindi:
        return f"{english} ({hindi})"
    return english or hindi


def _hindi_font_paths() -> tuple[Path | None, Path | None]:
    bundled = Path(__file__).resolve().parent.parent / "static" / "fonts"
    regular = bundled / "NotoSansDevanagari-Regular.ttf"
    bold = bundled / "NotoSansDevanagari-Bold.ttf"
    return (
        regular if regular.is_file() else None,
        bold if bold.is_file() else None,
    )


def _register_hindi_font() -> tuple[str, str]:
    global _HINDI_FONT_REGISTERED, _HINDI_FONT, _HINDI_FONT_BOLD
    if _HINDI_FONT_REGISTERED:
        return _HINDI_FONT, _HINDI_FONT_BOLD
    _HINDI_FONT_REGISTERED = True
    regular, bold = _hindi_font_paths()
    try:
        if regular is not None:
            pdfmetrics.registerFont(TTFont("RcHindi", str(regular)))
            pdfmetrics.registerFont(TTFont("RcHindi-Bold", str(bold or regular)))
            _HINDI_FONT, _HINDI_FONT_BOLD = "RcHindi", "RcHindi-Bold"
            return _HINDI_FONT, _HINDI_FONT_BOLD
    except Exception:
        pass
    fonts = Path(r"C:\Windows\Fonts")
    nirmala = fonts / "Nirmala.ttc"
    mangal = fonts / "mangal.ttf"
    mangal_bold = fonts / "mangalb.ttf"
    try:
        if nirmala.is_file():
            pdfmetrics.registerFont(TTFont("RcHindi", str(nirmala), subfontIndex=0))
            try:
                pdfmetrics.registerFont(TTFont("RcHindi-Bold", str(nirmala), subfontIndex=1))
            except Exception:
                pdfmetrics.registerFont(TTFont("RcHindi-Bold", str(nirmala), subfontIndex=0))
            _HINDI_FONT, _HINDI_FONT_BOLD = "RcHindi", "RcHindi-Bold"
            return _HINDI_FONT, _HINDI_FONT_BOLD
    except Exception:
        pass
    try:
        if mangal.is_file():
            pdfmetrics.registerFont(TTFont("RcHindi", str(mangal)))
            bold_path = mangal_bold if mangal_bold.is_file() else mangal
            pdfmetrics.registerFont(TTFont("RcHindi-Bold", str(bold_path)))
            _HINDI_FONT, _HINDI_FONT_BOLD = "RcHindi", "RcHindi-Bold"
    except Exception:
        _HINDI_FONT, _HINDI_FONT_BOLD = "Helvetica", "Helvetica-Bold"
    return _HINDI_FONT, _HINDI_FONT_BOLD


def _gender_bucket(value) -> str:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE"}:
        return "male"
    if text in {"F", "FEMALE"}:
        return "female"
    return "other"


def group_member_counts(members: list[dict]) -> dict:
    male = female = age_lt_10 = age_gt_10 = 0
    for member in members or []:
        bucket = _gender_bucket(member.get("gender"))
        if bucket == "male":
            male += 1
        elif bucket == "female":
            female += 1
        age = member.get("age")
        if isinstance(age, int):
            if age < 10:
                age_lt_10 += 1
            else:
                age_gt_10 += 1
    return {
        "male_count": male,
        "female_count": female,
        "age_lt_10": age_lt_10,
        "age_gt_10": age_gt_10,
    }


class RationCardReportService:
    def __init__(self, repository: RationDealerRepository | None = None):
        self.repo = repository or RationDealerRepository()

    @staticmethod
    def _clean_cell(value) -> str:
        text = str(value if value is not None else "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            text = text[1:-1].strip()
        if text.startswith("'"):
            text = text[1:].strip()
        if text.endswith("'") and " " not in text:
            text = text[:-1].strip()
        if text.lower() in EMPTY_TOKENS:
            return ""
        return " ".join(text.split())

    @classmethod
    def _normalize_id(cls, value) -> str:
        return cls._clean_cell(value).upper()

    @classmethod
    def _parse_age(cls, value) -> int | None:
        text = cls._clean_cell(value)
        if not text:
            return None
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _parse_hof(cls, value) -> bool:
        text = cls._clean_cell(value).lower()
        return text in {"yes", "y", "true", "1", "hof"}

    @classmethod
    def _member_key(cls, row: dict) -> str:
        member_id = cls._normalize_id(row.get("member_id") or row.get("existing_member_id"))
        if member_id:
            return "M:" + member_id
        scheme = cls._normalize_id(row.get("scheme_name"))
        rc_number = cls._normalize_id(row.get("rc_number") or row.get("existing_rc_number"))
        name = cls._clean_cell(row.get("full_name")).upper()
        return f"N:{scheme}|{rc_number}|{name}"

    @classmethod
    def _clone_member(cls, row: dict) -> dict:
        item = {key: row.get(key) for key in MEMBER_DATA_KEYS}
        item["age"] = row.get("age")
        item["is_hof"] = bool(row.get("is_hof"))
        item["change_status"] = row.get("change_status") or ""
        item["change_detail"] = row.get("change_detail") or ""
        return item

    @classmethod
    def _display_field(cls, row: dict, key: str) -> str:
        value = row.get(key)
        if key == "is_hof":
            return "Yes" if value else "No"
        if key == "age":
            return "" if value is None or value == "" else str(value)
        return cls._clean_cell(value)

    @classmethod
    def _diff_detail(cls, old: dict, new: dict) -> str:
        parts = []
        for key, label in COMPARE_FIELDS:
            before = cls._display_field(old, key)
            after = cls._display_field(new, key)
            if before != after:
                parts.append(f"{label}: {before or '—'} → {after or '—'}")
        return "; ".join(parts)

    @classmethod
    def _csv_fps_keys(cls, rows: list[dict]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for row in rows:
            key = cls._normalize_id(row.get("fps_id"))
            if key and key not in seen:
                seen.add(key)
                found.append(key)
        if found:
            return found
        for row in rows:
            key = cls._normalize_id(row.get("existing_fps_id"))
            if key and key not in seen:
                seen.add(key)
                found.append(key)
        return found

    @classmethod
    def _dealer_fps_keys(cls, dealer) -> set[str]:
        keys = set()
        for value in (getattr(dealer, "FPSID", None), getattr(dealer, "ExistingFPSID", None)):
            key = cls._normalize_id(value)
            if key:
                keys.add(key)
        return keys

    @classmethod
    def assert_csv_fps_matches_dealer(cls, dealer, rows: list[dict], fps_filter: str | None = None) -> str:
        dealer_keys = cls._dealer_fps_keys(dealer)
        if not dealer_keys:
            raise ValueError("Selected FPS / ration dealer has no FPS ID. Save FPS ID on the dealer first.")
        csv_ids = cls._csv_fps_keys(rows)
        if not csv_ids:
            raise ValueError("CSV file has no FPS ID. Import cancelled.")
        if len(csv_ids) > 1:
            raise ValueError(
                "CSV file has multiple FPS IDs ("
                + ", ".join(csv_ids)
                + "). Import one FPS shop at a time."
            )
        csv_id = csv_ids[0]
        if csv_id not in dealer_keys:
            shown = dealer.FPSID or dealer.ExistingFPSID
            raise ValueError(
                f"CSV FPS ID ({csv_id}) does not match selected dealer FPS ID ({shown}). Import cancelled."
            )
        typed = cls._normalize_id(fps_filter)
        if typed and typed not in dealer_keys and typed != csv_id:
            raise ValueError(
                f"FPS ID entered on screen ({fps_filter}) does not match selected dealer / CSV FPS ID. Import cancelled."
            )
        return csv_id

    @classmethod
    def apply_import(cls, previous: list[dict], incoming: list[dict], *, mode: str) -> list[dict]:
        if not previous:
            rows = []
            for row in incoming:
                item = cls._clone_member(row)
                item["change_status"] = ""
                item["change_detail"] = ""
                rows.append(item)
            return rows

        compare_rows = previous
        if mode == "overwrite":
            compare_rows = [
                row for row in previous if (row.get("change_status") or "").lower() != "deleted"
            ]

        previous_map: dict[str, dict] = {}
        for row in compare_rows:
            previous_map[cls._member_key(row)] = row
        incoming_map: dict[str, dict] = {}
        for row in incoming:
            incoming_map[cls._member_key(row)] = row

        merged: list[dict] = []
        for key, new in incoming_map.items():
            item = cls._clone_member(new)
            old = previous_map.get(key)
            if old is None:
                item["change_status"] = "added"
                item["change_detail"] = "New in CSV"
            else:
                detail = cls._diff_detail(old, new)
                old_status = (old.get("change_status") or "").lower()
                if old_status == "deleted":
                    item["change_status"] = "added"
                    item["change_detail"] = "Restored in CSV" + (f"; {detail}" if detail else "")
                elif detail:
                    item["change_status"] = "updated"
                    item["change_detail"] = detail
                else:
                    item["change_status"] = "unchanged"
                    item["change_detail"] = ""
            merged.append(item)

        for key, old in previous_map.items():
            if key in incoming_map:
                continue
            item = cls._clone_member(old)
            item["change_status"] = "deleted"
            item["change_detail"] = "Not in new CSV"
            merged.append(item)
        return merged

    @staticmethod
    def scheme_label(scheme: str) -> str:
        key = (scheme or "").strip().upper()
        return SCHEME_LABELS.get(key, scheme or "—")

    @classmethod
    def parse_csv(cls, file_bytes: bytes, *, file_name: str = "") -> list[dict]:
        if not file_bytes:
            raise ValueError("Uploaded file is empty.")

        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("Unable to read file encoding. Save the report as CSV (UTF-8) and try again.")

        text = decoded.replace("\r\n", "\n").replace("\r", "\n")
        reader = csv.reader(io.StringIO(text))
        header_row = None
        header_index = {}
        for raw in reader:
            cells = [cls._clean_cell(cell) for cell in raw]
            if not any(cells):
                continue
            lowered = [cell.lower() for cell in cells]
            if all(name in lowered for name in REQUIRED_HEADERS):
                header_row = lowered
                header_index = {
                    HEADER_MAP[name]: idx
                    for idx, name in enumerate(lowered)
                    if name in HEADER_MAP
                }
                break
        if header_row is None:
            raise ValueError(
                "This file is not a ration-card FPS CSV. "
                "Expected columns Tehsil Name, Scheme Name, and FPS ID."
                + (f" ({file_name})" if file_name else "")
            )

        rows: list[dict] = []
        for line_no, raw in enumerate(reader, start=2):
            if not raw or not any(str(cell).strip() for cell in raw):
                continue
            record = {}
            for key, idx in header_index.items():
                record[key] = cls._clean_cell(raw[idx] if idx < len(raw) else "")
            if not any(record.values()):
                continue
            record["age"] = cls._parse_age(record.get("age"))
            record["is_hof"] = cls._parse_hof(record.get("is_hof"))
            record["row_number"] = line_no
            rows.append(record)

        if not rows:
            raise ValueError("The CSV has headers but no ration-card member rows.")
        return rows

    @classmethod
    def _member_sort_key(cls, row: dict) -> tuple:
        scheme = (row.get("scheme_name") or "").upper()
        rc_number = (row.get("rc_number") or "").upper()
        hof_rank = 0 if row.get("is_hof") else 1
        name = (row.get("full_name") or "").lower()
        return (SCHEME_ORDER.get(scheme, 99), scheme, rc_number, hof_rank, name)

    @classmethod
    def _group_sort_key(cls, group: dict) -> tuple:
        scheme = (group.get("scheme_name") or "").upper()
        rc_number = (group.get("rc_number") or "").upper()
        return (SCHEME_ORDER.get(scheme, 99), scheme, rc_number)

    @staticmethod
    def _member_within_group_key(member: dict) -> tuple:
        return (0 if member.get("is_hof") else 1, (member.get("full_name") or "").lower())

    @classmethod
    def build_report(cls, rows: list[dict], *, fps_filter: str | None = None) -> dict:
        fps_key = cls._normalize_id(fps_filter) if fps_filter else ""
        filtered = []
        skipped_fps = 0
        for row in rows:
            if fps_key:
                fps_match = cls._normalize_id(row.get("fps_id")) == fps_key
                existing_match = cls._normalize_id(row.get("existing_fps_id")) == fps_key
                if not fps_match and not existing_match:
                    skipped_fps += 1
                    continue
            filtered.append(row)

        if fps_key and not filtered:
            raise ValueError(
                f"No rows in this CSV match FPS ID {fps_filter}. "
                "Select the correct dealer FPS or clear the FPS filter."
            )

        ordered_rows = sorted(filtered, key=cls._member_sort_key)
        groups: OrderedDict[tuple[str, str], dict] = OrderedDict()
        for row in ordered_rows:
            scheme = (row.get("scheme_name") or "—").upper()
            rc_number = row.get("rc_number") or f"ROW-{row.get('row_number')}"
            key = (scheme, rc_number.upper())
            group = groups.get(key)
            if group is None:
                group = {
                    "scheme_name": scheme,
                    "scheme_label": cls.scheme_label(scheme),
                    "rc_number": row.get("rc_number") or "",
                    "existing_rc_number": row.get("existing_rc_number") or "",
                    "hof_name": "",
                    "hof_name_display": "",
                    "tehsil_name": row.get("tehsil_name") or "",
                    "fps_id": row.get("fps_id") or "",
                    "existing_fps_id": row.get("existing_fps_id") or "",
                    "district_name": row.get("district_name") or "",
                    "members": [],
                }
                groups[key] = group
            if not group["existing_rc_number"] and row.get("existing_rc_number"):
                group["existing_rc_number"] = row["existing_rc_number"]
            if not group["existing_fps_id"] and row.get("existing_fps_id"):
                group["existing_fps_id"] = row["existing_fps_id"]
            group["members"].append(row)

        for group in groups.values():
            group["members"].sort(key=cls._member_within_group_key)
            hof = next((member for member in group["members"] if member.get("is_hof")), None)
            top = hof or (group["members"][0] if group["members"] else None)
            if top:
                group["hof_name"] = top.get("full_name") or ""
                group["hof_name_display"] = format_full_name(group["hof_name"])

        ordered_groups = sorted(groups.values(), key=cls._group_sort_key)
        scheme_summary: OrderedDict[str, dict] = OrderedDict()
        male = female = other = hof = 0
        grid_rows: list[dict] = []
        for group in ordered_groups:
            group["member_count"] = len(group["members"])
            group["card_count"] = 1
            group.update(group_member_counts(group["members"]))
            if group["hof_name"] and not group.get("hof_name_display"):
                group["hof_name_display"] = format_full_name(group["hof_name"])
            scheme = group["scheme_name"]
            summary = scheme_summary.get(scheme)
            if summary is None:
                summary = {
                    "scheme_name": scheme,
                    "scheme_label": group["scheme_label"],
                    "card_count": 0,
                    "member_count": 0,
                }
                scheme_summary[scheme] = summary
            summary["card_count"] += 1
            summary["member_count"] += group["member_count"]
            for index, member in enumerate(group["members"]):
                gender = (member.get("gender") or "").strip().upper()
                if gender in {"M", "MALE"}:
                    male += 1
                elif gender in {"F", "FEMALE"}:
                    female += 1
                else:
                    other += 1
                if member.get("is_hof"):
                    hof += 1
                english_name, hindi_name = split_full_name(member.get("full_name") or "")
                grid_rows.append(
                    {
                        **member,
                        "full_name_display": format_full_name(member.get("full_name") or ""),
                        "full_name_en": english_name,
                        "full_name_hi": hindi_name,
                        "group_scheme": group["scheme_name"],
                        "group_rc": group["rc_number"],
                        "group_first": index == 0,
                        "group_member_count": group["member_count"],
                        "group_male_count": group["male_count"],
                        "group_female_count": group["female_count"],
                        "group_age_lt_10": group["age_lt_10"],
                        "group_age_gt_10": group["age_gt_10"],
                        "hof_name": group["hof_name"],
                        "hof_name_display": group.get("hof_name_display") or format_full_name(group["hof_name"]),
                    }
                )

        fps_ids = sorted({row.get("fps_id") or "" for row in ordered_rows if row.get("fps_id")})
        tehsils = sorted({row.get("tehsil_name") or "" for row in ordered_rows if row.get("tehsil_name")})
        districts = sorted({row.get("district_name") or "" for row in ordered_rows if row.get("district_name")})
        added = updated = deleted = unchanged = 0
        for row in ordered_rows:
            status = (row.get("change_status") or "").lower()
            if status == "added":
                added += 1
            elif status == "updated":
                updated += 1
            elif status == "deleted":
                deleted += 1
            elif status == "unchanged":
                unchanged += 1

        return {
            "groups": ordered_groups,
            "grid_rows": grid_rows,
            "scheme_summary": sorted(
                scheme_summary.values(),
                key=lambda item: (SCHEME_ORDER.get(item["scheme_name"], 99), item["scheme_name"]),
            ),
            "totals": {
                "member_count": len(ordered_rows),
                "card_count": len(ordered_groups),
                "group_count": len(ordered_groups),
                "male_count": male,
                "female_count": female,
                "other_count": other,
                "hof_count": hof,
                "skipped_fps": skipped_fps,
                "added_count": added,
                "updated_count": updated,
                "deleted_count": deleted,
                "unchanged_count": unchanged,
                "active_count": max(len(ordered_rows) - deleted, 0),
            },
            "fps_ids": fps_ids,
            "tehsils": tehsils,
            "districts": districts,
        }

    @staticmethod
    def _pdf_text(value) -> str:
        return xml_escape(str(value if value is not None else "").strip())

    @classmethod
    def _pdf_member_name_html(cls, member: dict, scheme_key: str) -> str:
        english_name, hindi_name = split_full_name(member.get("full_name") or "")
        hindi_color = SCHEME_HINDI_COLORS.get(scheme_key, "#44403C")
        if hindi_name:
            name_html = (
                f"{cls._pdf_text(english_name)} "
                f"(<font color='{hindi_color}'>{cls._pdf_text(hindi_name)}</font>)"
            )
        else:
            name_html = cls._pdf_text(english_name or format_full_name(member.get("full_name") or ""))
        status = (member.get("change_status") or "").lower()
        detail = cls._pdf_text(member.get("change_detail") or "")
        if status == "updated" and detail:
            name_html = f"{name_html}<br/><font size='6'>{detail}</font>"
        return name_html

    @classmethod
    def build_pdf(
        cls,
        report: dict,
        *,
        company_name: str = "Joshi Tax Consultancy & Services",
        layout: str = "desktop",
    ) -> tuple[bytes, str]:
        dealer = report.get("dealer") or {}
        totals = report.get("totals") or {}
        groups = report.get("groups") or []
        if not groups:
            raise ValueError("Import the CSV onto the grid before creating the PDF.")

        layout_key = "mobile" if str(layout or "").strip().lower() == "mobile" else "desktop"
        mobile = layout_key == "mobile"
        page = A4
        buf = io.BytesIO()
        side_margin = 8 * mm if mobile else 10 * mm
        doc = SimpleDocTemplate(
            buf,
            pagesize=page,
            leftMargin=side_margin,
            rightMargin=side_margin,
            topMargin=14 * mm if mobile else 16 * mm,
            bottomMargin=12 * mm,
        )
        hindi_font, hindi_bold = _register_hindi_font()
        styles = getSampleStyleSheet()
        title_size = 12 if mobile else 13
        cell_size = 10 if mobile else 8
        title_style = ParagraphStyle(
            "RcPdfTitle",
            parent=styles["Heading1"],
            fontName=hindi_bold,
            fontSize=title_size,
            leading=title_size + 3,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#12324d"),
            spaceAfter=2,
        )
        sub_style = ParagraphStyle(
            "RcPdfSub",
            parent=styles["Normal"],
            fontName=hindi_font,
            fontSize=9 if mobile else 8,
            leading=12 if mobile else 11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#445566"),
            spaceAfter=4,
        )
        cell_style = ParagraphStyle(
            "RcPdfCell",
            parent=styles["Normal"],
            fontName=hindi_font,
            fontSize=cell_size,
            leading=cell_size + 3,
            alignment=TA_LEFT,
        )
        head_style = ParagraphStyle(
            "RcPdfHead",
            parent=styles["Normal"],
            fontSize=cell_size,
            leading=cell_size + 2,
            alignment=TA_CENTER,
            textColor=colors.white,
            fontName=hindi_bold,
        )
        group_style = ParagraphStyle(
            "RcPdfGroup",
            parent=styles["Normal"],
            fontSize=9 if mobile else 8,
            leading=12 if mobile else 11,
            textColor=colors.white,
            fontName=hindi_bold,
        )
        hof_style = ParagraphStyle(
            "RcPdfHof",
            parent=cell_style,
            fontName=hindi_bold,
            textColor=colors.HexColor("#0b3b4d"),
        )
        added_style = ParagraphStyle(
            "RcPdfAdded",
            parent=cell_style,
            textColor=colors.HexColor("#15803d"),
            fontName=hindi_bold,
        )
        deleted_style = ParagraphStyle(
            "RcPdfDeleted",
            parent=cell_style,
            textColor=colors.HexColor("#b91c1c"),
            fontName=hindi_bold,
        )
        updated_style = ParagraphStyle(
            "RcPdfUpdated",
            parent=cell_style,
            textColor=colors.HexColor("#1d4ed8"),
        )

        dealer_name = dealer.get("dealer_name") or ""
        fps_id = dealer.get("fps_id") or (report.get("fps_ids") or [""])[0]
        existing_fps = dealer.get("existing_fps_id") or ""
        district = (report.get("districts") or [dealer.get("district_name") or ""])[0]
        generated = report.get("generated_at") or ""
        import_mode = (report.get("import_mode") or "").title()
        subtitle = "  |  ".join(
            part
            for part in (
                f"Dealer: {dealer_name}" if dealer_name else "",
                f"FPS ID: {fps_id}" if fps_id else "",
                f"Existing FPS: {existing_fps}" if existing_fps else "",
                f"District: {district}" if district else "",
                f"Mode: {import_mode}" if import_mode else "",
                f"Generated: {generated}" if generated else "",
            )
            if part
        )
        summary_bits = [
            f"Cards {totals.get('card_count') or 0}",
            f"Members {totals.get('member_count') or 0}",
            f"Male {totals.get('male_count') or 0}",
            f"Female {totals.get('female_count') or 0}",
        ]
        if totals.get("added_count") or totals.get("updated_count") or totals.get("deleted_count"):
            summary_bits.extend(
                [
                    f"Added {totals.get('added_count') or 0}",
                    f"Updated {totals.get('updated_count') or 0}",
                    f"Deleted {totals.get('deleted_count') or 0}",
                ]
            )
        for item in report.get("scheme_summary") or []:
            summary_bits.append(
                f"{item.get('scheme_name')}: {item.get('card_count')} cards / {item.get('member_count')} members"
            )

        usable = page[0] - (side_margin * 2)
        if mobile:
            col_keys = ("sr", "name", "rc", "change")
            col_widths = [usable * 0.08, usable * 0.50, usable * 0.26, usable * 0.16]
            headers = [
                Paragraph("Sr", head_style),
                Paragraph("Full Name", head_style),
                Paragraph("RC Number", head_style),
                Paragraph("Change", head_style),
            ]
        else:
            col_keys = ("sr", "name", "scheme", "rc", "change")
            col_widths = [usable * 0.07, usable * 0.38, usable * 0.12, usable * 0.25, usable * 0.18]
            headers = [
                Paragraph("Sr", head_style),
                Paragraph("Full Name", head_style),
                Paragraph("Scheme", head_style),
                Paragraph("RC Number", head_style),
                Paragraph("Change", head_style),
            ]
        extra_blanks = [""] * (len(col_keys) - 1)

        table_data: list[list] = []
        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), hindi_bold),
            ("FONTSIZE", (0, 0), (-1, -1), cell_size),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5d0dc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 if mobile else 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 if mobile else 3),
            ("TOPPADDING", (0, 0), (-1, -1), 4 if mobile else 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if mobile else 2),
        ]
        table_data.append(headers)
        serial = 0
        for group in groups:
            counts = group_member_counts(group.get("members") or [])
            group_bits = [
                f"Scheme: {cls._pdf_text(group.get('scheme_label') or group.get('scheme_name'))}",
                f"RC: {cls._pdf_text(group.get('rc_number'))}",
                f"Members: {group.get('member_count') or 0}",
                f"Male: {counts['male_count']}",
                f"Female: {counts['female_count']}",
                f"Age&lt;10: {counts['age_lt_10']}",
                f"Age&gt;10: {counts['age_gt_10']}",
            ]
            joiner = "<br/>" if mobile else "&nbsp;&nbsp;|&nbsp;&nbsp;"
            table_data.append(
                [Paragraph(joiner.join(group_bits), group_style)] + extra_blanks
            )
            group_row = len(table_data) - 1
            scheme_key = (group.get("scheme_name") or "").upper()
            header_color = "#0e7490"
            if scheme_key == "AAY":
                header_color = "#b45309"
            elif scheme_key == "PHH":
                header_color = "#1d4ed8"
            elif scheme_key == "SFY":
                header_color = "#ca8a04"
            elif scheme_key == "NER":
                header_color = "#166534"
            style_commands.extend(
                [
                    ("SPAN", (0, group_row), (-1, group_row)),
                    ("BACKGROUND", (0, group_row), (-1, group_row), colors.HexColor(header_color)),
                    ("TEXTCOLOR", (0, group_row), (-1, group_row), colors.white),
                    ("TOPPADDING", (0, group_row), (-1, group_row), 5 if mobile else 4),
                    ("BOTTOMPADDING", (0, group_row), (-1, group_row), 5 if mobile else 4),
                ]
            )
            for member in group.get("members") or []:
                serial += 1
                status = (member.get("change_status") or "").lower()
                if status == "deleted":
                    row_style = deleted_style
                elif status == "added":
                    row_style = added_style
                elif status == "updated":
                    row_style = updated_style
                elif member.get("is_hof"):
                    row_style = hof_style
                else:
                    row_style = cell_style
                name_html = cls._pdf_member_name_html(member, scheme_key)
                change_label = CHANGE_LABELS.get(status, "")
                cells = {
                    "sr": Paragraph(str(serial), row_style),
                    "name": Paragraph(name_html, row_style),
                    "scheme": Paragraph(cls._pdf_text(member.get("scheme_name")), row_style),
                    "rc": Paragraph(cls._pdf_text(member.get("rc_number")), row_style),
                    "change": Paragraph(change_label, row_style),
                }
                table_data.append([cells[key] for key in col_keys])

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle(style_commands))

        story = [
            Paragraph(cls._pdf_text(company_name), title_style),
            Paragraph("Ration Card Detail Report for FPS", title_style),
            Paragraph(cls._pdf_text(subtitle), sub_style),
            Paragraph(cls._pdf_text("  ·  ".join(summary_bits)), sub_style),
            Spacer(1, 4),
            table,
        ]

        def _draw_page(canvas, _doc):
            canvas.saveState()
            canvas.setFillColor(colors.HexColor("#445566"))
            canvas.setFont("Helvetica", 8)
            canvas.drawString(side_margin, page[1] - 8 * mm, company_name[:80])
            canvas.setStrokeColor(colors.HexColor("#0e7490"))
            canvas.setLineWidth(0.6)
            canvas.line(side_margin, page[1] - 10 * mm, page[0] - side_margin, page[1] - 10 * mm)
            canvas.line(side_margin, 8 * mm, page[0] - side_margin, 8 * mm)
            canvas.restoreState()

        def _canvas_maker(*args, **kwargs):
            return _RcNumberedCanvas(
                *args,
                left_margin=side_margin,
                right_x=page[0] - side_margin,
                **kwargs,
            )

        doc.build(
            story,
            onFirstPage=_draw_page,
            onLaterPages=_draw_page,
            canvasmaker=_canvas_maker,
        )
        fps_part = re.sub(r"[^A-Za-z0-9]+", "_", str(fps_id or "FPS")).strip("_") or "FPS"
        layout_part = "Mobile" if mobile else "Desktop"
        filename = f"RationCard_FPS_{fps_part}_A4_Portrait_{layout_part}.pdf"
        return buf.getvalue(), filename

    @staticmethod
    def _serialize_dealer(row) -> dict:
        return {
            "dealer_id": row.DealerID,
            "dealer_name": row.DealerName or "",
            "fps_id": row.FPSID or "",
            "existing_fps_id": row.ExistingFPSID or "",
            "district_name": row.DistrictName or "",
            "tehsil_name": row.TehsilName or "",
            "mobile_number": row.MobileNumber or "",
            "address": row.Address or "",
            "active_status": bool(row.ActiveStatus),
            "shop_name": "",
            "fps_row_id": None,
        }

    def _district_name(self, district_id: int | None) -> str:
        if not district_id:
            return ""
        district = self.repo.session.get(PdsDistrictMaster, district_id)
        return (district.DistrictName if district else "") or ""

    def _search_fps_master(self, term: str | None, *, limit: int = 400) -> list[PdsFpsMaster]:
        PdsMasterRepository(self.repo.session).ensure_schema()
        stmt = select(PdsFpsMaster)
        cleaned = (term or "").strip()
        if cleaned:
            needle = f"%{cleaned.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(PdsFpsMaster.DealerName).like(needle),
                    func.lower(PdsFpsMaster.FpsName).like(needle),
                    func.lower(PdsFpsMaster.FpsCode).like(needle),
                    func.lower(PdsFpsMaster.ExistingFpsId).like(needle),
                    func.lower(PdsFpsMaster.TehsilName).like(needle),
                    func.lower(PdsFpsMaster.MobileNumber).like(needle),
                )
            )
        stmt = stmt.order_by(PdsFpsMaster.DealerName, PdsFpsMaster.FpsName, PdsFpsMaster.FpsRowID).limit(limit)
        return list(self.repo.session.scalars(stmt).all())

    def _ensure_dealer_for_fps(self, fps: PdsFpsMaster):
        found = None
        if fps.FpsCode:
            found = self.repo.find_by_fps(fps.FpsCode)
        if found is None and fps.ExistingFpsId:
            found = self.repo.find_by_fps(fps.ExistingFpsId)
        if found is None:
            name_match = None
            if fps.DealerName:
                name_match = self.repo.find_by_name(fps.DealerName)
            if name_match is None and fps.FpsName:
                name_match = self.repo.find_by_name(fps.FpsName)
            if name_match is not None:
                fps_norm = self._normalize_id(fps.FpsCode)
                found_norm = self._normalize_id(name_match.FPSID)
                if not found_norm or not fps_norm or found_norm == fps_norm:
                    found = name_match
        district_name = self._district_name(fps.DistrictID)
        payload = {
            "DealerName": (fps.DealerName or fps.FpsName or fps.FpsCode or "FPS")[:200],
            "FPSID": (fps.FpsCode or None),
            "ExistingFPSID": (fps.ExistingFpsId or None),
            "DistrictName": district_name or None,
            "TehsilName": fps.TehsilName or None,
            "MobileNumber": fps.MobileNumber or None,
            "Address": fps.Address or None,
        }
        if found is not None:
            updates = {}
            if payload["FPSID"] and not found.FPSID:
                updates["FPSID"] = payload["FPSID"]
            if payload["ExistingFPSID"] and not found.ExistingFPSID:
                updates["ExistingFPSID"] = payload["ExistingFPSID"]
            if payload["DistrictName"] and not found.DistrictName:
                updates["DistrictName"] = payload["DistrictName"]
            if payload["TehsilName"] and not found.TehsilName:
                updates["TehsilName"] = payload["TehsilName"]
            if payload["MobileNumber"] and not found.MobileNumber:
                updates["MobileNumber"] = payload["MobileNumber"]
            if payload["Address"] and not found.Address:
                updates["Address"] = payload["Address"]
            if updates:
                self.repo.update(found, updates)
            return found
        name = payload["DealerName"]
        if self.repo.find_by_name(name):
            suffix = fps.FpsCode or str(fps.FpsRowID)
            name = f"{name} ({suffix})"[:200]
            payload["DealerName"] = name
        return self.repo.create({**payload, "CreatedBy": "FPS Master"})

    def _serialize_fps_shop(self, dealer, fps: PdsFpsMaster) -> dict:
        item = self._serialize_dealer(dealer)
        item["dealer_name"] = (fps.DealerName or fps.FpsName or dealer.DealerName or "").strip()
        item["shop_name"] = fps.FpsName or ""
        item["fps_id"] = fps.FpsCode or dealer.FPSID or ""
        item["existing_fps_id"] = fps.ExistingFpsId or dealer.ExistingFPSID or ""
        item["tehsil_name"] = fps.TehsilName or dealer.TehsilName or ""
        item["mobile_number"] = fps.MobileNumber or dealer.MobileNumber or ""
        item["address"] = fps.Address or dealer.Address or ""
        item["district_name"] = dealer.DistrictName or self._district_name(fps.DistrictID)
        item["fps_row_id"] = fps.FpsRowID
        item["active_status"] = bool(fps.ActiveStatus)
        return item

    def _find_fps_for_dealer(self, dealer) -> PdsFpsMaster | None:
        PdsMasterRepository(self.repo.session).ensure_schema()
        codes = []
        for value in (dealer.FPSID, dealer.ExistingFPSID):
            key = self._normalize_id(value).lower()
            if key and key not in codes:
                codes.append(key)
        if not codes:
            return None
        stmt = select(PdsFpsMaster).where(
            or_(
                func.lower(PdsFpsMaster.FpsCode).in_(codes),
                func.lower(PdsFpsMaster.ExistingFpsId).in_(codes),
            )
        )
        return self.repo.session.scalars(stmt).first()

    def _serialize_linked(self, dealer) -> dict:
        fps = self._find_fps_for_dealer(dealer)
        if fps is not None:
            return self._serialize_fps_shop(dealer, fps)
        return self._serialize_dealer(dealer)

    def search_dealers(self, term: str | None = None, *, limit: int = 400) -> list[dict]:
        def _load() -> list[dict]:
            fps_rows = self._search_fps_master(term, limit=limit)
            results: list[dict] = []
            seen_ids: set[int] = set()
            seen_fps: set[str] = set()
            for fps in fps_rows:
                dealer = self._ensure_dealer_for_fps(fps)
                results.append(self._serialize_fps_shop(dealer, fps))
                seen_ids.add(dealer.DealerID)
                if dealer.FPSID:
                    seen_fps.add(self._normalize_id(dealer.FPSID))
                if fps.FpsCode:
                    seen_fps.add(self._normalize_id(fps.FpsCode))
            for row in self.repo.search(term, limit=limit):
                if row.DealerID in seen_ids:
                    continue
                if row.FPSID and self._normalize_id(row.FPSID) in seen_fps:
                    continue
                results.append(self._serialize_dealer(row))
            return results

        return persist(_load)

    def get_dealer(self, dealer_id: int) -> dict:
        row = self.repo.get_by_id(dealer_id)
        if row is None:
            raise ValueError("Ration dealer not found.")
        return self._serialize_linked(row)

    def find_dealer_by_fps(self, fps_id: str) -> dict | None:
        cleaned = self._clean_cell(fps_id)
        row = self.repo.find_by_fps(cleaned)
        if row is not None:
            return self._serialize_linked(row)

        def _from_master() -> dict | None:
            needle = self._normalize_id(cleaned)
            if not needle:
                return None
            for fps in self._search_fps_master(cleaned, limit=20):
                if self._normalize_id(fps.FpsCode) == needle or self._normalize_id(fps.ExistingFpsId) == needle:
                    dealer = self._ensure_dealer_for_fps(fps)
                    return self._serialize_fps_shop(dealer, fps)
            return None

        return persist(_from_master)

    def _parse_dealer_form(self, form: dict) -> dict:
        name = self._clean_cell(form.get("DealerName") or form.get("dealer_name"))
        if not name:
            raise ValueError("Ration dealer name is required.")
        fps_id = self._clean_cell(form.get("FPSID") or form.get("fps_id"))
        existing = self._clean_cell(form.get("ExistingFPSID") or form.get("existing_fps_id"))
        active_raw = str(form.get("ActiveStatus") if "ActiveStatus" in form else form.get("active_status", "1")).strip().lower()
        if "ActiveStatus" in form or "active_status" in form:
            active = active_raw in {"1", "true", "on", "yes"}
        else:
            active = True
        return {
            "DealerName": name[:200],
            "FPSID": fps_id[:80] or None,
            "ExistingFPSID": existing[:80] or None,
            "DistrictName": (self._clean_cell(form.get("DistrictName") or form.get("district_name")) or None),
            "TehsilName": (self._clean_cell(form.get("TehsilName") or form.get("tehsil_name")) or None),
            "MobileNumber": (self._clean_cell(form.get("MobileNumber") or form.get("mobile_number")) or None),
            "Address": (self._clean_cell(form.get("Address") or form.get("address")) or None),
            "ActiveStatus": active,
        }

    def _assert_unique(self, data: dict, *, exclude_id: int | None = None) -> None:
        existing_name = self.repo.find_by_name(data["DealerName"], exclude_id=exclude_id)
        if existing_name:
            raise ValueError("A ration dealer with this name already exists.")
        if data.get("FPSID"):
            existing_fps = self.repo.find_by_fps(data["FPSID"], exclude_id=exclude_id)
            if existing_fps and self._normalize_id(existing_fps.FPSID) == self._normalize_id(data["FPSID"]):
                raise ValueError(f"FPS ID {data['FPSID']} is already used by {existing_fps.DealerName}.")

    def create_dealer(self, form: dict, *, created_by: str = "System") -> dict:
        data = self._parse_dealer_form(form)
        self._assert_unique(data)

        def _write() -> dict:
            row = self.repo.create({**data, "CreatedBy": created_by})
            return self._serialize_linked(row)

        return persist(_write)

    def update_dealer(self, dealer_id: int, form: dict, *, modified_by: str = "System") -> dict:
        data = self._parse_dealer_form(form)
        self._assert_unique(data, exclude_id=dealer_id)

        def _write() -> dict:
            row = self.repo.get_by_id(dealer_id)
            if row is None:
                raise ValueError("Ration dealer not found.")
            fps = self._find_fps_for_dealer(row)
            self.repo.update(row, {**data, "ModifiedBy": modified_by})
            if fps is not None:
                fps.DealerName = row.DealerName
                if row.FPSID:
                    fps.FpsCode = row.FPSID
                if row.ExistingFPSID:
                    fps.ExistingFpsId = row.ExistingFPSID
                if row.TehsilName:
                    fps.TehsilName = row.TehsilName
                if row.MobileNumber:
                    fps.MobileNumber = row.MobileNumber
                if row.Address:
                    fps.Address = row.Address
                fps.ActiveStatus = bool(row.ActiveStatus)
                fps.ModifiedBy = modified_by
                fps.ModifiedDate = now_app().replace(tzinfo=None)
                self.repo.session.flush()
            return self._serialize_linked(row)

        return persist(_write)

    def delete_dealer(self, dealer_id: int) -> str:
        def _write() -> str:
            row = self.repo.get_by_id(dealer_id)
            if row is None:
                raise ValueError("Ration dealer not found.")
            fps = self._find_fps_for_dealer(row)
            if fps is not None:
                assert_master_unused(
                    table="PdsFpsMaster",
                    pk_column="FpsRowID",
                    pk_value=fps.FpsRowID,
                    display_name="FPS Master",
                    skip_tables={"RationDealerMaster", "RationCardUploadBatch", "RationCardMember"},
                )
            self.repo.delete_imports_for_dealer(row.DealerID)
            self.repo.delete(row)
            if fps is not None:
                self.repo.session.delete(fps)
                self.repo.session.flush()
            return "Ration dealer deleted."

        return persist(_write)

    def _apply_csv_defaults(self, dealer, rows: list[dict]) -> None:
        sample = rows[0]
        updates = {}
        if not dealer.FPSID and sample.get("fps_id"):
            updates["FPSID"] = sample["fps_id"][:80]
        if not dealer.ExistingFPSID and sample.get("existing_fps_id"):
            updates["ExistingFPSID"] = sample["existing_fps_id"][:80]
        if not dealer.DistrictName and sample.get("district_name"):
            updates["DistrictName"] = sample["district_name"][:120]
        if not dealer.TehsilName and sample.get("tehsil_name"):
            updates["TehsilName"] = sample["tehsil_name"][:120]
        if updates:
            self.repo.update(dealer, updates)

    def _sync_ration_card_master(self, dealer, report: dict, *, actor: str) -> dict:
        fps = self._find_fps_for_dealer(dealer)
        if fps is None:
            return {
                "added": 0,
                "updated": 0,
                "warning": "FPS Master shop not found. Ration Card Master was not updated.",
            }
        cards = []
        for group in report.get("groups") or []:
            rc_number = (group.get("rc_number") or "").strip()
            if not rc_number:
                continue
            members = [
                member
                for member in (group.get("members") or [])
                if str(member.get("change_status") or "").lower() != "deleted"
            ]
            hof = next((member for member in members if member.get("is_hof")), members[0] if members else None)
            hof_name = ""
            mobile = ""
            if hof:
                english_name, _hindi = split_full_name(hof.get("full_name") or "")
                hof_name = (english_name or hof.get("full_name") or "")[:200]
                mobile = (hof.get("mobile_number") or "").strip()
            if not mobile:
                for member in members:
                    if member.get("mobile_number"):
                        mobile = str(member.get("mobile_number") or "").strip()
                        break
            cards.append(
                {
                    "FpsRowID": fps.FpsRowID,
                    "RcNumber": rc_number[:80],
                    "ExistingRcNumber": (group.get("existing_rc_number") or None),
                    "SchemeName": (group.get("scheme_name") or None),
                    "HofName": hof_name or None,
                    "MemberCount": len(members),
                    "MobileNumber": mobile[:20] or None,
                    "ActiveStatus": True,
                }
            )
        pds = PdsMasterService(PdsMasterRepository(self.repo.session))
        return pds.upsert_ration_cards(cards, actor=actor)

    def _member_dict(self, item: RationCardMember) -> dict:
        return {
            "district_name": item.DistrictName or "",
            "tehsil_name": item.TehsilName or "",
            "scheme_name": item.SchemeName or "",
            "existing_fps_id": item.ExistingFPSID or "",
            "fps_id": item.FPSID or "",
            "rc_number": item.RCNumber or "",
            "existing_rc_number": item.ExistingRCNumber or "",
            "member_id": item.MemberID or "",
            "existing_member_id": item.ExistingMemberID or "",
            "full_name": item.FullName or "",
            "father_name": item.FatherName or "",
            "mother_name": item.MotherName or "",
            "gender": item.Gender or "",
            "mobile_number": item.MobileNumber or "",
            "age": item.Age,
            "is_hof": bool(item.IsHOF),
            "ekyc": item.Ekyc or "",
            "uid_status": item.UIDStatus or "",
            "row_number": item.RowNumber or 0,
            "change_status": item.ChangeStatus or "",
            "change_detail": item.ChangeDetail or "",
        }

    def _previous_rows(self, dealer_id: int) -> list[dict]:
        batch = self.repo.latest_batch(dealer_id)
        if batch is None:
            return []
        return [self._member_dict(item) for item in self.repo.members_for_batch(batch.BatchID)]

    def _orm_member(self, *, batch_id: int, dealer_id: int, index: int, row: dict) -> RationCardMember:
        return RationCardMember(
            BatchID=batch_id,
            DealerID=dealer_id,
            RowNumber=row.get("row_number") or index,
            DistrictName=row.get("district_name") or None,
            TehsilName=row.get("tehsil_name") or None,
            SchemeName=row.get("scheme_name") or None,
            ExistingFPSID=row.get("existing_fps_id") or None,
            FPSID=row.get("fps_id") or None,
            RCNumber=row.get("rc_number") or None,
            ExistingRCNumber=row.get("existing_rc_number") or None,
            MemberID=row.get("member_id") or None,
            ExistingMemberID=row.get("existing_member_id") or None,
            FullName=row.get("full_name") or None,
            FatherName=row.get("father_name") or None,
            MotherName=row.get("mother_name") or None,
            Gender=row.get("gender") or None,
            MobileNumber=row.get("mobile_number") or None,
            Age=row.get("age"),
            IsHOF=bool(row.get("is_hof")),
            Ekyc=row.get("ekyc") or None,
            UIDStatus=row.get("uid_status") or None,
            ChangeStatus=(row.get("change_status") or None) or None,
            ChangeDetail=((row.get("change_detail") or "")[:800] or None),
        )

    def generate_from_csv(
        self,
        *,
        dealer_id: int,
        file_bytes: bytes,
        file_name: str,
        fps_filter: str | None = None,
        uploaded_by: str = "System",
        import_mode: str | None = None,
    ) -> dict:
        rows = self.parse_csv(file_bytes, file_name=file_name)
        fps_filter = self._clean_cell(fps_filter)
        dealer = self.repo.get_by_id(dealer_id)
        if dealer is None:
            raise ValueError("Select a ration dealer before uploading the CSV.")
        csv_fps = self.assert_csv_fps_matches_dealer(dealer, rows, fps_filter or None)
        previous = self._previous_rows(dealer.DealerID)
        mode = (import_mode or "").strip().lower()
        if previous:
            if mode not in {"update", "overwrite"}:
                raise ValueError("Imported data already exists. Choose Update or Overwrite.")
        else:
            mode = "import"
        merged = self.apply_import(previous, rows, mode=mode)
        report = self.build_report(merged)
        PdsMasterRepository(self.repo.session).ensure_schema()

        def _write() -> dict:
            current = self.repo.get_by_id(dealer_id)
            if current is None:
                raise ValueError("Select a ration dealer before uploading the CSV.")
            self._apply_csv_defaults(current, rows)
            batch = self.repo.create_batch(
                {
                    "DealerID": current.DealerID,
                    "SourceFileName": (file_name or "")[:260],
                    "FPSID": (current.FPSID or csv_fps),
                    "UploadedBy": uploaded_by,
                    "ImportMode": mode,
                    "TotalRows": report["totals"]["member_count"],
                    "CardCount": report["totals"]["card_count"],
                    "MemberCount": report["totals"]["member_count"],
                }
            )
            members = [
                self._orm_member(
                    batch_id=batch.BatchID,
                    dealer_id=current.DealerID,
                    index=index,
                    row=row,
                )
                for index, row in enumerate(merged, start=1)
            ]
            self.repo.add_members(members)
            master_sync = self._sync_ration_card_master(current, report, actor=uploaded_by)
            warnings = []
            if master_sync.get("warning"):
                warnings.append(master_sync["warning"])
            return {
                "dealer": self._serialize_dealer(current),
                "file_name": file_name,
                "generated_at": now_app().strftime("%d/%m/%Y %H:%M"),
                "batch_id": batch.BatchID,
                "import_mode": mode,
                "warnings": warnings,
                "overwritten": mode == "overwrite",
                "master_sync": master_sync,
                **report,
            }

        return persist(_write)

    def latest_report(self, dealer_id: int) -> dict | None:
        dealer = self.repo.get_by_id(dealer_id)
        if dealer is None:
            raise ValueError("Ration dealer not found.")
        batch = self.repo.latest_batch(dealer_id)
        if batch is None:
            return None
        stored = self.repo.members_for_batch(batch.BatchID)
        rows = [self._member_dict(item) for item in stored]
        if not rows:
            return None
        report = self.build_report(rows)
        return {
            "dealer": self._serialize_dealer(dealer),
            "file_name": batch.SourceFileName or "",
            "generated_at": batch.UploadedDate.strftime("%d/%m/%Y %H:%M") if batch.UploadedDate else "",
            "batch_id": batch.BatchID,
            "import_mode": batch.ImportMode or "",
            "warnings": [],
            **report,
        }

"""Income-tax WDV depreciation (Appendix I) for Item Master fixed assets."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.extensions import db

ZERO = Decimal("0.00")
PUBLIC_DEPRECIATION_CHART_URL = (
    "https://incometaxindia.gov.in/charts%20%20tables/depreciation%20rates.htm"
)

# Income-tax Rules, 1962 — Appendix I (WDV). Rate changes on 01-Apr-2017
# reduced computers/software from 60% to 40%.
_RATE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "motor-car",
        "block": "Motor cars (other than used in the business of running them on hire)",
        "rate": Decimal("15.00"),
        "rate_before_2017": Decimal("15.00"),
        "keywords": (
            "car",
            "motor car",
            "motorcar",
            "suv",
            "sedan",
            "vehicle",
            "xl6",
            "wagon",
            "jeep",
            "van",
        ),
        "hsn_prefixes": ("8703", "8704"),
    },
    {
        "key": "hire-vehicle",
        "block": "Motor buses, lorries and taxis used in the business of hire",
        "rate": Decimal("30.00"),
        "rate_before_2017": Decimal("30.00"),
        "keywords": ("taxi", "bus", "lorry", "hire vehicle", "cab"),
        "hsn_prefixes": ("8702",),
    },
    {
        "key": "computer",
        "block": "Computers including computer software",
        "rate": Decimal("40.00"),
        "rate_before_2017": Decimal("60.00"),
        "keywords": (
            "computer",
            "laptop",
            "desktop",
            "printer",
            "scanner",
            "software",
            "keyboard",
            "monitor",
            "server",
        ),
        "hsn_prefixes": ("8471", "8443"),
    },
    {
        "key": "furniture",
        "block": "Furniture and fittings including electrical fittings",
        "rate": Decimal("10.00"),
        "rate_before_2017": Decimal("10.00"),
        "keywords": ("furniture", "fitting", "chair", "table", "sofa", "almirah"),
        "hsn_prefixes": ("9401", "9402", "9403"),
    },
    {
        "key": "building-other",
        "block": "Buildings other than mainly residential",
        "rate": Decimal("10.00"),
        "rate_before_2017": Decimal("10.00"),
        "keywords": ("building", "office", "premises", "property"),
        "hsn_prefixes": (),
    },
    {
        "key": "building-residential",
        "block": "Buildings used mainly for residential purposes",
        "rate": Decimal("5.00"),
        "rate_before_2017": Decimal("5.00"),
        "keywords": ("residential building", "house", "flat"),
        "hsn_prefixes": (),
    },
    {
        "key": "ship",
        "block": "Ocean-going ships",
        "rate": Decimal("20.00"),
        "rate_before_2017": Decimal("20.00"),
        "keywords": ("ship", "vessel", "boat"),
        "hsn_prefixes": ("89",),
    },
    {
        "key": "aircraft",
        "block": "Aeroplanes — aeroengines",
        "rate": Decimal("40.00"),
        "rate_before_2017": Decimal("40.00"),
        "keywords": ("aircraft", "aeroplane", "airplane"),
        "hsn_prefixes": ("88",),
    },
    {
        "key": "intangible",
        "block": "Intangible assets (know-how, patents, copyrights, trademarks, licences)",
        "rate": Decimal("25.00"),
        "rate_before_2017": Decimal("25.00"),
        "keywords": (
            "intangible",
            "patent",
            "trademark",
            "copyright",
            "licence",
            "license",
            "goodwill",
            "know-how",
        ),
        "hsn_prefixes": (),
    },
    {
        "key": "plant-general",
        "block": "Plant and machinery — general",
        "rate": Decimal("15.00"),
        "rate_before_2017": Decimal("15.00"),
        "keywords": ("plant", "machinery", "equipment", "machine", "generator"),
        "hsn_prefixes": ("84", "85"),
    },
)


def _as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()[:10]
    if not text_value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            continue
    return None


def _money(value, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default).quantize(Decimal("0.01"))
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal(default).quantize(Decimal("0.01"))


def _rate_for_row(row: dict[str, Any], purchase: date | None) -> Decimal:
    if purchase and purchase < date(2017, 4, 1):
        return Decimal(row["rate_before_2017"])
    return Decimal(row["rate"])


class DepreciationService:
    """Public Appendix I lookup, WDV calculation, and Item → FixedAssetMaster sync."""

    PUBLIC_CHART_URL = PUBLIC_DEPRECIATION_CHART_URL
    _fa_group_ids: set[int] | None = None
    _inv_group_ids: set[int] | None = None
    _asset_col_ready = False

    @staticmethod
    def fy_start(as_of: date) -> date:
        year = as_of.year if as_of.month >= 4 else as_of.year - 1
        return date(year, 4, 1)

    @staticmethod
    def fy_end(as_of: date) -> date:
        start = DepreciationService.fy_start(as_of)
        return date(start.year + 1, 3, 31)

    def public_chart_rows(self, purchase_date: date | None = None) -> list[dict[str, Any]]:
        out = []
        for row in _RATE_ROWS:
            rate = _rate_for_row(row, purchase_date)
            out.append(
                {
                    "key": row["key"],
                    "block": row["block"],
                    "rate": str(rate),
                    "effective_from": (
                        "2005-04-01"
                        if purchase_date and purchase_date < date(2017, 4, 1)
                        else "2017-04-01"
                    ),
                }
            )
        return out

    def lookup_public_rate(
        self,
        *,
        purchase_date: date | None = None,
        item_code: str = "",
        item_name: str = "",
        hsn_sac: str = "",
        ping_public: bool = True,
    ) -> dict[str, Any]:
        """Pick Appendix I WDV % from purchase date + item/HSN. Tries official page first."""
        purchase = _as_date(purchase_date)
        if ping_public:
            self._refresh_from_public_page()
        match = self._match_block(item_code=item_code, item_name=item_name, hsn_sac=hsn_sac)
        if match is None:
            match = next(row for row in _RATE_ROWS if row["key"] == "plant-general")
        rate = _rate_for_row(match, purchase)
        return {
            "ok": True,
            "rate": str(rate),
            "method": "WDV",
            "block": match["block"],
            "block_key": match["key"],
            "purchase_date": purchase.isoformat() if purchase else "",
            "source": "Income-tax Rules, 1962 — Appendix I (WDV)",
            "source_url": self.PUBLIC_CHART_URL,
            "half_year_note": (
                "If put to use for less than 180 days in the year of purchase, "
                "only 50% of this rate is applied while calculating depreciation."
            ),
        }

    def _match_block(
        self, *, item_code: str = "", item_name: str = "", hsn_sac: str = ""
    ) -> dict[str, Any] | None:
        blob = " ".join(
            part.strip().lower()
            for part in (item_code, item_name, hsn_sac)
            if part and str(part).strip()
        )
        hsn = "".join(ch for ch in str(hsn_sac or "") if ch.isdigit())
        best = None
        best_score = 0
        for row in _RATE_ROWS:
            score = 0
            for prefix in row["hsn_prefixes"]:
                if hsn.startswith(prefix):
                    score = max(score, 80 + len(prefix))
            for word in row["keywords"]:
                if word in blob:
                    score = max(score, 40 + len(word))
            if score > best_score:
                best_score = score
                best = row
        return best if best_score else None

    def _refresh_from_public_page(self) -> None:
        """Best-effort ping of the official chart so Sync uses a live public page."""
        try:
            req = Request(
                self.PUBLIC_CHART_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; JTCS-DepreciationSync/1.0)",
                    "Accept": "text/html",
                },
            )
            with urlopen(req, timeout=4) as resp:
                resp.read(2048)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return

    @staticmethod
    def resolve_as_of(as_of: date | None, *, cap_today: bool = True) -> date:
        """Never compute depreciation past the current system date (unless tests)."""
        parsed = _as_date(as_of) or date.today()
        if not cap_today:
            return parsed
        today = date.today()
        return parsed if parsed <= today else today

    @staticmethod
    def half_year_bounds(as_of: date) -> tuple[date, date, date, date]:
        """FY halves: 01/04–30/09 and 01/10–31/03."""
        fy_s = DepreciationService.fy_start(as_of)
        fy_e = DepreciationService.fy_end(as_of)
        h1_end = date(fy_s.year, 9, 30)
        h2_start = date(fy_s.year, 10, 1)
        return fy_s, h1_end, h2_start, fy_e

    @staticmethod
    def resolve_put_to_use(
        purchase_date,
        opening_date,
        as_of: date,
    ) -> date | None:
        """Purchase date if it is on/before as-of; otherwise the opening date."""
        purchase = _as_date(purchase_date)
        opening = _as_date(opening_date)
        if purchase and purchase <= as_of:
            return purchase
        if opening and opening <= as_of:
            return opening
        return purchase or opening

    def _fy_charge(
        self,
        cost: Decimal,
        rate: Decimal,
        purchase: date | None,
        as_of: date,
        *,
        cap_to_cost: bool = True,
    ) -> tuple[Decimal, Decimal]:
        """Current-FY WDV charge on this opening: 01/04–30/09 and 01/10–31/03."""
        if cost <= ZERO or rate <= ZERO:
            return ZERO, ZERO
        if purchase and purchase > as_of:
            return ZERO, ZERO

        _fy_s, h1_end, h2_start, fy_e = self.half_year_bounds(as_of)
        annual = (cost * rate / Decimal("100")).quantize(Decimal("0.01"))
        if cap_to_cost and annual > cost:
            annual = cost
        half1 = (annual / Decimal("2")).quantize(Decimal("0.01"))
        half2 = annual - half1
        bought_in_h2 = bool(purchase and purchase >= h2_start)

        if as_of <= h1_end:
            cy = ZERO if bought_in_h2 else half1
            return cy, Decimal("1")

        if bought_in_h2:
            start = purchase if purchase and purchase > h2_start else h2_start
            elapsed = (as_of - start).days + 1
            span = (fy_e - start).days + 1
            elapsed = max(0, min(elapsed, span))
            cy = (half1 * Decimal(elapsed) / Decimal(span or 1)).quantize(Decimal("0.01"))
            return cy, Decimal("1")

        if as_of >= fy_e:
            return annual, ZERO

        h2_days = (fy_e - h2_start).days + 1
        elapsed = (as_of - h2_start).days + 1
        elapsed = max(0, min(elapsed, h2_days))
        h2_cy = (half2 * Decimal(elapsed) / Decimal(h2_days or 1)).quantize(Decimal("0.01"))
        return half1 + h2_cy, Decimal("1")

    def calculate(
        self,
        *,
        cost: Decimal,
        rate: Decimal,
        purchase_date: date | None,
        as_of: date,
        method: str = "WDV",
        opening_date: date | None = None,
        cap_today: bool = True,
    ) -> dict[str, Decimal]:
        """WDV depreciation in FY halves: 01/04–30/09 and 01/10–31/03.

        Completed years close on 31/03; that WDV becomes the 01/04 opening.
        - System date in first half → first-half (50% of annual) on current WDV.
        - System date in second half → first half + 01/10 to as-of.
        - System date 01/04 → current-year 0; closing of the year just ended.
        """
        del method
        cost = _money(cost)
        rate = _money(rate)
        as_of = self.resolve_as_of(as_of, cap_today=cap_today)
        purchase = self.resolve_put_to_use(purchase_date, opening_date, as_of)
        if cost <= ZERO:
            return {"current_year": ZERO, "wdv": ZERO, "half_year": ZERO, "accumulated": ZERO}
        if rate <= ZERO or (purchase and purchase > as_of):
            return {"current_year": ZERO, "wdv": cost, "half_year": ZERO, "accumulated": ZERO}

        book = cost
        # OpeningBalance is WDV as of opening_date (or purchase). Do not
        # close years that already sit inside that opening figure.
        basis = _as_date(opening_date) or purchase
        if basis:
            walk_fy = self.fy_start(basis)
            current_fy = self.fy_start(as_of)
            while walk_fy < current_fy:
                fy_close = date(walk_fy.year + 1, 3, 31)
                if basis <= fy_close:
                    closed, _ = self._fy_charge(book, rate, purchase, fy_close)
                    if closed > book:
                        closed = book
                    book = (book - closed).quantize(Decimal("0.01"))
                walk_fy = date(walk_fy.year + 1, 4, 1)

        # 1 April = opening of new FY; previous 31/03 closing is now WDV.
        if as_of == self.fy_start(as_of):
            acc = (cost - book).quantize(Decimal("0.01"))
            return {"current_year": ZERO, "wdv": book, "half_year": ZERO, "accumulated": acc}

        cy, half_flag = self._fy_charge(book, rate, purchase, as_of)
        if cy > book:
            cy = book
        wdv = (book - cy).quantize(Decimal("0.01"))
        if wdv < ZERO:
            wdv = ZERO
        return {
            "current_year": cy,
            "wdv": wdv,
            "half_year": half_flag,
            "accumulated": (cost - wdv).quantize(Decimal("0.01")),
        }

    def calculate_appreciation(
        self,
        *,
        cost: Decimal,
        rate: Decimal,
        purchase_date: date | None,
        as_of: date,
        opening_date: date | None = None,
        cap_today: bool = True,
    ) -> dict[str, Decimal]:
        """Investment appreciation — same FY halves as depreciation, value goes up.

        Requires cost, rate, and a put-to-use date. Missing inputs → no charge.
        """
        cost = _money(cost)
        rate = _money(rate)
        as_of = self.resolve_as_of(as_of, cap_today=cap_today)
        purchase = self.resolve_put_to_use(purchase_date, opening_date, as_of)
        empty = {
            "current_year": ZERO,
            "current_value": cost if cost > ZERO else ZERO,
            "half_year": ZERO,
            "accumulated": ZERO,
        }
        if cost <= ZERO or rate <= ZERO or purchase is None or purchase > as_of:
            return empty

        book = cost
        basis = _as_date(opening_date) or purchase
        if basis:
            walk_fy = self.fy_start(basis)
            current_fy = self.fy_start(as_of)
            while walk_fy < current_fy:
                fy_close = date(walk_fy.year + 1, 3, 31)
                if basis <= fy_close:
                    added, _ = self._fy_charge(
                        book, rate, purchase, fy_close, cap_to_cost=False
                    )
                    book = (book + added).quantize(Decimal("0.01"))
                walk_fy = date(walk_fy.year + 1, 4, 1)

        if as_of == self.fy_start(as_of):
            acc = (book - cost).quantize(Decimal("0.01"))
            return {
                "current_year": ZERO,
                "current_value": book,
                "half_year": ZERO,
                "accumulated": acc if acc > ZERO else ZERO,
            }

        cy, half_flag = self._fy_charge(book, rate, purchase, as_of, cap_to_cost=False)
        value = (book + cy).quantize(Decimal("0.01"))
        acc = (value - cost).quantize(Decimal("0.01"))
        return {
            "current_year": cy,
            "current_value": value,
            "half_year": half_flag,
            "accumulated": acc if acc > ZERO else ZERO,
        }

    def _group_ids_matching(self, hints: set[str]) -> set[int]:
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT GroupID, GroupName, ParentGroupID
                    FROM dbo.ChartOfGroupMaster
                    """
                )
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return set()
        by_id = {int(r["GroupID"]): r for r in rows}
        wanted: set[int] = set()
        for gid, row in by_id.items():
            cur = row
            hops = 0
            seen: set[int] = set()
            while cur is not None and hops < 40:
                cid = int(cur["GroupID"])
                if cid in seen:
                    break
                seen.add(cid)
                if (cur.get("GroupName") or "").strip().casefold() in hints:
                    wanted.add(gid)
                    break
                pid = cur.get("ParentGroupID")
                cur = by_id.get(int(pid)) if pid else None
                hops += 1
        return wanted

    def fixed_asset_group_ids(self, engine=None) -> set[int]:
        if DepreciationService._fa_group_ids is not None:
            return DepreciationService._fa_group_ids
        if engine is not None:
            ids = engine.fixed_asset_group_ids()
            DepreciationService._fa_group_ids = ids
            return ids
        DepreciationService._fa_group_ids = self._group_ids_matching(
            {
                "fixed assets",
                "computers printers & electric items",
                "immovable property",
            }
        )
        return DepreciationService._fa_group_ids

    def is_fixed_asset_group(self, group_id: int | None) -> bool:
        if not group_id:
            return False
        try:
            return int(group_id) in self.fixed_asset_group_ids()
        except (TypeError, ValueError):
            return False

    def investment_group_ids(self, engine=None) -> set[int]:
        if DepreciationService._inv_group_ids is not None:
            return DepreciationService._inv_group_ids
        if engine is not None:
            ids = engine.investment_group_ids()
            DepreciationService._inv_group_ids = ids
            return ids
        DepreciationService._inv_group_ids = self._group_ids_matching(
            {"investments", "investment"}
        )
        return DepreciationService._inv_group_ids

    def is_investment_group(self, group_id: int | None) -> bool:
        if not group_id:
            return False
        try:
            return int(group_id) in self.investment_group_ids()
        except (TypeError, ValueError):
            return False

    def sync_item_row(self, row) -> None:
        """Upsert / deactivate FixedAssetMaster for an Item Master row."""
        self._ensure_asset_item_column()
        item_id = int(getattr(row, "ItemID", 0) or 0)
        if not item_id:
            return
        group_id = getattr(row, "ChartGroupID", None)
        is_fa = bool(getattr(row, "IsActive", True)) and self.is_fixed_asset_group(group_id)
        existing = db.session.execute(
            text("SELECT AssetID FROM dbo.FixedAssetMaster WHERE ItemID = :id"),
            {"id": item_id},
        ).first()
        if not is_fa:
            if existing:
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.FixedAssetMaster
                        SET IsActive = 0, UpdatedDate = SYSUTCDATETIME()
                        WHERE ItemID = :id
                        """
                    ),
                    {"id": item_id},
                )
            return

        purchase = _as_date(getattr(row, "PurchaseDate", None)) or _as_date(
            getattr(row, "OpeningBalanceDate", None)
        )
        opening_date = _as_date(getattr(row, "OpeningBalanceDate", None))
        if purchase is None:
            purchase = opening_date or date.today()
        cost = _money(getattr(row, "OpeningBalance", None))
        if cost <= ZERO:
            qty = _money(getattr(row, "OpeningQty", None), "0")
            rate_amt = _money(getattr(row, "OpeningRate", None))
            cost = (qty * rate_amt).quantize(Decimal("0.01"))
        if cost <= ZERO:
            if existing:
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.FixedAssetMaster
                        SET IsActive = 0, UpdatedDate = SYSUTCDATETIME()
                        WHERE ItemID = :id
                        """
                    ),
                    {"id": item_id},
                )
            return
        dep_rate = _money(getattr(row, "DepreciationRate", None))
        name = (getattr(row, "ItemName", None) or getattr(row, "ItemCode", None) or "Asset").strip()
        computed = self.calculate(
            cost=cost,
            rate=dep_rate,
            purchase_date=purchase,
            opening_date=opening_date,
            as_of=date.today(),
            method="WDV",
        )
        params = {
            "name": name[:200],
            "gid": int(group_id) if group_id else None,
            "pdate": purchase,
            "pval": cost,
            "rate": dep_rate,
            "cy": computed["current_year"],
            "acc": computed.get("accumulated", computed["current_year"]),
            "wdv": computed["wdv"],
            "id": item_id,
        }
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.FixedAssetMaster
                    SET AssetName = :name,
                        GroupID = :gid,
                        PurchaseDate = :pdate,
                        PurchaseValue = :pval,
                        DepreciationRate = :rate,
                        CurrentYearDepreciation = :cy,
                        AccumulatedDepreciation = :acc,
                        WDV = :wdv,
                        Method = N'WDV',
                        IsActive = 1,
                        UpdatedDate = SYSUTCDATETIME()
                    WHERE ItemID = :id
                    """
                ),
                params,
            )
            return
        db.session.execute(
            text(
                """
                INSERT INTO dbo.FixedAssetMaster (
                    AssetName, ItemID, GroupID, PurchaseDate, PurchaseValue,
                    DepreciationRate, OpeningAccumulatedDep, CurrentYearDepreciation,
                    AccumulatedDepreciation, WDV, Method, IsActive, CreatedDate
                )
                VALUES (
                    :name, :id, :gid, :pdate, :pval,
                    :rate, 0, :cy, :acc, :wdv, N'WDV', 1, SYSUTCDATETIME()
                )
                """
            ),
            params,
        )

    def deactivate_item_asset(self, item_id: int) -> None:
        self._ensure_asset_item_column()
        db.session.execute(
            text(
                """
                UPDATE dbo.FixedAssetMaster
                SET IsActive = 0, UpdatedDate = SYSUTCDATETIME()
                WHERE ItemID = :id
                """
            ),
            {"id": int(item_id)},
        )

    def sync_all_item_fixed_assets(self) -> None:
        self._ensure_asset_item_column()
        fa_ids = self.fixed_asset_group_ids()
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT ItemID, ItemCode, ItemName, ChartGroupID, IsActive,
                           OpeningQty, OpeningRate, OpeningBalance, OpeningBalanceDate,
                           PurchaseDate, DepreciationRate
                    FROM dbo.ItemMaster
                    """
                )
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return
        for raw in rows:
            gid = raw.get("ChartGroupID")
            try:
                in_fa = int(gid) in fa_ids if gid else False
            except (TypeError, ValueError):
                in_fa = False
            if not in_fa:
                continue
            self.sync_item_row(_RowProxy(raw))

    def _ensure_asset_item_column(self) -> None:
        if DepreciationService._asset_col_ready:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.FixedAssetMaster', N'ItemID') IS NULL
                    ALTER TABLE dbo.FixedAssetMaster ADD ItemID INT NULL;
                """
            )
        )
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.FixedAssetMaster', N'ItemID') IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE name = N'UX_FixedAssetMaster_ItemID'
                          AND object_id = OBJECT_ID(N'dbo.FixedAssetMaster')
                   )
                BEGIN
                    CREATE UNIQUE INDEX UX_FixedAssetMaster_ItemID
                        ON dbo.FixedAssetMaster (ItemID)
                        WHERE ItemID IS NOT NULL;
                END
                """
            )
        )
        DepreciationService._asset_col_ready = True


class _RowProxy:
    """Attribute access over a SQLAlchemy mapping / dict."""

    def __init__(self, raw: Any):
        self._raw = raw

    def __getattr__(self, name: str):
        try:
            return self._raw[name]
        except Exception as exc:
            raise AttributeError(name) from exc

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app.repositories.item_master_repository import ItemMasterRepository
from app.utils.db_session import persist


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _q3(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"))


class ItemMasterService:
    def __init__(self, repository: ItemMasterRepository | None = None):
        self.repo = repository or ItemMasterRepository()

    @staticmethod
    def _money(value, default: str = "0", *, places: str = "0.01") -> Decimal:
        if value in (None, ""):
            return Decimal(default).quantize(Decimal(places))
        try:
            return Decimal(str(value)).quantize(Decimal(places))
        except (InvalidOperation, ValueError):
            return Decimal(default).quantize(Decimal(places))

    @staticmethod
    def _parse_date(value) -> date | None:
        if value in (None, ""):
            return None
        text = str(value).strip()[:10]
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("Opening balance date is invalid.") from exc

    @staticmethod
    def _serialize(row) -> dict:
        gst_applicable = bool(getattr(row, "GstApplicable", True))
        opening_qty = getattr(row, "OpeningQty", None)
        opening_rate = getattr(row, "OpeningRate", None)
        opening_balance = getattr(row, "OpeningBalance", None)
        opening_date = getattr(row, "OpeningBalanceDate", None)
        chart_group_id = getattr(row, "ChartGroupID", None)
        return {
            "item_id": row.ItemID,
            "item_code": row.ItemCode or "",
            "item_name": row.ItemName or "",
            "description": row.Description or "",
            "hsn_sac": row.HsnSac or "",
            "hsn_sac_type": row.HsnSacType or "SAC",
            "unit": row.Unit or "NOS",
            "default_rate": str(row.DefaultRate if row.DefaultRate is not None else "0.00"),
            "gst_applicable": gst_applicable,
            "gst_rate_percent": str(row.GstRatePercent if row.GstRatePercent is not None else "0.00"),
            "opening_qty": str(opening_qty if opening_qty is not None else "0.000"),
            "opening_rate": str(opening_rate if opening_rate is not None else "0.00"),
            "opening_balance": str(opening_balance if opening_balance is not None else "0.00"),
            "opening_balance_date": opening_date.isoformat() if opening_date else "",
            "chart_group_id": int(chart_group_id) if chart_group_id else None,
            "order_no": int(row.OrderNo or 100),
            "is_active": bool(row.IsActive),
            "created_at": row.CreatedAt.isoformat() if row.CreatedAt else "",
            "updated_at": row.UpdatedAt.isoformat() if row.UpdatedAt else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        return [
            self._serialize(row)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def list_active_for_dropdown(self) -> list[dict]:
        return [
            {
                "item_id": row.ItemID,
                "item_code": row.ItemCode,
                "item_name": row.ItemName,
                "hsn_sac": row.HsnSac or "",
                "hsn_sac_type": row.HsnSacType or "SAC",
                "unit": row.Unit or "NOS",
                "default_rate": float(row.DefaultRate or 0),
                "gst_applicable": bool(getattr(row, "GstApplicable", True)),
                "gst_rate_percent": float(row.GstRatePercent or 0),
                "label": f"{row.ItemCode} — {row.ItemName}",
            }
            for row in self.repo.list_all(active_only=True)
        ]

    def get_record(self, item_id: int) -> dict:
        row = self.repo.get_by_id(item_id)
        if row is None:
            raise ValueError("Item not found.")
        return self._serialize(row)

    def _parse(self, payload: dict, *, existing=None) -> dict:
        code = (payload.get("item_code") or payload.get("ItemCode") or "").strip().upper()
        name = (payload.get("item_name") or payload.get("ItemName") or "").strip()
        description = (payload.get("description") or payload.get("Description") or "").strip() or None
        hsn = (payload.get("hsn_sac") or payload.get("HsnSac") or "").strip()
        hsn_type = (payload.get("hsn_sac_type") or payload.get("HsnSacType") or "SAC").strip().upper()
        if hsn_type not in {"HSN", "SAC"}:
            hsn_type = "SAC"
        unit = (payload.get("unit") or payload.get("Unit") or "NOS").strip() or "NOS"
        rate = self._money(payload.get("default_rate") or payload.get("DefaultRate"))

        if "gst_applicable" in payload or "GstApplicable" in payload:
            gst_raw = payload.get("gst_applicable")
            if gst_raw is None:
                gst_raw = payload.get("GstApplicable")
            gst_applicable = str(gst_raw).lower() in {"1", "true", "yes", "on"}
        elif existing is not None:
            gst_applicable = bool(getattr(existing, "GstApplicable", True))
        else:
            gst_applicable = True

        if gst_applicable:
            gst = self._money(payload.get("gst_rate_percent") or payload.get("GstRatePercent"), "18")
        else:
            gst = Decimal("0.00")

        opening_qty = self._money(
            payload.get("opening_qty") or payload.get("OpeningQty"),
            "0",
            places="0.001",
        )
        opening_rate = self._money(payload.get("opening_rate") or payload.get("OpeningRate"))
        opening_balance = _q2(opening_qty * opening_rate)
        opening_date = self._parse_date(
            payload.get("opening_balance_date") or payload.get("OpeningBalanceDate")
        )

        try:
            order_no = int(payload.get("order_no") or payload.get("OrderNo") or 100)
        except (TypeError, ValueError):
            order_no = 100

        chart_raw = (
            payload.get("chart_group_id")
            if payload.get("chart_group_id") is not None
            else payload.get("ChartGroupID")
        )
        chart_group_id = None
        if chart_raw not in (None, ""):
            try:
                chart_group_id = int(chart_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Select a valid Chart of Account group.") from exc
            if chart_group_id <= 0:
                chart_group_id = None

        if "is_active" in payload or "IsActive" in payload:
            active_raw = payload.get("is_active")
            if active_raw is None:
                active_raw = payload.get("IsActive")
            is_active = str(active_raw).lower() in {"1", "true", "yes", "on"}
        elif existing is not None:
            is_active = bool(existing.IsActive)
        else:
            is_active = True

        if not code:
            raise ValueError("Item Code is required.")
        if not name:
            raise ValueError("Item Name is required.")
        if not hsn:
            raise ValueError("HSN / SAC is required.")
        if not chart_group_id:
            raise ValueError("Select Chart of Account group.")
        # Validate against active Chart of Group Master options.
        from app.services.chart_group_service import ChartGroupService

        active_ids = {
            int(g["group_id"])
            for g in ChartGroupService().list_active_for_dropdown()
            if g.get("group_id") is not None
        }
        if chart_group_id not in active_ids:
            raise ValueError("Selected Chart of Account group is invalid or inactive.")
        if gst < 0 or gst > 100:
            raise ValueError("GST Rate must be between 0 and 100.")
        if opening_qty < 0:
            raise ValueError("Qty cannot be negative.")
        if opening_rate < 0:
            raise ValueError("Rate cannot be negative.")

        return {
            "ItemCode": code[:40],
            "ItemName": name[:200],
            "Description": (description[:500] if description else None),
            "HsnSac": hsn[:20],
            "HsnSacType": hsn_type,
            "Unit": unit[:30],
            "DefaultRate": rate,
            "GstApplicable": gst_applicable,
            "GstRatePercent": gst,
            "OpeningQty": _q3(opening_qty),
            "OpeningRate": _q2(opening_rate),
            "OpeningBalance": opening_balance,
            "OpeningBalanceDate": opening_date,
            "ChartGroupID": chart_group_id,
            "OrderNo": order_no,
            "IsActive": is_active,
        }

    def create_record(self, payload: dict) -> dict:
        data = self._parse(payload)
        if self.repo.find_by_code(data["ItemCode"]):
            raise ValueError(f"Item Code '{data['ItemCode']}' already exists.")

        def _write() -> dict:
            row = self.repo.create({**data, "CreatedAt": datetime.utcnow()})
            return self._serialize(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Item Code '{data['ItemCode']}' already exists.") from exc

    def update_record(self, item_id: int, payload: dict) -> dict:
        row = self.repo.get_by_id(item_id)
        if row is None:
            raise ValueError("Item not found.")
        data = self._parse(payload, existing=row)
        other = self.repo.find_by_code(data["ItemCode"])
        if other and other.ItemID != row.ItemID:
            raise ValueError(f"Item Code '{data['ItemCode']}' already exists.")

        def _write() -> dict:
            updated = self.repo.update(row, {**data, "UpdatedAt": datetime.utcnow()})
            return self._serialize(updated)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Item Code '{data['ItemCode']}' already exists.") from exc

    def delete_record(self, item_id: int) -> str:
        row = self.repo.get_by_id(item_id)
        if row is None:
            raise ValueError("Item not found.")

        def _write() -> str:
            self.repo.delete(row)
            return "Item deleted successfully."

        return persist(_write)

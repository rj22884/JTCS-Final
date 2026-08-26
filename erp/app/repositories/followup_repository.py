from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.orm import Session, joinedload, load_only

from app.extensions import db
from app.models.followup import FollowupEntryMaster, FollowupEntryStage, FollowupWorkflowStage


class FollowupRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._entry_master_columns: set[str] | None = None

    def _entry_master_columns_set(self) -> set[str]:
        if self._entry_master_columns is None:
            rows = self.session.execute(
                text(
                    """
                    SELECT c.name
                    FROM sys.columns c
                    INNER JOIN sys.objects o ON o.object_id = c.object_id
                    WHERE o.type = 'U' AND o.name = 'FollowupEntryMaster'
                    """
                )
            ).scalars().all()
            self._entry_master_columns = set(rows)
        return self._entry_master_columns

    def _filter_entry_data(self, data: dict) -> dict:
        allowed = self._entry_master_columns_set()
        return {key: value for key, value in data.items() if key in allowed}

    def _entry_select_columns(self) -> str:
        columns = [
            "e.EntryID",
            "e.ModuleCode",
            "e.WorkDate",
            "e.TaxPeriod",
            "e.CustomerID",
            "e.ReturnType",
            "e.BillNo",
            "e.BillDate",
        ]
        available = self._entry_master_columns_set()
        if "FormType" in available:
            columns.append("e.FormType")
        if "Quarter" in available:
            columns.append("e.Quarter")
        if "ApplicationNumber" in available:
            columns.insert(columns.index("e.BillNo"), "e.ApplicationNumber")
        if "Location" in available:
            columns.append("e.Location")
        if "IntroducedBy" in available:
            columns.append("e.IntroducedBy")
        if "BillAmount" in available:
            columns.append("e.BillAmount")
        if "ITRFiledDate" in available:
            columns.append("e.ITRFiledDate")
        if "ReturnFilingStatus" in available:
            columns.append("e.ReturnFilingStatus")
        if "FilingDate" in available:
            columns.append("e.FilingDate")
        columns.extend(
            [
                "e.PANNumber",
                "e.Remarks",
                "e.ReasonForUnverified",
                "e.CreatedDate",
                "c.CustomerName",
                "c.MobileNumber",
                "c.EmailID",
            ]
        )
        # Optional customer GST filing frequency (Customer Master).
        cust_cols = self.session.execute(
            text(
                """
                SELECT c.name
                FROM sys.columns c
                INNER JOIN sys.objects o ON o.object_id = c.object_id
                WHERE o.type = 'U' AND o.name = 'CustomerMaster'
                  AND c.name = N'FilingFrequency'
                """
            )
        ).scalars().first()
        if cust_cols:
            columns.append("c.FilingFrequency")
        return ",\n                ".join(columns)

    def entry_master_columns(self) -> set[str]:
        return self._entry_master_columns_set()

    def _orm_loadable_columns(self) -> list:
        available = self._entry_master_columns_set()
        attrs = []
        for name in (
            "EntryID",
            "ModuleCode",
            "WorkDate",
            "TaxPeriod",
            "CustomerID",
            "ReturnType",
            "FormType",
            "Quarter",
            "ApplicationNumber",
            "Location",
            "IntroducedBy",
            "BillNo",
            "BillDate",
            "BillAmount",
            "ITRFiledDate",
            "ReturnFilingStatus",
            "FilingDate",
            "PANNumber",
            "Remarks",
            "ReasonForUnverified",
            "CreatedBy",
            "CreatedDate",
            "ModifiedDate",
            "IsActive",
        ):
            if name in available:
                attrs.append(getattr(FollowupEntryMaster, name))
        return attrs

    def ensure_tds_period_columns(self) -> None:
        """Ensure FormType / Quarter exist for TDS period bifurcation."""
        available = set(self._entry_master_columns_set())
        changed = False
        if "FormType" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD FormType NVARCHAR(30) NULL")
            )
            changed = True
        if "Quarter" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD Quarter NVARCHAR(10) NULL")
            )
            changed = True
        if changed:
            self.session.flush()
            self._entry_master_columns = None

    def ensure_billing_columns(self) -> None:
        available = set(self._entry_master_columns_set())
        changed = False
        if "ITRFiledDate" not in available:
            self.session.execute(text("ALTER TABLE dbo.FollowupEntryMaster ADD ITRFiledDate DATE NULL"))
            changed = True
        if "BillAmount" not in available:
            self.session.execute(text("ALTER TABLE dbo.FollowupEntryMaster ADD BillAmount DECIMAL(18, 2) NULL"))
            changed = True
        if changed:
            self.session.flush()
            self._entry_master_columns = None

    def ensure_filing_status_columns(self) -> None:
        available = set(self._entry_master_columns_set())
        changed = False
        if "ReturnFilingStatus" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD ReturnFilingStatus NVARCHAR(150) NULL")
            )
            changed = True
        if "FilingDate" not in available:
            self.session.execute(text("ALTER TABLE dbo.FollowupEntryMaster ADD FilingDate DATE NULL"))
            changed = True
        if changed:
            self.session.flush()
            self._entry_master_columns = None

    def find_by_tally_bill_no(self, bill_no: str) -> dict | None:
        """Look up an active GST / TDS / DSC / ITR followup by Tally Bill Number."""
        key = (bill_no or "").strip()
        if not key:
            return None
        available = self._entry_master_columns_set()
        amount_sql = "e.BillAmount" if "BillAmount" in available else "CAST(NULL AS DECIMAL(18, 2)) AS BillAmount"
        quarter_sql = "e.Quarter" if "Quarter" in available else "CAST(NULL AS NVARCHAR(10)) AS Quarter"
        sql = f"""
            SELECT TOP 1
                e.EntryID,
                e.ModuleCode,
                e.WorkDate,
                e.TaxPeriod,
                e.CustomerID,
                e.ReturnType,
                e.BillNo,
                e.BillDate,
                {amount_sql},
                {quarter_sql},
                c.CustomerName,
                c.MobileNumber
            FROM FollowupEntryMaster e
            INNER JOIN CustomerMaster c ON c.CustomerID = e.CustomerID
            WHERE e.IsActive = 1
              AND e.ModuleCode IN (N'GST', N'TDS', N'DSC', N'ITR')
              AND e.BillNo IS NOT NULL
              AND UPPER(LTRIM(RTRIM(e.BillNo))) = :bill_no
            ORDER BY CASE WHEN e.BillDate IS NULL THEN 1 ELSE 0 END,
                     e.BillDate DESC, e.WorkDate DESC, e.EntryID DESC
        """
        row = self.session.execute(text(sql), {"bill_no": key.upper()}).mappings().first()
        return dict(row) if row else None

    def find_active_itr_by_customer_period(self, customer_name: str, tax_period: str) -> FollowupEntryMaster | None:
        from app.models.transactions import CustomerMaster

        name = (customer_name or "").strip()
        period = (tax_period or "").strip()
        if not name or not period:
            return None
        stmt = (
            select(FollowupEntryMaster)
            .join(CustomerMaster, CustomerMaster.CustomerID == FollowupEntryMaster.CustomerID)
            .where(
                FollowupEntryMaster.ModuleCode == "ITR",
                FollowupEntryMaster.IsActive == True,  # noqa: E712
                FollowupEntryMaster.TaxPeriod == period,
                CustomerMaster.CustomerName == name,
            )
            .order_by(FollowupEntryMaster.EntryID.desc())
        )
        return self.session.scalars(stmt).first()

    def ensure_application_number_column(self) -> None:
        available = set(self._entry_master_columns_set())
        changed = False
        if "ApplicationNumber" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD ApplicationNumber NVARCHAR(50) NULL")
            )
            changed = True
        if "Location" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD Location NVARCHAR(200) NULL")
            )
            changed = True
        if "IntroducedBy" not in available:
            self.session.execute(
                text("ALTER TABLE dbo.FollowupEntryMaster ADD IntroducedBy NVARCHAR(200) NULL")
            )
            changed = True
        if changed:
            self.session.flush()
            self._entry_master_columns = None

    def ensure_dsc_extra_columns(self) -> None:
        """Ensure Location / IntroducedBy exist for DSC entry form."""
        self.ensure_application_number_column()

    def ensure_gst_return_filed_stage(self) -> None:
        """
        GST only: merge gstr1_filed + gstr3b_filed into return_filed (idempotent).
        Does not touch ITR / DSC / TDS stages.
        """
        self.session.execute(
            text(
                """
                DECLARE @ReturnFiledID INT;
                DECLARE @OldGstr1ID INT;
                DECLARE @OldGstr3bID INT;

                SELECT TOP 1 @ReturnFiledID = StageID
                FROM dbo.FollowupWorkflowStage
                WHERE ModuleCode = N'GST' AND StageCode = N'return_filed'
                ORDER BY StageID;

                SELECT TOP 1 @OldGstr1ID = StageID
                FROM dbo.FollowupWorkflowStage
                WHERE ModuleCode = N'GST' AND StageCode = N'gstr1_filed'
                ORDER BY StageID;

                SELECT TOP 1 @OldGstr3bID = StageID
                FROM dbo.FollowupWorkflowStage
                WHERE ModuleCode = N'GST' AND StageCode = N'gstr3b_filed'
                ORDER BY StageID;

                IF @ReturnFiledID IS NULL
                BEGIN
                    INSERT INTO dbo.FollowupWorkflowStage (
                        ModuleCode, StageCode, StageName, DisplayOrder, ActiveStatus
                    )
                    VALUES (N'GST', N'return_filed', N'Return Filed', 2, 1);
                    SET @ReturnFiledID = SCOPE_IDENTITY();
                END
                ELSE
                BEGIN
                    UPDATE dbo.FollowupWorkflowStage
                    SET StageName = N'Return Filed',
                        DisplayOrder = 2,
                        ActiveStatus = 1
                    WHERE StageID = @ReturnFiledID;
                END;

                IF @ReturnFiledID IS NOT NULL AND (@OldGstr1ID IS NOT NULL OR @OldGstr3bID IS NOT NULL)
                BEGIN
                    ;WITH migrated AS (
                        SELECT
                            es.EntryID,
                            MAX(es.CompletedDate) AS CompletedDate
                        FROM dbo.FollowupEntryStage es
                        WHERE es.StageID IN (@OldGstr1ID, @OldGstr3bID)
                        GROUP BY es.EntryID
                    )
                    INSERT INTO dbo.FollowupEntryStage (EntryID, StageID, CompletedDate)
                    SELECT m.EntryID, @ReturnFiledID, m.CompletedDate
                    FROM migrated m
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM dbo.FollowupEntryStage x
                        WHERE x.EntryID = m.EntryID
                          AND x.StageID = @ReturnFiledID
                    );

                    DELETE FROM dbo.FollowupEntryStage
                    WHERE StageID IN (@OldGstr1ID, @OldGstr3bID);
                END;

                UPDATE dbo.FollowupWorkflowStage
                SET ActiveStatus = 0,
                    StageName = CASE StageCode
                        WHEN N'gstr1_filed' THEN N'GSTR-1 Filed (merged)'
                        WHEN N'gstr3b_filed' THEN N'GSTR-3B Filed (merged)'
                        ELSE StageName
                    END
                WHERE ModuleCode = N'GST'
                  AND StageCode IN (N'gstr1_filed', N'gstr3b_filed');

                UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 1, ActiveStatus = 1
                WHERE ModuleCode = N'GST' AND StageCode = N'documents_received';

                UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 2, ActiveStatus = 1
                WHERE ModuleCode = N'GST' AND StageCode = N'return_filed';

                UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 3, ActiveStatus = 1
                WHERE ModuleCode = N'GST' AND StageCode = N'tally_bill_generated';

                UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 4, ActiveStatus = 1
                WHERE ModuleCode = N'GST' AND StageCode = N'payment_received';
                """
            )
        )
        self.session.commit()

    def list_stages(self, module_code: str, *, active_only: bool = True) -> list[FollowupWorkflowStage]:
        stmt = select(FollowupWorkflowStage).where(FollowupWorkflowStage.ModuleCode == module_code)
        if active_only:
            stmt = stmt.where(FollowupWorkflowStage.ActiveStatus == True)  # noqa: E712
        stmt = stmt.order_by(FollowupWorkflowStage.DisplayOrder, FollowupWorkflowStage.StageID)
        return list(self.session.scalars(stmt).all())

    def get_stage(self, stage_id: int) -> FollowupWorkflowStage | None:
        return self.session.get(FollowupWorkflowStage, stage_id)

    def get_stage_by_code(self, module_code: str, stage_code: str) -> FollowupWorkflowStage | None:
        stmt = select(FollowupWorkflowStage).where(
            FollowupWorkflowStage.ModuleCode == module_code,
            FollowupWorkflowStage.StageCode == stage_code,
        )
        return self.session.scalars(stmt).first()

    def create_stage(self, data: dict) -> FollowupWorkflowStage:
        row = FollowupWorkflowStage(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update_stage(self, row: FollowupWorkflowStage, data: dict) -> FollowupWorkflowStage:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate_stage(self, row: FollowupWorkflowStage) -> FollowupWorkflowStage:
        row.ActiveStatus = False
        self.session.flush()
        return row

    def create_entry(self, data: dict) -> FollowupEntryMaster:
        row = FollowupEntryMaster(**self._filter_entry_data(data))
        self.session.add(row)
        self.session.flush()
        return row

    def get_entry(self, entry_id: int) -> FollowupEntryMaster | None:
        load_cols = self._orm_loadable_columns()
        stmt = (
            select(FollowupEntryMaster)
            .options(
                load_only(*load_cols),
                joinedload(FollowupEntryMaster.stages).joinedload(FollowupEntryStage.stage),
            )
            .where(FollowupEntryMaster.EntryID == entry_id)
        )
        return self.session.scalars(stmt).unique().first()

    def find_active_entry_by_return_key(
        self,
        *,
        module_code: str,
        tax_period: str,
        return_type: str,
        pan_number: str,
        exclude_entry_id: int | None = None,
    ) -> FollowupEntryMaster | None:
        normalized_pan = (pan_number or "").strip().upper()
        normalized_period = (tax_period or "").strip()
        normalized_return = (return_type or "Original").strip() or "Original"
        if not normalized_pan or not normalized_period:
            return None

        if normalized_return == "Original":
            return_type_match = or_(
                FollowupEntryMaster.ReturnType == "Original",
                FollowupEntryMaster.ReturnType.is_(None),
                FollowupEntryMaster.ReturnType == "",
            )
        elif normalized_return == "Revised1":
            return_type_match = or_(
                FollowupEntryMaster.ReturnType == "Revised1",
                FollowupEntryMaster.ReturnType == "Revised",
            )
        else:
            return_type_match = FollowupEntryMaster.ReturnType == normalized_return

        stmt = (
            select(FollowupEntryMaster)
            .where(
                FollowupEntryMaster.ModuleCode == module_code,
                FollowupEntryMaster.IsActive == True,  # noqa: E712
                FollowupEntryMaster.TaxPeriod == normalized_period,
                FollowupEntryMaster.PANNumber == normalized_pan,
                return_type_match,
            )
            .order_by(FollowupEntryMaster.EntryID.desc())
        )
        if exclude_entry_id:
            stmt = stmt.where(FollowupEntryMaster.EntryID != exclude_entry_id)
        return self.session.scalars(stmt).first()

    def find_active_entry_by_customer_return_key(
        self,
        *,
        module_code: str,
        tax_period: str,
        return_type: str,
        customer_id: int,
        exclude_entry_id: int | None = None,
    ) -> FollowupEntryMaster | None:
        normalized_period = (tax_period or "").strip()
        normalized_return = (return_type or "Original").strip() or "Original"
        if not normalized_period or not customer_id:
            return None

        if normalized_return == "Original":
            return_type_match = or_(
                FollowupEntryMaster.ReturnType == "Original",
                FollowupEntryMaster.ReturnType.is_(None),
                FollowupEntryMaster.ReturnType == "",
            )
        elif normalized_return == "Revised1":
            return_type_match = or_(
                FollowupEntryMaster.ReturnType == "Revised1",
                FollowupEntryMaster.ReturnType == "Revised",
            )
        else:
            return_type_match = FollowupEntryMaster.ReturnType == normalized_return

        stmt = (
            select(FollowupEntryMaster)
            .where(
                FollowupEntryMaster.ModuleCode == module_code,
                FollowupEntryMaster.IsActive == True,  # noqa: E712
                FollowupEntryMaster.TaxPeriod == normalized_period,
                FollowupEntryMaster.CustomerID == customer_id,
                return_type_match,
            )
            .order_by(FollowupEntryMaster.EntryID.desc())
        )
        if exclude_entry_id:
            stmt = stmt.where(FollowupEntryMaster.EntryID != exclude_entry_id)
        return self.session.scalars(stmt).first()

    def update_entry(self, row: FollowupEntryMaster, data: dict) -> FollowupEntryMaster:
        for key, value in self._filter_entry_data(data).items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate_entry(self, row: FollowupEntryMaster) -> FollowupEntryMaster:
        row.IsActive = False
        self.session.flush()
        return row

    def replace_entry_stages(self, entry_id: int, stage_ids: list[int]) -> None:
        """Replace completed stages for an entry.

        Must go through the ORM relationship when the entry is already loaded.
        A bulk DELETE + session.add bypasses delete-orphan on FollowupEntryMaster.stages
        and can drop newly added stages (e.g. payment_received) on the final flush.
        """
        now = datetime.utcnow()
        unique_ids: list[int] = []
        seen: set[int] = set()
        for stage_id in stage_ids:
            try:
                sid = int(stage_id)
            except (TypeError, ValueError):
                continue
            if sid in seen:
                continue
            seen.add(sid)
            unique_ids.append(sid)

        entry = self.session.get(FollowupEntryMaster, entry_id)
        if entry is not None:
            entry.stages.clear()
            self.session.flush()
            for sid in unique_ids:
                entry.stages.append(
                    FollowupEntryStage(
                        EntryID=entry_id,
                        StageID=sid,
                        CompletedDate=now,
                    )
                )
            self.session.flush()
            return

        self.session.execute(delete(FollowupEntryStage).where(FollowupEntryStage.EntryID == entry_id))
        for sid in unique_ids:
            self.session.add(
                FollowupEntryStage(
                    EntryID=entry_id,
                    StageID=sid,
                    CompletedDate=now,
                )
            )
        self.session.flush()

    def list_entries(
        self,
        module_code: str,
        *,
        search: str | None = None,
        status_filter: str | None = None,
        tax_period: str | None = None,
        return_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        sql = f"""
            SELECT
                {self._entry_select_columns()}
            FROM FollowupEntryMaster e
            INNER JOIN CustomerMaster c ON c.CustomerID = e.CustomerID
            WHERE e.ModuleCode = :module
              AND e.IsActive = 1
        """
        params: dict = {"module": module_code, "lim": limit}
        if search:
            sql += """
              AND (
                c.CustomerName LIKE :search
                OR c.MobileNumber LIKE :search
                OR e.PANNumber LIKE :search_upper
                OR e.BillNo LIKE :search_upper
                OR ISNULL(c.EmailID, N'') LIKE :search
              )
            """
            params["search"] = f"%{search.strip()}%"
            params["search_upper"] = f"%{search.strip().upper()}%"
        period = (tax_period or "").strip()
        if period:
            sql += " AND e.TaxPeriod = :tax_period"
            params["tax_period"] = period
        rt = (return_type or "").strip()
        if rt:
            sql += " AND e.ReturnType = :return_type"
            params["return_type"] = rt
        df = (date_from or "").strip()
        if df:
            sql += " AND e.WorkDate >= :date_from"
            params["date_from"] = df
        dt = (date_to or "").strip()
        if dt:
            sql += " AND e.WorkDate <= :date_to"
            params["date_to"] = dt

        sql += " ORDER BY e.WorkDate DESC, e.EntryID DESC"
        rows = list(self.session.execute(text(sql), params).mappings().all())
        results = [dict(row) for row in rows[:limit]]

        stage_rows = self.list_stages(module_code)
        stage_map = {s.StageID: s for s in stage_rows}
        completed = self.session.execute(
            text(
                """
                SELECT es.EntryID, es.StageID, s.StageCode, s.StageName, s.DisplayOrder
                FROM FollowupEntryStage es
                INNER JOIN FollowupWorkflowStage s ON s.StageID = es.StageID
                INNER JOIN FollowupEntryMaster e ON e.EntryID = es.EntryID
                WHERE e.ModuleCode = :module AND e.IsActive = 1
                """
            ),
            {"module": module_code},
        ).mappings().all()
        by_entry: dict[int, list] = {}
        for row in completed:
            by_entry.setdefault(row["EntryID"], []).append(dict(row))

        payment_stage = next((s for s in stage_rows if s.StageCode == "payment_received"), None)
        for item in results:
            entry_stages = sorted(
                by_entry.get(item["EntryID"], []),
                key=lambda x: x.get("DisplayOrder") or 0,
            )
            item["completed_stages"] = entry_stages
            item["workflow_status"] = self._workflow_status(entry_stages, stage_rows)
            item["payment_received"] = bool(
                payment_stage
                and any(es["StageID"] == payment_stage.StageID for es in entry_stages)
            )
            item["has_tally_bill"] = any(es.get("StageCode") == "tally_bill_generated" for es in entry_stages)
            if item.get("BillAmount") is not None:
                item["bill_amount"] = float(item["BillAmount"])
            if item.get("ITRFiledDate") and hasattr(item["ITRFiledDate"], "isoformat"):
                item["itr_filed_date"] = item["ITRFiledDate"].isoformat()

        if status_filter:
            sf = status_filter.strip().lower()
            if sf == "pending":
                results = [r for r in results if r["workflow_status"] == "Pending"]
            elif sf == "payment_pending":
                results = [r for r in results if not r["payment_received"]]
            elif sf == "payment_received":
                results = [r for r in results if r["payment_received"]]
            else:
                results = [
                    r
                    for r in results
                    if (r["workflow_status"] or "").lower() == sf.replace("_", " ")
                    or any(es["StageCode"] == sf for es in r["completed_stages"])
                ]
        return results

    @staticmethod
    def _workflow_status(completed: list[dict], all_stages: list[FollowupWorkflowStage]) -> str:
        if not completed:
            return "Pending"
        if any((row.get("StageCode") or "").lower() == "unverified" for row in completed):
            return "Unverified"

        # Prefer highest DisplayOrder among completed progress stages.
        # Using completed rows directly avoids empty all_stages / id-mismatch edge cases
        # (e.g. Payment Received must win over Tally Bill Generated).
        progress = [
            row
            for row in completed
            if (row.get("StageCode") or "").lower() != "unverified"
        ]
        if progress and all(row.get("StageName") for row in progress):
            progress.sort(
                key=lambda row: (row.get("DisplayOrder") or 0, row.get("StageID") or 0)
            )
            return progress[-1]["StageName"]

        completed_ids = {row["StageID"] for row in completed}
        last_name = "Pending"
        for stage in all_stages:
            if stage.StageID in completed_ids:
                last_name = stage.StageName
        return last_name

    def stats(self, module_code: str) -> dict:
        rows = self.list_entries(module_code, limit=2000)
        total = len(rows)
        pending = sum(1 for r in rows if (r.get("workflow_status") or "Pending") == "Pending")
        payment_received = sum(1 for r in rows if r["payment_received"])
        by_status: dict[str, int] = {}
        for stage in self.list_stages(module_code):
            code = (stage.StageCode or "").strip().lower()
            name = (stage.StageName or "").strip()
            if not name:
                continue
            by_status[name] = sum(
                1
                for r in rows
                if any(
                    (es.get("StageCode") or "").lower() == code
                    for es in (r.get("completed_stages") or [])
                )
            )
        return {
            "total": total,
            "pending": pending,
            "payment_received": payment_received,
            "payment_pending": total - payment_received,
            "by_status": by_status,
        }

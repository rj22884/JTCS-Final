"""CRM workflow definitions and instance progression."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class WorkflowService:
    def list_definitions(self) -> list[dict]:
        ensure_crm_schema()
        defs = db.session.execute(
            text(
                """
                SELECT DefinitionID, WorkflowCode, WorkflowName, Description, IsActive, CreatedDate
                FROM dbo.CrmWorkflowDefinition
                WHERE IsActive = 1
                ORDER BY WorkflowName
                """
            ),
        ).mappings().all()
        result = []
        for d in defs:
            item = dict(d)
            steps = db.session.execute(
                text(
                    """
                    SELECT StepID, DefinitionID, StepCode, StepName, DisplayOrder, IsActive
                    FROM dbo.CrmWorkflowStep
                    WHERE DefinitionID = :def_id AND IsActive = 1
                    ORDER BY DisplayOrder, StepID
                    """
                ),
                {"def_id": item["DefinitionID"]},
            ).mappings().all()
            item["steps"] = [dict(s) for s in steps]
            result.append(item)
        return result

    def start_instance(
        self,
        definition_code: str,
        *,
        customer_id: int | None = None,
        lead_id: int | None = None,
        user_id: int | None = None,
    ) -> dict:
        ensure_crm_schema()
        def_row = db.session.execute(
            text(
                """
                SELECT TOP 1 DefinitionID FROM dbo.CrmWorkflowDefinition
                WHERE WorkflowCode = :code AND IsActive = 1
                """
            ),
            {"code": definition_code.strip()},
        ).mappings().first()
        if not def_row:
            raise ValueError(f"Workflow definition '{definition_code}' not found.")

        definition_id = int(def_row["DefinitionID"])
        first_step = db.session.execute(
            text(
                """
                SELECT TOP 1 StepID FROM dbo.CrmWorkflowStep
                WHERE DefinitionID = :def_id AND IsActive = 1
                ORDER BY DisplayOrder, StepID
                """
            ),
            {"def_id": definition_id},
        ).scalar()

        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmWorkflowInstance
                    (DefinitionID, CustomerID, LeadID, CurrentStepID, Status,
                     CreatedByUserID, CreatedDate)
                OUTPUT INSERTED.InstanceID
                VALUES
                    (:def_id, :customer_id, :lead_id, :step_id, N'InProgress', :user_id, :now)
                """
            ),
            {
                "def_id": definition_id,
                "customer_id": customer_id,
                "lead_id": lead_id,
                "step_id": first_step,
                "user_id": user_id,
                "now": now,
            },
        ).first()
        db.session.commit()
        return self.get_instance(int(row[0])) or {}

    def advance_instance(
        self,
        instance_id: int,
        *,
        user_id: int | None = None,
        notes: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError("Workflow instance not found.")
        if instance.get("Status") != "InProgress":
            raise ValueError("Workflow instance is not in progress.")

        current_step_id = instance.get("CurrentStepID")
        if not current_step_id:
            raise ValueError("Workflow instance has no current step.")

        now = datetime.utcnow()
        db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmWorkflowInstanceStep
                    (InstanceID, StepID, CompletedDate, CompletedByUserID, Notes)
                VALUES
                    (:instance_id, :step_id, :now, :user_id, :notes)
                """
            ),
            {
                "instance_id": instance_id,
                "step_id": current_step_id,
                "now": now,
                "user_id": user_id,
                "notes": (notes or "")[:500] or None,
            },
        )

        next_step = db.session.execute(
            text(
                """
                SELECT TOP 1 s.StepID
                FROM dbo.CrmWorkflowStep s
                WHERE s.DefinitionID = :def_id AND s.IsActive = 1
                  AND s.DisplayOrder > (
                      SELECT DisplayOrder FROM dbo.CrmWorkflowStep WHERE StepID = :current
                  )
                ORDER BY s.DisplayOrder, s.StepID
                """
            ),
            {"def_id": instance["DefinitionID"], "current": current_step_id},
        ).scalar()

        if next_step:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.CrmWorkflowInstance
                    SET CurrentStepID = :step_id, ModifiedDate = :now
                    WHERE InstanceID = :id
                    """
                ),
                {"step_id": next_step, "now": now, "id": instance_id},
            )
        else:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.CrmWorkflowInstance
                    SET Status = N'Completed', CompletedDate = :now, ModifiedDate = :now
                    WHERE InstanceID = :id
                    """
                ),
                {"now": now, "id": instance_id},
            )
        db.session.commit()
        return self.get_instance(instance_id) or {}

    def list_instances(
        self,
        *,
        customer_id: int | None = None,
        lead_id: int | None = None,
        status: str | None = None,
    ) -> list[dict]:
        ensure_crm_schema()
        clauses = ["i.IsActive = 1"]
        params: dict = {}
        if customer_id:
            clauses.append("i.CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_id:
            clauses.append("i.LeadID = :lead_id")
            params["lead_id"] = lead_id
        if status:
            clauses.append("i.Status = :status")
            params["status"] = status
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT i.InstanceID, i.DefinitionID, i.CustomerID, i.LeadID, i.CurrentStepID,
                       i.Status, i.AssignedUserID, i.CreatedByUserID, i.CreatedDate,
                       i.ModifiedDate, i.CompletedDate,
                       d.WorkflowCode, d.WorkflowName,
                       s.StepCode AS CurrentStepCode, s.StepName AS CurrentStepName
                FROM dbo.CrmWorkflowInstance i
                INNER JOIN dbo.CrmWorkflowDefinition d ON d.DefinitionID = i.DefinitionID
                LEFT JOIN dbo.CrmWorkflowStep s ON s.StepID = i.CurrentStepID
                WHERE {where}
                ORDER BY i.CreatedDate DESC
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_instance(self, instance_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT i.InstanceID, i.DefinitionID, i.CustomerID, i.LeadID, i.CurrentStepID,
                       i.Status, i.AssignedUserID, i.CreatedByUserID, i.CreatedDate,
                       i.ModifiedDate, i.CompletedDate,
                       d.WorkflowCode, d.WorkflowName,
                       s.StepCode AS CurrentStepCode, s.StepName AS CurrentStepName
                FROM dbo.CrmWorkflowInstance i
                INNER JOIN dbo.CrmWorkflowDefinition d ON d.DefinitionID = i.DefinitionID
                LEFT JOIN dbo.CrmWorkflowStep s ON s.StepID = i.CurrentStepID
                WHERE i.InstanceID = :id AND i.IsActive = 1
                """
            ),
            {"id": instance_id},
        ).mappings().first()
        if not row:
            return None
        result = dict(row)
        steps = db.session.execute(
            text(
                """
                SELECT ist.InstanceStepID, ist.StepID, ist.CompletedDate, ist.CompletedByUserID,
                       ist.Notes, ws.StepCode, ws.StepName, ws.DisplayOrder
                FROM dbo.CrmWorkflowInstanceStep ist
                INNER JOIN dbo.CrmWorkflowStep ws ON ws.StepID = ist.StepID
                WHERE ist.InstanceID = :id
                ORDER BY ist.CompletedDate ASC, ist.InstanceStepID ASC
                """
            ),
            {"id": instance_id},
        ).mappings().all()
        result["completed_steps"] = [dict(s) for s in steps]
        return result

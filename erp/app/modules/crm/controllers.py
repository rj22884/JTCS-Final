"""CRM controllers — thin orchestration helpers used by routes."""

from __future__ import annotations

from app.modules.crm.customer360_service import Customer360Service
from app.modules.crm.followup_service import CrmFollowUpService
from app.modules.crm.lead_service import CrmLeadService
from app.modules.crm.task_service import CrmTaskService


class CrmController:
    def __init__(self):
        self.leads = CrmLeadService()
        self.tasks = CrmTaskService()
        self.followups = CrmFollowUpService()
        self.customer360 = Customer360Service()

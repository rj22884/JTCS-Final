"""CRM module — leads, tasks, follow-ups, customer 360."""

from app.modules.crm.followup_service import CrmFollowUpService
from app.modules.crm.lead_service import CrmLeadService
from app.modules.crm.task_service import CrmTaskService

__all__ = [
    "CrmLeadService",
    "CrmTaskService",
    "CrmFollowUpService",
]

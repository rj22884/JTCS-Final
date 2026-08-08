"""CRM communication / inbox — unified multi-channel Communication Center."""

from app.modules.communication.services import CommunicationService
from app.modules.communication.whatsapp_provider import get_whatsapp_provider

__all__ = ["CommunicationService", "get_whatsapp_provider"]

from typing import Dict, List, Optional, Union

from pydantic import BaseModel


class SyncLMSRequest(BaseModel):
    """Модель запроса для синхронизации с LMS"""

    phone: Union[str, int]
    max_id: Optional[str] = None
    platform_url: Optional[str] = None
    lead_id: Optional[Union[int, str]] = None
    contact_id: Optional[Union[int, str]] = None
    chat_id: Optional[Union[int, str]] = None


class SyncLMSResponse(BaseModel):
    """Модель ответа для синхронизации с LMS"""

    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    max_id: Optional[str | int] = None
    phone: Optional[str | int] = None
    contact_id: Optional[str | int] = None
    lead_id: Optional[str | int] = None
    contact_type: Optional[str] = None
    lms_contact_id: Optional[str | int] = None
    lms_contact_holder: Optional[str | int] = None
    platform_url: Optional[str] = None
    old_max_id: Optional[str | int] = None
    updated_fields: Optional[List[str]] = None
    available_contacts: Optional[List[Dict]] = None

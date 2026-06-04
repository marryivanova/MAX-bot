from typing import List, Optional

from pydantic import BaseModel


class BitrixMessage(BaseModel):
    message_text: str
    variables: Optional[List[str]] = None
    client_contact_title: Optional[str] = None
    client_phone_number: Optional[str] = None
    max_id: Optional[str] = None
    sender: Optional[str] = "MAX"
    direction: Optional[str] = None
    bitrix_type_client: Optional[str] = None
    bitrix_client_id: Optional[int] = None
    mailing_name: Optional[str] = "Рассылка сообщений: MAX"

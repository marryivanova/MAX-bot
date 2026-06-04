# ========== Event Data Extractor ==========
from typing import Any, Dict, Optional


class EventDataExtractor:
    """Извлечение данных из событий"""

    @staticmethod
    def extract_chat_id(event_object: Any, raw_data: Dict[str, Any]) -> Optional[str]:
        """Извлечь chat_id из события"""
        sources = [
            raw_data.get("message", {}).get("recipient", {}).get("chat_id"),
            getattr(event_object, "chat_id", None),
            EventDataExtractor._extract_from_message(event_object),
        ]

        for source in sources:
            if source:
                chat_id_str = str(source).strip()
                if chat_id_str and chat_id_str.lower() not in ["none", "null", ""]:
                    return chat_id_str

        return None

    @staticmethod
    def _extract_from_message(event_object: Any) -> Optional[str]:
        if not hasattr(event_object, "message") or not event_object.message:
            return None

        recipient = event_object.message.recipient
        if isinstance(recipient, dict):
            return recipient.get("chat_id")
        return getattr(recipient, "chat_id", None)

import re
from typing import Any, Dict, List, Optional, Protocol

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from max_sdk.core.enums.update import UpdateType
from max_sdk.core.helper.getted_updates import process_update_webhook


# ========== Phone Extractor  ==========
class PhoneExtractorProtocol(Protocol):
    async def extract(self, event_object: Any, raw_data: Dict[str, Any]) -> Optional[str]: ...


class PhoneExtractor:
    """Сервис для извлечения телефонов из событий"""

    PHONE_PATTERNS = [
        r"(\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})",
        r"(7\d{10})",
        r"(8\d{10})",
        r"(\d{11})",
        r"(\d{10})",
        r"номер\s*[:\-]?\s*(\+?[78]?\d{10})",
        r"телефон\s*[:\-]?\s*(\+?[78]?\d{10})",
        r"(\+?[78]\s?\(\d{3}\)\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})",
    ]

    def __init__(self):
        self.compiled_patterns = [re.compile(p) for p in self.PHONE_PATTERNS]

    async def extract(self, event_object: Any, raw_data: Dict[str, Any]) -> Optional[str]:
        """Извлечь номер телефона из события"""
        sources = [
            self._extract_from_message_body(event_object),
            self._extract_from_event_text(event_object),
            self._extract_from_attachments(event_object),
        ]

        for source_func in sources:
            phone = source_func
            if phone:
                normalized = self._normalize_phone(phone)
                if normalized:
                    return normalized

        return None

    def _extract_from_event_text(self, event_object: Any) -> Optional[str]:
        if not hasattr(event_object, "text") or not event_object.text:
            return None
        return self._extract_from_text(event_object.text)

    def _extract_from_message_body(self, event_object: Any) -> Optional[str]:
        if not hasattr(event_object, "message") or not event_object.message:
            return None

        body = event_object.message.body

        if body.text:
            phone = self._extract_from_text(body.text)
            if phone:
                return phone

        if body.attachments:
            return self._extract_from_attachments(body.attachments)

        return None

    def _extract_from_attachments(self, attachments: List[Any]) -> Optional[str]:
        for attachment in attachments:
            if getattr(attachment, "type", None) == "contact":
                payload = getattr(attachment, "payload", None)
                if payload and getattr(payload, "vcf_info", None):
                    return self._extract_from_vcard(payload.vcf_info)
        return None

    @staticmethod
    def _extract_from_vcard(vcf_info: str) -> Optional[str]:
        tel_pattern = r"TEL[^:]*:([^\r\n]+)"
        match = re.search(tel_pattern, vcf_info, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else None

    def _extract_from_text(self, text: str) -> Optional[str]:
        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _normalize_phone(phone: str) -> Optional[str]:
        """Нормализовать номер телефона"""
        if not phone:
            return None

        digits = re.sub(r"\D", "", phone)

        if len(digits) == 11:
            if digits.startswith("8"):
                return "7" + digits[1:]
            return digits
        elif len(digits) == 10:
            return "7" + digits

        return None

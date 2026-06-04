import re
from typing import Optional

from loguru import logger


def extract_phone_from_vcard(vcf_text: str) -> Optional[str]:
    """Извлекает номер телефона из vCard (обычная, НЕ async)"""
    if not vcf_text:
        return None

    phone_pattern = r"TEL[^:]*:([^\r\n]+)"
    match = re.search(phone_pattern, vcf_text)
    if match:
        phone = match.group(1).strip()
        phone = re.sub(r"[^\d+]", "", phone)
        return phone

    return None


def parse_contact_attachment(attachments, sender_name: str) -> Optional[str]:
    """Возвращает vcf_info если в сообщении есть контакт"""
    if not attachments:
        return None

    logger.info(f"Получен attachments parse_contact_attachment от: {attachments}")

    for attachment in attachments:
        if getattr(attachment, "type", None) == "contact":
            logger.info(f"Получен контакт от {sender_name}")

            payload = getattr(attachment, "payload", None)
            if payload:
                if payload.vcf_info:
                    return payload.vcf_info
                if isinstance(payload, dict):
                    return payload.get("vcf_info")

    return None

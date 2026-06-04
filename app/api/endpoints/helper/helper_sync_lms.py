import re
from typing import Optional

from loguru import logger


def extract_client_id_from_url(url: str) -> Optional[str]:
    """
    Извлекает client_id из URL платформы LMS.
    """
    logger.info(f"ШАГ 1 - Извлечение client_id из URL: {url}")

    if not url:
        logger.warning("URL пустой или None")
        return None

    clean_url = url.rstrip("/")
    parts = clean_url.split("/")
    logger.debug(f"Разбил URL на части: {parts}")

    if "clients" in parts:
        clients_index = parts.index("clients")
        logger.debug(f"Нашел 'clients' на позиции: {clients_index}")
        if clients_index + 1 < len(parts):
            client_id = parts[clients_index + 1]
            if client_id.isdigit():
                logger.success(f"Извлек client_id из пути с 'clients': {client_id}")
                return client_id
            else:
                logger.warning(f"client_id не является числом: {client_id}")

    last_part = parts[-1]
    if last_part.isdigit():
        logger.success(f"Извлек client_id из последней части: {last_part}")
        return last_part

    numbers = re.findall(r"\d+", url)
    logger.debug(f"Нашел все числа в URL: {numbers}")
    if numbers:
        client_id = numbers[-1]
        logger.success(f"Извлек последнее число из URL: {client_id}")
        return client_id

    logger.warning(f"Не удалось найти client_id в URL: {url}")

    return None


def extract_platform_url_from_bitrix_contact(bitrix_contact: dict) -> Optional[str]:
    """Извлекает URL платформы из поля WEB контакта Битрикс."""

    web_field = bitrix_contact.get("WEB") if bitrix_contact else None
    if not web_field:
        return None

    urls = []
    if isinstance(web_field, list):
        urls = [e.get("VALUE", "") for e in web_field if isinstance(e, dict)]
    elif isinstance(web_field, str):
        urls = [web_field]

    platform_url = next(
        (
            url.rstrip("/")
            for url in urls
            if isinstance(url, str) and ("hwschool.online" in url or "my.hwschool.online" in url)
        ),
        None,
    )
    return platform_url

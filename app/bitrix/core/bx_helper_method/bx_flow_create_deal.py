from datetime import datetime

from loguru import logger
from requests import get

from app.bitrix.bx_method import bitrix_bot
from app.bitrix.core.model import DealData
from app.services.model import MaxUrl
from db.crud_db import get_lms_id_by_chat_id
from settings import settings


def _fetch_managers(params: dict) -> list:
    response = get(url=f"{MaxUrl.hw_awto.value}/get_work-managers/", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def _get_responsible_manager() -> int:
    """Получить ID ответственного менеджера"""
    params = dict(
        manager_type_id="",
        datetime_work=f"{datetime.now().replace(minute=0, second=0, microsecond=0)}",
        is_future=True,
    )
    try:
        managers = _fetch_managers(params)
        if managers:
            return managers[0]["manager_bitrix_id"]
        logger.warning("Список менеджеров пуст")
    except Exception as e:
        logger.error(f"Ошибка получения менеджеров: {e}")

    return settings.bitrix.albus_id


def create_deal(chat_id, course: str):
    if not chat_id or not course:
        logger.error(f"Неверные параметры: chat_id={chat_id}, course={course}")
        return None

    logger.debug(f"Создание сделки для chat_id={chat_id}, course={course}")

    customer = get_lms_id_by_chat_id(chat_id)
    logger.debug(f"Нашли в БД {customer}")

    lms_link = f"{settings.lms.domain}/clients/{customer}/"
    lms_customer = [] # TODO: заменить на метожд, который получит данные

    deal_data = DealData.from_customer_data(
        lms_customer=lms_customer,
        customer=customer,
        course=course,
        lms_link=lms_link,
        manager_id=_get_responsible_manager(),
    )
    bx_data = deal_data.to_bitrix_format()
    logger.debug(f"BX Data: {bx_data}")

    response = bitrix_bot.create_lead(lead_data=bx_data)
    return response

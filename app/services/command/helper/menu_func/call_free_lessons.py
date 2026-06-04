from typing import Any, Dict

from loguru import logger


from app.services.command.helper.constants_and_patterns import (
    free_lessons_fast_payment,
    free_lessons_referral_first,
    free_lessons_referral_second,
)


def get_free_lessons(lms_id: int) -> Dict[str, Any]:
    """Получение бонусных уроков"""
    logger.info(f"Start free lessons for lms_id: {lms_id}")

    lms_customer = [] #TODO: взять с апи или БД данные
    logger.debug(f"get lms customer = {lms_customer}")

    if not lms_customer:
        logger.error(f"LMS customer not found for id: {lms_id}")
        return dict(status="error", message="Клиент не найден", need_fill_form=False, schedule_text=None)

    message_to_bx = ""
    text = free_lessons_referral_first

    message_to_bx += text
    logger.debug(f"create text {text}")

    customer_lms_id = lms_customer.get("lms_id")
    referral_link = f"https://hwschool.pro/referee?fr={customer_lms_id}&utm_medium=max"
    logger.debug(f"create link {referral_link}")

    text = free_lessons_referral_second.format(link=referral_link)
    logger.debug(f"create new text {text}")
    message_to_bx += text

    links = lms_customer.get("links", {})
    if links.get("contact_id"):
        text = free_lessons_fast_payment
        message_to_bx += text
        logger.debug(f"create answer = {text}")

    return dict(status="success", message=message_to_bx, need_fill_form=False, schedule_text=None)

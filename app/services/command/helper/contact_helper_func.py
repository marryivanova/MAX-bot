import re

from loguru import logger

from app.bitrix.bx_method import get_users_by_phone_in_bitrix
from app.bitrix.core.bx_helper_method import add_by_phone_in_bitrix
from app.helper.parsers import extract_phone_from_vcard
from app.services.command.get_contact import send_choosing_answer_request_button, send_get_phone
from db.crud_db.create_new_user import create_max_customer


async def validate_phone_number(phone_number: str) -> bool:
    """
    Валидация номера телефона с проверкой формата ввода
    """
    if not phone_number or not isinstance(phone_number, str):
        return False

    if not re.match(r"^[\d\s\-()+]+$", phone_number.strip()):
        return False

    digits = re.sub(r"\D", "", phone_number)

    if len(digits) == 10:
        return True
    elif len(digits) == 11:
        return digits.startswith(("7", "8"))

    return False


async def process_contact(event, bot, vcf_info: str):
    """Полный цикл обработки контакта"""
    phone = extract_phone_from_vcard(vcf_info)
    if not phone:
        logger.warning("Не удалось извлечь телефон из vCard")
        return

    logger.success(f"Извлечён телефон: {phone}")

    bx_result, found = get_users_by_phone_in_bitrix(
        phone=phone,
        name_called_function="contact_handler",
        type_find="exact",
        return_found_status=True,
    )

    add_phone = add_by_phone_in_bitrix(
        phone=phone,
        name_called_function="contact_handler_phone_in_bitrix",
        type_find="exact",
    )

    logger.info(f"Результат поиска в Bitrix: {bx_result}")
    logger.info(f"Номер телефона добавлен в Bitrix: {add_phone}")

    chat_id = None
    if event.message.recipient:
        rcpt = event.message.recipient
        chat_id = getattr(rcpt, "chat_id", None) or rcpt.get("chat_id")

    if chat_id:
        if not found or not add_phone:
            await send_get_phone(bot, chat_id, phone)
            create_max_customer(chat_id=chat_id, phone=phone)
            await send_choosing_answer_request_button(bot, chat_id=chat_id)

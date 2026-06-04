from loguru import logger

from app.bitrix.bx_method import get_users_by_phone_in_bitrix
from app.helper.parsers import extract_phone_from_vcard
from app.services.command.get_contact import send_success_response
from app.services.command.helper.contact_helper_func_for_lms import (
    find_contact_to_update,
    get_bitrix_contact,
    get_lms_contacts_for_bitrix_contact,
    prepare_update_data,
    update_contact_in_lms,
)

# -------------------------------
#   ОБРАБОТКА КОНТАКТА ЦЕЛИКОМ
# -------------------------------


async def process_contact_lms(event, bot, vcf_info: str):
    """0бработки контакта"""

    phone, chat_id = get_basic_data(vcf_info, event)
    if not phone:
        return

    bitrix_contact = await handle_bitrix_operations(phone, vcf_info, bot, chat_id)
    if not bitrix_contact:
        return

    await handle_lms_operations(bitrix_contact, phone, bot, chat_id)


async def handle_lms_operations(bitrix_contact: dict, phone: str, bot, chat_id: int):
    """Все операции с LMS"""

    contact_id = bitrix_contact.get("ID")
    logger.debug(f"Получен контакт: {contact_id}")

    lms_contacts = get_lms_contacts_for_bitrix_contact(bitrix_contact)
    if not lms_contacts:
        logger.error("Не удалось получить контакты из LMS")
        if chat_id:
            await send_success_response(bot, chat_id=chat_id, phone=phone)
        return

    logger.info(f"Получено {len(lms_contacts)} контактов из LMS")

    contact_to_update = find_contact_to_update(lms_contacts, phone)
    if not contact_to_update:
        logger.error("Не найден подходящий контакт для обновления в LMS")
        if chat_id:
            await send_success_response(bot, chat_id=chat_id, phone=phone)

    logger.info(f"Выбран контакт для обновления: ID={contact_to_update.id}")

    update_data = prepare_update_data(contact=contact_to_update, chat_id=chat_id, phone=phone)
    update_result = update_contact_in_lms(update_data, contact_to_update.id)

    logger.debug(f"Результат обновления: {update_result}")

    logger.success("Обработка контакта завершена успешно")


def get_basic_data(vcf_info: str, event):
    """Извлекаем телефон и chat_id"""
    phone = extract_phone_from_vcard(vcf_info)
    if not phone:
        logger.warning("Не удалось извлечь телефон из vCard")
        return None, None

    logger.success(f"Извлечён телефон: {phone}")

    chat_id = None
    if event.message and event.message.recipient:
        rcpt = event.message.recipient
        chat_id = getattr(rcpt, "chat_id", None) or (rcpt.get("chat_id") if isinstance(rcpt, dict) else None)

    return phone, chat_id


async def handle_bitrix_operations(phone: str, vcf_info: str, bot, chat_id: int):
    """Все операции с Bitrix"""

    bx_result, found = get_users_by_phone_in_bitrix(
        phone=phone,
        name_called_function="contact_handler",
        type_find="exact",
        return_found_status=True,
    )
    logger.info(f"Результат поиска в Bitrix: {bx_result}")

    if not found:
        bitrix_contact = get_bitrix_contact(vcf_info)
        if not bitrix_contact or not bitrix_contact.get("ID"):
            logger.error("Не удалось создать/получить контакт в Bitrix")
            if chat_id:
                return None

        logger.info(f"Создан контакт в Bitrix: ID={bitrix_contact.get('ID')}")
        return bitrix_contact

    bitrix_contact = get_bitrix_contact(vcf_info)
    if not bitrix_contact:
        logger.error("Не удалось получить данные контакта из Bitrix")
        if chat_id:
            await send_success_response(bot, chat_id=chat_id, phone=phone)
        return None

    return bitrix_contact

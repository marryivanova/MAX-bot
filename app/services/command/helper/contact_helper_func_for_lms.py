from typing import Any, Dict, List, Optional

from loguru import logger

from app.bitrix.bx_method import get_users_by_phone_in_bitrix
from app.helper.parsers import extract_phone_from_vcard
from app.services.model.get_client_contact import CategoryInfo, ContactInfo, ContactUpdate
from db.db_bx.method import get_lms_from_db


def get_bitrix_contact(vcf_info: str) -> Optional[Dict[str, Any]]:
    """
    Получает контакт из Bitrix по телефону из vCard
    """
    phone = extract_phone_from_vcard(vcf_info)
    if not phone:
        logger.warning("Не удалось извлечь телефон из vCard")
        return None

    logger.debug(f"Поиск в Bitrix по телефону: {phone}")
    bx_result = get_users_by_phone_in_bitrix(phone=phone, name_called_function="contact_handler", type_find="exact")

    if not bx_result or bx_result.get("status") != "ok":
        logger.error("Не удалось получить данные из Bitrix")
        return None

    bitrix_contact = bx_result.get("message", {}).get("result", {})

    if not bitrix_contact:
        logger.error("Контакт не найден в Bitrix")
        return None

    logger.debug(f"Данные контакта из Bitrix: ID={bitrix_contact.get('ID')}")
    return bitrix_contact


def get_lms_contacts_for_bitrix_contact(
    bitrix_contact: Dict[str, Any],
) -> Optional[List[ContactInfo]]:
    """
    Получает все связанные контакты из LMS для контакта Bitrix
    """
    contact_id = bitrix_contact.get("ID")
    if not contact_id:
        logger.error("Отсутствует ID контакта Bitrix")
        return None

    logger.debug(f"Получение платформ из БД для контакта Bitrix ID={contact_id}...")

    lms_platforms = get_lms_from_db(id_bitrix_contact=contact_id)
    data_lms = [] #TODO: взять с апи или БД данные

    if not lms_platforms:
        logger.error(f"Не удалось получить платформы из БД для контакта Bitrix ID={contact_id}")
        return None

    logger.debug(f"Получено {len(data_lms)} платформ из БД")

    bitrix_parent_id = None
    for platform_info in data_lms:
        if platform_info.get("is_main") and platform_info.get("holder") == "parent":
            bitrix_parent_id = platform_info["holder_id"]
            id_parent = platform_info["id"]
            logger.debug(f"Найден основной id: holder_id={id_parent}")
            logger.debug(f"Найден основной parent: holder_id={bitrix_parent_id}")
            break

    if not bitrix_parent_id:
        for platform_info in data_lms:
            if platform_info.get("holder") == "parent":
                bitrix_parent_id = platform_info["holder_id"]
                logger.debug(f"Найден parent (не основной): holder_id={bitrix_parent_id}")
                break

    if not bitrix_parent_id:
        logger.error("Не найден parent контакт в платформах")
        return None

    logger.debug(f"Используем holder_id={bitrix_parent_id} для запроса к LMS")

    lms_response = [] #TODO: взять с апи или БД данные
    if not lms_response:
        logger.error("Не удалось получить контакты из LMS")
        return None

    contacts = parse_lms_contacts_response(lms_response)
    if not contacts:
        logger.error("Нет контактов в ответе от LMS")
        return None

    logger.debug(f"Успешно получено {len(contacts)} контактов из LMS")
    logger.debug(f"Информация по контактам: {contacts}")
    return contacts


def parse_lms_contacts_response(response_data: List[Dict]) -> List[ContactInfo]:
    """
    Парсит ответ от LMS API и преобразует в список ContactInfo объектов
    """
    contacts = []

    for contact_dict in response_data:
        categories = []
        active_categories = contact_dict.get("active_categories", [])

        for cat_dict in active_categories:
            if isinstance(cat_dict, dict):
                category = CategoryInfo(
                    id=cat_dict.get("id"),
                    title=cat_dict.get("title", ""),
                    is_for_parents=cat_dict.get("is_for_parents", False),
                    is_for_kids=cat_dict.get("is_for_kids", False),
                )
                categories.append(category)

        contact = ContactInfo(
            id=contact_dict.get("id"),
            title=contact_dict.get("title", ""),
            telegram_id=contact_dict.get("telegram_id"),
            max_id=contact_dict.get("max_id"),
            phone=contact_dict.get("phone", ""),
            is_main=contact_dict.get("is_main", False),
            holder=contact_dict.get("holder", ""),
            holder_id=contact_dict.get("holder_id"),
            is_telegram=contact_dict.get("is_telegram", False),
            is_whatsapp=contact_dict.get("is_whatsapp", False),
            is_max=contact_dict.get("is_max", False),
            is_child=contact_dict.get("is_child", False),
            active_categories=categories,
        )
        contacts.append(contact)

    return contacts


def find_contact_to_update(contacts: List[ContactInfo] | Any, phone: str) -> Optional[ContactInfo]:
    """
    Находит контакт для обновления по приоритетам:
    1. Контакт parent с совпадающим телефоном
    2. Контакт kid с совпадающим телефоном
    3. Первый контакт parent
    4. Первый контакт kid

    Возвращает None, если контакты отсутствуют
    """
    if not contacts:
        logger.warning("Список контактов пуст")
        return None

    # 1. Parent с совпадающим телефоном (высший приоритет)
    for contact in contacts:
        if contact.holder == "parent" and contact.phone == phone:
            logger.debug(f"Найден parent контакт с совпадающим телефоном: ID={contact.id}")
            return contact

    # 2. Kid с совпадающим телефоном
    for contact in contacts:
        if contact.holder == "kid" and contact.phone == phone:
            logger.debug(f"Найден kid контакт с совпадающим телефоном: ID={contact.id}")
            return contact

    # 3. Первый контакт parent (без совпадения телефона)
    for contact in contacts:
        if contact.holder == "parent":
            logger.debug(f"Выбран первый parent контакт: ID={contact.id}")
            return contact

    # 4. Первый контакт kid (без совпадения телефона)
    for contact in contacts:
        if contact.holder == "kid":
            logger.debug(f"Выбран первый kid контакт: ID={contact.id}")
            return contact

    logger.warning("Не найден подходящий контакт по приоритетам")
    return None


def prepare_update_data(contact: ContactInfo, chat_id: Optional[int], phone: str) -> Dict[str, Any]:
    """
    Подготавливает данные для обновления контакта в LMS
    """
    update_data = ContactUpdate(
        holder_id=contact.holder_id,
        holder=contact.holder,
        max_id=chat_id,
        phone=phone,
        is_max=True,
        is_main=contact.is_main,
    )

    logger.debug(f"Подготовлены данные для обновления: {update_data.dict()}")
    return update_data.dict()


def update_contact_in_lms(update_data: Dict[str, Any], contact_id: int) -> Optional[Dict[str, Any]]:
    """
    Обновляет контакт в LMS
    """
    logger.debug(f"Данные до моделирования: {update_data}")
    logger.info(f"Обновление контакта в LMS (ID={contact_id})...")
    update_data_model = ContactUpdate(**update_data)
    logger.debug(f"Данные для обновления: {update_data_model}")
    update_result = update_client_contact(update_data_model, client_contact_id=contact_id)

    if not update_result:
        logger.error("Ошибка при обновлении контакта в LMS")
        return None

    logger.success(f"Контакт ID={contact_id} успешно обновлен в LMS")
    return update_result

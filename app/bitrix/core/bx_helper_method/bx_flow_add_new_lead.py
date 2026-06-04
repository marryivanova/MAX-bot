import threading

from loguru import logger

from app.bitrix.bx_method import bitrix_bot, create_new_lead


def call_with_timeout(func, timeout=25, *args, **kwargs):
    """Универсальная функция для вызовов с таймаутом"""
    result = {}
    error = None

    def worker():
        nonlocal result, error
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error = e

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        logger.error(f"Таймаут {timeout}с при вызове {func.__name__}")
        return {}

    if error:
        logger.error(f"Ошибка при вызове {func.__name__}: {error}")
        return {}

    return result


def add_by_phone_in_bitrix(
    phone,
    contact_bitrix_id=None,
    lead_bitrix_id=None,
    name_called_function="Add phone in BX",
    type_find="",
):
    """
    Добавляет или обновляет контакт/лид в Bitrix24 по номеру телефона.
    """
    logger.debug(f"{name_called_function} || add_by_phone_in_bitrix ||\nНачинаем обработку телефона: {phone}")

    if contact_bitrix_id is not None or lead_bitrix_id is not None:
        result = update_existing_entity(
            phone=phone,
            contact_bitrix_id=contact_bitrix_id,
            lead_bitrix_id=lead_bitrix_id,
            name_called_function=name_called_function,
        )
        if result:
            return result

    logger.debug(f"{name_called_function} || add_by_phone_in_bitrix ||\nИщем клиентов по телефону: {phone}")

    data = {"TYPE": "PHONE", "VALUES": [phone]}

    response = call_with_timeout(bitrix_bot.find_duplicates_by_phone(phone), 25, data_for_find_duplicate=data)

    if not response:
        logger.error(f"{name_called_function} || Таймаут или ошибка при поиске дубликатов")
        search_result = {"CONTACT": [], "LEAD": []}
    elif response.get("status") == "error":
        logger.error(f"{name_called_function} || Ошибка при поиске дубликатов: {response.get('message')}")
        search_result = {"CONTACT": [], "LEAD": []}
    else:
        search_result = response.get("message", {}).get("result", {"CONTACT": [], "LEAD": []})

    logger.debug(f"{name_called_function} || add_by_phone_in_bitrix ||\nРезультат поиска: {search_result}")

    if not search_result:
        search_result = {"CONTACT": [], "LEAD": []}

    found_entity = handle_search_results(
        search_result=search_result,
        phone=phone,
        name_called_function=name_called_function,
        type_find=type_find,
    )

    if found_entity:
        return found_entity

    logger.debug(f"{name_called_function} || add_by_phone_in_bitrix ||\nНомер {phone} не найден в базе.")
    return None


def create_new_lead_with_directions(
    phone,
    chat_id,
    user_id,
    direction,
    name_called_function="Создание лида с направлением",
):
    """Создает лида, если пользователь выбрал направление."""
    lead_data = create_new_lead(
        phone=phone,
        user_id=user_id,
        chat_id=chat_id,
        direction=direction,
        name_called_function=name_called_function,
    )

    if lead_data:
        lead_data["TYPE"] = "lead"
        lead_data["IS_NEW"] = True
        logger.debug(f"{name_called_function} || Создан новый лид: {lead_data.get('ID')}")

    return lead_data


def update_existing_entity(phone, contact_bitrix_id=None, lead_bitrix_id=None, name_called_function="Update entity"):
    """Обновление существующего контакта или лида с таймаутом"""
    data = {"TYPE": "PHONE", "VALUES": [phone]}

    if contact_bitrix_id is not None:
        contact_data = call_with_timeout(bitrix_bot.get_contact, 25, contact_bitrix_id=contact_bitrix_id)
        if not contact_data:
            logger.error(f"{name_called_function} || Таймаут при получении контакта {contact_bitrix_id}")
            return None

        update_result = call_with_timeout(
            bitrix_bot.update_contact, 25, contact_bitrix_id=contact_bitrix_id, data_for_update=data
        )
        if not update_result:
            logger.error(f"{name_called_function} || Таймаут при обновлении контакта {contact_bitrix_id}")
            return None

        contact_data["TYPE"] = "contact"
        return contact_data

    if lead_bitrix_id is not None:
        lead_data = call_with_timeout(bitrix_bot.get_lead, 25, lead_bitrix_id=lead_bitrix_id)
        if not lead_data:
            logger.error(f"{name_called_function} || Таймаут при получении лида {lead_bitrix_id}")
            return None

        update_result = call_with_timeout(
            bitrix_bot.update_lead, 25, lead_bitrix_id=lead_bitrix_id, data_for_update=data
        )
        if not update_result:
            logger.error(f"{name_called_function} || Таймаут при обновлении лида {lead_bitrix_id}")
            return None

        lead_data["TYPE"] = "lead"
        return lead_data

    return None


def handle_search_results(search_result, phone, name_called_function="Handle search", type_find=""):
    """Обработка результатов поиска с таймаутами"""

    if search_result.get("CONTACT") and search_result["CONTACT"]:
        contact_id = search_result["CONTACT"][0]
        logger.info(f"{name_called_function} || Найден контакт в Битрикс || contact_id={contact_id}")

        contact_data = call_with_timeout(bitrix_bot.get_contact, 25, contact_bitrix_id=contact_id)

        if contact_data:
            contact_data["TYPE"] = "contact"
            logger.info(f"{name_called_function} || Успешно найден контакт с ID={contact_id}")

            if type_find and type_find.upper() == "LEAD":
                return None
            return contact_data
        else:
            logger.error(f"{name_called_function} || Таймаут при получении контакта {contact_id}")

    elif search_result.get("LEAD") and search_result["LEAD"]:
        lead_id = search_result["LEAD"][0]
        logger.info(f"{name_called_function} || Найден лид в Битрикс || lead_id={lead_id}")

        lead_data = call_with_timeout(bitrix_bot.get_lead, 25, lead_bitrix_id=lead_id)

        if lead_data:
            lead_data["TYPE"] = "lead"
            logger.info(f"{name_called_function} || Успешно найден лид с ID={lead_id}")
            return lead_data
        else:
            logger.error(f"{name_called_function} || Таймаут при получении лида {lead_id}")

    return None

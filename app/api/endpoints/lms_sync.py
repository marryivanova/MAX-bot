from typing import Optional, Union

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from loguru import logger
from max_sdk.core.helper.getted_updates import process_update_webhook
from max_sdk.dispatcher import Bot, Dispatcher, Router
from pydantic import BaseModel

from app.api.endpoints.helper.helper_sync_lms import (
    extract_client_id_from_url,
    extract_platform_url_from_bitrix_contact,
)
from app.bitrix.bx_method import get_users_by_phone_in_bitrix
from app.bitrix.core.bitrix_send_alert import send_to_chat_sync_max_id, send_to_manager_max_for_sync_max_id
from app.lms.get_client_contact import get_contact_lms
from app.services.command.helper.contact_helper_func_for_lms import (
    find_contact_to_update,
    get_lms_contacts_for_bitrix_contact,
    parse_lms_contacts_response,
    update_contact_in_lms,
)
from app.services.model.all_url import MaxUrl
from app.services.model.model_lms_sync import SyncLMSResponse
from db.crud_db.get_max_user_chat_id import get_max_user_by_chat_id
from db.db_bx.method import get_lead_from_db, get_lms_from_db

router = APIRouter(prefix="/api", tags=["Lms sync"])


async def get_max_id_by_phone(phone: str, webhook_handler) -> Optional[str]:
    """Получить MAX ID по номеру телефона"""
    logger.info(f"Поиск chat_id в MAX боте по телефону: {phone}")
    max_id = await webhook_handler.get_chat_id_by_phone(phone)
    if not max_id:
        logger.error(f"Не удалось найти chat_id для пользователя {phone}")
    return max_id


def get_bitrix_contact_by_phone(phone: str) -> Optional[dict]:
    """Найти контакт в Битрикс по номеру телефона"""
    logger.info(f"Поиск контакта в Битрикс по телефону: {phone}")
    return get_users_by_phone_in_bitrix(phone=phone, name_called_function="sync_lms_max_id", type_find="exact")


def handle_lead_contact(bitrix_contact: dict, phone: str) -> dict:
    """Обработка лида в Битрикс"""
    contact_id = bitrix_contact.get("ID")
    logger.info(f"Обработка ЛИДА (ID={contact_id})")

    lead_id_from_db = get_lead_from_db(id_bitrix_contact=contact_id, name_called_function="sync_lms_max_id_lead")

    if lead_id_from_db:
        return _process_lead_from_db(lead_id_from_db, phone, contact_id)
    else:
        return _process_lead_from_platform_url(bitrix_contact, phone, contact_id)


def _process_lead_from_db(lead_id: str, phone: str, contact_id: str) -> dict:
    """Обработка лида найденного в БД LMS"""
    logger.success(f"Найден лид в БД LMS: {lead_id}")

    contacts_response = get_contact_lms(int(lead_id))
    contact_to_update = find_contact_to_update(contacts_response, phone)

    if not contact_to_update and contacts_response:
        contact_to_update = contacts_response[0]

    return _prepare_lead_response(contact_to_update, lead_id, contact_id, True)


def _process_lead_from_platform_url(bitrix_contact: dict, phone: str, contact_id: str) -> dict:
    """Обработка лида через URL платформы"""
    platform_url = extract_platform_url_from_bitrix_contact(bitrix_contact)
    if not platform_url:
        raise ValueError("Не найден URL платформы в контакте")

    logger.success(f"Найден URL платформы: {platform_url}")

    lms_client_id = extract_client_id_from_url(platform_url)
    if not lms_client_id:
        raise ValueError("Не удалось извлечь client_id из URL платформы")

    contacts_response = get_contact_lms(int(lms_client_id))
    cont_list = parse_lms_contacts_response(contacts_response)
    logger.debug(f"Список контактов карточки: {cont_list}")
    contact_to_update = find_contact_to_update(cont_list, phone)
    logger.debug(f"Выбор по совпадению номера: {contact_to_update}")

    if not contact_to_update:
        contact_to_update = _find_any_contact(contacts_response, phone)

    return _prepare_lead_response(contact_to_update, lms_client_id, contact_id, False)


def _find_any_contact(contacts_response: list, phone: str):
    """Найти любой контакт для обновления"""
    for contact in contacts_response:
        if contact.get("phone"):
            return contact
    return contacts_response[0] if contacts_response else None


def _prepare_lead_response(contact_to_update: dict, lms_client_id: str, contact_id: str, from_db: bool) -> dict:
    """Подготовить ответ для лида"""
    if not contact_to_update:
        raise ValueError("Не найден контакт клиента в LMS")

    return dict(
        contact_to_update=contact_to_update,
        lms_client_id=lms_client_id,
        contact_id=contact_id,
        is_lead_in_lms=from_db,
        contact_type="lead",
    )


def handle_regular_contact(bitrix_contact: dict, phone: str) -> dict:
    """Обработка обычного контакта в Битрикс"""
    contact_id = None
    if "message" in bitrix_contact and "result" in bitrix_contact["message"]:
        contact_id = bitrix_contact["message"]["result"].get("ID")
    elif "ID" in bitrix_contact:
        contact_id = bitrix_contact.get("ID")

    logger.info(f"Обработка КОНТАКТА (ID={contact_id})")

    lms_id_from_db = get_lms_from_db(id_bitrix_contact=contact_id, name_called_function="sync_lms_max_id_contact")
    logger.debug(f"lms_id_from_db = {lms_id_from_db}")

    if lms_id_from_db:
        result = _process_contact_from_db(lms_id_from_db, phone, contact_id)
        if result.get("contact_to_update"):
            logger.success("Контакт найден и обработан через БД")
            return result
        else:
            logger.warning("Контакт из БД не содержит подходящего контакта для обновления, переходим к общему методу")

    logger.info("Переход к общему методу поиска")
    return _process_contact_from_general_method(bitrix_contact, phone, contact_id)


def _process_contact_from_db(lms_id: str, phone: str, contact_id: str) -> dict:
    """Обработка контакта найденного в БД LMS"""
    logger.success(f"Найден контакт в БД LMS: {lms_id}")

    lms_response = get_contact_lms(client_user_id=int(lms_id))
    if not lms_response:
        logger.warning(f"Нет данных в LMS для ID={lms_id}")
        return {}

    contacts = parse_lms_contacts_response(lms_response)
    logger.debug(f"Получено контактов из LMS: {len(contacts)}")

    contact_to_update = find_contact_to_update(contacts, phone)

    if contact_to_update:
        return dict(
            contact_to_update=contact_to_update,
            lms_client_id=lms_id,
            contact_id=contact_id,
            contact_type="contact",
        )
    else:
        logger.warning(f"Не найден подходящий контакт для номера {phone} в карточке LMS ID={lms_id}")

    return {}


def _process_contact_from_general_method(bitrix_contact: dict, phone: str, contact_id: str) -> dict:
    """Обработка контакта через общий метод поиска"""
    lms_contacts = get_lms_contacts_for_bitrix_contact(bitrix_contact)
    if not lms_contacts:
        raise ValueError("Не найден подходящий контакт в LMS")

    logger.info(f"Получено {len(lms_contacts)} контактов из LMS")

    contact_to_update = find_contact_to_update(lms_contacts, phone)
    if not contact_to_update:
        raise ValueError("Не найден подходящий контакт для обновления")

    return dict(
        contact_to_update=contact_to_update,
        lms_client_id=None,
        contact_id=contact_id,
        contact_type="contact",
    )


def prepare_update_data(contact_to_update: dict, max_id: str, contact_type: str) -> dict:
    """Подготовить данные для обновления контакта"""
    if hasattr(contact_to_update, "id"):
        contact_id = contact_to_update.id
        holder = contact_to_update.holder if contact_to_update.holder else "parent"
        holder_id = getattr(contact_to_update, "holder_id", contact_id)
    elif isinstance(contact_to_update, dict):
        contact_id = contact_to_update.get("id")
        holder = contact_to_update.get("holder", "parent")
        holder_id = contact_to_update.get("holder_id", contact_id)
    else:
        raise ValueError("Некорректный формат contact_to_update")

    return dict(
        id=contact_id,
        max_id=max_id,
        holder=holder,
        holder_id=holder_id,
        is_max=True,
    )


def check_max_id_needs_update(old_max_id: Optional[str], new_max_id: str, contact_type: str) -> bool:
    """Проверить, нужно ли обновлять MAX ID"""
    if not old_max_id:
        return True
    return old_max_id != new_max_id


@router.get(
    "/sync-lms-max-id",
    response_model=SyncLMSResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_lms_max_id(
    phone: Union[str, int] = Query(..., description="Номер телефона клиента"),
    request: Request = None,
):
    """
    Синхронизация MAX ID между MAX ботом, Битрикс и LMS платформой.

    ## Описание
    Этот эндпоинт позволяет связать пользователя MAX бота с сущностью в Битрикс,
    передав в LMS платформу max_id (chat_id из MAX бота) для дальнейших рассылок.

    Поддерживает два типа сущностей в Битрикс:
    1. Лиды (LEAD) - потенциальные клиенты
    2. Контакты (CONTACT) - существующие клиенты

    ## Логика работы
    1. По номеру телефона ищется chat_id в MAX боте
    2. По тому же номеру находится контакт/лид в Битрикс
    3. В зависимости от типа контакта применяется разная логика поиска в LMS:
       - Для лидов: сначала проверяется локальная БД, затем URL платформы из поля WEB
       - Для контактов: сначала проверяется локальная БД, затем общий поиск
    4. Найденный контакт в LMS обновляется с новым max_id

    ## Параметры запроса
    - **phone** (string/integer, обязательный): Номер телефона клиента для поиска

    ## Ответ
    Возвращает объект SyncLMSResponse со следующими полями:
    - **success** (boolean): Статус выполнения операции
    - **error** (string или null): Сообщение об ошибке (если есть)
    - **message** (string): Информационное сообщение
    - **max_id** (string): Установленный MAX ID
    - **phone** (string): Номер телефона
    - **contact_id** (string): ID контакта в Битрикс
    - **contact_type** (string): Тип контакта ('lead' или 'contact')
    - **lead_id** (string, optional): ID лида (только для лидов)
    - **lms_client_id** (string, optional): ID клиента в LMS
    - **old_max_id** (string, optional): Предыдущий MAX ID
    - **is_lead_in_lms** (boolean, optional): Флаг лида в LMS
    - **updated_fields** (list, optional): Список обновленных полей

    ## Коды состояния HTTP
    - **200 OK**: Операция выполнена успешно
    - **400 Bad Request**: Неверные параметры запроса (например, невалидный номер телефона)
    - **404 Not Found**: Контакт не найден в Битрикс или MAX боте
    - **422 Unprocessable Entity**: Ошибка валидации данных (отсутствует URL платформы и т.д.)
    - **500 Internal Server Error**: Внутренняя ошибка сервера
    - **503 Service Unavailable**: Сервис временно недоступен
    - **504 Gateway Timeout**: Превышено время ожидания ответа от внешнего сервиса
    """

    additional_info = dict()
    filtered_info = dict()

    try:
        logger.info(f"=== НАЧАЛО РАБОТЫ sync_lms_max_id ===")
        phone_str = str(phone).strip()

        # 1. Получение MAX ID
        webhook_handler = request.app.state.webhook_handler
        if not webhook_handler:
            raise ValueError("Webhook handler не инициализирован")

        max_id = await get_max_id_by_phone(phone_str, webhook_handler)
        if not max_id:
            return SyncLMSResponse(
                success=False,
                error=f"Не удалось найти chat_id для пользователя {phone_str}",
                phone=phone_str,
            )

        # 2. Поиск контакта в Битрикс
        bitrix_contact = get_bitrix_contact_by_phone(phone_str)
        if not bitrix_contact:
            return SyncLMSResponse(
                success=False,
                error=f"Контакт не найден в Битрикс по номеру {phone_str}",
                phone=phone_str,
                max_id=max_id,
            )

        contact_id = bitrix_contact.get("ID")
        contact_type_raw = bitrix_contact.get("TYPE", "").lower().replace("_", "")

        # 3. Разделение логики по типу контакта
        if contact_type_raw == "lead":
            contact_info = handle_lead_contact(bitrix_contact, phone_str)
        else:
            contact_info = handle_regular_contact(bitrix_contact, phone_str)

        contact_to_update = contact_info["contact_to_update"]

        # 4. Проверка необходимости обновления MAX ID
        old_max_id = (
            contact_to_update.get("max_id")
            if isinstance(contact_to_update, dict)
            else getattr(contact_to_update, "max_id", None)
        )

        if not check_max_id_needs_update(old_max_id, max_id, contact_type_raw):
            return SyncLMSResponse(
                success=True,
                message=f"MAX ID уже установлен и совпадает: {max_id}",
                max_id=max_id,
                phone=phone_str,
                contact_id=contact_id,
                contact_type=contact_type_raw,
                lms_client_id=contact_info.get("lms_client_id"),
                is_lead_in_lms=contact_info.get("is_lead_in_lms", False),
            )

        # 5. Обновление контакта в LMS
        max_user = get_max_user_by_chat_id(chat_id=max_id)
        if max_user is not None:
            final_max_id = max_user["chat_id"]
        else:
            final_max_id = max_id

        update_data = prepare_update_data(contact_to_update, max_id=final_max_id, contact_type=contact_type_raw)
        update_result = update_contact_in_lms(update_data=update_data, contact_id=update_data["id"])

        if contact_type_raw == "lead":
            additional_info.update(
                dict(
                    lead_id=bitrix_contact.get("ID"),
                    lead_url=f"{MaxUrl.url_lead.value}{bitrix_contact.get('ID')}/",
                )
            )
        else:
            additional_info.update(
                dict(
                    contact_id=bitrix_contact.get("ID"),
                    contact_url=f"{MaxUrl.url_contact.value}{bitrix_contact.get('ID')}/",
                )
            )

        additional_info.update(
            dict(
                chat_id=max_id,
                phone=phone_str,
                contact_type=contact_type_raw,
                lms_client_id=contact_info.get("lms_client_id"),
                is_lead_in_lms=contact_info.get("is_lead_in_lms", False),
            )
        )

        filtered_info = {k: v for k, v in additional_info.items() if v is not None}

        if not update_result:
            raise ValueError("Не удалось обновить контакт в LMS")

        send_to_manager_max_for_sync_max_id(
            chat_id=additional_info.get("chat_id"), system="MAX — ОБНАРУЖЕН НОВЫЙ ГОСТЬ В БОТЕ 🚨"
        )

        return SyncLMSResponse(
            success=True,
            message=f"MAX ID успешно обновлен: {max_id}",
            max_id=max_id,
            phone=phone_str,
            contact_id=contact_id,
            lead_id=contact_id if contact_type_raw == "lead" else None,
            contact_type=contact_type_raw,
            lms_client_id=contact_info.get("lms_client_id"),
            old_max_id=old_max_id,
            is_lead_in_lms=contact_info.get("is_lead_in_lms", False),
            updated_fields=list(update_data.keys()),
        )

    except ValueError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        send_to_chat_sync_max_id(
            chat_id=additional_info.get("chat_id"),
            system=f"MAX id LMS CRITICAL ERROR: {str(e)} -> Клиенту не проставлен MAX_ID",
            additional_info=filtered_info,
        )
        send_to_manager_max_for_sync_max_id(
            chat_id=additional_info.get("chat_id"),
            system=f"MAX id LMS CRITICAL ERROR: {str(e)} -> Клиенту не проставлен MAX_ID",
            additional_info=filtered_info,
        )
        return SyncLMSResponse(success=False, error=str(e), phone=str(phone) if phone else None)
    except TimeoutError as e:
        logger.error(f"Таймаут: {str(e)}")
        return SyncLMSResponse(
            success=False,
            error="Превышено время ожидания ответа",
            phone=str(phone) if phone else None,
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        logger.exception("Детали ошибки")
        if additional_info:
            send_to_chat_sync_max_id(
                chat_id=additional_info.get("chat_id"),
                system="MAX id LMS CRITICAL ERROR -> Клиенту не проставлен MAX_ID",
                additional_info=filtered_info,
            )
        return SyncLMSResponse(
            success=False,
            error=f"Внутренняя ошибка сервера: {str(e)}",
            phone=str(phone) if phone else None,
        )
    finally:
        logger.info("=== ЗАВЕРШЕНИЕ РАБОТЫ sync_lms_max_id ===")

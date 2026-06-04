import re
from datetime import datetime
from inspect import stack
from typing import Any, Dict, Optional

from bitrix24 import Bitrix24
from loguru import logger

from app.bitrix.core import BitrixSDK
from app.bitrix.core.model import ListAlertID
from app.bitrix.core.model.status_code import MaxHttpStatus
from app.services.model.all_url import MaxUrl
from db.crud_db.get_lms_id import get_info_lms
from db.crud_db.get_max_user_chat_id import get_max_user_by_chat_id
from settings import settings


class AlertNotifier:

    def __init__(self) -> None:
        self.albus: BitrixSDK = BitrixSDK(
            bitrix_token=settings.bitrix_bots.max_token,
            bitrix_user_id=settings.bitrix_bots.max_id,
        )

    def send_to_chat(self, chat_id: str, message: str, system: Optional[str] = None):
        if system:
            message = f"[{system}]\n{message}"

        try:
            response = self.albus.call_method("im.message.add", {"DIALOG_ID": f"{chat_id}", "MESSAGE": message})
            if response and response.get("result"):
                logger.info(f"Сообщение отправлено в чат {chat_id}")
            else:
                logger.error(f"Ошибка отправки в чат {chat_id}: {response}")
        except Exception as e:
            logger.error(f"Исключение при отправке в чат {chat_id}: {e}")

    @staticmethod
    def build_error_message(
        error: Optional[str] = None,
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts = [
            "\n[B]⚠️ ОБНАРУЖЕНА ОШИБКА ПРИ ОТПРАВКЕ СООБЩЕНИЯ В MAX[/B]\n",
        ]

        if error:
            http_status = AlertNotifier._parse_error_status(error)

            if http_status:
                if http_status.is_client_error:
                    error_line = f"👤 [КЛИЕНТСКАЯ ОШИБКА] {error}"
                elif http_status.is_server_error:
                    error_line = f"🔧 [СЕРВЕРНАЯ ОШИБКА] {error}"
                elif http_status.is_permanent_failure:
                    error_line = f"⛔ [ПОСТОЯННАЯ ОШИБКА] {error}"
                elif http_status.is_retryable:
                    error_line = f"🔄 [ПОВТОРЯЕМАЯ ОШИБКА] {error}"
                else:
                    error_line = f"❌ {error}"

                parts.append(error_line)

                user_message = http_status.get_user_message("ru")
                parts.append(f"📌 Описание: {user_message}")

                if http_status.is_retryable:
                    parts.append("💡 Рекомендация: Повторите запрос позже")
                elif http_status.is_permanent_failure or http_status.is_client_error:
                    parts.append("💡 Рекомендация: Проверьте правильность chat_id или данных лида/контакта")
                elif http_status.is_server_error:
                    parts.append("💡 Рекомендация: Обратитесь к администратору системы")
            else:
                parts.append(f"{error}")

        if additional_info:
            parts.append("\n📋 Дополнительная информация:")
            for key, value in additional_info.items():
                if key == "chat_id" and value:
                    chat_id_str = str(value)
                    if len(chat_id_str) != 8:
                        parts.append(f"\n  • {key}: {value} ⚠️ (необычная длина: {len(chat_id_str)} вместо 8)")
                    else:
                        parts.append(f"  • {key}: {value}")
                elif value:
                    parts.append(f"  • {key}: {value}")

        return "\n".join(parts)

    @staticmethod
    def _parse_error_status(error: str) -> Optional[MaxHttpStatus]:
        match = re.search(r"(\d{3})", str(error))
        if match:
            return MaxHttpStatus.from_http_code(int(match.group(1)))
        return None


def send_to_chat_service_manager(
    chat_id: str,
    message: str,
    system: Optional[str] = "",
    additional_info: Optional[Dict[str, Any]] = None,
):
    notifier = AlertNotifier()

    client_info = dict(
        name="",
        age="",
        timezone="",
        platform_link="",
    )
    max_user_data = get_max_user_by_chat_id(chat_id=chat_id)

    if max_user_data:
        lead_id = max_user_data.get("lead_id")
        contact_id = max_user_data.get("contact_id")

        lms_info = get_info_lms(
            chat_id=chat_id,
            lead_id=lead_id if isinstance(lead_id, int) else None,
            contact_id=contact_id if isinstance(contact_id, int) else None,
        )

        if lms_info:
            client_info["platform_link"] = f"[B]Платформа [/B]: {lms_info['client_link']}\n"
            client_info["name"] = lms_info.get("name", client_info["name"])
            client_info["timezone"] = lms_info.get("timezone", client_info["timezone"])

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "+00:00"
    full_message = f"[B]Клиенту [/B] {client_info['name']} [{client_info['timezone']}] - не было доставлено сообщение в {current_time}\n{client_info['platform_link']} [B]Причина [/B]: {message}"

    if system:
        full_message = f"[{system}]\n{full_message}"

    if additional_info:
        for key, value in additional_info.items():
            full_message += f"\n{key}: {value}"

    notifier.send_to_chat(
        chat_id=ListAlertID.id_alert_chat.value,
        message=full_message,
        system=system,
    )


def send_to_manager_max_for_sync_max_id(
    chat_id: str,
    system: Optional[str] = "",
    additional_info: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Отправляет все события менеджеру при появлении нового клиента.
    Отправляет в чат информацию о клиенте: name, age, phone, platform_link.
    """
    notifier = AlertNotifier()

    client_info = dict(name="", phone="", client_link="", lead_id="", contact_id="")

    max_user_data = get_max_user_by_chat_id(chat_id=chat_id)

    if max_user_data:
        lead_id = max_user_data.get("lead_id")
        contact_id = max_user_data.get("contact_id")
        client_info["phone"] = max_user_data.get("phone", "")
        client_info["lead_id"] = lead_id if lead_id else ""
        client_info["contact_id"] = contact_id if contact_id else ""

        lms_info = get_info_lms(
            chat_id=chat_id,
            lead_id=lead_id if isinstance(lead_id, int) else None,
            contact_id=contact_id if isinstance(contact_id, int) else None,
        )

        if lms_info:
            client_info["name"] = lms_info.get("name", "")
            client_info["client_link"] = lms_info.get("client_link", "")

    message = f"Ура! Новый клиент :)\n\n"
    message += f"Информация о клиенте:\n"
    message += f"Имя: {client_info['name']}\n"
    message += f"MAX_ID: {chat_id}\n"
    message += f"Телефон: {client_info['phone']}\n"
    message += f"Ссылка: {client_info['client_link']}\n"

    if client_info.get("lead_id"):
        message += f"Lead ID: {MaxUrl.url_lead.value}{client_info['lead_id']}/\n"
    if client_info.get("contact_id"):
        message += f"Contact ID: {MaxUrl.url_contact.value}{client_info['contact_id']}/\n"

    if additional_info:
        for key, value in additional_info.items():
            message += f"{key}: {value}\n"

    notifier.send_to_chat(
        chat_id=ListAlertID.id_alert_for_manager.value,
        message=message,
        system=system,
    )


def send_to_chat_sync_max_id(
    chat_id: str,
    system: Optional[str] = "",
    additional_info: Optional[Dict[str, Any]] = None,
):
    notifier = AlertNotifier()
    client_info = dict(name="", age="", phone="", platform_link="")

    max_user_data = get_max_user_by_chat_id(chat_id=chat_id)

    if max_user_data:
        lead_id = max_user_data.get("lead_id")
        contact_id = max_user_data.get("contact_id")
        client_info["phone"] = max_user_data.get("phone", "")

        lms_info = get_info_lms(
            chat_id=chat_id,
            lead_id=lead_id if isinstance(lead_id, int) else None,
            contact_id=contact_id if isinstance(contact_id, int) else None,
        )

        if lms_info:
            client_info["platform_link"] = f"[B]Платформа [/B]: {lms_info['client_link']}\n"
            client_info["name"] = lms_info.get("name", client_info["name"])

    full_message = (
        f"[B]Клиенту [/B] {client_info['name']} - "
        f"Не произошел синк платформы и max_id - "
        f"нужно перейти по ссылке и проставить руками в соответствии "
        f"с номером {client_info['phone']}\n"
        f"{client_info['platform_link']}"
    )

    if additional_info:
        for key, value in additional_info.items():
            full_message += f"\n{key}: {value}"

    notifier.send_to_chat(
        chat_id=ListAlertID.id_alert_max_id.value,
        message=full_message,
        system=system,
    )


def send_to_chat_error(
    message: str,
    error: Optional[str] = None,
    additional_info: Optional[Dict[str, Any]] = None,
    system: Optional[str] = "MAX Bot API",
) -> None:
    notifier = AlertNotifier()

    logger.debug(f"📦 send_to_chat_error получен additional_info: {additional_info}")

    if additional_info:
        chat_id = additional_info.get("chat_id")
        lead_id = additional_info.get("lead_id")
        contact_id = additional_info.get("contact_id")

        if lead_id and isinstance(lead_id, str):
            match = re.search(r"(\d+)", lead_id)
            if match:
                lead_id = int(match.group(1))
                additional_info["lead_id_parsed"] = lead_id
                logger.debug(f"🔍 Извлечён lead_id из строки: {lead_id}")

        if contact_id and isinstance(contact_id, str):
            match = re.search(r"(\d+)", contact_id)
            if match:
                contact_id = int(match.group(1))
                additional_info["contact_id_parsed"] = contact_id
                logger.debug(f"🔍 Извлечён contact_id из строки: {contact_id}")

        if chat_id or lead_id or contact_id:
            logger.info(f"🔍 Вызов get_info_lms с chat_id={chat_id}, lead_id={lead_id}, contact_id={contact_id}")

            db_client_link = get_info_lms(
                chat_id=str(chat_id) if chat_id else "",
                lead_id=lead_id if isinstance(lead_id, int) else None,
                contact_id=contact_id if isinstance(contact_id, int) else None,
            )

            if db_client_link:
                additional_info["client_link_from_db"] = db_client_link
                logger.info(f"✅ Найдена ссылка на клиента: {db_client_link}")
            else:
                logger.warning(f"⚠️ Ссылка на клиента не найдена в БД")

    if error:
        http_status = AlertNotifier._parse_error_status(error)
        if http_status:
            if http_status.is_server_error:
                logger.error(f"🔧 Серверная ошибка ({http_status.code}): {error}")
            elif http_status.is_client_error:
                logger.warning(f"👤 Клиентская ошибка ({http_status.code}): {error}")
            elif http_status.is_retryable:
                logger.warning(f"🔄 Повторяемая ошибка ({http_status.code}): {error}")
            else:
                logger.error(f"Ошибка: {error}")
        else:
            logger.error(f"Ошибка: {error}")

    if additional_info and "chat_id" in additional_info:
        chat_id = str(additional_info["chat_id"])
        if len(chat_id) not in [8, 9, 10, 11]:
            logger.warning(f"⚠️ chat_id имеет необычную длину: {len(chat_id)} (обычно 8-11 цифр)")

    error_message = notifier.build_error_message(
        error=error,
        additional_info=additional_info,
    )

    full_message = f"{message}\n\n{error_message}"

    notifier.send_to_chat(
        chat_id=ListAlertID.id_alert_developers.value,
        message=full_message,
        system=system,
    )


def send_message_to_bx_chat(text):
    caller_frame = stack()[1]
    func_name = caller_frame.function
    text = f"{text}\n[SIZE=8][COLOR=#8a8a8a] Отправлено с сервера MAX- #{func_name}[/COLOR][/SIZE]"
    notifier = AlertNotifier()

    result = notifier.send_to_chat(chat_id=ListAlertID.vacation_chat.value, message=text)
    logger.debug(f"{func_name} || Результат отправки сообщения: {result}")
    return result

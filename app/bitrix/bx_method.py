import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from app.bitrix.core.bitrix_sdk import BxBots
from db.crud_db.add_table_max_lead_or_contact import update_max_user_from_bitrix

bitrix_bot = BxBots.max


class BitrixUserService:
    """Сервис для работы с пользователями Bitrix"""

    TIMEOUT_SECONDS = 25

    def __init__(self, bitrix_client=None):
        self.bitrix_client = bitrix_client or bitrix_bot
        self._thread_local = threading.local()

    @staticmethod
    def normalize_phone(phone: str) -> Optional[str]:
        """Нормализация номера телефона"""
        if not phone:
            return None

        digits = "".join(filter(str.isdigit, phone))
        if not digits:
            return None

        if digits.startswith("8") and len(digits) == 11:
            return "+7" + digits[1:]
        if digits.startswith("9") and len(digits) == 10:
            return "+7" + digits
        if digits.startswith("7") and len(digits) == 11:
            return "+" + digits

        return digits

    def _call_with_timeout(self, method: str, params: Dict = None, timeout: int = None) -> Optional[Dict]:
        if params is None:
            params = {}

        timeout = timeout or self.TIMEOUT_SECONDS
        result = {}
        error = None

        def call_method():
            nonlocal result, error
            try:
                result = self.bitrix_client.call_method(method, params, timeout=timeout)
            except Exception as e:
                error = e

        thread = threading.Thread(target=call_method)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            logger.error(f"ТАЙМАУТ {timeout} сек при вызове {method}")
            return None

        if error:
            logger.error(f"Ошибка при вызове {method}: {error}")
            return None

        return result

    def get_users_by_phone(
        self,
        phone: str,
        type_find: str = "",
        return_found_status: bool = False,
        name_called_function: Optional[str] = None,
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], bool]]:
        """
        Получение пользователя (лида или контакта) по номеру телефона

        Args:
            phone: Номер телефона для поиска
            type_find: Тип сущности для поиска ("LEAD" или "CONTACT")
            return_found_status: Возвращать кортеж (данные, найдено) или только данные
            name_called_function: Имя вызывающей функции для логирования

        Returns:
            Данные найденной сущности или None
        """
        func_name = name_called_function or "get_users_by_phone_in_bitrix"
        logger.debug(f"{func_name} || Запуск поиска по телефону: {phone}")

        normalized_phone = self.normalize_phone(phone)
        if not normalized_phone:
            logger.warning(f"{func_name} || Некорректный номер: {phone}")
            return self._empty_result(return_found_status)

        logger.info(f"{func_name} || Поиск по номеру: {normalized_phone}")

        duplicates = self._find_duplicates(normalized_phone, func_name)
        if duplicates is None:
            return self._empty_result(return_found_status)

        self._update_max_user_background(normalized_phone, duplicates, func_name)
        return self._find_entity(duplicates, type_find, return_found_status, func_name)

    def _find_duplicates(self, phone: str, func_name: str) -> Optional[Dict[str, list]]:
        """Поиск дубликатов по телефону"""
        data = {"entity_type": "LEAD", "type": "PHONE", "values": [phone]}
        logger.debug(f"{func_name} || Поиск дубликатов с данными: {data}")

        response = self._call_with_timeout("crm.duplicate.findbycomm", data)

        if response is None:
            return None

        logger.debug(f"{func_name} || Ответ find_duplicates: {response}")

        if response.get("error"):
            error_msg = response.get("error_description", "Неизвестная ошибка")
            logger.error(f"{func_name} || Ошибка при поиске дубликатов: {error_msg}")
            return None

        result = response.get("result", {})
        logger.info(f"{func_name} || Результат поиска дубликатов: {result}")
        return result

    def _update_max_user_background(self, phone: str, duplicates: Dict, func_name: str) -> None:
        """Фоновое обновление максимального пользователя"""
        try:
            thread = threading.Thread(
                target=self._update_max_user_safe, args=(phone, duplicates, func_name), daemon=True
            )
            thread.start()
        except Exception as e:
            logger.error(f"{func_name} || Ошибка запуска фонового обновления: {e}")

    @staticmethod
    def _update_max_user_safe(phone: str, duplicates: Dict, func_name: str) -> None:
        """Безопасное обновление максимального пользователя"""
        try:
            update_max_user_from_bitrix(phone=phone, bitrix_data=duplicates)
            logger.debug(f"{func_name} || update_max_user_from_bitrix выполнен успешно")
        except Exception as e:
            logger.error(f"{func_name} || Ошибка в update_max_user_from_bitrix: {e}", exc_info=True)

    def _find_entity(
        self, duplicates: Dict, type_find: str, return_found_status: bool, func_name: str
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], bool]]:
        """Поиск сущности среди дубликатов"""

        if not type_find or type_find.upper() != "LEAD":
            contact_result = self._get_contact_from_duplicates(duplicates, func_name)
            if contact_result:
                return self._format_result(contact_result, return_found_status)

        if not type_find or type_find.upper() != "CONTACT":
            lead_result = self._get_lead_from_duplicates(duplicates, func_name)
            if lead_result:
                return self._format_result(lead_result, return_found_status)

        logger.warning(f"{func_name} || Пользователь не найден")
        return self._empty_result(return_found_status)

    def _get_contact_from_duplicates(self, duplicates: Dict, func_name: str) -> Optional[Dict]:
        """Получение контакта из дубликатов"""
        if not duplicates.get("CONTACT"):
            return None

        contact_id = duplicates["CONTACT"][0]
        logger.info(f"{func_name} || Найден контакт: {contact_id}")

        contact_response = self._call_with_timeout("crm.contact.get", {"id": int(contact_id)})

        if contact_response and contact_response.get("result"):
            contact_info = contact_response["result"]
            contact_info["TYPE"] = "contact"
            logger.info(f"{func_name} || Данные контакта получены")
            return contact_info

        logger.warning(f"{func_name} || Не удалось получить контакт {contact_id}")
        return None

    def _get_lead_from_duplicates(self, duplicates: Dict, func_name: str) -> Optional[Dict]:
        """Получение лида из дубликатов"""
        if not duplicates.get("LEAD"):
            return None

        lead_id = duplicates["LEAD"][0]
        logger.info(f"{func_name} || Найден лид: {lead_id}")

        lead_response = self._call_with_timeout("crm.lead.get", {"id": int(lead_id)})

        if lead_response and lead_response.get("result"):
            lead_info = lead_response["result"]
            lead_info["TYPE"] = "lead"
            logger.info(f"{func_name} || Данные лида получены")
            return lead_info

        logger.warning(f"{func_name} || Не удалось получить лид {lead_id}")
        return None

    @staticmethod
    def _format_result(data: Dict, return_found_status: bool) -> Union[Dict, Tuple[Dict, bool]]:
        """Форматирование результата"""
        return (data, True) if return_found_status else data

    @staticmethod
    def _empty_result(return_found_status: bool) -> Union[None, Tuple[None, bool]]:
        """Возврат пустого результата"""
        return (None, False) if return_found_status else None

    def create_new_lead(
        self, phone: str, user_id: str, chat_id: str, direction: str, name_called_function: str = "Add new lead in BX"
    ) -> Optional[Dict]:
        """Создание нового лида"""
        normalized_phone = self.normalize_phone(phone) or phone

        lead_data = {
            "fields": {
                "TITLE": f"MAX - {normalized_phone} [{direction}]",
                "PHONE": [{"VALUE": normalized_phone, "VALUE_TYPE": "WORK"}],
                "COMMENTS": "Лид пришел с MAX bot",
                "STATUS_ID": "NEW",
                "SOURCE_DESCRIPTION": "Лид из чат-бота MAX",
                "UF_CRM_1732021659": f"{direction}",
                "IM": [
                    {
                        "VALUE_TYPE": "IMOL",
                        "VALUE": f"imol|max|143|{chat_id}|{user_id}",
                        "TYPE_ID": "IM",
                    }
                ],
            }
        }

        result = self.bitrix_client.call_method("crm.lead.add", lead_data)

        logger.debug(
            f"{name_called_function} || Создан новый лид\n"
            f"Телефон: {normalized_phone}\n"
            f"Направление: {direction}\n"
            f"Результат: {result}"
        )

        if result and result.get("result"):
            lead_id = result["result"]
            lead_response = self.bitrix_client.call_method("crm.lead.get", {"id": lead_id})
            if lead_response and lead_response.get("result"):
                lead_response["result"]["IS_NEW"] = True
                return lead_response["result"]

        return None

    def get_lead(self, lead_bitrix_id: Union[int, str], name_called_function: Optional[str] = None) -> Dict:
        """Получение лида по ID"""
        func_name = name_called_function or "get_lead"

        try:
            if not lead_bitrix_id:
                logger.error(f"{func_name} || ID лида не указан")
                return {}

            lead_id = int(str(lead_bitrix_id).strip())
            logger.debug(f"{func_name} || Получение лида {lead_id}")

            response = self.bitrix_client.call_method("crm.lead.get", {"id": lead_id})

            if response and response.get("result"):
                logger.info(f"{func_name} || Лид {lead_id} получен")
                return response

            logger.warning(f"{func_name} || Лид {lead_id} не найден")
            return {}

        except Exception as e:
            logger.error(f"{func_name} || Ошибка: {e}", exc_info=True)
            return {}

    def get_contact(self, contact_id: Union[int, str], name_called_function: Optional[str] = None) -> Dict:
        """Получение контакта по ID"""
        func_name = name_called_function or "get_contact"

        try:
            if not contact_id:
                logger.error(f"{func_name} || ID контакта не указан")
                return {}

            contact_id = int(str(contact_id).strip())
            logger.debug(f"{func_name} || Получение контакта {contact_id}")

            response = self._call_with_timeout("crm.contact.get", {"id": contact_id})

            if response and response.get("result"):
                logger.info(f"{func_name} || Контакт {contact_id} получен")
                return response

            logger.warning(f"{func_name} || Контакт {contact_id} не найден")
            return {}

        except Exception as e:
            logger.error(f"{func_name} || Ошибка: {e}", exc_info=True)
            return {}

    def add_phone_to_user(
        self,
        phone: str,
        contact_bitrix_id: Optional[int] = None,
        lead_bitrix_id: Optional[int] = None,
        name_called_function: str = "Add phone in BX",
        type_find: str = "",
    ) -> Optional[Dict]:
        """Добавление или обновление телефона у пользователя"""

        phone_data = {"fields": {"PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}]}}

        if contact_bitrix_id is None and lead_bitrix_id is None:
            user_data = self.get_users_by_phone(phone)
            if user_data:
                if user_data.get("TYPE") == "contact":
                    contact_bitrix_id = user_data.get("ID")
                elif user_data.get("TYPE") == "lead":
                    lead_bitrix_id = user_data.get("ID")

        if contact_bitrix_id:
            contact_response = self._call_with_timeout("crm.contact.get", {"id": int(contact_bitrix_id)})

            if contact_response and contact_response.get("result"):
                update_result = self.bitrix_client.call_method(
                    "crm.contact.update", {"id": int(contact_bitrix_id), "fields": phone_data["fields"]}
                )

                logger.debug(
                    f"{name_called_function} || Обновлен контакт {contact_bitrix_id}\n"
                    f"Телефон: {phone}\n"
                    f"Результат: {update_result}"
                )

                if type_find and type_find.upper() == "LEAD":
                    return None

                contact_info = contact_response["result"]
                contact_info["TYPE"] = "contact"
                return contact_info

        if lead_bitrix_id:
            lead_response = self._call_with_timeout("crm.lead.get", {"id": int(lead_bitrix_id)})

            if lead_response and lead_response.get("result"):
                update_result = self.bitrix_client.call_method(
                    "crm.lead.update", {"id": int(lead_bitrix_id), "fields": phone_data["fields"]}
                )

                logger.debug(
                    f"{name_called_function} || Обновлен лид {lead_bitrix_id}\n"
                    f"Телефон: {phone}\n"
                    f"Результат: {update_result}"
                )

                lead_info = lead_response["result"]
                lead_info["TYPE"] = "lead"
                return lead_info

        return None

    def send_comment(self, user_bitrix_id: Union[int, str], user_bitrix_type: str, comment: str) -> Dict[str, Any]:
        """Отправка комментария пользователю"""
        logger.info(f"Отправка комментария для {user_bitrix_type} {user_bitrix_id}")

        if not all([user_bitrix_id, user_bitrix_type, comment]):
            return {"success": False, "error": "Все параметры обязательны: user_bitrix_id, user_bitrix_type, comment"}

        response = self._call_with_timeout(
            "crm.timeline.comment.add",
            {
                "fields": {
                    "ENTITY_ID": int(user_bitrix_id),
                    "ENTITY_TYPE": user_bitrix_type.upper(),
                    "COMMENT": comment,
                }
            },
        )

        if response is None:
            return {"success": False, "error": "Таймаут при отправке комментария"}

        logger.debug(f"Ответ от Bitrix: {response}")

        if response and response.get("result"):
            return dict(
                success=True,
                comment_id=response.get("result"),
                message="Комментарий успешно отправлен",
            )
        else:
            return dict(
                success=False,
                error=response.get("error_description", "Неизвестная ошибка API"),
                response=response,
            )

    def get_users_by_phones_batch(
        self, phones: List[str], type_find: str = "", max_workers: int = 5
    ) -> Dict[str, Optional[Dict]]:
        """Массовый поиск пользователей по списку телефонов"""
        results = {}

        def search_single(phone: str) -> Tuple[str, Optional[Dict]]:
            try:
                user_data = self.get_users_by_phone(phone, type_find, return_found_status=False)
                return phone, user_data
            except Exception as e:
                logger.error(f"Ошибка поиска для {phone}: {e}")
                return phone, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_phone = {executor.submit(search_single, phone): phone for phone in phones}

            for future in as_completed(future_to_phone):
                phone = future_to_phone[future]
                try:
                    _, result = future.result()
                    results[phone] = result
                except Exception as e:
                    logger.error(f"Ошибка обработки {phone}: {e}")
                    results[phone] = None

        return results


bitrix_user_service = BitrixUserService(bitrix_bot)

# ========== ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ==========


def get_users_by_phone_in_bitrix(phone, name_called_function=None, type_find="", return_found_status=False):
    """Обертка для обратной совместимости"""
    return bitrix_user_service.get_users_by_phone(
        phone=phone,
        type_find=type_find,
        return_found_status=return_found_status,
        name_called_function=name_called_function,
    )


def create_new_lead(phone, user_id, chat_id, direction, name_called_function="Add new lead in BX"):
    """Обертка для обратной совместимости"""
    return bitrix_user_service.create_new_lead(
        phone=phone, user_id=user_id, chat_id=chat_id, direction=direction, name_called_function=name_called_function
    )


def add_by_phone_in_bitrix(
    phone, contact_bitrix_id=None, lead_bitrix_id=None, name_called_function="Add phone in BX", type_find=""
):
    """Обертка для обратной совместимости"""
    return bitrix_user_service.add_phone_to_user(
        phone=phone,
        contact_bitrix_id=contact_bitrix_id,
        lead_bitrix_id=lead_bitrix_id,
        name_called_function=name_called_function,
        type_find=type_find,
    )


def get_lead(lead_bitrix_id: Union[int, str], name_called_function: Optional[str] = None) -> dict:
    """Обертка для обратной совместимости"""
    return bitrix_user_service.get_lead(lead_bitrix_id, name_called_function)


def get_contact(contact_id: Union[int, str], name_called_function: Optional[str] = None) -> dict:
    """Обертка для обратной совместимости"""
    return bitrix_user_service.get_contact(contact_id, name_called_function)


def send_comment_to_user_simple(user_bitrix_id: Union[int, str], user_bitrix_type: str, comment: str) -> dict:
    """Обертка для обратной совместимости"""
    return bitrix_user_service.send_comment(user_bitrix_id, user_bitrix_type, comment)


def get_link_for_bitrix(id_client, name, type_link):
    if type_link == "lms":
        return f"[URL=https://my.hwschool.online/clients/{id_client}/]{name}[/URL]"
    elif type_link == "lead":
        return f"[URL=https://hwschool.bitrix24.ru/crm/lead/details/{id_client}/]{name}[/URL]"
    elif type_link == "contact":
        return f"[URL=https://hwschool.bitrix24.ru/crm/contact/details/{id_client}/]{name}[/URL]"
    elif type_link == "user":
        return f"[USER={id_client}]{name}[/USER]"
    elif type_link == "lms_teacher":
        return f"[URL=https://my.hwschool.online/teachers/profile/{id_client}/]{name}[/URL]"
    else:
        return None

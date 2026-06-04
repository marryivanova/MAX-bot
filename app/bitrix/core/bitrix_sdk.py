from collections import OrderedDict
from datetime import datetime, timedelta
from time import sleep
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from loguru import logger

from db.crud_db.add_table_max_lead_or_contact import update_max_user_from_bitrix
from settings import settings


class SimpleCache:

    def __init__(self, max_size: int = 100, ttl: int = 300):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        value, timestamp = self.cache[key]
        if datetime.now() - timestamp > timedelta(seconds=self.ttl):
            del self.cache[key]
            return None
        self.cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any):
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[key] = (value, datetime.now())

    def invalidate(self, key: str):
        if key in self.cache:
            del self.cache[key]


class BitrixSDK:
    """Bitrix bot SDK для работы с Bitrix24 REST API"""

    def __init__(self, bitrix_user_id: str, bitrix_token: str, bx_domain: str = "") -> None:
        self.bx_domain = bx_domain or settings.bitrix_bots.bx_domain
        if self.bx_domain:
            if "/rest/" in self.bx_domain:
                self.bx_domain = self.bx_domain.split("/rest/")[0]
            if not self.bx_domain.startswith(("http://", "https://")):
                self.bx_domain = f"https://{self.bx_domain}"
            self.bx_domain = self.bx_domain.rstrip("/")
        self.bx_domain = bx_domain or settings.bitrix_bots.bx_domain
        self.token = bitrix_token
        self.user_id = bitrix_user_id
        self.webhook_url = f"{self.bx_domain}/rest/{self.token}"
        self.cache = SimpleCache(max_size=100, ttl=300)

        logger.info(f"BitrixSDK инициализирован: domain={self.bx_domain}, user_id={self.user_id}")
        logger.debug(f"Webhook URL: {self.webhook_url[:50]}...")

    def call_method(self, method: str, params: Dict = None, timeout: int = 30) -> Dict:
        """
        Universal method for calling Bitrix API
        """
        if params is None:
            params = {}

        domain = self.bx_domain
        if domain and not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"

        url = f"{domain}/rest/{self.token}/{method}"

        logger.debug(f"Вызов {method} с параметрами: {params}")

        try:
            response = requests.post(url, json=params, timeout=timeout)
            response.raise_for_status()
            result = response.json()

            if result.get("error"):
                logger.error(f"Ошибка API {method}: {result.get('error_description', result.get('error'))}")

            sleep(0.5)
            return result

        except requests.exceptions.Timeout:
            logger.error(f"Таймаут {timeout}с при вызове {method}")
            return dict(error="timeout", error_description=f"Превышен таймаут {timeout} секунд")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к {method}: {e}")
            return dict(error="request_error", error_description=str(e))
        except Exception as e:
            logger.error(f"Неизвестная ошибка при вызове {method}: {e}", exc_info=True)
            return dict(error="unknown_error", error_description=str(e))

    def find_duplicates_by_phone(self, phone: str) -> Dict[str, List]:
        """Find duplicates by phone number"""
        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            logger.warning(f"Некорректный номер: {phone}")
            return dict(LEAD=[], CONTACT=[])

        result = dict(LEAD=[], CONTACT=[])

        lead_response = self.call_method(
            "crm.duplicate.findbycomm",
            dict(entity_type="LEAD", type="PHONE", values=[normalized_phone]),
            timeout=25,
        )
        if lead_response.get("result"):
            result["LEAD"] = [lead_response["result"]]

        contact_response = self.call_method(
            "crm.duplicate.findbycomm",
            dict(entity_type="CONTACT", type="PHONE", values=[normalized_phone]),
            timeout=25,
        )
        if contact_response.get("result"):
            result["CONTACT"] = [contact_response["result"]]

        return result

    def get_lead(self, lead_id: Union[int, str], use_cache: bool = True) -> Dict:
        """Get lead by ID with caching"""
        if not lead_id:
            logger.error("ID не указан")
            return {}

        if use_cache:
            cache_key = f"lead_{lead_id}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Возвращаем лид {lead_id} из кэша")
                return cached

        response = self.call_method("crm.lead.get", {"id": int(lead_id)}, timeout=30)

        if response and response.get("result"):
            response["result"]["TYPE"] = "lead"
            if use_cache:
                self.cache.set(cache_key, response)
            logger.info(f"Лид {lead_id} получен")
            return response
        else:
            logger.warning(f"Лид {lead_id} не найден: {response.get('error_description', '')}")
            return {}

    def get_contact(self, contact_id: Union[int, str], use_cache: bool = True) -> Dict:
        """Get contact by ID with caching"""
        if not contact_id:
            logger.error("ID не указан")
            return {}

        if use_cache:
            cache_key = f"contact_{contact_id}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Возвращаем контакт {contact_id} из кэша")
                return cached

        response = self.call_method("crm.contact.get", {"id": int(contact_id)}, timeout=30)

        if response and response.get("result"):
            response["result"]["TYPE"] = "contact"
            if use_cache:
                self.cache.set(cache_key, response)
            logger.info(f"Контакт {contact_id} получен")
            return response
        else:
            logger.warning(f"Контакт {contact_id} не найден")
            return {}

    def get_deal(self, deal_id: Union[int, str], use_cache: bool = True) -> Dict:
        """Get deal by ID with caching"""
        if not deal_id:
            logger.error("ID не указан")
            return {}

        if use_cache:
            cache_key = f"deal_{deal_id}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Возвращаем сделку {deal_id} из кэша")
                return cached

        response = self.call_method("crm.deal.get", {"id": int(deal_id)}, timeout=30)

        if response and response.get("result"):
            if use_cache:
                self.cache.set(cache_key, response)
            logger.info(f"Сделка {deal_id} получена")
            return response
        else:
            logger.warning(f"Сделка {deal_id} не найдена")
            return {}

    def create_lead(self, lead_data: Dict) -> Optional[int]:
        """Create new lead"""
        response = self.call_method("crm.lead.add", lead_data, timeout=30)
        if response and response.get("result"):
            lead_id = response["result"]
            self.cache.invalidate(f"lead_{lead_id}")
            return lead_id
        return None

    def update_lead(self, lead_id: Union[int, str], data: Dict) -> bool:
        """Update lead"""
        response = self.call_method("crm.lead.update", {"id": int(lead_id), "fields": data}, timeout=30)
        if response and response.get("result"):
            self.cache.invalidate(f"lead_{lead_id}")
            return True
        return False

    def update_contact(self, contact_id: Union[int, str], data: Dict) -> bool:
        """Update contact"""
        response = self.call_method("crm.contact.update", {"id": int(contact_id), "fields": data}, timeout=30)
        if response and response.get("result"):
            self.cache.invalidate(f"contact_{contact_id}")
            return True
        return False

    def add_comment(self, entity_id: Union[int, str], entity_type: str, comment: str) -> bool:
        """Add comment to lead/contact/deal"""
        response = self.call_method(
            "crm.timeline.comment.add",
            {"fields": {"ENTITY_ID": int(entity_id), "ENTITY_TYPE": entity_type.upper(), "COMMENT": comment}},
            timeout=25,
        )
        return response.get("result", False) if response else False

    def get_users_by_phone(
        self, phone: str, type_find: str = "", return_found_status: bool = False
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], bool]]:
        """Get user (lead or contact) by phone number"""
        func_name = "get_users_by_phone_in_bitrix"
        logger.debug(f"{func_name} || Поиск по телефону: {phone}")

        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            logger.warning(f"{func_name} || Некорректный номер: {phone}")
            return (None, False) if return_found_status else None

        logger.info(f"{func_name} || Поиск по номеру: {normalized_phone}")

        duplicates = self.find_duplicates_by_phone(phone)
        logger.info(f"{func_name} || Результат: {duplicates}")

        try:
            update_max_user_from_bitrix(phone=normalized_phone, bitrix_data=duplicates)
        except Exception as e:
            logger.error(f"{func_name} || Ошибка обновления MAX: {e}")

        if duplicates.get("CONTACT"):
            contact_id = duplicates["CONTACT"][0]
            logger.info(f"{func_name} || Найден контакт: {contact_id}")

            if type_find and type_find.upper() == "LEAD":
                return (None, False) if return_found_status else None

            contact_data = self.get_contact(contact_id)
            if contact_data and contact_data.get("result"):
                contact_info = contact_data["result"]
                if return_found_status:
                    return (contact_info, True)
                return contact_info

        if duplicates.get("LEAD"):
            lead_id = duplicates["LEAD"][0]
            logger.info(f"{func_name} || Найден лид: {lead_id}")

            lead_data = self.get_lead(lead_id)
            if lead_data and lead_data.get("result"):
                lead_info = lead_data["result"]
                if return_found_status:
                    return (lead_info, True)
                return lead_info

        logger.warning(f"{func_name} || Пользователь не найден")
        return (None, False) if return_found_status else None

    def create_new_lead(self, phone: str, user_id: str, chat_id: str, direction: str) -> Optional[Dict]:
        """Create new lead from chat bot"""
        func_name = "Add new lead in BX"
        normalized_phone = self._normalize_phone(phone)

        lead_data = dict(
            fields={
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
        )

        lead_id = self.create_lead(lead_data)
        if lead_id:
            logger.info(f"{func_name} || Создан лид: {lead_id}")
            lead_data = self.get_lead(lead_id, use_cache=False)
            if lead_data and lead_data.get("result"):
                lead_data["result"]["IS_NEW"] = True
                return lead_data["result"]

        return None

    def send_comment(self, user_bitrix_id: Union[int, str], user_bitrix_type: str, comment: str) -> Dict[str, Any]:
        """Send comment to user"""
        logger.info(f"Отправка комментария для {user_bitrix_type} {user_bitrix_id}")
        try:
            success = self.add_comment(user_bitrix_id, user_bitrix_type, comment)
            if success:
                return dict(success=True, result=success, message="Комментарий отправлен")
            else:
                return dict(success=False, error="Неизвестная ошибка", response=None)
        except Exception as e:
            logger.error(f"Ошибка отправки комментария: {e}")
            return dict(success=False, error=str(e))

    def get_many_items(
        self, method: str, params: Dict[str, Any], name_id: str = "ID", add_dict_value: str = ""
    ) -> List[Dict[str, Any]]:
        """Get many items from Bitrix with pagination."""
        retrieved_data = []
        params["start"] = -1

        if method != "voximplant.statistic.get":
            params["order"] = {name_id: "ASC"}

        if "filter" not in params:
            params["filter"] = {}

        while True:
            response = self.call_method(method=method, params=params, timeout=30)

            if add_dict_value:
                response_data = response.get("result", {}).get(add_dict_value, [])
            else:
                response_data = response.get("result", [])

            if not response_data:
                break

            last_id = response_data[-1][name_id]
            params["filter"][f">{name_id}"] = last_id

            retrieved_data.extend(response_data)
            sleep(0.5)

        return retrieved_data

    def get_many_tasks(self, params_for_get_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get many tasks from Bitrix"""
        retrieved_data = []
        params_for_get_data["start"] = -1
        params_for_get_data["order"] = {"ID": "ASC"}

        if "filter" not in params_for_get_data:
            params_for_get_data["filter"] = {}

        while True:
            response = self.call_method(method="tasks.task.list", params=params_for_get_data, timeout=30)

            response_data = response.get("result", {}).get("tasks", [])

            if not response_data:
                break

            last_id = response_data[-1]["id"]
            params_for_get_data["filter"][f">ID"] = last_id

            retrieved_data.extend(response_data)
            sleep(0.5)

        return retrieved_data

    def create_list_element(self, params_for_create: dict) -> Optional[Dict]:
        """Create element of list (lists.element.add)"""
        response = self.call_method(method="lists.element.add", params=params_for_create, timeout=30)
        logger.debug(f"create element {response}")
        return response.get("result")

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number"""
        if not phone:
            return ""

        digits = "".join(filter(str.isdigit, phone))

        if digits.startswith("8") and len(digits) == 11:
            return "+7" + digits[1:]
        if digits.startswith("9") and len(digits) == 10:
            return "+7" + digits
        if digits.startswith("7") and len(digits) == 11:
            return "+" + digits

        return phone


class BxBots:

    max: BitrixSDK = None


try:
    BxBots.max = BitrixSDK(
        bitrix_user_id=settings.bitrix_bots.max_id,
        bitrix_token=settings.bitrix_bots.max_token,
        bx_domain=settings.bitrix_bots.bx_domain,
    )
    logger.info("BxBots.max успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации BxBots.max: {e}", exc_info=True)
    raise


# ========== СИНХРОННЫЕ ФУНКЦИИ ДЛЯ ПРЯМОГО ВЫЗОВА ==========


def get_lead_sync(lead_bitrix_id: Union[int, str], name_called_function: Optional[str] = None) -> dict:
    """Синхронная функция для получения лида"""
    func_name = name_called_function or "get_lead_sync"

    if not BxBots.max:
        logger.error(f"{func_name} || BxBots.max не инициализирован")
        return {}

    try:
        lead_id_int = int(lead_bitrix_id)
        logger.debug(f"{func_name} || Вызываем get_lead для ID: {lead_id_int}")

        result = BxBots.max.get_lead(lead_id_int)

        if result and result.get("result"):
            logger.info(f"{func_name} || Лид {lead_id_int} успешно получен")
            return result
        else:
            logger.warning(f"{func_name} || Лид {lead_id_int} не найден")
            return {}

    except Exception as e:
        logger.error(f"{func_name} || Ошибка: {e}", exc_info=True)
        return {}


def get_contact_sync(contact_id: Union[int, str], name_called_function: Optional[str] = None) -> dict:
    """Синхронная функция для получения контакта"""
    func_name = name_called_function or "get_contact_sync"

    if not BxBots.max:
        logger.error(f"{func_name} || BxBots.max не инициализирован")
        return {}

    try:
        contact_id_int = int(contact_id)
        logger.debug(f"{func_name} || Вызываем get_contact для ID: {contact_id_int}")

        result = BxBots.max.get_contact(contact_id_int)

        if result and result.get("result"):
            logger.info(f"{func_name} || Контакт {contact_id_int} успешно получен")
            return result
        else:
            logger.warning(f"{func_name} || Контакт {contact_id_int} не найден")
            return {}

    except Exception as e:
        logger.error(f"{func_name} || Ошибка: {e}", exc_info=True)
        return {}

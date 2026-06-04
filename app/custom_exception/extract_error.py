import json
import re
from typing import Any, Optional, Tuple

from fastapi import status


class MaxBotError(Exception):
    """Базовое исключение для ошибок MaxBot"""

    pass


class MaxBotHTTPError(MaxBotError):
    """Исключение для  MaxBot с сохранением оригинального статуса и тела ответа"""

    def __init__(self, message: str, status_code: int, response_body: Any):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)

    def __str__(self):
        return f"MaxBotHTTPError: {self.message} (status={self.status_code}, body={self.response_body})"


def handle_max_api_error(e: Exception, error_str: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Обрабатывает ошибки от MAX API и возвращает HTTP статус и детали ошибки.
    Возвращает (None, None) если ошибка не распознана как специфичная.
    """
    if "chat.denied" in error_str and "error.dialog.suspended" in error_str:
        suspended_chat_id = None

        chat_id_match = re.search(r"args: \[(\d+),?", error_str)
        if chat_id_match:
            suspended_chat_id = chat_id_match.group(1)

        if not suspended_chat_id:
            try:
                json_match = re.search(r"({.*})", error_str)
                if json_match:
                    error_data = json.loads(json_match.group(1))
                    if "args" in error_data and error_data["args"]:
                        suspended_chat_id = str(error_data["args"][0])
            except:
                pass

        error_message = f"Чат {suspended_chat_id or 'неизвестный'} заблокирован или приостановлен пользователем"
        return (status.HTTP_410_GONE, error_message)

    if hasattr(e, "status_code") and e.status_code == 403:
        return (status.HTTP_403_FORBIDDEN, f"Ошибка доступа к MAX API: {error_str}")

    return (None, None)

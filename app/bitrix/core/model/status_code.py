from enum import Enum


class MaxHttpStatus(Enum):
    HTTP_200_OK = (200, "success", "Успешная операция")

    HTTP_400_BAD_REQUEST = (400, "bad_request", "Недействительный запрос")
    HTTP_401_UNAUTHORIZED = (401, "unauthorized", "Ошибка аутентификации")
    HTTP_404_NOT_FOUND = (404, "not_found", "Ресурс не найден")
    HTTP_405_METHOD_NOT_ALLOWED = (405, "method_not_allowed", "Метод не допускается")
    HTTP_429_TOO_MANY_REQUESTS = (429, "rate_limit_exceeded", "Превышено количество запросов")
    HTTP_503_SERVICE_UNAVAILABLE = (503, "service_unavailable", "Сервис недоступен")

    def __init__(self, code: int, status: str, description: str):
        self.code = code
        self.status = status
        self.description = description

    @property
    def is_success(self) -> bool:
        """Проверка, является ли статус успешным."""
        return self.code == 200

    @property
    def is_client_error(self) -> bool:
        """Проверка, является ли ошибка клиентской (4xx)."""
        return 400 <= self.code < 500

    @property
    def is_server_error(self) -> bool:
        """Проверка, является ли ошибка серверной (5xx)."""
        return 500 <= self.code < 600

    @property
    def is_retryable(self) -> bool:
        """Проверка, можно ли повторить запрос."""
        retryable_codes = [429, 503]
        return self.code in retryable_codes

    @property
    def is_permanent_failure(self) -> bool:
        """Проверка, является ли ошибка постоянной."""
        permanent_codes = [400, 401, 404, 405]
        return self.code in permanent_codes

    def get_user_message(self, language: str = "ru") -> str:
        messages = {
            "ru": {
                200: "Отправлено",
                400: "Недействительный запрос",
                401: "Ошибка аутентификации",
                404: "Ресурс не найден",
                405: "Метод не допускается",
                429: "Превышено количество запросов",
                503: "Сервис недоступен",
            },
            "en": {
                200: "Sent",
                400: "Bad request",
                401: "Authentication error",
                404: "Resource not found",
                405: "Method not allowed",
                429: "Rate limit exceeded",
                503: "Service unavailable",
            },
        }
        return messages.get(language, messages["ru"]).get(self.code, str(self))

    @classmethod
    def from_http_code(cls, http_code: int) -> "MaxHttpStatus":
        mapping = {
            200: cls.HTTP_200_OK,
            400: cls.HTTP_400_BAD_REQUEST,
            401: cls.HTTP_401_UNAUTHORIZED,
            404: cls.HTTP_404_NOT_FOUND,
            405: cls.HTTP_405_METHOD_NOT_ALLOWED,
            429: cls.HTTP_429_TOO_MANY_REQUESTS,
            503: cls.HTTP_503_SERVICE_UNAVAILABLE,
        }
        return mapping.get(http_code, cls.HTTP_400_BAD_REQUEST)

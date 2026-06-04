from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class DefaultDataForMessages(str, Enum):
    MAILING_NAME = "Автосообщение: Отпуск преподавателя"
    MESSENGER = "MAX"
    MAX_AUTO = "MAX sender auto"

    def __str__(self) -> str:
        return self.value


class MessageChat(Enum):
    holiday_mailing = "[B]Для его клиентов выполнена отпускная рассылка:[/B]"
    dont_get_holiday_mailing = "Не смог отправить сообщения этим клиентам: "
    have_trial_lessons = "Не отправлены, потому что есть вводные уроки: "
    have_group_lessons = "Не отправлены, потому что есть групповые уроки: "
    no_bitrix_links = "Не отправлены, потому что у клиента не указаны ссылки на битрикс: "
    bitrix_links_note = "Необходимо добавить ссылки на битрикс в профиле клиента"
    not_cancelled_days = "[B]В эти дни уроки не был отменены:[/B]"
    manual_cancellation_note = "Необходимо отменить уроки вручную и поставить модесту на эти дни"


class LogsMessages(str, Enum):

    not_set = "Not sent"
    event_message = "Это событие на отмену уроков и отправку сообщения"
    count_client = "Получили клиентов"
    attempt_send_message = "Пытаемся отправить сообщени"
    received_regular_lessons = "Получили регулярные уроки"
    requests_regular_lessons = "Запрос для получения регулярных уроков"

    make_text_for_message = "Готовим текста для отправки сообщения"

    message_send = "Отправляем сообщение"
    message_request = "Отправка запроса на URL"
    message_data = "Данные для отправки"
    message_success = "Сообщение успешно отправлено"

    message_error = "Ошибка при отправке"
    message_error_network = "Ошибка сети при отправке сообщения"
    message_error_same = "Неожиданная ошибка при отправке сообщения"

    message_status = "Не доставлено"
    message_success_delivery = "Сообщение успешно отправлено для клиента"
    message_error_delivery = "Не удалось отправить сообщение для клиента"

    message_client_not_found = "Не нашли клиента в битриксе"
    message_client_not_found_platform = "Не нашли клиента на платформе"
    message_lesson_first = "У клиента вводный урок не отправляем значит"

    holiday_mailing = "[B]Для его клиентов выполнена отпускная рассылка:[/B]"
    get_holiday_mailing = "Рассылка выполнена для клиентов:"
    dont_get_holiday_mailing = "Не смог отправить сообщения этим клиентам: "

    def __str__(self) -> str:
        return self.value

    @staticmethod
    def check_success_status(response_data: Any) -> bool:
        if not isinstance(response_data, dict):
            return False

        status = response_data.get("status")
        if status is None:
            return False

        success_statuses = ["Success", "Ok", "ok", "OK", "success"]
        return str(status).lower() in [s.lower() for s in success_statuses]


class LmsCustomerForSend(BaseModel):
    """LMS customer with lesson."""

    lms_customer_id: int
    is_trial: bool = False
    is_group: bool = False
    is_send: bool = False
    is_english: bool = False
    is_not_bitrix_field: bool = False
    count_days_vacation: int = 0
    timezone: str = "Europe/Moscow"

    @property
    def type_vacation(self) -> str:
        """Get type vacation."""

        if self.count_days_vacation > 4:
            if self.is_english:
                return "long_en"
            return "long_ru"

        if self.is_english:
            return "short_en"
        return "short_ru"

    @property
    def link_to_lms_customer(self) -> str:
        return f"[URL={self.lms_customer_id}/]{self.lms_customer_id}[/URL]"


class DeliveryStatus(Enum):
    not_sent = "Not sent"
    sent = "sent"
    failed = "failed"


class TeacherVacation(BaseModel):
    """Teacher vacation DTO."""

    bitrix_teacher_id: int
    lms_teacher_id: int
    teacher_name: str
    date_start_str: str
    date_end_str: str
    vacation_id: Optional[str | int]

    @property
    def teacher_id(self) -> int:
        return self.bitrix_teacher_id

    @property
    def date_start(self) -> date:
        return datetime.strptime(self.date_start_str, "%d.%m.%Y").date()

    @property
    def date_end(self) -> date:
        return datetime.strptime(self.date_end_str, "%d.%m.%Y").date()

    @property
    def day_weeks_str_for_lms(self) -> str:
        day_weeks = []
        current_date = self.date_start
        while current_date <= self.date_end:
            weekday = current_date.weekday() + 2
            if weekday == 8:
                weekday = 1
            weekday = str(weekday)
            if weekday not in day_weeks:
                day_weeks.append(weekday)
            current_date += timedelta(days=1)
            if len(day_weeks) == 7:
                break
        return ", ".join(day_weeks)

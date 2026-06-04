from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
from babel.dates import format_date
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import and_

from app.bitrix.core.bitrix_send_alert import send_message_to_bx_chat
from app.bitrix.core.model import ListAlertID
from app.services.vacation_teacher.helper import convert_timezone_datetime
from app.services.vacation_teacher.model import (
    DeliveryStatus,
    LmsCustomerForSend,
    LogsMessages,
    MessageChat,
    TeacherVacation,
)
from db.core import session_scope
from db.models.teachers_vacation import TeachersVacationModel

# Todo: тут доработать методы и обращение в БД

def RegularRule():
    pass

class CustomerById:
    pass

class DayOff:
    pass

class Customer:
    pass

class NewSendMessage(BaseModel):
    sid_id: str
    max_id: Optional[str | int] = None
    lead_id: Optional[str | int] = None
    contact_id: Optional[str | int] = None
    twilio_variables: Optional[str | int] = None


class MessageAPIService:
    """Service for sending messages via MaxBot API"""

    BASE_URL = ""

    def __init__(self, logger_name: str):
        self.logger_name = logger_name

    async def send_message_and_get_status(self, message_data: NewSendMessage) -> Optional[str]:
        params = dict(
            sid_id=message_data.sid_id,
            lead_id=message_data.lead_id,
            contact_id=message_data.contact_id,
            chat_id=message_data.max_id,
        )

        if message_data.twilio_variables:
            params["twilio_variables"] = message_data.twilio_variables

        logger.debug(f"{self.logger_name} || Отправка запроса в MaxBot: {params}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.BASE_URL, params=params)

                if response.status_code == 200:
                    logger.debug(f"{self.logger_name} || {LogsMessages.message_success}")
                    return DeliveryStatus.sent.value
                else:
                    logger.error(
                        f"{self.logger_name} || {LogsMessages.message_error}: "
                        f"{response.status_code} - {response.text}"
                    )
                    return DeliveryStatus.failed.value
        except Exception as e:
            logger.error(f"{self.logger_name} || Ошибка при отправке сообщения: {e}")
            return DeliveryStatus.failed.value


class SendMessageAndCancelLessonsAfterVacationService:
    """Send message and cancel lessons after teacher's vacation."""

    _teacher: TeacherVacation
    _logger_name: str
    _lms_customers: Dict[int, LmsCustomerForSend]
    _chat_id: str
    _get_lms_customer: CustomerById
    _set_day_off_for_teacher: DayOff
    _block_mailing: Customer

    def __init__(self, logger_name: str, teacher: TeacherVacation) -> None:
        """Init."""
        self._teacher = teacher
        self._logger_name = logger_name
        self._chat_id = ListAlertID.vacation_chat.value
        self._get_lms_customer = CustomerById()
        self._set_day_off_for_teacher = DayOff(logger_name=logger_name)
        self._message_service = MessageAPIService(logger_name=logger_name)
        self._block_mailing_lists = Customer()

    async def work(self):
        logger.debug(f"{self._logger_name} || {LogsMessages.event_message}\n")

        self._lms_customers = {}
        self._get_lms_customers()
        await self._send_message_for_clients()
        self._delete_teacher_vacation_from_database()
        self._create_message_for_send_to_bitrix()

    def _get_lms_customers(self):
        """Get LMS customers using ORM instead of raw SQL"""
        logger.debug("Start lms")

        lessons = by_period(
            date_start=self._teacher.date_end,
            date_end=self._teacher.date_start,
            teacher_id=self._teacher.lms_teacher_id,
        )
        logger.debug(f"Lessons from period: {lessons}")

        regular_lessons = self._get_regular_lessons_orm()
        lessons.extend(regular_lessons)
        logger.debug(f"{self._logger_name} || Получено регулярных уроков: {len(regular_lessons)}")

        for lesson in lessons:
            lms_customer_id = lesson.get("pupil")
            if not lms_customer_id:
                continue

            timezone = lesson.get("timezone", "Europe/Moscow")

            is_trial = lesson.get("type") == "trial"
            is_group = "GR" in lesson.get("course_title", "")
            is_english = "EN " in lesson.get("course_title", "") or "DEU " in lesson.get("course_title", "")

            if lms_customer_id not in self._lms_customers:
                self._lms_customers[lms_customer_id] = LmsCustomerForSend(
                    lms_customer_id=lms_customer_id,
                    is_trial=is_trial,
                    is_group=is_group,
                    is_english=is_english,
                    timezone=timezone,
                )

            lms_customer = self._lms_customers[lms_customer_id]

            if is_trial and not lms_customer.is_trial:
                lms_customer.is_trial = is_trial

            if is_english and not lms_customer.is_english:
                lms_customer.is_english = is_english

            if is_group and not lms_customer.is_group:
                lms_customer.is_group = is_group

        logger.debug(
            f"{self._logger_name} || {LogsMessages.count_client}\n" f"lms customers = {len(self._lms_customers)}\n"
        )

    def _get_regular_lessons_orm(self) -> List[Dict]:
        """Get regular lessons using ORM instead of raw SQL"""
        from sqlalchemy import select

        with session_scope() as session:
            query = (
                select(RegularRule.pupil, RegularRule.course.label("course_title"), RegularRule.weekday)
                .where(
                    and_(
                        RegularRule.teacher == self._teacher.lms_teacher_id,
                        RegularRule.weekday.in_(self._teacher.day_weeks_str_for_lms.split(",")),
                        RegularRule.is_modesta == False,
                    )
                )
                .group_by(RegularRule.pupil)
            )

            results = session.execute(query).all()

            return [
                {"pupil": result.pupil, "type": "regular", "course_title": result.course_title} for result in results
            ]

    def _check_mailing_block_and_notify(self, lms_customer_id: int, teacher_name: str) -> bool:
        """
        Проверяет, заблокирована ли рассылка для клиента.
        Если заблокирована - отправляет предупреждение в чат.
        """
        customer_info = self._block_mailing_lists.get_customer_info_about_mailing_lists(lms_customer_id)

        if not customer_info:
            logger.warning(
                f"{self._logger_name} || Не удалось получить информацию о рассылках для клиента {lms_customer_id}"
            )
            return False

        is_mailing_blocked = customer_info.get("is_mailing_blocked", False)

        if is_mailing_blocked:
            warning_message = (
                f"⚠️ ВНИМАНИЕ: Клиент {lms_customer_id}/ не получит уведомление ⚠️\n\n"
                f"Об отпуске {teacher_name}!\n"
                f"Причина: у клиента заблокирована отправка рассылок\n"
            )

            result = send_message_to_bx_chat(warning_message)
            logger.debug(f"{self._logger_name} || Результат отправки предупреждения в чат: {result}")

            logger.warning(
                f"{self._logger_name} || Mailing blocked for client {lms_customer_id}. "
                f"Notification about teacher {teacher_name} vacation won't be sent."
            )

            return True

        return False

    async def _send_message_for_clients(self):
        for lms_customer in self._lms_customers.values():
            logger.debug(f"{self._logger_name} || {LogsMessages.attempt_send_message}\nlms_customer = {lms_customer}\n")

            if lms_customer.is_trial:
                logger.debug(f"{self._logger_name} || {LogsMessages.message_lesson_first}\n")
                continue

            if lms_customer.is_send:
                logger.debug(
                    f"{self._logger_name} || Сообщение для клиента {lms_customer.lms_customer_id} "
                    f"уже было отправлено. Пропускаем."
                )
                continue

            logger.debug(
                f"{self._logger_name} || Проверка блокировки рассылки для клиента {lms_customer.lms_customer_id}"
            )

            is_blocked = self._check_mailing_block_and_notify(
                lms_customer_id=lms_customer.lms_customer_id, teacher_name=self._teacher.teacher_name
            )

            logger.debug(
                f"{self._logger_name} || Результат проверки блокировки для клиента {lms_customer.lms_customer_id}: {is_blocked}"
            )

            if is_blocked:
                logger.debug(
                    f"{self._logger_name} || Рассылка заблокирована для клиента {lms_customer.lms_customer_id}. "
                    f"Сообщение не отправлено."
                )
                lms_customer.is_send = False
                continue

            lms_customer.count_days_vacation = (self._teacher.date_end - self._teacher.date_start).days + 1

            lms_customer_from_api = self._get_lms_customer.get_customer(lms_customer_id=lms_customer.lms_customer_id)

            if not lms_customer_from_api:
                logger.warning(f"{self._logger_name} || {LogsMessages.message_client_not_found_platform}")
                warning_message = (
                    f"⚠️ ВНИМАНИЕ: Клиент {lms_customer.lms_customer_id}/ "
                    f"не получит уведомление ⚠️\n\n"
                    f"Об отпуске преподавателя {self._teacher.teacher_name}!\n"
                    f"Причина: клиент не найден\n"
                )
                send_message_to_bx_chat(warning_message)

            lead_id = None
            contact_id = None

            bitrix_client_id = lms_customer_from_api.bitrix_lead_id

            if lms_customer_from_api.bitrix_contact_id:
                bitrix_client_id = lms_customer_from_api.bitrix_contact_id
                contact_id = bitrix_client_id
            else:
                lead_id = bitrix_client_id

            if lms_customer_from_api.max_id:
                chat_id = lms_customer_from_api.max_id
                lead_id = None
                contact_id = None
            else:
                chat_id = None

            if not bitrix_client_id:
                logger.debug(f"{self._logger_name} || {LogsMessages.message_client_not_found}")
                lms_customer.is_not_bitrix_field = True
                warning_message = (
                    f"⚠️ ВНИМАНИЕ: {lms_customer.lms_customer_id}/ "
                    f"не получит уведомление ⚠️\n\n"
                    f"Об отпуске {self._teacher.teacher_name}!\n"
                    f"Причина: отсутствует Bitrix ID\n"
                )
                send_message_to_bx_chat(warning_message)
                continue

            message_data = NewSendMessage(
                sid_id="",
                lead_id=lead_id,
                contact_id=contact_id,
                chat_id=chat_id,
                twilio_variables=";;".join(
                    [self._teacher.teacher_name, self._teacher.date_start_str, self._teacher.date_end_str]
                ),
            )

            message_status = await self._message_service.send_message_and_get_status(
                message_data=message_data,
            )

            if message_status and message_status == DeliveryStatus.sent.value:
                lms_customer.is_send = True
                logger.debug(
                    f"{self._logger_name} || {LogsMessages.message_success_delivery} {lms_customer.lms_customer_id}"
                )
            else:
                lms_customer.is_send = False
                warning_message = (
                    f"⚠️ ОШИБКА ДОСТАВКИ: Клиент {lms_customer.lms_customer_id}/ "
                    f"не получил уведомление ⚠️\n\n"
                    f"Об отпуске {self._teacher.teacher_name}!\n"
                    f"Причина: ошибка отправки сообщения (статус: {message_status})\n"
                )
                send_message_to_bx_chat(warning_message)
                logger.warning(
                    f"{self._logger_name} || {LogsMessages.message_error_delivery} {lms_customer.lms_customer_id}"
                )

    def _delete_teacher_vacation_from_database(self):
        with session_scope() as session:
            if self._teacher.vacation_id:
                session.query(TeachersVacationModel).filter_by(vacation_id=self._teacher.vacation_id).delete()
            else:
                session.query(TeachersVacationModel).filter(
                    and_(
                        TeachersVacationModel.teacher_id == self._teacher.teacher_id,
                        TeachersVacationModel.start_vacation == self._teacher.date_start,
                        TeachersVacationModel.end_vacation == self._teacher.date_end,
                    )
                ).delete()

    def convert_vacation_dates_to_client_timezone(self, client_timezone: str) -> Tuple[str, str]:
        vacation_time = time(0, 0)

        logger.debug(
            f"Converting vacation dates for teacher. "
            f"Moscow dates: {self._teacher.date_start} - {self._teacher.date_end}, "
            f"Target timezone: {client_timezone}"
        )

        start_datetime = convert_timezone_datetime(
            date_time=datetime.combine(self._teacher.date_start, vacation_time), to_tz=client_timezone
        )

        end_datetime = convert_timezone_datetime(
            date_time=datetime.combine(self._teacher.date_end, vacation_time), to_tz=client_timezone
        )

        start_dt = format_date(start_datetime, "d MMMM yyyy", locale="ru")
        end_dt = format_date(end_datetime, "d MMMM yyyy", locale="ru")

        start_dt = start_dt.replace(" г.", "") + " года"
        end_dt = end_dt.replace(" г.", "") + " года"

        return start_dt, end_dt

    def _create_message_for_send_to_bitrix(self):
        text_good_clients = ", ".join(
            [lms_customer.link_to_lms_customer for lms_customer in self._lms_customers.values() if lms_customer.is_send]
        )
        text_bad_clients = ", ".join(
            [
                lms_customer.link_to_lms_customer
                for lms_customer in self._lms_customers.values()
                if not lms_customer.is_send
            ]
        )
        text_who_have_trial = ", ".join(
            [
                lms_customer.link_to_lms_customer
                for lms_customer in self._lms_customers.values()
                if lms_customer.is_trial
            ]
        )
        text_who_have_group = ", ".join(
            [
                lms_customer.link_to_lms_customer
                for lms_customer in self._lms_customers.values()
                if lms_customer.is_group
            ]
        )
        text_who_not_link_to_bitrix = ", ".join(
            [
                lms_customer.link_to_lms_customer
                for lms_customer in self._lms_customers.values()
                if lms_customer.is_not_bitrix_field
            ]
        )

        logger.debug(
            f"{self._logger_name} || {LogsMessages.make_text_for_message}\n"
            f"text_good_clients = {text_good_clients}\n"
            f"text_bad_clients = {text_bad_clients}\n"
            f"text_who_have_trial = {text_who_have_trial}\n"
            f"text_who_have_group = {text_who_have_group}\n"
        )

        message_to_chat = (
            f"{self._teacher.teacher_name} уходит в отпуск с {self._teacher.date_start_str} "
            f"по {self._teacher.date_end_str}:\n"
        )

        if text_good_clients:
            message_to_chat = "\n".join([message_to_chat, MessageChat.holiday_mailing.value, text_good_clients])
        if text_bad_clients:
            message_to_chat = "\n".join([message_to_chat, MessageChat.dont_get_holiday_mailing.value, text_bad_clients])
        if text_who_have_trial:
            message_to_chat = "\n".join([message_to_chat, MessageChat.have_trial_lessons.value, text_who_have_trial])
        if text_who_have_group:
            message_to_chat = "\n".join([message_to_chat, MessageChat.have_group_lessons.value, text_who_have_group])
        if text_who_not_link_to_bitrix:
            message_to_chat = "\n".join(
                [
                    message_to_chat,
                    MessageChat.no_bitrix_links.value,
                    text_who_not_link_to_bitrix,
                    "\nMessageChat.bitrix_links_note.value",
                ]
            )

        not_cancelled_days = []

        date_start = self._teacher.date_start

        while date_start <= self._teacher.date_end:
            status, message = self._set_day_off_for_teacher.set_day_off(
                lms_teacher_id=self._teacher.lms_teacher_id,
                date_day_off=date_start,
            )

            if status == "error":
                not_cancelled_days.append(f'{date_start.strftime("%d.%m.%Y")} - {message}')

            date_start += timedelta(days=1)
            logger.debug(
                f"{self._logger_name} || Отменяем уроки на день\n"
                f"message = {message}\n"
                f"status = {status}\n"
                f"date_start = {date_start}"
            )

        text_who_have_canceled_days = ", ".join([date_reason for date_reason in not_cancelled_days])
        if text_who_have_canceled_days:
            message_to_chat = "\n".join(
                [
                    message_to_chat,
                    "\nMessageChat.not_cancelled_days.value",
                    text_who_have_canceled_days,
                    MessageChat.manual_cancellation_note.value,
                ]
            )

        result = send_message_to_bx_chat(message_to_chat)
        logger.debug(f"{self._logger_name} || Отправляем сообщение в чат битрикса\nresult = {result}\n")

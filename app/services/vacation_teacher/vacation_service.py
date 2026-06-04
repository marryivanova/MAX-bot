from datetime import date, datetime
from types import SimpleNamespace
from typing import Callable, Dict, Optional, Tuple

from fastapi import Request
from loguru import logger
from pydantic import BaseModel, Field, validator
from sqlalchemy import and_, select

from app.bitrix.bx_method import get_link_for_bitrix
from app.bitrix.core.bitrix_send_alert import send_message_to_bx_chat
from app.services.vacation_teacher.model import TeacherVacation
from app.services.vacation_teacher.sender_message import SendMessageAndCancelLessonsAfterVacationService
from db.core import session_scope
from db.models.leads import LeadsUser
from db.models.teachers_lms import LMSTeacher
from db.models.teachers_vacation import TeachersVacationModel


class BitrixVacationRequest(BaseModel):
    event: str
    teacher_id: int
    date_start_str: str
    date_end_str: str
    vacation_id: Optional[int | str] = None

    @validator("date_start_str", "date_end_str")
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%d.%m.%Y")
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected format: DD.MM.YYYY")

    @property
    def date_start(self) -> date:
        return datetime.strptime(self.date_start_str, "%d.%m.%Y").date()

    @property
    def date_end(self) -> date:
        return datetime.strptime(self.date_end_str, "%d.%m.%Y").date()


class VacationMessageBuilder:
    @staticmethod
    def build_vacation_cancelled_message(teacher_id: int, date_start: date, date_end: date) -> str:
        teacher_link = get_link_for_bitrix(teacher_id, "преподавателя", "user")
        return f"Для {teacher_link} был отменён отпуск с {date_start} по {date_end}."

    @staticmethod
    def build_teacher_not_found_message(teacher_id: int) -> str:
        return (
            f'Проблема с отпуском у {get_link_for_bitrix(teacher_id, "учителя", "user")} '
            f"надо проверить, что номера телефонов учителя совпадают и в битриксе и на платформе"
        )

    @staticmethod
    def build_lesson_line(lesson: dict) -> str:
        return (
            f'Урок будет {lesson["event_date"]} {lesson["start_time"]} '
            f'{get_link_for_bitrix(lesson["pupil"], "посмотреть", "lms")}'
        )

# Todo: Реализовать метод

def by_period(date_end, date_start, id_lms):
    pass


class VacationTeacherService:

    def __init__(self):
        self.message_builder = VacationMessageBuilder()

    async def bitrix_vacation_teacher(self, request: Request, **kwargs) -> Tuple[str, int]:
        """Основной метод для обработки запросов из Битрикс (FastAPI)"""
        func_name = f"bx vacation teacher № {datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"{func_name} || Start work")

        try:
            request_data = await self._collect_request_data(request, kwargs)
            logger.debug(f"{func_name} || Данные в запросе || {request_data}")

            vacation_request = self._parse_and_validate_request(request_data)
            return await self._handle_event(func_name, vacation_request)

        except ValueError as e:
            logger.error(f"{func_name} || Validation error: {e}")
            return str(e), 400
        except Exception as e:
            logger.error(f"{func_name} || Unexpected error: {e}")
            return "Internal server error", 500

    @staticmethod
    async def _collect_request_data(request: Request, kwargs: dict) -> dict:
        request_data = {}
        request_data.update(kwargs)
        try:
            json_data = await request.json()
            request_data.update(json_data)
        except:
            pass

        try:
            form_data = await request.form()
            request_data.update(dict(form_data))
        except:
            pass

        return request_data

    @staticmethod
    def _parse_and_validate_request(request_data: dict) -> BitrixVacationRequest:
        return BitrixVacationRequest(**request_data)

    async def _handle_event(self, func_name: str, request: BitrixVacationRequest) -> Tuple[str, int]:
        event_handlers: Dict[str, Callable] = dict(
            delete_vacation=self._handle_delete_vacation,
            check_teacher=self._handle_check_teacher,
            find_bad_lessons=self._handle_find_bad_lessons,
            send_message_and_cancel_lessons=self._handle_send_message_and_cancel,
            accept_curator=self._handle_accept_curator,
        )

        handler = event_handlers.get(request.event)
        if not handler:
            logger.warning(f"{func_name} || Unknown event: {request.event}")
            return "Unknown event", 400

        return await handler(func_name, request)

    def _handle_delete_vacation(self, func_name: str, request: BitrixVacationRequest) -> Tuple[str, int]:
        logger.debug(f"{func_name} || Удаляю отпуск")

        with session_scope() as session:
            if request.vacation_id:
                session.query(TeachersVacationModel).filter_by(vacation_id=request.vacation_id).delete()
            else:
                session.query(TeachersVacationModel).filter(
                    and_(
                        TeachersVacationModel.teacher_id == request.teacher_id,
                        TeachersVacationModel.start_vacation == request.date_start,
                        TeachersVacationModel.end_vacation == request.date_end,
                    )
                ).delete()

        message = self.message_builder.build_vacation_cancelled_message(
            request.teacher_id, request.date_start, request.date_end
        )
        self._send_chat_message(func_name, message)
        return "", 200

    @staticmethod
    def _handle_check_teacher(func_name: str, request: BitrixVacationRequest) -> Tuple[str, int]:
        logger.debug(f"{func_name} || Это просто проверка учителя")
        return "", 200

    def _handle_find_bad_lessons(self, func_name: str, request: BitrixVacationRequest) -> Tuple[str, int]:
        logger.debug(f"{func_name} || Поиск вводных и групповых уроков")

        teacher_info = self._get_teacher_info(func_name, request.teacher_id)
        if not teacher_info:
            return "", 200

        lessons = by_period(request.date_end, request.date_start, teacher_info.id_lms)

        trial_messages = []
        group_messages = []

        for lesson in lessons:
            lesson_line = self.message_builder.build_lesson_line(lesson)
            if lesson["type"] == "trial":
                trial_messages.append(lesson_line)
            elif "GR" in lesson.get("course_title", ""):
                group_messages.append(lesson_line)

        if trial_messages:
            message = (
                f"{teacher_info.name} уходит в отпуск с {request.date_start} "
                f"по {request.date_end}, но у него есть вводные уроки:\n\n"
            ) + "\n".join(trial_messages)
            self._send_chat_message(func_name, message)

        if group_messages:
            message = (
                f"{teacher_info.name} уходит в отпуск с {request.date_start} "
                f"по {request.date_end}, но у него есть групповые уроки:\n\n"
            ) + "\n".join(group_messages)
            self._send_chat_message(func_name, message)

        return "", 200

    async def _handle_send_message_and_cancel(self, func_name: str, request: BitrixVacationRequest) -> Tuple[str, int]:
        teacher_info = self._get_teacher_info(func_name, request.teacher_id)
        if not teacher_info:
            return "", 200

        teacher_dto = TeacherVacation(
            bitrix_teacher_id=request.teacher_id,
            lms_teacher_id=teacher_info.id_lms,
            teacher_name=teacher_info.name or f"преподаватель {teacher_info.id_lms}",
            date_start_str=request.date_start_str,
            date_end_str=request.date_end_str,
            vacation_id=request.vacation_id,
        )

        await SendMessageAndCancelLessonsAfterVacationService(
            logger_name=func_name,
            teacher=teacher_dto,
        ).work()

        return "", 200

    @staticmethod
    def _handle_accept_curator(request: BitrixVacationRequest) -> Tuple[str, int]:
        teacher_vacation = TeachersVacationModel(
            teacher_id=request.teacher_id,
            start_vacation=request.date_start,
            end_vacation=request.date_end,
            vacation_id=request.vacation_id,
        )

        with session_scope() as session:
            session.add(teacher_vacation)

        return "", 200

    def _get_teacher_info(self, func_name: str, teacher_id: int):

        with session_scope() as session:
            query = select(LMSTeacher).where(LMSTeacher.id_bx == teacher_id)
            teacher = session.execute(query).scalar_one_or_none()

            if teacher:
                teacher_name = teacher.name if teacher.name else f"преподаватель {teacher.id_lms}"
                logger.debug(f"{func_name} || Нашли учителя в LMS_teachers: {teacher.id_lms}, {teacher_name}")
                return SimpleNamespace(id_lms=teacher.id_lms, name=teacher_name)

            logger.debug(f"{func_name} || Не нашли в LMS_teachers, ищем в GPS_leads")
            query = select(LeadsUser).where(LeadsUser.ID == teacher_id)
            lead = session.execute(query).scalar_one_or_none()

            if lead:
                lead_name = lead.TITLE if lead.TITLE else f"учитель {lead.ID}"
                logger.debug(f"{func_name} || Нашли учителя в GPS_leads: {lead.ID}, {lead_name}")
                return SimpleNamespace(id_lms=None, name=lead_name)

            logger.debug(f"{func_name} || Не нашли учителя нигде")
            message = self.message_builder.build_teacher_not_found_message(teacher_id)
            self._send_chat_message(func_name, message)
            return None

    @staticmethod
    def _send_chat_message(func_name: str, message: str):
        result = send_message_to_bx_chat(message)
        logger.debug(f"{func_name} || Результат отправки сообщения: {result}")

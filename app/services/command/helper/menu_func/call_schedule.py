from base64 import urlsafe_b64encode
from typing import List

from loguru import logger


from app.lms.models import LessonResponse
from settings import settings


def get_schedule(lms_customer_id: int):
    """Получение расписания ученика"""
    logger.info(f"Start schedule for lms_id: {lms_customer_id}")

    lms_customer = [] #TODO: взять с апи или БД данные
    logger.debug(f"get lms customer = {lms_customer}")

    if not lms_customer:
        logger.error(f"LMS customer not found for id: {lms_customer_id}")
        return dict(status="error", message="Клиент не найден", need_fill_form=False, schedule_text=None)

    need_fill_form = False
    if "children" in lms_customer:
        for child in lms_customer["children"]:
            if not child.get("first_name") or child.get("first_name") == "Number":
                need_fill_form = True
                break

    if need_fill_form:
        uid = urlsafe_b64encode(str(lms_customer_id).encode("utf-8")).rstrip(b"\n=").decode("ascii")
        link_to_form_fill_kids = f"{settings.lms.lk_url}form/kids?client={uid}"
        logger.debug(f"link to form fill kids = {link_to_form_fill_kids}")

        return dict(
            status="need_form",
            message="Пожалуйста, заполните данные о ребенке",
            need_fill_form=True,
            form_link=link_to_form_fill_kids,
            schedule_text=None,
        )

    schedule_parts = []

    if "children" not in lms_customer or not lms_customer["children"]:
        return dict(status="no_children", message="Нет добавленных детей", need_fill_form=False, schedule_text=None)

    for child in lms_customer["children"]:
        child_id = child.get("id")
        child_name = child.get("first_name", "Ребенок")

        if not child_id:
            logger.warning(f"Child {child_name} has no id")
            continue

        lessons: List[LessonResponse] = [] #TODO: взять с апи или БД данные

        schedule_parts.append(f"\n🧑‍🎓 <b>{child_name}</b>")

        if not lessons:
            no_lessons = "📭 <i>Нет запланированных уроков</i>"
            schedule_parts.append(no_lessons)
            continue

        lessons_by_day = {}
        for lesson in lessons:
            day_key = (
                lesson.event_date.strftime("%Y-%m-%d")
                if hasattr(lesson, "event_date") and lesson.event_date
                else "other"
            )

            if day_key not in lessons_by_day:
                lessons_by_day[day_key] = []
            lessons_by_day[day_key].append(lesson)

        for day_lessons in lessons_by_day.values():
            for lesson in day_lessons:
                datetime_str = lesson.pretty_event_date_dmy_time_course()
                schedule_parts.append(f"▫️ {datetime_str}")

    if not schedule_parts:
        return dict(
            status="no_schedule",
            message="Расписание не найдено",
            need_fill_form=False,
            schedule_text=None,
        )

    schedule_text = "\n".join(schedule_parts)

    return dict(status="success", message=None, need_fill_form=False, schedule_text=schedule_text)

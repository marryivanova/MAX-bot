from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.services.model.all_url import MaxUrl
from db.core import session_scope
from db.models.lms_user import User
from db.models.max_user import MaxUser


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(OperationalError),
)
def get_info_lms(
    chat_id: str, lead_id: Optional[int] = None, contact_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Получает информацию из LMS_users на основе chat_id и/или lead_id/contact_id
    """
    with session_scope() as session:
        max_user = session.query(MaxUser).filter_by(chat_id=chat_id).first()

        if not max_user:
            logger.warning(f"MaxUser с chat_id={chat_id} не найден")
            return None

        logger.info(
            f"✅ Найден MaxUser: id={max_user.id}, lead_id={max_user.lead_id}, contact_id={max_user.contact_id}"
        )

        conditions = []

        if max_user.lead_id:
            conditions.append(User.id_lead == max_user.lead_id)
        if max_user.contact_id:
            conditions.append(User.id_contact == max_user.contact_id)

        if lead_id:
            conditions.append(User.id_lead == lead_id)
        if contact_id:
            conditions.append(User.id_contact == contact_id)

        if not conditions:
            logger.warning("⚠️ Нет условий для поиска в LMSUser")
            return None

        lms_user = session.query(User).filter(or_(*conditions)).first()

        if lms_user:
            client_link = f"{MaxUrl.url_lms.value}{lms_user.id}/"

            result = dict(client_link=client_link, name=lms_user.name, timezone=lms_user.timezone)

            logger.info(
                f"🔍 Найден пользователь LMS: "
                f"id={lms_user.id}, "
                f"name={lms_user.name}, "
                f"lead_id={lms_user.id_lead}, "
                f"contact_id={lms_user.id_contact}, "
                f"timezone={lms_user.timezone}, "
                f"client_link={client_link}"
            )
            return result
        else:
            logger.warning(f"❌ LMSUser не найден по условиям: {conditions}")
            return None


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(OperationalError),
)
def get_info_contact_by_phone(
    chat_id: str | int,
    phone: Optional[int | str] = None,
) -> Optional[Dict[str, Any]]:

    with session_scope() as session:
        max_user = session.query(MaxUser).filter_by(chat_id=chat_id).first()

        if not max_user:
            logger.warning(f"MaxUser с chat_id={chat_id} не найден")
            return None

        logger.info(f"✅ Найден MaxUser: id={max_user.chat_id}, phone={max_user.phone}")

        return dict(max_id=chat_id, phone=phone)


def get_users_with_conditions(phone_not_null: bool = True, limit: int = None) -> List[Tuple[int, str]]:
    """Выгружает с возможностью фильтрации"""

    with session_scope() as session:
        query = session.query(MaxUser.chat_id, MaxUser.phone)

        if phone_not_null:
            query = query.filter(MaxUser.phone.isnot(None))

        if limit:
            query = query.limit(limit)

        result = query.all()
        return [(row.chat_id, row.phone) for row in result]

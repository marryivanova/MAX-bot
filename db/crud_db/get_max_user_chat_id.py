from typing import Dict, Optional

from loguru import logger
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from db.core import session_scope
from db.models.max_user import MaxUser


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(OperationalError),
)
def get_max_user_by_chat_id(chat_id: str) -> Optional[Dict]:
    """
    Находит пользователя в max_user по chat_id
    """
    if not chat_id:
        logger.error("Не передан chat_id")
        return None

    with session_scope() as session:
        user = session.query(MaxUser).filter_by(chat_id=chat_id).first()

        if user:
            user_data = dict(
                id=user.id, chat_id=user.chat_id, phone=user.phone, contact_id=user.contact_id, lead_id=user.lead_id
            )
            logger.info(f"✅ Найден пользователь с chat_id={chat_id}: {user_data}")
            return user_data
        else:
            logger.info(f"Пользователь с chat_id={chat_id} не найден")
            return None

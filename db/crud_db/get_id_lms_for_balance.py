from typing import Optional

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
def get_lms_id_by_chat_id(chat_id: str) -> Optional[int]:
    """
    Получает lms_id по chat_id
    """
    with session_scope() as session:
        result = session.query(MaxUser.lms_id).filter_by(chat_id=chat_id).first()
        logger.info(f"Получает lms_id по chat_id: {chat_id}: {result}")
        return result[0] if result else None

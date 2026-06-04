from datetime import datetime

from loguru import logger
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from db.core import session_scope
from db.models.lms_user import User
from db.models.max_user import MaxUser


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(OperationalError),
)
def update_lms_id_max_orm():
    logger.info(f"Старт ORM версия: {datetime.now()}")

    with session_scope() as session:
        max_users = session.query(MaxUser).filter((MaxUser.lms_id.is_(None)) | (MaxUser.lms_id == 0)).all()

        updated_count = 0

        for max_user in max_users:
            lms_user = None

            if max_user.lead_id:
                lms_user = session.query(User).filter(User.id_lead == max_user.lead_id).first()

            if not lms_user and max_user.contact_id:
                lms_user = session.query(User).filter(User.id_contact == max_user.contact_id).first()

            if lms_user:
                max_user.lms_id = lms_user.id
                updated_count += 1

        session.flush()
        logger.info(f"Обновлено записей: {updated_count}")

    logger.info(f"Завершено ORM: {datetime.now()}")

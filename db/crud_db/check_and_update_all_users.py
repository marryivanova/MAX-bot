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
def update_max_user_from_lms():
    logger.info(f"Старт: {datetime.now()}")

    with session_scope() as session:
        max_users = session.query(MaxUser).filter((MaxUser.lead_id.is_(None)) | (MaxUser.contact_id.is_(None))).all()

        logger.info(f"Найдено записей для обновления: {len(max_users)}")

        for mu in max_users:
            if not mu.phone:
                continue

            mu_phone_clean = "".join(filter(str.isdigit, mu.phone))

            lms_user = None

            lms_user = session.query(User).filter(User.phone == mu.phone).first()

            if not lms_user:
                lms_user = (
                    session.query(User)
                    .filter(
                        (User.phone == mu_phone_clean)  # 79131930442
                        | (User.phone == f"+{mu_phone_clean}")  # +79131930442
                        | (User.phone == f"8{mu_phone_clean[1:]}")
                    )
                    .first()
                )

            if lms_user:
                changes = []

                if lms_user.id_lead and mu.lead_id is None:
                    mu.lead_id = lms_user.id_lead
                    changes.append(f"lead_id={lms_user.id_lead}")

                if lms_user.id_contact and mu.contact_id is None:
                    mu.contact_id = lms_user.id_contact
                    changes.append(f"contact_id={lms_user.id_contact}")

                if lms_user.id and mu.lms_id is None:
                    mu.lms_id = lms_user.id
                    changes.append(f"lms_id={lms_user.id}")

                if changes:
                    session.add(mu)
                    logger.info(f"Обновлен max_user {mu.id} ({mu.phone}): {', '.join(changes)}")
            else:
                logger.debug(f"LMS пользователь не найден для телефона {mu.phone} (очищенный: {mu_phone_clean})")

    logger.info(f"Готово: {datetime.now()}")

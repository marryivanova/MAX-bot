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
def create_max_customer(chat_id: str, phone: str = None, lead_id: int = None, contact_id: int = None):
    """
    Создание или обновление пользователя в max_user
    Если есть phone, ищем совпадения в users и проставляем lead_id и contact_id

    Args:
        chat_id: ID чата (обязательный)
        phone: Номер телефона (опционально)
        lead_id: ID лида (опционально)
        contact_id: ID контакта (опционально)

    Returns:
        MaxUser: созданный объект пользователя
    """
    with session_scope() as session:
        existing_user = session.query(MaxUser).filter_by(chat_id=chat_id).first()

        lms_lead_id = None
        lms_contact_id = None

        if phone:
            lms_user = session.query(User).filter_by(phone=phone).first()
            if lms_user:
                lms_lead_id = lms_user.id_lead
                lms_contact_id = lms_user.contact_id
                logger.info(
                    f"🔍 Найден пользователь LMS для телефона {phone}: lead_id={lms_lead_id}, contact_id={lms_contact_id}"
                )

        if existing_user:
            changes = []

            if phone is not None:
                existing_user.phone = phone
                changes.append("phone")

            if lead_id is not None:
                existing_user.lead_id = lead_id
                changes.append(f"lead_id={lead_id}")
            elif lms_lead_id is not None and existing_user.lead_id is None:
                existing_user.lead_id = lms_lead_id
                changes.append(f"lead_id={lms_lead_id} (из LMS)")

            if contact_id is not None:
                existing_user.contact_id = contact_id
                changes.append(f"contact_id={contact_id}")
            elif lms_contact_id is not None and existing_user.contact_id is None:
                existing_user.contact_id = lms_contact_id
                changes.append(f"contact_id={lms_contact_id} (из LMS)")

            session.add(existing_user)
            session.flush()

            if changes:
                logger.info(f"🔄 Обновлен пользователь {chat_id}: {', '.join(changes)}")
            else:
                logger.debug(f"⏭️ Пользователь {chat_id} без изменений")

            return existing_user
        else:
            final_lead_id = lead_id if lead_id is not None else lms_lead_id
            final_contact_id = contact_id if contact_id is not None else lms_contact_id

            new_user = MaxUser(chat_id=chat_id, phone=phone, lead_id=final_lead_id, contact_id=final_contact_id)

            session.add(new_user)
            session.flush()

            source = "из LMS" if (lms_lead_id or lms_contact_id) and not (lead_id or contact_id) else "явно указаны"
            logger.info(
                f"🆕 Создан пользователь {chat_id} с phone={phone}, lead_id={final_lead_id}, contact_id={final_contact_id} ({source})"
            )

            return new_user

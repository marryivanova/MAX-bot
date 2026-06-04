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
def update_max_user_from_bitrix(phone: str, bitrix_data: dict, name_called_function: str = None):
    """
    Обновляет запись в max_user по номеру телефона, проставляя lead_id и contact_id из Битрикса
    """
    func_name = name_called_function or "update_max_user_from_bitrix"

    phone_clean = "".join(filter(lambda x: x.isdigit(), phone))
    if phone_clean.startswith("8") and len(phone_clean) == 11:
        phone_clean = phone_clean.replace("8", "7", 1)

    logger.debug(f"{func_name} || Ищем в max_user по телефону: {phone_clean}")

    with session_scope() as session:
        users = session.query(MaxUser).filter(MaxUser.phone.like(f"%{phone_clean}")).all()

        if not users:
            logger.debug(f"{func_name} || Пользователь с телефоном {phone_clean} не найден в max_user")
            return

        logger.info(f"{func_name} || Найдено {len(users)} пользователей с телефоном {phone_clean}")

        lead_id = bitrix_data.get("LEAD", [None])[0]
        contact_id = bitrix_data.get("CONTACT", [None])[0]

        for user in users:
            changes = []

            if lead_id and user.lead_id is None:
                user.lead_id = lead_id
                changes.append(f"lead_id={lead_id}")

            if contact_id and user.contact_id is None:
                user.contact_id = contact_id
                changes.append(f"contact_id={contact_id}")

            if changes:
                session.add(user)
                logger.info(f"{func_name} || Обновлен пользователь {user.chat_id}: {', '.join(changes)}")
            else:
                logger.debug(f"{func_name} || Пользователь {user.chat_id} уже имеет все ID")

from loguru import logger

from db.core import session_scope
from db.models.lms_user import LMSUser


def get_lms_from_db(id_bitrix_contact, name_called_function="Get id platform from DB"):
    logger.debug(f"{name_called_function} || get_lms||\nЗапускаем функцию")

    with session_scope() as session:
        lead = session.query(LMSUser).filter(LMSUser.id_contact == id_bitrix_contact).first()

        if lead:
            logger.debug(f"{name_called_function} || get_lms || Получили id платформы из БД || [JSON]{lead}[/JSON]")
            return lead.id
        return None


def get_lead_from_db(id_bitrix_contact, name_called_function="Get lead from DB"):
    logger.debug(f"{name_called_function} || get_lead||\nЗапускаем функцию")

    with session_scope() as session:
        lead = session.query(LMSUser).filter(LMSUser.id_contact == id_bitrix_contact).first()

        if lead:
            logger.debug(f"{name_called_function} || get_lms_leads || Получили лида из БД || [JSON]{lead}[/JSON]")
            return lead.id_lead
        return None

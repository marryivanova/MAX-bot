import asyncio

from loguru import logger
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from db.core import read_session
from db.models.twilio import TwilioTemplate


def _get_text_by_sid_sync(sid_value: str) -> str | None:
    try:
        with read_session() as session:
            result = session.query(TwilioTemplate).filter_by(sid=sid_value).first()
            if result:
                logger.debug(f"Найден текст для SID: {sid_value}")
                logger.debug(result.текст)
                return result.текст
            else:
                logger.warning(f"SID {sid_value} не найден в БД")
                return None
    except OperationalError as e:
        logger.error(f"Ошибка подключения к БД при запросе SID {sid_value}: {e}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запросе SID {sid_value}: {e}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(OperationalError),
)
async def get_text_by_sid(sid_value: str) -> str | None:
    """
    Асинхронное получение текста шаблона по SID
    """
    result = await asyncio.to_thread(_get_text_by_sid_sync, sid_value)
    return result


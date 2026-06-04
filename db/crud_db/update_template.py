import asyncio
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.helper.google_spreadsheet import GoogleGetPatternMessage
from db.core import read_session
from db.models.twilio import TwilioTemplate


def _get_all_sids_from_db() -> List[str]:
    """Получить все существующие SID из БД"""
    try:
        with read_session() as session:
            results = session.query(TwilioTemplate.sid).all()
            existing_sids = [result[0] for result in results]
            logger.info(f"Найдено {len(existing_sids)} SID в БД")
            return existing_sids
    except Exception as e:
        logger.error(f"Ошибка при получении SID из БД: {e}")
        return []


def _get_all_sids_from_google() -> List[str]:
    """Получить ВСЕ SID из Google таблицы из колонки SID (индекс 1)"""
    try:
        searcher = GoogleGetPatternMessage(search_value="")
        all_rows = searcher.get_all_rows()

        all_sids = []
        for row in all_rows[1:]:
            if len(row) > 1 and row[1]:
                sid = row[1].strip()
                if sid:
                    all_sids.append(sid)

        logger.info(f"Найдено {len(all_sids)} SID в Google таблице")
        return all_sids

    except Exception as e:
        logger.error(f"Ошибка при получении SID из Google таблицы: {e}")
        return []


def _get_template_by_sid(sid: str) -> Dict[str, Any]:
    """Получить полные данные шаблона из Google по SID"""
    try:
        searcher = GoogleGetPatternMessage(search_value=sid)
        templates = searcher.get_pattern_message_full()
        if templates and len(templates) > 0:
            return templates[0]
        return {}
    except Exception as e:
        logger.error(f"Ошибка при получении шаблона для SID {sid}: {e}")
        return {}


def _add_new_templates(google_sids: List[str], db_sids: List[str]) -> int:
    """Добавить в БД шаблоны, которых там нет"""
    new_sids = [sid for sid in google_sids if sid not in db_sids]

    if not new_sids:
        logger.info("Нет новых шаблонов для добавления")
        return 0

    logger.info(f"Найдено {len(new_sids)} новых шаблонов для добавления")

    added_count = 0

    try:
        with read_session() as session:
            for sid in new_sids:
                template = _get_template_by_sid(sid)

                if not template:
                    logger.warning(f"Не удалось получить данные для SID {sid}")
                    continue

                new_template = TwilioTemplate(
                    am=template.get("АМ", ""),
                    sid=sid,
                    источник=template.get("Источник", ""),
                    текст=template.get("текст", ""),
                    место_использования=template.get("место_использования", ""),
                )
                session.add(new_template)
                added_count += 1
                logger.info(f"Добавлен новый шаблон с SID: {sid}")

            if added_count > 0:
                session.commit()
                logger.info(f"Успешно добавлено {added_count} новых шаблонов в БД")

    except Exception as e:
        logger.error(f"Ошибка при добавлении шаблонов в БД: {e}")
        if "session" in locals():
            session.rollback()

    return added_count


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(OperationalError),
)
async def sync_templates_from_google_to_db() -> Dict[str, int]:
    """Синхронизировать шаблоны из Google таблицы с БД"""
    logger.info("Начинаем синхронизацию шаблонов из Google таблицы в БД")

    google_sids = await asyncio.to_thread(_get_all_sids_from_google)

    if not google_sids:
        logger.warning("Не удалось получить SID из Google таблицы")
        return {"total_in_google": 0, "total_in_db": 0, "added": 0}

    db_sids = await asyncio.to_thread(_get_all_sids_from_db)

    added_count = await asyncio.to_thread(_add_new_templates, google_sids, db_sids)

    result = dict(total_in_google=len(google_sids), total_in_db=len(db_sids), added=added_count)

    logger.info(
        f"Синхронизация завершена. "
        f"Всего в Google: {result['total_in_google']}, "
        f"Всего в БД: {result['total_in_db']}, "
        f"Добавлено: {result['added']}"
    )

    return result

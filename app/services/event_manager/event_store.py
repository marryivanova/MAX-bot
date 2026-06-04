import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger


class EventStore:
    """Хранилище событий с сохранением в БД"""

    def __init__(self, phone_db, max_age_seconds: int = 86400):
        self.phone_db = phone_db
        self.events_cache = defaultdict(list)
        self.next_processed_cache: Dict[str, float] = {}
        self.next_timeout_seconds = 3600
        self.max_age = timedelta(seconds=max_age_seconds)

    async def add_event(self, phone: str, event_data: Dict[str, Any]):
        """Добавить событие для номера телефона"""
        event_data["timestamp"] = datetime.now().isoformat()
        self.events_cache[phone].append(event_data)

        chat_id = event_data.get("chat_id")
        update_type = event_data.get("update_type", "unknown")

        if hasattr(self.phone_db, "save_event"):
            self.phone_db.save_event(
                phone=phone,
                chat_id=chat_id,
                update_type=update_type,
                event_data=event_data,
            )

        logger.info(f"Событие сохранено для {phone} в БД и кэш")

        await self._cleanup_cache()

    async def get_events(self, phone: str) -> List[Dict[str, Any]]:
        """Получить все события для номера телефона"""
        if phone in self.events_cache:
            events = self.events_cache[phone]
            logger.info(f"Найдено {len(events)} событий в кэше для {phone}")
            return events

        logger.info(f"Загружаем события из БД для {phone}")
        if hasattr(self.phone_db, "get_events_by_phone"):
            db_events = self.phone_db.get_events_by_phone(phone)

            events = []
            for db_event in db_events:
                event_data = db_event.get("data", {}) if isinstance(db_event, dict) else {}

                if event_data:
                    events.append(event_data)
                else:
                    event = dict(
                        update_type=db_event.get("update_type", "unknown"),
                        chat_id=db_event.get("chat_id"),
                        timestamp=db_event.get("timestamp"),
                        extracted_phone=phone,
                        source="db",
                    )
                    events.append(event)

            if events:
                self.events_cache[phone] = events

            logger.info(f"Загружено {len(events)} событий из БД для {phone}")
            return events

        return []

    async def get_last_event(self, phone: str) -> Optional[Dict[str, Any]]:
        """Получить последнее событие для номера телефона"""
        events = await self.get_events(phone)
        return events[-1] if events else None

    async def mark_next_as_processed(self, chat_id: str, phone: Optional[str] = None):
        """Пометить /next как обработанный"""
        chat_id_str = str(chat_id)
        timestamp = time.time()

        self.next_processed_cache[chat_id_str] = timestamp
        logger.debug(f"/next помечен как обработанный для chat_id {chat_id}")

        if hasattr(self.phone_db, "save_next_processed"):
            self.phone_db.save_next_processed(chat_id_str, phone if phone else None)

    async def is_next_processed(self, chat_id: str) -> bool:
        """Проверить, был ли обработан /next (без таймаута)"""
        chat_id_str = str(chat_id)

        if chat_id_str in self.next_processed_cache:
            logger.debug(f"/next заблокирован для chat_id {chat_id}")
            return True

        if hasattr(self.phone_db, "is_next_processed"):
            return self.phone_db.is_next_processed(chat_id_str)

        return False

    async def cleanup_old_next_calls(self):
        """Очистка старых записей о /next вызовах"""
        current_time = time.time()
        old_chats = []

        for chat_id, timestamp in self.next_processed_cache.items():
            if current_time - timestamp > self.next_timeout_seconds:
                old_chats.append(chat_id)

        for chat_id in old_chats:
            del self.next_processed_cache[chat_id]

        if old_chats:
            logger.debug(f"🧹 Очищено {len(old_chats)} старых записей /next")

    async def _cleanup_cache(self):
        """Очистка старых событий только из кэша (не из БД!)"""
        now = datetime.now()
        for phone in list(self.events_cache.keys()):
            valid_events = []
            for event in self.events_cache[phone]:
                event_time_str = event.get("timestamp")
                if event_time_str:
                    try:
                        event_time = datetime.fromisoformat(event_time_str)
                        if now - event_time <= self.max_age:
                            valid_events.append(event)
                    except ValueError:
                        valid_events.append(event)

            if valid_events:
                self.events_cache[phone] = valid_events
            else:
                del self.events_cache[phone]

        await self.cleanup_old_next_calls()

    async def get_all_events_from_db(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получить все события из БД (для отладки)"""
        if hasattr(self.phone_db, "get_all_events"):
            return self.phone_db.get_all_events()
        return {}

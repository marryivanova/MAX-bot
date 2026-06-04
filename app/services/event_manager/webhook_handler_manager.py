import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from max_sdk.core.enums.update import UpdateType
from max_sdk.core.helper.getted_updates import process_update_webhook
from max_sdk.core.types import Message
from max_sdk.dispatcher import Bot, Dispatcher, Router

from app.services.event_manager import BotManager
from app.services.event_manager.db_event.db_phone import PhoneDatabaseORM
from app.services.event_manager.event_store import EventStore
from app.services.event_manager.helper import (
    CallbackHandler,
    EventDataExtractor,
    PhoneExtractor,
    PhoneExtractorProtocol,
    WelcomeSender,
    sync_lms_async,
)
from db.crud_db.create_new_user import create_max_customer


# ========== Основной Webhook Handler ==========
class WebhookHandler:
    """Упрощенный обработчик вебхуков"""

    def __init__(
        self,
        bot_manager: BotManager,
        phone_db: Optional[PhoneDatabaseORM] = None,
        event_store: Optional[EventStore] = None,
        phone_extractor: Optional[PhoneExtractorProtocol] = None,
    ):
        self.bot_manager = bot_manager
        self.phone_db = phone_db
        self.event_store = event_store

        self.phone_extractor = phone_extractor or PhoneExtractor()
        self.data_extractor = EventDataExtractor()
        self.welcome_sender = WelcomeSender(bot_manager)
        self.callback_handler = CallbackHandler(bot_manager, event_store)

        logger.info(f"✅ WebhookHandler инициализирован")

    async def handle_webhook(self, request: Request) -> JSONResponse:
        """Обработать вебхук"""
        try:
            event_data = await request.json()
            return await self._process_event(event_data)
        except json.JSONDecodeError:
            logger.debug("Получен пустой JSON")
            return JSONResponse(content={"ok": True}, status_code=200)

    async def _process_event(self, event_data: Dict[str, Any]) -> JSONResponse:
        """Обработать событие"""
        self._validate_services_ready()

        update_type = event_data.get("update_type", "unknown")
        logger.debug(f"Вебхук получен: {update_type}")

        event_object = await process_update_webhook(event_json=event_data, bot=self.bot_manager.bot)

        if not event_object:
            return JSONResponse(content={"ok": True}, status_code=200)

        await self._store_event(event_object, event_data)

        if event_object.update_type == UpdateType.BOT_STARTED:
            await self._handle_bot_started(event_object)
        elif event_object.update_type == UpdateType.MESSAGE_CALLBACK:
            await self.callback_handler.handle_callback(event_object)

        await self.bot_manager.dispatcher.handle(event_object)

        logger.info(f"Событие обработано: {event_object.update_type}")
        return JSONResponse(content={"ok": True}, status_code=200)

    def _validate_services_ready(self):
        """Проверить готовность сервисов"""
        if not self.bot_manager.bot or not self.bot_manager.dispatcher:
            raise HTTPException(status_code=503, detail="Service not ready")

    async def _store_event(self, event_object: Any, event_data: Dict[str, Any]):
        """Сохранить событие"""
        phone = await self.phone_extractor.extract(event_object, event_data)
        chat_id = self.data_extractor.extract_chat_id(event_object, event_data)

        logger.info(f" Извлечен телефон: {phone}")
        logger.info(f" Извлечен chat_id: {chat_id}")

        if phone and chat_id:
            self.phone_db.save_mapping(chat_id, phone)
            logger.info(f"Сохранен маппинг: {chat_id} -> {phone}")
            create_max_customer(chat_id=chat_id, phone=phone)
            asyncio.create_task(sync_lms_async(phone))

        store_data = dict(
            update_type=str(event_object.update_type),
            chat_id=chat_id,
            timestamp=datetime.now().isoformat(),
            raw_event=event_data,
            processed_event=(event_object.dict() if hasattr(event_object, "dict") else {}),
            extracted_phone=phone,
        )

        if phone:
            await self.event_store.add_event(phone, store_data)
            logger.info(f"Событие сохранено для телефона: {phone}")

    async def _handle_bot_started(self, event: Any) -> None:
        """Обработать запуск бота"""
        chat_id = event.chat_id
        logger.info(f"🎉 Новый пользователь начал диалог: {chat_id}")

        await self.welcome_sender.send(chat_id)

    async def get_chat_id_by_phone(self, phone: str) -> Optional[str]:
        """Получить chat_id по номеру телефона"""
        return self.phone_db.get_chat_id_by_phone(phone)

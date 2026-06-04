from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from loguru import logger
from max_sdk.core.types import Message
from max_sdk.dispatcher import Bot, Dispatcher, Router
from pydantic import BaseModel

from settings import settings

bot_instance: Optional[Bot] = None


def set_bot(bot: Bot):
    global bot_instance
    bot_instance = bot


def get_bot() -> Optional[Bot]:
    return bot_instance


class BotManager:
    """Менеджер для управления ботом и диспетчером"""

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None

    async def initialize(self, app: FastAPI):
        await self._initialize_bot(app)
        await self._initialize_dispatcher()
        await self._setup_handlers()
        logger.success("MAX BOT готов к работе!")

    async def start_polling(self):
        """Запуск получения сообщений (поллинг)"""
        if self.bot and self.dispatcher:
            logger.info("Запуск поллинга...")
            await self.dispatcher.start_polling(self.bot)
        else:
            logger.error("Не могу запустить поллинг: бот или диспетчер не инициализированы")

    async def _initialize_bot(self, app: FastAPI):
        self.bot = Bot(
            token=settings.max.secret,
            base_url=settings.max.domain,
            auto_check_subscriptions=True,
            auto_requests=True,
        )
        try:
            me = await self.bot.get_me()
            username = me.get("username", "unknown")
            logger.success(f"Бот инициализирован: @{username}")
        except Exception as e:
            logger.error(f"Ошибка при get_me: {e}")
            logger.warning("Продолжаем без проверки бота...")

        set_bot(self.bot)
        app.state.bot = self.bot

    async def _initialize_dispatcher(self):
        self.dispatcher = Dispatcher()
        logger.info("Диспетчер инициализирован")

    async def _setup_handlers(self):
        router = Router("main")

        @router.message_created()
        async def message_handler(event):
            from app.services.max_bot import handle_message_created

            await handle_message_created(event, self.bot)

        self.dispatcher.include_routers(router)

        total_handlers = len(self.dispatcher.event_handlers)
        router_handlers = sum(len(r.event_handlers) for r in self.dispatcher.routers)

        logger.info(f"Зарегистрировано обработчиков в диспетчере: {total_handlers}")
        logger.info(f"Зарегистрировано обработчиков в роутерах: {router_handlers}")

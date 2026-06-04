# ========== Welcome Message Sender ==========
from loguru import logger

from app.services.command.helper.constants_and_patterns.bot_buttons_text_menu import welcome_text
from app.services.event_manager import BotManager


class WelcomeSender:

    def __init__(self, bot_manager: BotManager):
        self.bot = bot_manager.bot

    async def send(self, chat_id: str) -> None:
        """Отправить приветственное сообщение"""

        await self.bot.messages.send_text_message(chat_id=chat_id, text=welcome_text)
        logger.info(f"Приветственное сообщение отправлено в чат {chat_id}")

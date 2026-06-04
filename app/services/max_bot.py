import re
from typing import Any

from loguru import logger
from max_sdk.dispatcher import Bot, Dispatcher, Router

from app.helper.parsers import parse_contact_attachment
from app.services.command.direction import send_direction_request_button
from app.services.command.get_contact import send_contact_request_button, send_unsuccess_phone
from app.services.command.helper.contact_helper_func import process_contact, validate_phone_number
from app.services.command.menu import balance_bot, free_lessons_bot, lk_bot, menu_bot, schedule_bot
from app.services.command.start_bot import start_bot
from app.services.event_manager.helper.extracts_additional_events import (
    get_attachments,
    get_chat_id,
    get_message_text,
    get_sender_name,
)
from app.services.vars.cmd import CmdType
from settings import settings

dp = Dispatcher()


async def send_start_command_response(bot: Bot, chat_id: str) -> None:
    """Отправляет ответ на команду /start"""
    await start_bot(bot, chat_id=chat_id)
    logger.info(f"Ответ на /start отправлен для чата {chat_id}")

    result = await send_contact_request_button(bot, chat_id=chat_id)

    logger.info(f"Результат запроса контакта: {result}")


async def handle_message_created(event: Any, bot: Bot) -> None:
    """Обработчик создания сообщения"""
    message = event.message if event else None

    sender_name = get_sender_name(message)
    text = get_message_text(message)
    attachments = get_attachments(message)
    chat_id = get_chat_id(event)

    if sender_name or text:
        logger.info(f"Сообщение от {sender_name}: {text}")

    if text:
        phones = re.findall(r"[\+7|7|8]?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", text)
        for phone in phones:
            if await validate_phone_number(phone):
                logger.info(f"Найден валидный номер: {phone}")
            else:
                await send_unsuccess_phone(bot, chat_id, phone)
                logger.info(f"Невалидный номер: {phone}")

    vcf_info = parse_contact_attachment(attachments, sender_name)
    if vcf_info:
        await process_contact(event, bot, vcf_info)
        return

    if not text or not chat_id:
        if not chat_id:
            logger.error("Не удалось определить chat_id")
        return

    if text.strip() == CmdType.start.value:
        logger.info(f"Обработка команды /start для чата {chat_id}")
        await send_start_command_response(bot, chat_id)
        return

    if text.strip() == CmdType.menu.value:
        logger.info(f"Обработка команды /menu для чата {chat_id}")
        await menu_bot(bot, chat_id=chat_id)
        return

    if text.strip() == CmdType.schedule.value:
        logger.info(f"Обработка команды /schedule_bot для чата {chat_id}")
        await schedule_bot(bot, chat_id=chat_id)
        return

    if text.strip() == CmdType.free_lessons.value:
        logger.info(f"Обработка команды /free_lessons для чата {chat_id}")
        await free_lessons_bot(bot, chat_id=chat_id)
        return

    if text.strip() == CmdType.lk.value:
        logger.info(f"Обработка команды /lk для чата {chat_id}")
        await lk_bot(bot, chat_id)
        return

    if text.strip() == CmdType.balance.value:
        logger.info(f"Обработка команды /balance для чата {chat_id}")
        await balance_bot(bot, chat_id=chat_id)
        return

    if text.strip() == CmdType.directions.value:
        logger.info(f"Обработка команды /directions для чата {chat_id}")
        await send_direction_request_button(bot, chat_id)
        return


async def setup_webhook():
    bot = Bot(
        token=settings.max.secret,
        base_url=settings.max.domain,
        auto_check_subscriptions=True,
        auto_requests=True,
    )

    me = await bot.get_me()
    username = me.get("username", "")
    logger.success(f"Бот: @{username}")

    @dp.message_created()
    async def message_handler(event):
        await handle_message_created(event, bot)

    return bot, dp

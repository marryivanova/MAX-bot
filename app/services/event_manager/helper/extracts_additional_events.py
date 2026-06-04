from typing import Any, Optional

from loguru import logger
from max_sdk.dispatcher import Bot, Dispatcher, Router


def get_sender_name(message: Any) -> str:
    """Извлекает имя отправителя из сообщения"""
    if not message or not message.sender:
        return ""

    sender = message.sender
    return sender.first_name or sender.username or ""


def get_message_text(message: Any) -> str:
    """Извлекает текст из сообщения"""
    if not message:
        return ""

    if message.body and message.body.text:
        return message.body.text
    elif message.text:
        return message.text

    return ""


def get_attachments(message: Any) -> list:
    """Извлекает вложения из сообщения"""
    if not message:
        return []

    if message.body and message.body.attachments:
        return message.body.attachments

    return []


def get_chat_id(event: Any) -> Optional[str]:
    """Извлекает chat_id из события"""
    if not event or not event.message or not event.message.recipient:
        return None

    return event.message.recipient.chat_id


def get_user_id(event: Any) -> Optional[str]:
    """Извлекает user_id из события"""
    if not event or not event.message or not event.message.recipient:
        return None

    return event.message.recipient.user_id

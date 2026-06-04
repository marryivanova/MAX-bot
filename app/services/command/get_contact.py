import asyncio
import time

from loguru import logger

from app.services.command import call_sync_lms_api
from app.services.command.helper.constants_and_patterns.bot_buttons import (
    buttons,
    buttons_choice,
    call_manager,
    users_response,
)
from app.services.command.helper.constants_and_patterns.bot_buttons_text_menu import menu_text_consultation
from app.services.command.helper.menu_func import send_present
from db.crud_db.create_new_user import create_max_customer


async def send_contact_request_button(bot, chat_id):
    """Отправляет кнопку запроса контакта"""
    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=(),
        buttons=buttons,
    )
    logger.debug(f"Кнопка отправлена: {result}")
    time.sleep(10)
    await send_present(bot, chat_id)


async def send_choosing_answer_request_button(bot, chat_id):
    """Отправляет кнопку выбора статуса пользователя"""

    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=menu_text_consultation,
        buttons=buttons_choice,
        format_type="html",
        disable_link_preview=True,
        notify=True,
    )
    logger.debug(f"Кнопка выбора статуса отправлена: {result}")


async def send_unsuccess_response(bot, chat_id):
    await bot.messages.send_text_message(chat_id=chat_id, test="")


async def send_student_message(bot, chat_id: str) -> None:
    await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text="",
        buttons=call_manager,
        format_type="html",
        disable_link_preview=True,
        notify=True,
    )


async def send_success_response(bot, chat_id, phone):
    """Отправляет пользователю подтверждение"""

    await bot.messages.send_text_message(
        chat_id=chat_id,
        text=f"Спасибо! Ваш номер {phone} обработан!  😊\n\n"
    )
    create_max_customer(chat_id=chat_id, phone=phone)
    logger.debug(f"Новый пользователь добавлен в БД")
    asyncio.create_task(call_sync_lms_api(phone))

    logger.debug(f"Новый пользователь получил подарок")
    await send_present(bot, chat_id)


async def send_get_phone(bot, chat_id, phone):
    """"""
    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=f"Подтвердите отправку номера: {phone}!  😊\n\n",
        buttons=users_response,
        format_type="html",
        disable_link_preview=True,
        notify=True,
    )
    logger.debug(f"Кнопки направления отправлены: {result}")


async def send_unsuccess_phone(bot, chat_id, phone):
    """Отправляет пользователю если номер неверный"""
    await bot.messages.send_text_message(
        chat_id=chat_id,
        text=f"Ваш номер {phone} указан в неверном формате!\n\n"
        f"Пожалуйста, укажите Ваш номер согласно формату: + 7 XXX XXX XX XX!",
    )

from loguru import logger

from app.services.command.helper.constants_and_patterns import error_balance, menu_text_core, menu_text_lk
from app.services.command.helper.constants_and_patterns.bot_buttons import (
    balance_menu_keyboard,
    core_menu_keyboard,
    lk_text_buttons,
)
from app.services.command.helper.constants_and_patterns.bot_buttons_text_menu import (
    menu_text_balance,
    menu_text_schedule,
    menu_text_schedule_empty,
    menu_text_schedule_error,
    menu_text_schedule_need_form,
)
from app.services.command.helper.menu_func import get_balance_lesson, get_schedule
from app.services.command.helper.menu_func.call_free_lessons import get_free_lessons
from db.crud_db.get_id_lms_for_balance import get_lms_id_by_chat_id
from db.crud_db.get_max_user_chat_id import get_max_user_by_chat_id

# -------------------------------
#       MENU
# -------------------------------


async def menu_bot(bot, chat_id) -> None:
    """Отправка главного меню"""
    logger.info(f"Отправка главного меню в чат {chat_id}")

    user = get_max_user_by_chat_id(chat_id=chat_id)

    if user:
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=menu_text_core,
            format_type="html",
            buttons=core_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )
        logger.info(f"✅ Показано меню для Контакта пользователя {chat_id}")

        return


async def balance_bot(bot, chat_id) -> None:
    """Отправка меню баланса"""

    lms_id = get_lms_id_by_chat_id(chat_id)

    balance_data = get_balance_lesson(lms_id)

    logger.info(f"Запрос баланса для chat_id: {chat_id}, lms_id: {lms_id}")

    if not balance_data:
        message_text = error_balance
    else:
        message_text = menu_text_balance.format(
            paid_lessons=balance_data["paid_lessons"],
            bonus_lessons=balance_data["bonus_lessons"],
            total_lessons=balance_data["total_lessons"],
        )

    await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=message_text,
        format_type="html",
        buttons=balance_menu_keyboard,
        disable_link_preview=True,
        notify=True,
    )


async def lk_bot(bot, chat_id) -> None:
    """Отправка меню личного кабинета"""
    logger.info(f"Отправка личного кабинета в чат {chat_id}")

    await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=menu_text_lk,
        buttons=lk_text_buttons,
        format_type="html",
        disable_link_preview=True,
        notify=True,
    )


async def schedule_bot(bot, chat_id) -> None:
    """Отправка меню расписания"""

    lms_id = get_lms_id_by_chat_id(chat_id)

    if not lms_id:
        logger.error(f"LMS ID not found for chat_id: {chat_id}")
        error_text = "⚠️ Ошибка: не удалось найти ваш профиль"

        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=error_text,
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )
        return

    schedule_data = get_schedule(lms_customer_id=lms_id)

    logger.info(f"Запрос расписания для chat_id: {chat_id}, lms_id: {lms_id}, status: {schedule_data['status']}")

    if schedule_data["status"] == "error":
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=menu_text_schedule_error,
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )

    elif schedule_data["status"] == "need_form":
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=menu_text_schedule_need_form,
            format_type="html",
            buttons=lk_text_buttons,
            disable_link_preview=True,
            notify=True,
        )

    elif schedule_data["status"] == "no_children":
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=menu_text_schedule_empty,
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )

    elif schedule_data["status"] == "no_schedule":
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=menu_text_schedule_empty,
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )

    elif schedule_data["status"] == "success":
        message_text = menu_text_schedule.format(schedule_content=schedule_data["schedule_text"])

        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=message_text,
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )


async def free_lessons_bot(bot, chat_id) -> None:
    """Отправка в меню реферальной программы"""

    lms_id = get_lms_id_by_chat_id(chat_id)
    logger.info(f"LMS ID found for chat_id: {lms_id}")

    free_lessons = get_free_lessons(lms_id)
    logger.info(f"Free lessons for lms_id: {free_lessons}")

    if free_lessons["status"] == "success":
        await bot.messages.send_message_with_keyboard(
            chat_id=chat_id,
            text=free_lessons["message"],
            format_type="html",
            buttons=balance_menu_keyboard,
            disable_link_preview=True,
            notify=True,
        )
        return

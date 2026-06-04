from loguru import logger

from app.services.command.helper.constants_and_patterns.bot_buttons import (
    balance_menu_keyboard,
    buttons_direction,
)


# -------------------------------
#    description of directions
# -------------------------------


async def send_direction_request_button(bot, chat_id):
    """Отправляет кнопки для выбора направления"""

    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text="",
        format_type="html",
        buttons=buttons_direction,
        disable_link_preview=True,
        notify=True,
    )
    logger.debug(f"Кнопки направления отправлены: {result}")


async def callback_after_choice_direction(bot, chat_id, direction) -> None:
    """Ответ на выбор направления"""
    logger.info(f"📤 Отправляем подтверждение выбора направления {direction} для chat_id={chat_id}")

    text = (
        f"🌟 Вы выбрали: *{direction}*\n\n"
        "Введите текст..."
    )

    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=text,
        format_type="html",
        buttons=balance_menu_keyboard,
        disable_link_preview=True,
        notify=True,
    )
    logger.info(f"✅ Отправлен ответ на выбранное направление - заявка на запись: {result}")
    return result

from loguru import logger

#TODO: тут нужно вставить текст и навание ссылок и сами ссылки

send_present_buttons = [
    [{"type": "link", "text": "", "url": ""}],
    [{"type": "link", "text": "", "url": ""}],
]

text = ""


async def send_present(bot, chat_id) -> None:
    result = await bot.messages.send_message_with_keyboard(
        chat_id=chat_id,
        text=text,
        format_type="html",
        buttons=send_present_buttons,
        disable_link_preview=True,
        notify=True,
    )
    logger.info(f"Отправлен ответ на отправку подарка новому пользователю: {result}")

from loguru import logger

# -------------------------------
#       START БОТА
# -------------------------------


async def start_bot(bot, chat_id) -> None:
    await bot.messages.send_text_message(
        chat_id=chat_id,
        text="",
    )
    logger.success("✅ Ответ на /start отправлен")

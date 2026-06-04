import aiohttp
from loguru import logger


async def call_sync_lms_api(phone: str):
    """Вызывает API синка с платформой"""

    url = f"https://maxbot.hwschool.pro/v1/api/sync-lms-max-id?phone={phone}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as response:
            if response.status == 200:
                data = await response.json()

                error_msg = f"Не удалось найти chat_id для пользователя {phone}"
                if data.get("error") == error_msg:
                    logger.debug("Пока пользователя нет на платформе")
                elif data.get("success") == True:
                    logger.debug("MAX ID успешно обновлен")
                else:
                    logger.debug(f"Неизвестный ответ от API: {data}")
            else:
                logger.error(f"API вернул статус {response.status}")

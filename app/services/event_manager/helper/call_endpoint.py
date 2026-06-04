import asyncio

import aiohttp
from loguru import logger

from app.services.model.all_url import MaxUrl


async def sync_lms_async(phone):
    try:
        async with aiohttp.ClientSession() as session:
            params = {"phone": phone}
            async with session.get(MaxUrl.lms_link.value, params=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Асинхронный синк LMS успешен: {data.get('max_id')}")
                else:
                    logger.warning(f"⚠️ LMS синк вернул {response.status}")
    except asyncio.TimeoutError:
        logger.warning("⚠️ Таймаут LMS синка (10с)")
    except Exception as e:
        logger.error(f"Ошибка LMS синка: {e}")

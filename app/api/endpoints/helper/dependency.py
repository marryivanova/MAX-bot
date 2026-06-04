from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasicCredentials
from loguru import logger
from max_sdk.dispatcher import Bot

from app.api.endpoints.auth import bearer_security, verify_token
from app.services.event_manager import BotManager, get_bot

bot_manager = BotManager()


async def get_bot_dependency() -> Bot:
    bot = get_bot()
    if bot is None:
        logger.error("Бот не инициализирован при попытке доступа к API")
        raise HTTPException(
            status_code=503,
            detail="Bot not initialized. Please wait for the service to start.",
        )
    return bot


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_security),
) -> dict:
    token = credentials.credentials
    payload = verify_token(token)
    return payload

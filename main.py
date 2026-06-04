from os import path

import sentry_sdk
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from loguru import logger
from max_sdk.core.helper.getted_updates import process_update_webhook
from max_sdk.dispatcher import Bot, Dispatcher, Router
from pydantic import BaseModel, Field
from sentry_sdk import init as sentry_init
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.api import api_router
from app.api.endpoints import health
from app.api.endpoints.auth import verify_credentials
from app.api.endpoints.helper.dependency import bot_manager
from app.services.event_manager import WebhookHandler
from app.services.event_manager.db_event.db_phone import PhoneDatabaseORM
from app.services.event_manager.event_store import EventStore
from app.services.event_manager.helper import PhoneExtractor
from settings import settings

debug_log_path = path.join(path.dirname(__file__), "logs", "debug", "logs.log")
logger.add(
    debug_log_path,
    format="|n| {time:YYYY-MM-DD HH:mm:ss} || {level} || {message}",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    compression="zip",
)

info_log_path = path.join(path.dirname(__file__), "logs", "info", "logs.log")
logger.add(
    info_log_path,
    format="{time:YYYY-MM-DD HH:mm:ss} || {message}",
    level="INFO",
    rotation="00:00",
    retention="30 days",
    compression="zip",
)

health.bot_manager = bot_manager
webhook_handler = WebhookHandler(bot_manager)

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    integrations=[
        FastApiIntegration(),
        StarletteIntegration(),
    ],
    traces_sample_rate=1.0,
    environment=settings.app.environment,
    send_default_pii=True,
)
app = FastAPI(
    title="MAX BOT",
    description="""
    ## Общее описание

    **MAX BOT** - интеллектуальный телеграм-бот на основе **API MAX**, 
    предназначенный для автоматизации бизнес-процессов и бесшовной интеграции 
    с экосистемой **Битрикс24 (BX24)**.
    """,
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment != "PROD" else None,
)


@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(verify_credentials)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Docs")


@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(username: str = Depends(verify_credentials)):
    return get_redoc_html(openapi_url="/openapi.json", title="ReDoc")


@app.on_event("startup")
async def startup_event():
    logger.info("Запуск инициализации бота...")
    await bot_manager.initialize(app)
    phone_db = PhoneDatabaseORM()
    event_store = EventStore(phone_db=phone_db, max_age_seconds=86400)
    phone_extractor = PhoneExtractor()

    webhook_handler = WebhookHandler(
        bot_manager=bot_manager,
        phone_db=phone_db,
        event_store=event_store,
        phone_extractor=phone_extractor,
    )

    app.state.webhook_handler = webhook_handler
    app.state.bot_manager = bot_manager
    app.state.phone_db = phone_db
    app.state.event_store = event_store

    logger.success("Бот успешно инициализирован")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Остановка приложения...")


@app.post("/", include_in_schema=False)
async def max_webhook(request: Request):
    webhook_handler = request.app.state.webhook_handler
    if webhook_handler is None:
        logger.error("WebhookHandler не инициализирован")
        return JSONResponse(content={"ok": False, "error": "Service not ready"}, status_code=503)
    return await webhook_handler.handle_webhook(request)


app.include_router(api_router)

if __name__ == "__main__":
    logger.info(f"Запуск сервера на {settings.app.host}:{settings.app.port}")

    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.environment == "DEV",
        log_level="info" if settings.environment == "PROD" else "debug",
        access_log=False,
    )

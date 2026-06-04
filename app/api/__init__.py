from fastapi import APIRouter, Depends

from app.api.endpoints import auth, health, lms_sync, message, sender_max

api_router = APIRouter(prefix="/v1")

api_router.include_router(auth.router)

api_router.include_router(health.router)
api_router.include_router(message.router)

api_router.include_router(lms_sync.router)

api_router.include_router(sender_max.router)

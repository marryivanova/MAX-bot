from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.endpoints.helper.dependency import bot_manager
from app.services.model.response_model import ServiceHealthResponse, ServiceStatus

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    bot_ready = bot_manager.bot is not None
    dispatcher_ready = bot_manager.dispatcher is not None

    if bot_ready and dispatcher_ready:
        status_value = ServiceStatus.RUNNING
    else:
        status_value = ServiceStatus.ERROR

    status_obj = ServiceHealthResponse(
        status=status_value,
        bot_ready=bot_ready,
        dispatcher_ready=dispatcher_ready,
        environment="prod",
        timestamp=datetime.utcnow().isoformat(),
    )

    if status_obj.status != ServiceStatus.RUNNING:
        return JSONResponse(content=status_obj.dict(), status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return status_obj

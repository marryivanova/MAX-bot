from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ServiceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"


class ServiceHealthResponse(BaseModel):
    status: ServiceStatus
    service: str = "MAX Bot Webhook"
    bot_ready: bool
    dispatcher_ready: bool
    environment: str
    uptime: Optional[float] = None
    version: Optional[str] = None
    timestamp: Optional[str] = None

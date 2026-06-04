from enum import Enum

from settings import settings


class TypeEnvironment(Enum):
    prod = "prod"
    local = "local"


def is_local_env() -> bool:
    return settings.environment == TypeEnvironment.local.value


def is_prod_env() -> bool:
    return settings.environment == TypeEnvironment.prod.value

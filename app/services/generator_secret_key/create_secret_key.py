import json
import secrets
from pathlib import Path

from loguru import logger

SECRET_FILE = Path("secret_key.json")


def get_or_create_secret_key() -> str:
    if SECRET_FILE.exists():
        try:
            with open(SECRET_FILE, "r") as f:
                data = json.load(f)
                return data["secret_key"]
        except:
            pass

    new_key = secrets.token_urlsafe(32)

    with open(SECRET_FILE, "w") as f:
        json.dump({"secret_key": new_key}, f)

    logger.debug(f"Новый SECRET_KEY сгенирирован и добавлен: {SECRET_FILE}")
    return new_key


secret_key = get_or_create_secret_key()

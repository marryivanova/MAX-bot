import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer

from app.services.generator_secret_key.create_secret_key import secret_key
from app.services.model.auth import LoginRequest, ResponseGetToken
from settings import settings

router = APIRouter(prefix="/api", tags=["Auth"])

swagger_security = HTTPBasic()

bearer_security = HTTPBearer()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(swagger_security)):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = settings.swagger_login.encode("utf8")
    is_correct_username = secrets.compare_digest(current_username_bytes, correct_username_bytes)

    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = settings.swagger_token.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, correct_password_bytes)

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=int(settings.access_token_expire_minutes))

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[settings.algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(request: LoginRequest):
    """
    Эндпоинт для входа в систему.

    Проверяет учетные данные и в случае успеха возвращает JWT (access token).

    **Параметры запроса (тело JSON):**
    - `username` (str): Обязательное. Имя пользователя.
    - `password` (str): Обязательное. Пароль пользователя.

    **Ответ в случае успеха (200 OK):**
    - `access_token` (str): JWT токен для авторизации.
    - `token_type` (str): Тип токена, всегда "bearer".
    - `expires_in` (int): Время жизни токена в секундах.

    **Ошибки:**
    - `401 Unauthorized`: Возвращается при неверном имени пользователя или пароле.

    **Пример запроса:**
    ```json
    {
        "username": "admin",
        "password": "secret_password"
    }
    ```

    **Пример ответа:**
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "expires_in": 1800
    }
    ```
    """
    if request.username != settings.admin_username and request.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid credentials: {settings.admin_username} and {settings.admin_password}",
        )

    access_token_expires = timedelta(minutes=int(settings.access_token_expire_minutes))
    access_token = create_access_token(data={"sub": request.username}, expires_delta=access_token_expires)

    return ResponseGetToken(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )

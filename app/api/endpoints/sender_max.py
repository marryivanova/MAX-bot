import asyncio
from typing import Dict, List, Optional

import aiohttp
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from max_sdk.core.helper.getted_updates import process_update_webhook
from max_sdk.dispatcher import Bot, Router
from pydantic import BaseModel, Field
from sentry_sdk import init as sentry_init
from starlette.requests import Request as StarletteRequest

from app.api.endpoints.helper import SendMessageResponse
from app.api.endpoints.helper.dependency import get_current_user
from app.api.endpoints.helper.helper_func import VacationTeacherRequest
from app.bitrix.core.bitrix_send_alert import send_to_chat_error, send_to_chat_service_manager
from app.services.model import MaxUrl
from app.services.vacation_teacher import VacationTeacherService

router = APIRouter(prefix="/api", tags=["Sender Message"])


class ButtonModel(BaseModel):
    type: str
    text: str
    url: Optional[str] = None
    payload: Optional[str] = None


class SendMassMailingRequest(BaseModel):
    chat_id: str
    text: str
    format_type: str = "html"
    buttons: Optional[List[List[ButtonModel]]] = None
    auth_token: str


async def send_to_max_bot_async(
    chat_id: str, text: str, format_type: str = "html", buttons: Optional[List[List[Dict]]] = None, auth_token=None
) -> dict:

    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    data = dict(chat_id=chat_id, text=text, format_type=format_type, disable_link_preview=True, notify=True)
    if buttons:
        data["buttons"] = buttons

    logger.debug(f"Данные для передачи: {data}")

    url = "https://maxbot.hwschool.pro/v1/api/send-message"

    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=30)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=data, headers=headers) as response:
                response_text = await response.text()
                logger.debug(f"Статус ответа: {response.status}")
                logger.debug(f"Ответ: {response_text}")

                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Ошибка {response.status}: {response_text}")

    except asyncio.TimeoutError:
        logger.error("Таймаут асинхронного запроса")
        raise TimeoutError("Превышено время ожидания")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        raise


@router.post("/mass-mailing-lists", response_model=SendMessageResponse, status_code=status.HTTP_200_OK)
async def send_mass_mailing(
    request: SendMassMailingRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Отправить сообщение с кнопками и HTML версткой через MAX бота.
    (Для массовых рассылок)

    ## Описание
    Этот эндпоинт предназначен для массовых рассылок сообщений с поддержкой HTML форматирования и интерактивных кнопок.
    В отличие от стандартного /send-message, этот эндпоинт не требует авторизации через Bitrix24 и предназначен
    для быстрой отправки сообщений по прямому chat_id.

    ## Параметры запроса (тело JSON)
    - **chat_id** (обязательный): Прямой идентификатор Telegram чата для отправки сообщения
    - **text** (обязательный): Текст сообщения для отправки с поддержкой HTML тегов
    - **format_type** (опциональный): Режим форматирования текста. Доступные значения: "html". По умолчанию "html"
    - **buttons** (опциональный): Массив кнопок для интерактивной клавиатуры. Поддерживаются типы:
        - `link` - кнопка-ссылка, открывает URL в новой вкладке
        - `callback` - callback-кнопка, отправляет команду боту

    ### Формат кнопок:
    ```json
    "buttons": [[{"type": "link", "text": "Записать ребенка на первый урок", "url": "https://link.hwschool.pro/DgKgLg"}]]
    ```

    ## Поддерживаемые HTML теги
        <b> - жирный текст
        <i> - курсив
        <u> - подчеркнутый текст
        <s> - зачеркнутый текст
        <a href="url"> - ссылка
        <code> - моноширинный текст
        <pre> - блок кода
    """
    try:
        logger.info(f"Запрос от пользователя {current_user.get('user_id')}")
        logger.info(f"Отправка в чат: {request.chat_id}")

        buttons_dict = None
        if request.buttons:
            buttons_dict = [[button.dict() for button in row] for row in request.buttons]

        await send_to_max_bot_async(
            chat_id=request.chat_id,
            text=request.text,
            format_type=request.format_type,
            buttons=buttons_dict,
            auth_token=request.auth_token,
        )

        logger.info("Сообщение успешно отправлено!")
        return SendMessageResponse(success=True, error=None)

    except TimeoutError as e:
        logger.error(f"Таймаут: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Превышено время ожидания ответа от MAX бота"
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Сервис MAX бота временно недоступен"
        )
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get("/bx-vacation-teacher", response_model=SendMessageResponse, status_code=status.HTTP_200_OK)
async def send_message_vacation_get(
    event: str,
    teacher_id: int,
    date_start_str: str,
    date_end_str: str,
    vacation_id: Optional[int | str] = None,
):
    """
    GET версия для интеграции с Bitrix

     ### Общие параметры для всех событий:
    - **event** (обязательный): Тип события. Доступные значения:
        - `delete_vacation` - удаление отпуска
        - `check_teacher` - проверка учителя
        - `find_bad_lessons` - поиск вводных и групповых уроков
        - `send_message_and_cancel_lessons` - отправка сообщений и отмена уроков
        - `accept_curator` - подтверждение куратора

    - **teacher_id** (обязательный): ID преподавателя в Битрикс (integer)

    - **date_start_str** (обязательный): Дата начала отпуска. Формат: `DD.MM.YYYY`
        - Пример: `"10.12.2024"`

    - **date_end_str** (обязательный): Дата окончания отпуска. Формат: `DD.MM.YYYY`
        - Пример: `"25.12.2024"`

    - **vacation_id** (опциональный): ID отпуска в системе. Обязателен для события `delete_vacation` (integer или string)
        - Пример: `67890`

    {{Константы глобальные: max_ip}}/bx-vacation-teacher/?event=send_message_and_cancel_lessons&teacher_id={{Сотрудник > int}}&date_start_str={{Начало отпуска}}&date_end_str={{Окончание отпуска}}&vacation_id={{[IT] vacation_id}}
    """
    try:
        vacation_request = VacationTeacherRequest(
            event=event,
            teacher_id=teacher_id,
            date_start_str=date_start_str,
            date_end_str=date_end_str,
            vacation_id=vacation_id,
        )

        service = VacationTeacherService()
        request_data = vacation_request.dict(exclude_none=True)
        logger.info(f"GET bx-vacation-teacher || Получены данные: {request_data}")
        mock_request = StarletteRequest(scope={"type": "http", "headers": []})
        result_message, status_code = await service.bitrix_vacation_teacher(mock_request, **request_data)

        if status_code == 200:
            return SendMessageResponse(
                success=True, error=None, message=result_message if result_message else "Операция выполнена успешно"
            )
        else:
            return SendMessageResponse(success=False, error=result_message, message=None)

    except ValueError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неверный формат данных: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.post("/vacation-teacher", response_model=SendMessageResponse, status_code=status.HTTP_200_OK)
async def send_message_vacation(
    vacation_request: VacationTeacherRequest,
    request: Request,
):
    """
    Обработка запросов по отпуску преподавателей из Битрикс

    ## Описание
    Этот эндпоинт предназначен для обработки различных событий, связанных с отпусками преподавателей.
    Поддерживает удаление отпусков, проверку учителей, поиск проблемных уроков, отправку уведомлений и подтверждение отпусков.

    ## Параметры запроса (тело JSON или form-data)

    ### Общие параметры для всех событий:
    - **event** (обязательный): Тип события. Доступные значения:
        - `delete_vacation` - удаление отпуска
        - `check_teacher` - проверка учителя
        - `find_bad_lessons` - поиск вводных и групповых уроков
        - `send_message_and_cancel_lessons` - отправка сообщений и отмена уроков
        - `accept_curator` - подтверждение куратора

    - **teacher_id** (обязательный): ID преподавателя в Битрикс (integer)

    - **date_start_str** (обязательный): Дата начала отпуска. Формат: `DD.MM.YYYY`
        - Пример: `"10.12.2024"`

    - **date_end_str** (обязательный): Дата окончания отпуска. Формат: `DD.MM.YYYY`
        - Пример: `"25.12.2024"`

    - **vacation_id** (опциональный): ID отпуска в системе. Обязателен для события `delete_vacation` (integer или string)
        - Пример: `67890`

    ## Примеры запросов

    ### 1. Отпуск (vacation)
    ```json
    {
        "event": "vacation",
        "teacher_id": 12345,
        "date_start_str": "10.12.2024",
        "date_end_str": "25.12.2024",
        "vacation_id": 1
    }
     ```
    """
    service = VacationTeacherService()

    try:
        request_data = vacation_request.dict(exclude_none=True)

        query_params = dict(request.query_params)
        if query_params:
            request_data.update(query_params)

        logger.info(f"POST vacation-teacher || Получены данные: {request_data}")
        result_message, status_code = await service.bitrix_vacation_teacher(request, **request_data)

        if status_code == 200:
            return SendMessageResponse(
                success=True, error=None, message=result_message if result_message else "Операция выполнена успешно"
            )
        else:
            return SendMessageResponse(success=False, error=result_message, message=None)

    except ValueError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неверный формат данных: {str(e)}")
    except TimeoutError as e:
        logger.error(f"Таймаут: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Превышено время ожидания ответа от сервера"
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Сервис временно недоступен")
    except Exception as e:
        additional_info = dict(
            lead_id=vacation_request.lead_id if hasattr(vacation_request, "lead_id") else None,
            contact_id=vacation_request.contact_id if hasattr(vacation_request, "contact_id") else None,
            chat_id=vacation_request.chat_id if hasattr(vacation_request, "chat_id") else None,
            text_preview=(
                vacation_request.text[:400] + "..."
                if hasattr(vacation_request, "text") and len(vacation_request.text) > 100
                else None
            ),
        )
        if additional_info.get("lead_id"):
            additional_info["lead_url"] = f"{MaxUrl.url_lead.value}{additional_info['lead_id']}/"
        if additional_info.get("contact_id"):
            additional_info["contact_url"] = f"{MaxUrl.url_contact.value}{additional_info['contact_id']}/"

        error_msg = f"\n Ошибка при отправке сообщения: {str(e)}"
        filtered_info = {k: v for k, v in additional_info.items() if v is not None}

        send_to_chat_service_manager(
            chat_id=additional_info.get("chat_id"),
            message=error_msg,
            additional_info=filtered_info,
        )
        send_to_chat_error(
            message=error_msg,
            error=str(e),
            additional_info=additional_info,
        )
        logger.error(f"Ошибка: {str(e)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

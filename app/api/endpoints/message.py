from typing import Optional, Union

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from max_sdk.core.helper.getted_updates import process_update_webhook
from max_sdk.dispatcher import Bot, Router
from pydantic import BaseModel, Field
from sentry_sdk import init as sentry_init

from app.api.endpoints.helper import (
    SendMessageRequest,
    SendMessageResponse,
    _add_bitrix_comment,
    _prepare_send_params,
    _resolve_chat_id,
    _send_message_via_bot,
    _validate_and_process_text,
    get_bot_dependency,
)
from app.api.endpoints.helper.dependency import get_current_user
from app.api.endpoints.helper.helper_sid import process_pattern_and_send
from app.bitrix.core.bitrix_add_comment import _add_error_comment_to_bitrix, _add_successful_comment_to_bitrix
from app.bitrix.core.bitrix_send_alert import send_to_chat_error, send_to_chat_service_manager
from app.custom_exception import handle_max_api_error
from app.services.event_manager.bot_manager import get_bot
from app.services.model.all_url import MaxUrl

router = APIRouter(prefix="/api", tags=["Message"])


@router.post("/send-message", response_model=SendMessageResponse, status_code=status.HTTP_200_OK)
async def send_message(
    request: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
    bot: Bot = Depends(get_bot_dependency),
):
    """
    Отправить одно сообщение через MAX бота.

    ## Описание
    Этот эндпоинт позволяет отправить текстовое сообщение через MAX бота.
    Поддерживает два способа идентификации получателя:
    1. Прямое указание `chat_id` - для отправки в конкретный чат
    2. Указание `lead_id` - для автоматического определения чата из данных лида Bitrix24
    3. Указание `contact_id` - для автоматического определения чата из данных контакта Bitrix24

    ## Параметры запроса (тело JSON)
    - **text** (обязательный): Текст сообщения для отправки
    - **chat_id** (опциональный): Прямой идентификатор Telegram чата
    - **lead_id** (опциональный): ID лида в Bitrix24 для автоматического определения чата
    - **twilio_variables** (опциональный): Переменные для подстановки в шаблон сообщения -> {"name": "Иван"} = (text= Привет, {{ name }}.)
    - **contact_id** (опциональный): ID контакта в Bitrix24 для автоматического определения чата
    - **template_variables** (опциональный): Переменные для подстановки в шаблон сообщения
    - **format_type** (опциональный): Режим форматирования текста. Доступные значения: "html". По умолчанию "html"
    - **buttons** (опциональный): Массив кнопок для интерактивной клавиатуры. Поддерживаются типы:
        - `link` - кнопка-ссылка, открывает URL в новой вкладке
        - `callback` - callback-кнопка, отправляет команду боту

    ### Формат кнопок:
    ```json
    {"buttons": [[{"type": "link","text": "Текст кнопки", "url": "https://example.com"}]]}
    ```

     **Важно:** Должен быть указан либо `chat_id`, либо `lead_id`, либо `contact_id`

    ## Ответ
    - **success** (boolean): Статус выполнения операции
    - **error** (string или null): Сообщение об ошибке (если есть)

    ## Коды состояния HTTP
    - **200 OK**: Сообщение успешно отправлено
    - **400 Bad Request**: Неверные параметры запроса
    - **403 Forbidden**: Недостаточно прав для отправки
    - **404 Not Found**: Лид не найден
    - **422 Unprocessable Entity**: Ошибка валидации данных
    - **500 Internal Server Error**: Внутренняя ошибка сервера
    - **503 Service Unavailable**: Сервис временно недоступен
    - **504 Gateway Timeout**: Превышено время ожидания

    ## Логика работы
    1. Определение получателя (по chat_id или из данных лида)
    2. Валидация и обработка текста сообщения
    3. Подготовка параметров для отправки
    4. Отправка сообщения через MAX бота
    5. Добавление комментария в Bitrix24 (если указан lead_id)
    6. Возврат результата операции

    ## Примечания
    - Для работы с `lead_id` необходимо, чтобы в лиде была открытая линия (Open Channel) с пользователем
    - Сообщение не может быть пустым
    - При успешной отправке в Bitrix24 добавляется комментарий с информацией о сообщении
    - Метод автоматически обрабатывает подстановку переменных из `var`
    """
    try:
        logger.info(f"Запрос от пользователя {current_user.get('user_id')}")

        chat_id, user_id = await _resolve_chat_id(request)

        final_text = _validate_and_process_text(request.text)

        params = _prepare_send_params(request, chat_id, user_id, final_text)

        await _send_message_via_bot(bot, params)

        logger.info("Сообщение успешно отправлено")
        return SendMessageResponse(success=True, error=None)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Ошибка валидации данных: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка валидации данных: {str(e)}",
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен. Попробуйте позже.",
        )
    except TimeoutError as e:
        logger.error(f"Таймаут при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от сервиса отправки",
        )
    except PermissionError as e:
        logger.error(f"Ошибка прав доступа: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для отправки сообщения",
        )
    except Exception as e:
        additional_info = dict(
            user_id=current_user.get("user_id"),
            lead_id=request.lead_id,
            contact_id=request.contact_id,
            chat_id=request.chat_id,
            text_preview=request.text[:400] + "..." if len(request.text) > 100 else request.text,
        )
        if request.lead_id:
            additional_info["lead_url"] = f"{MaxUrl.url_lead.value}{request.lead_id}/"
        if request.contact_id:
            additional_info["contact_url"] = f"{MaxUrl.url_contact.value}{request.contact_id}/"

        error_msg = f"\n Ошибка при отправке сообщения: {str(e)}"
        filtered_info = {k: v for k, v in additional_info.items() if v is not None}

        send_to_chat_service_manager(
            chat_id=request.chat_id,
            message=error_msg,
            additional_info=filtered_info,
        )
        send_to_chat_error(
            message=error_msg,
            error=str(e),
            additional_info=additional_info,
        )
        logger.debug(f"📤 additional_info для ошибки: {additional_info}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.post(
    "/send-message-unauthorized",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def send_message_unauthorized(request: SendMessageRequest, bot: Bot = Depends(get_bot_dependency)):
    """
    Отправить одно сообщение через MAX бота - скрыт без авторизации
    Метод используются для интеграции с платформой!!
    """
    try:
        chat_id, user_id = await _resolve_chat_id(request)

        final_text = _validate_and_process_text(request.text)

        params = _prepare_send_params(request, chat_id, user_id, final_text)

        await _send_message_via_bot(bot, params)

        logger.info("Сообщение успешно отправлено")
        return SendMessageResponse(success=True, error=None)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Ошибка валидации данных: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка валидации данных: {str(e)}",
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен. Попробуйте позже.",
        )
    except TimeoutError as e:
        logger.error(f"Таймаут при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от сервиса отправки",
        )
    except PermissionError as e:
        logger.error(f"Ошибка прав доступа: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для отправки сообщения",
        )
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке сообщения: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get(
    "/send-message-bx",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message_bx(
    text: str = Query(..., description="Текст сообщения"),
    lead_id: Optional[Union[int, str]] = Query(None, description="ID сделки в Bitrix24"),
    contact_id: Optional[Union[int, str]] = Query(None, description="ID контакта в Bitrix24"),
    chat_id: Optional[Union[int, str]] = Query(None, description="ID чата"),
    twilio_variables: Optional[str] = Query(None, description="Переменные в формате JSON: {'name':'value'}"),
    parse_mode: Optional[str] = Query(None, description="Режим парсинга (Markdown, HTML)"),
    disable_web_page_preview: Optional[bool] = Query(None, description="Отключить превью ссылок"),
    bot: Bot = Depends(get_bot_dependency),
):
    """
    Метод для Битрикса: Отправить одно сообщение через MAX бота.
    (Битрикс POST не поддерживает, только GET)

    ## Описание
    Этот эндпоинт позволяет отправить текстовое сообщение через MAX бота.
    Поддерживает два способа идентификации получателя:
    1. Прямое указание `chat_id` - для отправки в конкретный чат
    2. Указание `lead_id` - для автоматического определения чата из данных лида Bitrix24
    3. Указание `contact_id` - для автоматического определения чата из данных контакта Bitrix24

    ## Параметры запроса (Передаем в query peram)
    - **text** (обязательный): Текст сообщения для отправки
    - **chat_id** (опциональный): Прямой идентификатор Telegram чата
    - **lead_id** (опциональный): ID лида в Bitrix24 для автоматического определения чата
    - **contact_id** (опциональный): ID контакта в Bitrix24 для автоматического определения чата
    - **twilio_variables** (опциональный): Переменные для подстановки в шаблон сообщения -> {"name": "Иван"} = (text= Привет, {{ name }}.)

    **Важно:** Должен быть указан либо `chat_id`, либо `lead_id`, либо `contact_id`

    ## Ответ
    - **success** (boolean): Статус выполнения операции
    - **error** (string или null): Сообщение об ошибке (если есть)

    ## Коды состояния HTTP
    - **200 OK**: Сообщение успешно отправлено
    - **400 Bad Request**: Неверные параметры запроса
    - **403 Forbidden**: Недостаточно прав для отправки
    - **404 Not Found**: Лид не найден
    - **422 Unprocessable Entity**: Ошибка валидации данных
    - **500 Internal Server Error**: Внутренняя ошибка сервера
    - **503 Service Unavailable**: Сервис временно недоступен
    - **504 Gateway Timeout**: Превышено время ожидания

    ## Логика работы
    1. Определение получателя (по chat_id или из данных лида)
    2. Валидация и обработка текста сообщения
    3. Подготовка параметров для отправки
    4. Отправка сообщения через MAX бота
    5. Добавление комментария в Bitrix24 (если указан lead_id)
    6. Возврат результата операции

    ## Примечания
    - Для работы с `lead_id` необходимо, чтобы в лиде была открытая линия (Open Channel) с пользователем
    - Сообщение не может быть пустым
    - При успешной отправке в Bitrix24 добавляется комментарий с информацией о сообщении
    - Метод автоматически обрабатывает подстановку переменных из `twilio_variables`
    """
    try:
        request = SendMessageRequest(
            text=text,
            lead_id=lead_id,
            chat_id=chat_id,
            contact_id=contact_id,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            twilio_variables=twilio_variables,
        )

        chat_id_resolved, user_id = await _resolve_chat_id(request)

        final_text = _validate_and_process_text(request.text)

        params = _prepare_send_params(request, chat_id_resolved, user_id, final_text)

        await _send_message_via_bot(bot, params)

        await _add_bitrix_comment(
            request,
            chat_id_resolved,
            user_id,
            final_text,
            lead_id=request.lead_id,
            contact_id=request.contact_id,
        )

        logger.info("Сообщение успешно отправлено")
        return SendMessageResponse(success=True, error=None)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Ошибка валидации данных: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка валидации данных: {str(e)}",
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен. Попробуйте позже.",
        )
    except TimeoutError as e:
        logger.error(f"Таймаут при отправке сообщения: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от сервиса отправки",
        )
    except PermissionError as e:
        logger.error(f"Ошибка прав доступа: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для отправки сообщения",
        )
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке сообщения: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}",
        )


@router.get(
    "/send-id-sid-message-bx",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message_bx(
    sid_id: str = Query(..., description="Id sid"),
    lead_id: Optional[Union[int, str]] = Query(None, description="ID сделки в Bitrix24"),
    contact_id: Optional[Union[int, str]] = Query(None, description="ID контакта в Bitrix24"),
    chat_id: Optional[Union[int, str]] = Query(None, description="ID чата"),
    twilio_variables: Optional[str] = Query(None, description="Переменные в формате var;;var1"),
    parse_mode: Optional[str] = Query(None, description="Режим парсинга (Markdown, HTML)"),
    disable_web_page_preview: Optional[bool] = Query(None, description="Отключить превью ссылок"),
):
    """
    Метод для Битрикса: Отправить одно сообщение через MAX бота.
    (Битрикс POST не поддерживает, только GET)

    Метод берет перданные в нем SID ID и по нему подставляет сообщенпие.

    ## Описание
    Этот эндпоинт позволяет отправить текстовое сообщение через MAX бота.
    Поддерживает два способа идентификации получателя:
    1. Прямое указание `chat_id` - для отправки в конкретный чат
    2. Указание `lead_id` - для автоматического определения чата из данных лида Bitrix24
    3. Указание `contact_id` - для автоматического определения чата из данных контакта Bitrix24

    ## Параметры запроса (Передаем в query peram)
    - **sid_id** (обязательный): Id sid берем из https://docs.google.com/spreadsheets/d/1MD7v9iJ0oLLhOm8g1Q545HNYIj-In0SYfOTsS7rF5FE/edit?pli=1&gid=587246353#gid=587246353"
    - **chat_id** (опциональный): Прямой идентификатор Telegram чата
    - **lead_id** (опциональный): ID лида в Bitrix24 для автоматического определения чата
    - **contact_id** (опциональный): ID контакта в Bitrix24 для автоматического определения чата
    - **twilio_variables** (опциональный): Переменные для подстановки в шаблон сообщения -> var;;var1;;var2

    **Пример** "Напоминаем, что {{1}} по Вашему времени запланировано занятие. Ссылка для оплаты - {{2}}"
    Значит -> `Europe;;https://lol-kek`

    **Важно:** Должен быть указан либо `chat_id`, либо `lead_id`, либо `contact_id`

    ## Ответ
    - **success** (boolean): Статус выполнения операции
    - **error** (string или null): Сообщение об ошибке (если есть)

    ## Коды состояния HTTP
    - **200 OK**: Сообщение успешно отправлено
    - **400 Bad Request**: Неверные параметры запроса
    - **403 Forbidden**: Недостаточно прав для отправки
    - **404 Not Found**: Лид не найден
    - **422 Unprocessable Entity**: Ошибка валидации данных
    - **500 Internal Server Error**: Внутренняя ошибка сервера
    - **503 Service Unavailable**: Сервис временно недоступен
    - **504 Gateway Timeout**: Превышено время ожидания

    ## Логика работы
    1. Определение получателя (по chat_id или из данных лида)
    2. Валидация и обработка текста сообщения
    3. Подготовка параметров для отправки
    4. Отправка сообщения через MAX бота
    5. Добавление комментария в Bitrix24 (если указан lead_id)
    6. Возврат результата операции

    ## Примечания
    - Для работы с `lead_id` необходимо, чтобы в лиде была открытая линия (Open Channel) с пользователем
    - Сообщение не может быть пустым
    - При успешной отправке в Bitrix24 добавляется комментарий с информацией о сообщении
    - Метод автоматически обрабатывает подстановку переменных из `twilio_variables`
    """
    try:
        request = SendMessageRequest(
            sid_id=sid_id,
            lead_id=lead_id,
            chat_id=chat_id,
            contact_id=contact_id,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            twilio_variables=twilio_variables,
        )
        chat_id, user_id = await _resolve_chat_id(request)

        final_message = await process_pattern_and_send(
            pattern_id=sid_id,
            lead_id=lead_id,
            contact_id=contact_id,
            chat_id=chat_id,
            var_params=twilio_variables,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            return_message=True,
        )

        logger.info("Сообщение успешно отправлено")
        await _add_successful_comment_to_bitrix(
            message=sid_id,
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
            message_for_comment=final_message,
        )
        return SendMessageResponse(success=True, error=None)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Ошибка валидации данных: {str(e)}")
        await _add_error_comment_to_bitrix(
            error_message=f"Ошибка валидации данных: {str(e)}",
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка валидации данных: {str(e)}",
        )
    except ConnectionError as e:
        logger.error(f"Ошибка соединения при отправке сообщения: {str(e)}")
        await _add_error_comment_to_bitrix(
            error_message=f"Ошибка соединения: {str(e)}",
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис временно недоступен. Попробуйте позже.",
        )
    except TimeoutError as e:
        logger.error(f"Таймаут при отправке сообщения: {str(e)}")
        await _add_error_comment_to_bitrix(
            error_message=f"Таймаут при отправке сообщения: {str(e)}",
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от сервиса отправки",
        )
    except PermissionError as e:
        logger.error(f"Ошибка прав доступа: {str(e)}")
        await _add_error_comment_to_bitrix(
            error_message=f"Ошибка прав доступа: {str(e)}",
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для отправки сообщения",
        )
    except Exception as e:
        error_str = str(e)

        http_status, error_detail = handle_max_api_error(e, error_str)
        if http_status and error_detail:
            logger.error(f"Специфичная ошибка MAX API: {error_detail}")
            await _add_error_comment_to_bitrix(
                error_message=error_detail,
                lead_id=lead_id,
                contact_id=contact_id,
                sid_id=sid_id,
                twilio_variables=twilio_variables,
            )
            raise HTTPException(status_code=http_status, detail=error_detail)

        await _add_error_comment_to_bitrix(
            error_message=f"Внутренняя ошибка сервера: {error_str}",
            lead_id=lead_id,
            contact_id=contact_id,
            sid_id=sid_id,
            twilio_variables=twilio_variables,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {error_str}",
        )


@router.get("/bot-info")
async def get_bot_info(bot: Bot = Depends(get_bot)):
    try:
        me = await bot.get_me()
        return {"success": True, "data": me}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

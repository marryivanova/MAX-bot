import json
from typing import Any, Dict, Optional, Union

import httpx
from fastapi import HTTPException, Query, status
from loguru import logger

from app.api.endpoints.helper import _validate_and_process_text
from app.custom_exception import MaxBotHTTPError
from db.crud_db.get_twilio_template import get_text_by_sid


async def send_message_to_maxbot(
    text: str,
    lead_id: Optional[Union[int, str]] = None,
    contact_id: Optional[Union[int, str]] = None,
    chat_id: Optional[Union[int, str]] = None,
    twilio_variables: Optional[str] = None,
    parse_mode: Optional[str] = None,
    disable_web_page_preview: Optional[bool] = None,
    additional_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = "https://maxbot.hwschool.pro/v1/api/send-message-unauthorized"

    payload = {"text": text}

    if lead_id:
        payload["lead_id"] = lead_id
    elif contact_id:
        payload["contact_id"] = contact_id
    elif chat_id:
        payload["chat_id"] = chat_id

    if twilio_variables:
        if isinstance(twilio_variables, str):
            try:
                payload["twilio_variables"] = json.loads(twilio_variables)
            except json.JSONDecodeError:
                logger.warning(f"Не удалось распарсить var как JSON: {twilio_variables}")
                payload["twilio_variables"] = twilio_variables
        else:
            payload["twilio_variables"] = twilio_variables

    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview is not None:
        payload["disable_web_page_preview"] = disable_web_page_preview
    if additional_params:
        payload.update(additional_params)

    try:
        timeout = httpx.Timeout(30.0, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)

            try:
                response_body = response.json()
            except:
                response_body = response.text

            if response.status_code >= 400:
                logger.error(f"HTTP ошибка от MaxBot: {response.status_code} - {response_body}")
                raise MaxBotHTTPError(
                    message=f"MaxBot вернул ошибку {response.status_code}",
                    status_code=response.status_code,
                    response_body=response_body,
                )

            logger.info(f"MaxBot ответил: {response_body}")
            return response_body

    except httpx.TimeoutException as e:
        logger.error(f"Таймаут при отправке в MaxBot: {str(e)}")
        raise MaxBotHTTPError(
            message="Таймаут подключения к MaxBot",
            status_code=504,
            response_body={"error": "timeout", "detail": str(e)},
        )
    except httpx.HTTPError as e:
        logger.error(f"Ошибка подключения к MaxBot: Пользователь закрыл чат или заблокировал: {str(e)}")
        raise MaxBotHTTPError(
            message="Ошибка подключения к MaxBot",
            status_code=503,
            response_body={"error": "connection_error", "detail": str(e)},
        )
    except MaxBotHTTPError:
        raise
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке в MaxBot: {str(e)}")
        raise MaxBotHTTPError(
            message="Неизвестная ошибка MaxBot",
            status_code=500,
            response_body={"error": "unknown", "detail": str(e)},
        )


async def process_pattern_and_send(
    pattern_id: str,
    lead_id: Optional[Union[int, str]] = None,
    contact_id: Optional[Union[int, str]] = None,
    chat_id: Optional[Union[int, str]] = None,
    var_params: Optional[str] = None,
    parse_mode: Optional[str] = None,
    disable_web_page_preview: Optional[bool] = None,
    return_message: bool = False,
):
    """
    Обработка шаблона и отправка сообщения через MaxBot

    Args:
        pattern_id: ID шаблона (SID в БД)
        lead_id: ID лида
        contact_id: ID контакта
        chat_id: ID чата
        var_params: Параметры для замены в шаблоне (разделитель ";;")
        parse_mode: Режим парсинга сообщения
        disable_web_page_preview: Отключать превью ссылок
        return_message: Вернуть текст сообщения вместо результата отправки
    """
    if not any([lead_id, contact_id, chat_id]):
        raise ValueError("Должен быть указан хотя бы один из: lead_id, contact_id или chat_id")

    processed_var_params = {}
    if var_params:
        if isinstance(var_params, str):
            values = [v.strip() for v in var_params.split(";;")]
            for i, value in enumerate(values, 1):
                if value:
                    processed_var_params[str(i)] = value

            if processed_var_params:
                logger.debug(f"Обработано {len(processed_var_params)} параметров: {processed_var_params}")

    try:
        raw_message = await get_text_by_sid(sid_value=pattern_id)

        if not raw_message:
            raise ValueError(f"Шаблон с SID '{pattern_id}' не найден в базе данных")

        logger.info(f"Получен шаблон {pattern_id} из базы данных")

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона {pattern_id} из БД: {str(e)}")
        raise ValueError(f"Не удалось получить шаблон {pattern_id} из БД: {str(e)}")

    processed_message = raw_message
    if processed_var_params:
        for key, value in processed_var_params.items():
            placeholders = [
                f"{{{{{key}}}}}",  # {{1}}
                f"{{{key}}}",  # {1}
                f"{{{{ {key} }}}}",  # {{ 1 }}
                f"{{ {key} }}",  # { 1 }
            ]

            for placeholder in placeholders:
                if placeholder in processed_message:
                    processed_message = processed_message.replace(placeholder, str(value))
                    logger.debug(f"Заменен {placeholder} на '{value}'")
                    break

    validated_text = _validate_and_process_text(processed_message)
    logger.info(f"Валидированный текст ({len(validated_text)} символов): {validated_text[:200]}...")

    try:
        result = await send_message_to_maxbot(
            text=validated_text,
            lead_id=lead_id,
            contact_id=contact_id,
            chat_id=chat_id,
            twilio_variables=processed_var_params,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )

        logger.info(f"Сообщение успешно отправлено, результат: {result}")

        if return_message:
            return validated_text

        return result

    except MaxBotHTTPError as e:
        logger.error(f"Ошибка от MaxBot: статус {e.status_code}, тело: {e.response_body}")
        error_message = f"MaxBot error {e.status_code}: {e.response_body}"
        raise Exception(error_message)

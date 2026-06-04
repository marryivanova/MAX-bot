import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field, validator

from app.bitrix.core.bitrix_add_comment import BitrixAddComment
from db.core import db_manager
from db.models.max_user import MaxUser
from db.models.twilio import TwilioTemplate


class VacationTeacherRequest(BaseModel):
    event: str = Field(..., description="Тип события")
    teacher_id: int = Field(..., description="ID преподавателя в Битрикс")
    date_start_str: str = Field(..., description="Дата начала отпуска в формате DD.MM.YYYY")
    date_end_str: str = Field(..., description="Дата окончания отпуска в формате DD.MM.YYYY")
    vacation_id: Optional[int | str] = Field(None, description="ID отпуска")
    lead_id: Optional[int] = Field(None, description="ID лида (опционально)")
    contact_id: Optional[int] = Field(None, description="ID контакта (опционально)")
    chat_id: Optional[str] = Field(None, description="ID чата (опционально)")

    @validator("date_start_str", "date_end_str")
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%d.%m.%Y")
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected format: DD.MM.YYYY")


class SendMessageRequest(BaseModel):
    chat_id: Optional[int | str] = None
    lead_id: Optional[int | str] = None
    contact_id: Optional[int | str] = None
    sid: Optional[int | str] = None
    text: Optional[int | str] = None
    twilio_variables: Optional[Dict[str, str]] | str = Field(
        default_factory=dict, description="Переменные для замены в шаблоне сообщения"
    )
    parse_mode: Optional[str] = None
    buttons: Optional[List[List[dict]]] = None
    format_type: Optional[str] = None
    disable_web_page_preview: Optional[bool] = None


class SendMessageResponse(BaseModel):
    success: bool = Field(..., description="Успешность отправки")
    error: Optional[str] = Field(None, description="Текст ошибки, если есть")


def get_vars(request, final_text):
    """
    Заменяет переменные в тексте.

    Args:
        request: SendMessageRequest или dict с полем 'twilio_variables'
        final_text: Исходный текст

    Returns:
        Текст с замененными переменными
    """
    logger.info(
        f"Начало get_vars Тип request.twilio_variables: {type(request.twilio_variables)}, значение: {request.twilio_variables}"
    )

    var_dict = {}

    if isinstance(request.twilio_variables, str):
        try:
            var_dict = json.loads(request.twilio_variables)
            logger.info(f"Распарсены переменные из строки: {var_dict}")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Ошибка парсинга JSON из строки '{request.twilio_variables}': {e}")
            return final_text

    elif request.twilio_variables is not None:
        logger.error(f"Неизвестный тип request.var: {type(request.twilio_variables)}")
        return final_text

    if not var_dict:
        logger.info("Нет переменных для замены")
        return final_text

    logger.info(f"Заменяем переменные в тексте: {var_dict}")
    logger.info(f"Исходный текст: '{final_text}'")

    for var_name, var_value in var_dict.items():
        if not isinstance(var_value, str):
            var_value = str(var_value)

        placeholders = [
            f"{{{{ {var_name} }}}}",
            f"{{{{{var_name}}}}}",
            f"{{{var_name} }}}}",
        ]

        for placeholder in placeholders:
            if placeholder in final_text:
                logger.info(f"Замена '{placeholder}' на '{var_value}'")
                final_text = final_text.replace(placeholder, var_value)

    logger.info(f"Текст после замены: '{final_text}'")
    return final_text


# ==================== Функции для получения шаблона из БД ====================


def get_template_from_db(sid_id: str, db) -> Optional[TwilioTemplate]:
    """
    Получить шаблон из БД по sid
    """
    try:
        template = db.query(TwilioTemplate).filter(TwilioTemplate.sid == sid_id).first()

        if not template:
            logger.error(f"Шаблон с sid={sid_id} не найден в БД")
            return None

        logger.info(f"Найден шаблон: sid={template.sid}, am={template.am}, текст={template.текст[:100]}...")
        return template

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона из БД: {e}")
        return None


async def _resolve_chat_id(request) -> Tuple[str, Optional[str]]:
    """
    Определить chat_id и user_id на основе запроса

    Новая логика:
    1. Если есть chat_id - используем его
    2. Если есть lead_id - ищем в БД max_user по lead_id
    3. Если есть contact_id - ищем в БД max_user по contact_id
    4. Если есть lms_id - ищем в БД max_user по lms_id
    """

    # Случай 1: прямой chat_id
    if request.chat_id:
        logger.info(f"Получен прямой chat_id: {request.chat_id}")
        return str(request.chat_id), None

    # Случай 2: поиск по lead_id
    if request.lead_id:
        logger.info(f"Поиск chat_id по lead_id: {request.lead_id}")

        try:
            lead_id_int = int(request.lead_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"lead_id должен быть числом, получено: {request.lead_id}",
            )

        with db_manager.session_scope() as db:
            max_user = db.query(MaxUser).filter(MaxUser.lead_id == lead_id_int).first()

            if not max_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Пользователь с lead_id={request.lead_id} не найден в БД max_user",
                )

            if not max_user.chat_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"У пользователя с lead_id={request.lead_id} не заполнен chat_id в БД",
                )

            logger.info(f"Найден chat_id={max_user.chat_id} по lead_id={request.lead_id}")
            return max_user.chat_id, str(max_user.chat_id)

    # Случай 3: поиск по contact_id
    if request.contact_id:
        logger.info(f"Поиск chat_id по contact_id: {request.contact_id}")

        try:
            contact_id_int = int(request.contact_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"contact_id должен быть числом, получено: {request.contact_id}",
            )

        with db_manager.session_scope() as db:
            max_user = db.query(MaxUser).filter(MaxUser.contact_id == contact_id_int).first()

            if not max_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Пользователь с contact_id={request.contact_id} не найден в БД max_user",
                )

            if not max_user.chat_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"У пользователя с contact_id={request.contact_id} не заполнен chat_id в БД",
                )

            logger.info(f"Найден chat_id={max_user.chat_id} по contact_id={request.contact_id}")
            return max_user.chat_id, str(max_user.chat_id)

    # Случай 4: поиск по lms_id
    if hasattr(request, "lms_id") and request.lms_id:
        logger.info(f"Поиск chat_id по lms_id: {request.lms_id}")

        try:
            lms_id_int = int(request.lms_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"lms_id должен быть числом, получено: {request.lms_id}"
            )

        with db_manager.session_scope() as db:
            max_user = db.query(MaxUser).filter(MaxUser.lms_id == lms_id_int).first()

            if not max_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Пользователь с lms_id={request.lms_id} не найден в БД max_user",
                )

            if not max_user.chat_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"У пользователя с lms_id={request.lms_id} не заполнен chat_id в БД",
                )

            logger.info(f"Найден chat_id={max_user.chat_id} по lms_id={request.lms_id}")
            return max_user.chat_id, str(max_user.chat_id)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Необходимо указать либо chat_id, либо lead_id, либо contact_id, либо lms_id",
    )


def _validate_and_process_text(text: Optional[str]) -> str:
    """
    Проверить и обработать текст сообщения

    Логика обработки подчеркиваний:
    - Каждые 2 подчеркивания (__) → преобразуются в символ новой строки (\n)
    - Каждые 3 подчеркивания (___) → делает перенос строки вниз \n
    - Одиночные подчеркивания (_) → удаляются (Если они прочто перед словом или одиночные - " _Занятия проходят"
    - Если Одиночные подчеркивания (_) внутри слова - не удаляем пример lead_id - тут не трогаем.
    - 4 подчеркивания (____) → Пропускаем строку вниз одну

    - Если в тесте есть перенос строки вниз как в питоне \n, а в обычном текст это просто ничего
    - Каждые \n\n → делает перенос строки вниз \n
    - Каждые \n\n\n → делает перенос строки вниз \n\n
    """
    if not text or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текст сообщения не может быть пустым",
        )

    processed_text = re.sub(r"_{4}", "\n\n", text)
    processed_text = re.sub(r"_{2,3}", "\n", processed_text)
    processed_text = re.sub(r"(?<!\w)_(?!\w)|^_|_$", "", processed_text)
    processed_text = re.sub(r"\n{3,}", "\n\n", processed_text)  # 3+ -> 2
    processed_text = "\n".join(line.strip() for line in processed_text.split("\n")).strip()

    return processed_text


def _prepare_send_params(request: SendMessageRequest, chat_id: str, user_id: Optional[str], original_text: str) -> dict:
    """
    Подготовить параметры для отправки сообщения
    """
    processed_text = get_vars(request, original_text)

    params = request.dict(exclude_none=True)

    fields_to_remove = ["twilio_variables", "lead_id", "contact_id", "lms_id", "sid", "parse_mode"]
    for field in fields_to_remove:
        if field in params:
            del params[field]

    params["text"] = processed_text
    params["chat_id"] = str(chat_id)

    if "format_type" not in params:
        params["format_type"] = "html"

    has_buttons = False
    if "buttons" in params and params["buttons"] and len(params["buttons"]) > 0:
        has_buttons = True
        params["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": params["buttons"]}}]
        del params["buttons"]
    else:
        if "buttons" in params:
            del params["buttons"]
        if "attachments" not in params:
            params["attachments"] = []

    logger.info(f"Параметры для отправки: chat_id={chat_id}, has_buttons={has_buttons}")

    logger.debug(f"Параметры сообщения: {params}")
    logger.debug(f"Текст после замены переменных: '{processed_text}'")
    return params


async def _send_message_via_bot(bot, params: dict):
    """
    Отправить сообщение через бота
    """
    logger.info("Попытка отправить сообщение")

    has_buttons = False
    if "buttons" in params and params["buttons"] and len(params["buttons"]) > 0:
        has_buttons = True
    elif "attachments" in params and params["attachments"] and len(params["attachments"]) > 0:
        has_buttons = True
        if "attachments" in params and params["attachments"]:
            params["buttons"] = params["attachments"][0].get("payload", {}).get("buttons", [])
            params.pop("attachments", None)

    if has_buttons:
        if not (bot.messages and bot.messages.send_message_with_keyboard):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Функция отправки сообщений с клавиатурой не реализована в боте",
            )

        if "disable_link_preview" not in params:
            params["disable_link_preview"] = True
        if "notify" not in params:
            params["notify"] = True

        await bot.messages.send_message_with_keyboard(**params)
    else:
        if not (bot.messages and bot.messages.send_text_message):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Функция отправки текстовых сообщений не реализована в боте",
            )

        clean_params = {"chat_id": params["chat_id"], "text": params["text"]}

        if "format_type" in params:
            clean_params["format_type"] = params["format_type"]

        await bot.messages.send_text_message(**clean_params)


async def _add_bitrix_comment(
    request: SendMessageRequest,
    chat_id: str,
    user_id: Optional[str],
    final_text: str,
    lead_id: Optional[str] = None,
    contact_id: Optional[str] = None,
):
    """
    Добавить комментарий в Bitrix
    """
    bitrix_data = dict(
        message_text=final_text,
        twilio_variables=request.twilio_variables or {},
        lead_id=request.lead_id if request.lead_id else None,
        contact_id=request.contact_id if request.contact_id else None,
        user_id=user_id if user_id else str(chat_id),
        chat_id=chat_id,
    )
    logger.info(f"Данные для комментария: {bitrix_data}")

    bitrix_comment = BitrixAddComment(bitrix_data)

    comment_id = bitrix_comment.add_comment(message_status="Отправлено", lead_id=lead_id, contact_id=contact_id)

    if comment_id:
        logger.info(f"Комментарий в Bitrix добавлен с ID: {comment_id}")
    else:
        logger.warning("Не удалось добавить комментарий в Bitrix (вернулся 0 ID)")

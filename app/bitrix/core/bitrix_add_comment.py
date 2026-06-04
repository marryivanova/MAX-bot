from datetime import datetime
from typing import Optional, Union

from loguru import logger

from app.bitrix.bx_method import send_comment_to_user_simple
from app.services.model.sender_message_model import BitrixMessage
from db.core import db_manager
from db.models.max_user import MaxUser


class CommentColor:
    GREEN = "0a7014"
    RED = "ff0000"
    GRAY = "5e5a5a"

    STATUS_MAPPING = {
        ("Не доставлено", "Not sent"): RED,
        ("Отправляется", "Sending"): GRAY,
    }

    @classmethod
    def get_color_for_status(cls, status: str) -> str:
        for status_keywords, color in cls.STATUS_MAPPING.items():
            if any(keyword in status for keyword in status_keywords):
                logger.debug(f"Устанавливаем {color} цвет для статуса '{status}'")
                return color
        logger.debug("Устанавливаем зеленый цвет по умолчанию")
        return cls.GREEN


class MessageFormatter:

    @staticmethod
    def format_variables(message_text: str, variables: list) -> str:
        if not variables:
            logger.debug("Нет переменных для обработки")
            return message_text

        logger.debug(f"Обрабатываем {len(variables)} переменных")
        for variable in variables:
            if variable.startswith("https://"):
                continue
            message_text = message_text.replace(variable, f"[B]{variable}[/B]")

        return message_text

    @staticmethod
    def format_recipient_info(message_obj) -> str:
        if not message_obj.client_contact_title:
            return ""

        recipient = f"+{message_obj.client_phone_number}"

        if "через MAX[/B][/COLOR]" in message_obj.message_text:
            recipient = f"id: {message_obj.max_id}"

        if message_obj.sender:
            recipient = f"{recipient}. Отправил: {message_obj.sender}."

        return f"Отправлено для: {message_obj.client_contact_title}, {recipient}\n"


class BitrixAddComment:

    def __init__(self, message: BitrixMessage | dict):
        if isinstance(message, dict):
            self._message = BitrixMessage(**message)
        elif isinstance(message, BitrixMessage):
            self._message = message

    @staticmethod
    def _get_ids_from_db(chat_id: Optional[str] = None) -> tuple[Optional[int], Optional[int]]:
        """
        Получить lead_id и contact_id из БД по chat_id
        """
        if not chat_id:
            return None, None

        try:
            with db_manager.session_scope() as db:
                max_user = db.query(MaxUser).filter(MaxUser.chat_id == str(chat_id)).first()

                if max_user:
                    logger.info(
                        f"Найдены данные в БД: lead_id={max_user.lead_id}, contact_id={max_user.contact_id} для chat_id={chat_id}"
                    )
                    return max_user.lead_id, max_user.contact_id
                else:
                    logger.warning(f"Не найден пользователь с chat_id={chat_id} в БД max_user")
                    return None, None
        except Exception as e:
            logger.error(f"Ошибка при поиске в БД: {e}")
            return None, None

    def _build_comment_text(self, message_status: str) -> str:
        logger.info("Начинаем формирование комментария для Bitrix")
        logger.debug(f"Статус для комментария: {message_status}")

        message_color = CommentColor.get_color_for_status(message_status)

        formatted_text = MessageFormatter.format_variables(self._message.message_text, self._message.variables or [])

        lines = [
            f"[COLOR=#{message_color}][B]{message_status}[/B][/COLOR]",
            formatted_text,
        ]

        recipient_info = MessageFormatter.format_recipient_info(self._message)
        if recipient_info:
            logger.debug(f"Добавляем информацию о получателе: {self._message.client_contact_title}")
            lines.insert(0, recipient_info.strip())

        if self._message.mailing_name:
            logger.debug(f"Добавляем название рассылки: {self._message.mailing_name}")
            lines.insert(0, f"[B]{self._message.mailing_name}[/B]")

        comment_text = "\n".join(lines)
        logger.debug(f"Финальный текст комментария:\n{comment_text}")

        return comment_text

    async def _add_comment_to_bitrix(
        self,
        message_status: str,
        lead_id: Optional[int | str] = None,
        contact_id: Optional[int | str] = None,
        chat_id: Optional[int | str] = None,
    ) -> dict:
        """
        Добавляет комментарий к лиду, контакту или напрямую по chat_id.
        Теперь lead_id и contact_id могут быть получены из БД по chat_id
        """
        logger.info("Начинаем добавление комментария в Bitrix")

        if chat_id is not None and lead_id is None and contact_id is None:
            logger.info(f"Пытаемся найти lead_id и contact_id в БД по chat_id={chat_id}")
            lead_id, contact_id = self._get_ids_from_db(chat_id)

        if lead_id is None and contact_id is None and chat_id is None:
            logger.error("Не указан ни lead_id, ни contact_id, ни chat_id")
            raise ValueError("Должен быть указан lead_id, contact_id или chat_id")

        comment_text = self._build_comment_text(message_status)

        if chat_id is not None and lead_id is None and contact_id is None:
            logger.info(f"Добавляем комментарий напрямую к чату: {chat_id}")
            response = send_comment_to_user_simple(
                user_bitrix_id=chat_id, user_bitrix_type="contact", comment=comment_text
            )
            return response

        if lead_id is not None:
            logger.info(f"Добавляем комментарий к лиду: {lead_id}")
            response = send_comment_to_user_simple(
                user_bitrix_id=lead_id, user_bitrix_type="lead", comment=comment_text
            )
            return response

        if contact_id is not None:
            logger.info(f"Добавляем комментарий к контакту: {contact_id}")
            response = send_comment_to_user_simple(
                user_bitrix_id=contact_id, user_bitrix_type="contact", comment=comment_text
            )
            return response

        raise ValueError("Не удалось определить тип получателя комментария")

    async def add_comment(
        self,
        message_status: str,
        lead_id: Optional[int | str] = None,
        contact_id: Optional[int | str] = None,
        chat_id: Optional[int | str] = None,
    ) -> int:
        """
        Добавляет комментарий (асинхронная версия).

        Args:
            message_status: Статус сообщения
            lead_id: ID лида (если None, попробуем получить из БД по chat_id)
            contact_id: ID контакта (если None, попробуем получить из БД по chat_id)
            chat_id: ID чата (используется для поиска в БД)
        """
        if lead_id is None and contact_id is None and chat_id is None:
            raise ValueError("Должен быть указан lead_id, contact_id или chat_id")

        response = await self._add_comment_to_bitrix(message_status, lead_id, contact_id, chat_id)

        comment_id = response.get("result", 0) if response.get("success", True) else 0
        logger.info(f"Комментарий добавлен в Bitrix с ID: {comment_id}")

        return comment_id


async def add_error_comment_to_bitrix(
    error_message: str,
    lead_id: Optional[Union[int, str]] = None,
    contact_id: Optional[Union[int, str]] = None,
    chat_id: Optional[Union[int, str]] = None,
    sid_id: Optional[str] = None,
    twilio_variables: Optional[str] = None,
) -> None:
    """
    Добавляет комментарий об ошибке в Bitrix.
    Теперь можно передать chat_id, и lead_id/contact_id найдутся в БД
    """
    if chat_id is not None and lead_id is None and contact_id is None:
        try:
            with db_manager.session_scope() as db:
                max_user = db.query(MaxUser).filter(MaxUser.chat_id == str(chat_id)).first()
                if max_user:
                    lead_id = max_user.lead_id
                    contact_id = max_user.contact_id
                    logger.info(f"Найдены в БД: lead_id={lead_id}, contact_id={contact_id} для chat_id={chat_id}")
                else:
                    logger.warning(f"Не найден пользователь с chat_id={chat_id} в БД")
        except Exception as e:
            logger.error(f"Ошибка поиска в БД: {e}")

    if lead_id is None and contact_id is None and chat_id is None:
        logger.debug("Нет данных для комментария об ошибке")
        return

    try:
        error_comment_parts = [
            f"[COLOR=#{CommentColor.RED}][B]❌ ОШИБКА ОТПРАВКИ СООБЩЕНИЯ[/B][/COLOR]",
            f"[COLOR=#{CommentColor.RED}]{error_message}[/COLOR]",
        ]

        if sid_id:
            error_comment_parts.append(f"\n[B]ID шаблона (sid):[/B] {sid_id}")

        if twilio_variables:
            vars_list = twilio_variables.split(";;")
            formatted_vars = "\n".join([f"  • {v}" for v in vars_list])
            error_comment_parts.append(f"[B]Переменные:[/B]\n{formatted_vars}")

        error_comment_parts.append(f"\n[B]Время ошибки:[/B] {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

        comment_text = "\n".join(error_comment_parts)

        bitrix_message = BitrixMessage(
            message_text=comment_text,
            variables=twilio_variables.split(";;") if twilio_variables else [],
            client_contact_title="",
            client_phone_number="",
            max_id="",
            sender="System",
            mailing_name="Упс, что-то пошло не так :(",
        )

        comment_adder = BitrixAddComment(bitrix_message)

        comment_id = await comment_adder.add_comment(
            message_status="Не доставлено", lead_id=lead_id, contact_id=contact_id, chat_id=chat_id
        )

        if comment_id > 0:
            logger.info(f"✅ Комментарий об ошибке добавлен в Bitrix с ID: {comment_id}")
        else:
            logger.warning(f"⚠️ Комментарий об ошибке не был добавлен (ID=0)")

    except Exception as e:
        logger.error(f"Не удалось добавить комментарий об ошибке в Bitrix: {str(e)}", exc_info=True)


async def add_successful_comment_to_bitrix(
    message: str,
    lead_id: Optional[Union[int, str]] = None,
    contact_id: Optional[Union[int, str]] = None,
    chat_id: Optional[Union[int, str]] = None,
    sid_id: Optional[str] = None,
    twilio_variables: Optional[str] = None,
    message_for_comment: Optional[str] = None,
) -> None:
    """
    Добавляет комментарий об успешной отправке в Bitrix.
    Теперь можно передать chat_id, и lead_id/contact_id найдутся в БД
    """
    if chat_id is not None and lead_id is None and contact_id is None:
        try:
            with db_manager.session_scope() as db:
                max_user = db.query(MaxUser).filter(MaxUser.chat_id == str(chat_id)).first()
                if max_user:
                    lead_id = max_user.lead_id
                    contact_id = max_user.contact_id
                    logger.info(f"Найдены в БД: lead_id={lead_id}, contact_id={contact_id} для chat_id={chat_id}")
                else:
                    logger.warning(f"Не найден пользователь с chat_id={chat_id} в БД")
        except Exception as e:
            logger.error(f"Ошибка поиска в БД: {e}")

    if lead_id is None and contact_id is None and chat_id is None:
        logger.debug("Нет данных для комментария")
        return

    try:
        comment_parts = [
            f"[COLOR=#{CommentColor.GREEN}][B]Сообщение отправлено[/B][/COLOR]",
            f"[COLOR=#{CommentColor.GRAY}]{message}[/COLOR]",
        ]

        if sid_id:
            comment_parts.append(f"\n[B]ID шаблона (sid):[/B] {sid_id}")

        if twilio_variables:
            vars_list = twilio_variables.split(";;")
            formatted_vars = "\n".join([f"  • {v}" for v in vars_list])
            comment_parts.append(f"[B]Переменные:[/B]\n{formatted_vars}")

        comment_parts.append(f"\n[B]Время отправки:[/B] {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

        if message_for_comment:
            comment_parts.append(f"\n[B]Итоговый текст, который отправлен в чат:[/B] \n{message_for_comment}")

        comment_text = "\n".join(comment_parts)

        bitrix_message = BitrixMessage(
            message_text=comment_text,
            variables=twilio_variables.split(";;") if twilio_variables else [],
            client_contact_title="",
            client_phone_number="",
            max_id="",
            sender="System",
            mailing_name="",
        )

        comment_adder = BitrixAddComment(bitrix_message)

        comment_id = await comment_adder.add_comment(
            message_status="Доставлено", lead_id=lead_id, contact_id=contact_id, chat_id=chat_id
        )

        if comment_id > 0:
            logger.warning(f"✅ Комментарий не был добавлен")

    except Exception as e:
        logger.error(f"Не удалось добавить комментарий в Bitrix: {str(e)}", exc_info=True)


_add_error_comment_to_bitrix = add_error_comment_to_bitrix
_add_successful_comment_to_bitrix = add_successful_comment_to_bitrix

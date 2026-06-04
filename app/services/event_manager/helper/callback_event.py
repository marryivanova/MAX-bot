# ========== Callback Handler ==========
import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from loguru import logger

from app.bitrix.core.bx_helper_method import create_deal
from app.helper.parsers import extract_phone_from_vcard, parse_contact_attachment
from app.services.command.direction import callback_after_choice_direction, send_direction_request_button
from app.services.command.get_contact import send_get_phone, send_student_message, send_success_response

#TODO: тут нужно доделать часть с командами
from app.services.command.helper.constants_and_patterns.direcrions.service import (
    DESIGN_HANDLERS,
    DIRECTION_HANDLERS,
    PROGRAMMING_HANDLERS,
    SUBJECT_HANDLERS,
    DesignService,
    DirectionService,
    ProgrammingService,
    SubjectService,
)

from app.services.command.menu import balance_bot, free_lessons_bot, lk_bot, menu_bot, schedule_bot
from app.services.event_manager import BotManager
from app.services.event_manager.event_store import EventStore
from app.services.event_manager.helper.extracts_additional_events import get_attachments, get_sender_name
from app.services.vars.cmd import CmdType
from db.crud_db.get_max_user_chat_id import get_max_user_by_chat_id


@dataclass
class EventContext:
    event: Any
    chat_id: str
    user_id: str
    payload: str
    attachments: list
    sender_name: str

    @classmethod
    async def from_event(
        cls, event: Any, bot_manager: BotManager, event_store: Optional[EventStore] = None
    ) -> "EventContext":
        chat_id, user_id = event.get_ids()
        message = event.message if hasattr(event, "message") else None
        attachments = get_attachments(message) if message else []
        sender_name = get_sender_name(message) if message else ""
        payload = event.callback.payload if hasattr(event, "callback") else ""

        return cls(
            event=event,
            chat_id=chat_id,
            user_id=user_id,
            payload=payload,
            attachments=attachments,
            sender_name=sender_name,
        )


class CallbackHandler:
    """Обработчик callback-событий"""

    DEDUP_WINDOW_SECONDS = 300  # 5 минут
    CLEANUP_MAX_AGE_SECONDS = 3600  # 1 час

    _command_handlers: Dict[str, Callable] = {}
    _dynamic_handlers: Dict[str, Callable] = {}
    _processed_combinations: Dict[str, float] = {}
    _last_selected_direction: Dict[str, str] = {}

    def __init__(self, bot_manager: BotManager, event_store: Optional[EventStore] = None):
        self.bot_manager = bot_manager
        self.event_store = event_store

        self._command_handlers = self.__class__._command_handlers.copy()
        self._dynamic_handlers = self.__class__._dynamic_handlers.copy()
        self._processed_combinations = self.__class__._processed_combinations
        self._last_selected_direction = self.__class__._last_selected_direction

        self._register_handlers()

    def command(self, *commands: str):
        """Декоратор для регистрации команд"""

        def decorator(func: Callable) -> Callable:
            for cmd in commands:
                self._command_handlers[cmd] = func
            return func

        return decorator

    def dynamic_command(self, prefix: str):
        """Декоратор для регистрации динамических команд"""

        def decorator(func: Callable) -> Callable:
            self._dynamic_handlers[prefix] = func
            return func

        return decorator

    # ========== Регистрация обработчиков ==========

    def _register_handlers(self):
        """Регистрация всех обработчиков команд"""
        simple_commands = {
            CmdType.consultation.value: send_direction_request_button,
            CmdType.student.value: send_student_message,
            CmdType.lk.value: lk_bot,
            CmdType.balance.value: balance_bot,
            CmdType.schedule.value: schedule_bot,
            CmdType.free_lessons.value: free_lessons_bot,
            CmdType.back_to_menu.value: menu_bot,
            CmdType.directions.value: send_direction_request_button,
        }

        for cmd, handler in simple_commands.items():
            self._register_simple_command(cmd, handler)

        self._register_next_command()
        self._register_subject_handler()
        self._register_programming_handler()
        self._register_design_handler()
        self._register_direction_handler()
        self._register_sign_up_lesson()

    # ========== Методы для работы с последним направлением ==========

    async def _store_last_selected_direction(self, chat_id: str, direction_abbreviation: str) -> None:
        """Сохраняет последнее выбранное направление"""
        self._last_selected_direction[chat_id] = direction_abbreviation
        logger.debug(f"💾 Сохранено последнее направление для {chat_id}: {direction_abbreviation}")

    async def _get_last_selected_direction(self, chat_id: str) -> Optional[str]:
        """Получает последнее выбранное направление"""
        return self._last_selected_direction.get(chat_id)

    async def _save_direction_by_prefix(self, payload: str, chat_id: str) -> None:
        """Сохраняет направление в зависимости от префикса payload"""
        if payload.startswith("/d_"):
            await self._store_last_selected_direction(chat_id, "D")
            logger.debug(f"💾 Сохранено направление D для {chat_id} (выбран курс дизайна)")
        elif payload.startswith("/ru_"):
            await self._store_last_selected_direction(chat_id, "RU")
            logger.debug(f"💾 Сохранено направление RU для {chat_id} (выбран курс программирования)")
        elif payload.startswith("/rep_"):
            await self._store_last_selected_direction(chat_id, "REP")
            logger.debug(f"💾 Сохранено направление REP для {chat_id} (выбран предмет репетиторства)")
        elif payload.startswith("/direction_"):
            # Для основных направлений извлекаем аббревиатуру из payload
            direction_abbreviation = DirectionService.get_abbreviation_by_payload(payload)
            if direction_abbreviation:
                await self._store_last_selected_direction(chat_id, direction_abbreviation)
                logger.debug(f"💾 Сохранено направление {direction_abbreviation} для {chat_id}")

    # ========== Обработчики ==========

    def _register_sign_up_lesson(self):
        """Регистрация обработчика записи на урок"""

        @self.command("/sign_up_lesson")
        async def _handle_sign_up_lesson(chat_id: str) -> None:
            logger.info(f"📝 Запись на урок для chat_id={chat_id}")

            try:
                user_data = await asyncio.to_thread(get_max_user_by_chat_id, chat_id)
                phone = user_data.get("phone") if user_data else None
                last_direction = await self._get_last_selected_direction(chat_id)

                if phone:
                    if await self._is_duplicate(phone, last_direction or "SIGN_UP"):
                        logger.warning(f"⚠️ Повторная запись на урок для {phone}")

                    final_abbreviation = last_direction if last_direction else "SIGN_UP"
                    logger.info(
                        f"📝 Создание лида с направлением: {final_abbreviation} (последнее выбранное: {last_direction})"
                    )

                    await self._create_deal_and_send_response(
                        chat_id=chat_id,
                        abbreviation=final_abbreviation,
                        label="Запись на урок",
                        bot_method=self._send_sign_up_confirmation,
                    )
                else:
                    logger.info(f"📱 Телефон не найден для chat_id={chat_id}, запрашиваем...")
                    await send_get_phone(self.bot_manager.bot, chat_id, None)

            except Exception as e:
                logger.error(f"Ошибка при обработке записи на урок для chat_id={chat_id}: {e}", exc_info=True)
                await self.bot_manager.bot.send_message(
                    chat_id=chat_id, text="❌ Произошла техническая ошибка. Пожалуйста, попробуйте позже."
                )

    @staticmethod
    async def _send_sign_up_confirmation(bot, chat_id: str, label: str) -> None:
        """Отправка подтверждения записи на урок"""
        await bot.messages.send_text_message(
            chat_id=chat_id,
            text="✅ Спасибо! Совсем скоро с вами свяжется наш менеджер, чтобы помочь записаться на первый урок и ответить на все ваши вопросы.\n\n"
            "Если у вас появятся вопросы или пожелания до звонка, смело пишите, мы всегда на связи и готовы помочь!",
        )

    def _register_simple_command(self, cmd: str, handler_func: Callable):
        """Регистрация простой команды"""

        @self.command(cmd)
        async def _handler(chat_id: str) -> None:
            await handler_func(self.bot_manager.bot, chat_id)

        return _handler

    def _register_next_command(self):
        """Регистрация обработчика команды /next"""

        @self.command(CmdType.next.value)
        async def _handle_next(chat_id: str) -> None:
            """Обработка команды /next"""
            if self.event_store and await self.event_store.is_next_processed(chat_id):
                logger.warning(f"⏭️ /next уже был обработан для chat_id {chat_id}")
                return

            if self.event_store:
                await self.event_store.mark_next_as_processed(chat_id)

            phone = None
            if self.event_store:
                phone = await self._find_phone_by_chat_id(chat_id)

            logger.info(f"📱 Телефон для chat_id {chat_id}: {'найден' if phone else 'не найден'}")
            await send_get_phone(self.bot_manager.bot, chat_id, phone)
            await send_success_response(self.bot_manager.bot, chat_id=chat_id, phone=phone)

    def _register_subject_handler(self):
        """Регистрация обработчика выбора предмета"""

        @self.dynamic_command("/rep_")
        async def _handle_subject(context: EventContext) -> None:
            """Обработка выбора предмета репетиторства"""
            subject_label = SubjectService.get_label_by_payload(context.payload)
            subject_abbreviation = SubjectService.get_abbreviation_by_payload(context.payload)

            logger.debug(f"Предмет выбран: {context.payload}, аббревиатура: {subject_abbreviation}")

            await self._save_direction_by_prefix(context.payload, context.chat_id)

            handler = SUBJECT_HANDLERS.get(subject_abbreviation)
            if handler:
                await handler(self.bot_manager.bot, context.chat_id)

            phone = await self._extract_phone(context)
            if phone:
                logger.info(f"📝 Создаем сделку для предмета: {subject_label}")
                await self._create_deal_and_send_response(
                    chat_id=context.chat_id,
                    abbreviation=f"REP + {subject_label}",
                    label=f"Выбран предмет: {subject_label}",
                    bot_method=self._send_sign_up_confirmation,
                )
            else:
                logger.warning(f"⚠️ Телефон не найден для создания сделку по предмету {subject_label}")

    def _register_programming_handler(self):
        """Регистрация обработчика выбора программирования"""

        @self.dynamic_command("/ru_")
        async def _handle_programming(context: EventContext) -> None:
            """Обработка выбора предмета программирование"""
            programming_label = ProgrammingService.get_label_by_payload(context.payload)
            programming_abbreviation = ProgrammingService.get_abbreviation_by_payload(context.payload)

            logger.debug(f"Прога направление выбрано: {context.payload}, аббревиатура: {programming_abbreviation}")

            await self._save_direction_by_prefix(context.payload, context.chat_id)

            if "_sign_up" in context.payload:
                await self._process_direction_choice(
                    context=context,
                    abbreviation=programming_abbreviation,
                    label=programming_label,
                    main_direction_abbreviation="RU",
                )
            else:
                handler = PROGRAMMING_HANDLERS.get(programming_abbreviation)
                if handler:
                    await handler(self.bot_manager.bot, context.chat_id)

    def _register_design_handler(self):
        """Регистрация обработчика выбора дизайна"""

        @self.dynamic_command("/d_")
        async def _handle_design(context: EventContext) -> None:
            """Обработка выбора предмета дизайн"""
            design_label = DesignService.get_label_by_payload(context.payload)
            design_abbreviation = DesignService.get_abbreviation_by_payload(context.payload)

            logger.debug(f"Дизайн направление выбрано: {context.payload}, аббревиатура: {design_abbreviation}")

            await self._save_direction_by_prefix(context.payload, context.chat_id)

            if "_sign_up" in context.payload:
                await self._process_direction_choice(
                    context=context,
                    abbreviation=design_abbreviation,
                    label=design_label,
                    main_direction_abbreviation="D",
                )
            else:
                handler = DESIGN_HANDLERS.get(design_abbreviation)
                if handler:
                    await handler(self.bot_manager.bot, context.chat_id)

    def _register_direction_handler(self):
        """Регистрация обработчика выбора направления"""

        @self.dynamic_command("/direction_")
        async def _handle_direction(context: EventContext) -> None:
            """Обработка выбора направления"""
            direction_label = DirectionService.get_label_by_payload(context.payload)
            direction_abbreviation = DirectionService.get_abbreviation_by_payload(context.payload)

            logger.debug(f"Направление: {context.payload}, аббревиатура: {direction_abbreviation}")
            await self._save_direction_by_prefix(context.payload, context.chat_id)

            if "_sign_up" in context.payload:
                await self._process_direction_choice(
                    context=context,
                    abbreviation=direction_abbreviation,
                    label=direction_label,
                    main_direction_abbreviation=direction_abbreviation,
                )
            else:
                handler = DIRECTION_HANDLERS.get(direction_abbreviation)
                if handler:
                    await handler(self.bot_manager.bot, context.chat_id)

    # ========== Основные методы ==========

    async def handle_callback(self, event: Any) -> None:
        """Основной метод обработки callback-событий"""
        try:
            if not hasattr(event, "callback") or not event.callback:
                logger.error("Событие не содержит callback")
                return

            context = await EventContext.from_event(event, self.bot_manager, self.event_store)
            logger.info(f"🔄 Callback получен: chat_id={context.chat_id}, payload={context.payload}")

            await self._process_payload(context)

            logger.success(f"✅ Callback обработан: {context.payload}")

        except Exception as e:
            logger.error(f"Ошибка при обработке callback: {e}", exc_info=True)

    async def _process_payload(self, context: EventContext) -> None:
        """Обработка payload с выбором нужного обработчика"""
        for prefix, handler in self._dynamic_handlers.items():
            if context.payload.startswith(prefix):
                await handler(context)
                return

        handler = self._command_handlers.get(context.payload)
        if handler:
            await handler(context.chat_id)
        else:
            logger.warning(f"⚠️ Неизвестный payload: {context.payload}")

    # ========== Бизнес-логика ==========

    async def _process_direction_choice(
        self, context: EventContext, abbreviation: str, label: str, main_direction_abbreviation: str = None
    ) -> None:
        """Обработка выбора направления

        Args:
            context: Контекст события
            abbreviation: Аббревиатура конкретного курса (PL, SCRATCH и т.д.)
            label: Название для отображения
            main_direction_abbreviation: Аббревиатура основного направления (D, RU, REP и т.д.)
        """
        phone = await self._extract_phone(context)
        if not phone:
            logger.warning(f"⚠️ Не удалось извлечь телефон для chat_id: {context.chat_id}")
            return

        final_abbreviation = main_direction_abbreviation if main_direction_abbreviation else abbreviation

        logger.info(
            f"📝 Создание сделки: phone={phone}, course={abbreviation}, "
            f"main_direction={main_direction_abbreviation}, final={final_abbreviation}"
        )

        if main_direction_abbreviation:
            await self._store_last_selected_direction(context.chat_id, main_direction_abbreviation)

        await self._create_deal_and_send_response(
            chat_id=context.chat_id,
            abbreviation=f"{final_abbreviation} + {abbreviation}",
            label=label,
            bot_method=callback_after_choice_direction,
        )

    async def _create_deal_and_send_response(
        self, chat_id: str, abbreviation: str, label: str, bot_method: Callable
    ) -> None:
        """Создание сделки и отправка ответа"""
        create_task = create_deal(chat_id=chat_id, course=abbreviation)

        if create_task is not None:
            logger.debug(f"Создана новая задача в битрикс: {create_task}")
            await bot_method(self.bot_manager.bot, chat_id, label)
            logger.success(f"✅ Сделка созданна успешно создан для: {label}")
        else:
            logger.error(f"❌ Не удалось создать сделку для: {label}")

    # ========== Вспомогательные методы ==========

    async def _extract_phone(self, context: EventContext) -> Optional[str]:
        """Извлечение телефона из различных источников"""
        import asyncio

        # 1. Сначала пробуем извлечь из VCF вложения
        vcf_info = parse_contact_attachment(context.attachments, context.sender_name)
        phone = extract_phone_from_vcard(vcf_info) if vcf_info else None

        if phone:
            logger.debug(f"📱 Телефон найден в VCF: {phone}")
            return phone

        # 2. Если не нашли в VCF, ищем в базе данных по chat_id
        if context.chat_id:
            try:
                user_data = await asyncio.to_thread(get_max_user_by_chat_id, context.chat_id)
                if user_data and user_data.get("phone"):
                    phone = user_data["phone"]
                    logger.debug(f"📱 Телефон найден в БД по chat_id {context.chat_id}: {phone}")
                    return phone
            except Exception as e:
                logger.error(f"Ошибка при поиске телефона в БД для chat_id {context.chat_id}: {e}")

        # 3. Если не нашли в БД, ищем в кэше event_store
        if not phone and self.event_store:
            try:
                phone = await self._find_phone_by_chat_id(context.chat_id)
                if phone:
                    logger.debug(f"📱 Телефон найден в кэше по chat_id {context.chat_id}: {phone}")
                    return phone
            except Exception as e:
                logger.error(f"Ошибка при поиске телефона в кэше для chat_id {context.chat_id}: {e}")

        logger.debug(f"⚠️ Телефон не найден для chat_id {context.chat_id}")
        return None

    async def _is_duplicate(self, phone: str, direction: str) -> bool:
        """Проверка на дублирование создания"""
        unique_key = f"{phone}_{direction}"
        current_time = time.time()

        if unique_key in self._processed_combinations:
            last_processed = self._processed_combinations[unique_key]
            if current_time - last_processed < self.DEDUP_WINDOW_SECONDS:
                logger.warning(
                    f"⚠️ Сделка уже создавался недавно для {phone} направление {direction}. "
                    f"Прошло {current_time - last_processed:.0f} сек"
                )
                return True

        self._processed_combinations[unique_key] = current_time
        self._cleanup_old_processed_combinations()

        return False

    def _cleanup_old_processed_combinations(self) -> None:
        """Очистка старых записей о созданных сделках"""
        current_time = time.time()
        old_keys = [
            key
            for key, timestamp in self._processed_combinations.items()
            if current_time - timestamp > self.CLEANUP_MAX_AGE_SECONDS
        ]

        for key in old_keys:
            del self._processed_combinations[key]

        if old_keys:
            logger.debug(f"🧹 Очищено {len(old_keys)} старых записей из кэша дублей")

    async def _find_phone_by_chat_id(self, chat_id: str) -> Optional[str]:
        """Найти телефон по chat_id в кэше событий"""
        if not self.event_store:
            return None

        cache = self.event_store.events_cache
        for phone, events in cache.items():
            for event_data in events:
                if str(event_data.get("chat_id")) == str(chat_id):
                    extracted_phone = event_data.get("extracted_phone")
                    if extracted_phone:
                        logger.debug(f"🔍 Найден телефон {extracted_phone} в кэше по chat_id {chat_id}")
                        return extracted_phone

        return None

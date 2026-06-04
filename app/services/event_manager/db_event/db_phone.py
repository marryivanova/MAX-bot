import json
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.event_manager.db_event.db_model import Base, Event, NextCall, PhoneMapping


class PhoneDatabaseORM:

    def __init__(self, db_path="sqlite:///phone_mapping.db"):
        self.engine = create_engine(db_path, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._init_db()

    def _init_db(self):
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_mapping(self, chat_id: str, phone: str):
        """Сохранить маппинг"""
        with self.get_session() as session:
            existing = session.query(PhoneMapping).filter(PhoneMapping.chat_id == chat_id).first()

            if existing:
                existing.phone = phone
                existing.updated_at = datetime.utcnow()
            else:
                mapping = PhoneMapping(chat_id=chat_id, phone=phone)
                session.add(mapping)

    def get_chat_id_by_phone(self, phone: str) -> Optional[str]:
        """Получить chat_id по телефону"""
        with self.get_session() as session:
            mapping = session.query(PhoneMapping).filter(PhoneMapping.phone == phone).first()
            return mapping.chat_id if mapping else None

    def save_event(
        self,
        phone: str,
        chat_id: Optional[str],
        update_type: str,
        event_data: Dict[str, Any],
    ):
        """Сохранить событие в БД"""
        try:
            event_json = json.dumps(event_data, ensure_ascii=False)

            with self.get_session() as session:
                event = Event(
                    phone=phone,
                    chat_id=chat_id,
                    update_type=update_type,
                    event_data=event_json,
                )
                session.add(event)

            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения события в БД: {e}")
            return False

    def get_events_by_phone(self, phone: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить события по номеру телефона"""
        with self.get_session() as session:
            events = (
                session.query(Event).filter(Event.phone == phone).order_by(Event.timestamp.desc()).limit(limit).all()
            )

            result = []
            for event in events:
                if event.event_data:
                    try:
                        event_data = json.loads(event.event_data)
                    except json.JSONDecodeError:
                        event_data = {}
                else:
                    event_data = {}

                if "update_type" not in event_data:
                    event_data["update_type"] = event.update_type
                if "chat_id" not in event_data:
                    event_data["chat_id"] = event.chat_id
                if "timestamp" not in event_data:
                    event_data["timestamp"] = event.timestamp.isoformat() if event.timestamp else None
                if "extracted_phone" not in event_data:
                    event_data["extracted_phone"] = event.phone

                result.append(event_data)

            return result

    def get_all_events(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получить все события"""

        with self.get_session() as session:
            events = session.query(Event).order_by(Event.timestamp.desc()).all()

            events_by_phone = defaultdict(list)
            for event in events:
                event_data = json.loads(event.event_data) if event.event_data else {}
                event_dict = dict(
                    id=event.id,
                    phone=event.phone,
                    chat_id=event.chat_id,
                    update_type=event.update_type,
                    timestamp=event.timestamp.isoformat() if event.timestamp else None,
                    data=event_data,
                )
                events_by_phone[event.phone].append(event_dict)

            return dict(events_by_phone)

    def is_next_processed(self, chat_id: str) -> bool:
        """Проверить, был ли обработан /next для chat_id в течение таймаута"""
        with self.get_session() as session:
            next_call = (
                session.query(NextCall).filter(NextCall.chat_id == chat_id).order_by(NextCall.timestamp.desc()).first()
            )

            if not next_call:
                return False

    def save_next_processed(self, chat_id: str, phone: Optional[str] = None):
        """Сохранить факт обработки /next"""
        try:
            with self.get_session() as session:
                existing = session.query(NextCall).filter(NextCall.chat_id == chat_id).first()

                if existing:
                    existing.timestamp = datetime.utcnow()
                    existing.phone = phone or existing.phone
                    logger.debug(f"🔄 Обновлен /next для chat_id {chat_id}")
                else:
                    next_call = NextCall(chat_id=chat_id, phone=phone, timestamp=datetime.utcnow())
                    session.add(next_call)
                    logger.debug(f"✅ Сохранен /next для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"Ошибка сохранения /next в БД: {e}")

    def get_next_call_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о /next вызове"""
        with self.get_session() as session:
            next_call = (
                session.query(NextCall).filter(NextCall.chat_id == chat_id).order_by(NextCall.timestamp.desc()).first()
            )

            if next_call:
                return dict(
                    chat_id=next_call.chat_id,
                    phone=next_call.phone,
                    timestamp=next_call.timestamp.isoformat(),
                    seconds_ago=(datetime.utcnow() - next_call.timestamp).total_seconds(),
                )
            return None

    def cleanup_old_next_calls(self, days: int = 7):
        """Очистить старые записи /next (старше N дней)"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with self.get_session() as session:
            deleted_count = session.query(NextCall).filter(NextCall.timestamp < cutoff_date).delete()

            if deleted_count > 0:
                logger.info(f"🧹 Очищено {deleted_count} старых записей /next (старше {days} дней)")

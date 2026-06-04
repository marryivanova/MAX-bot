from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class PhoneMapping(Base):
    """Модель маппинга телефонов"""

    __tablename__ = "phone_mapping"

    chat_id = Column(String, primary_key=True)
    phone = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_phone", "phone"),)


class Event(Base):
    """Модель событий"""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String, nullable=False)
    chat_id = Column(String)
    update_type = Column(String)
    event_data = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_events_phone", "phone"),
        Index("idx_events_chat_id", "chat_id"),
    )


class NextCall(Base):
    """Модель для хранения обработанных /next вызовов"""

    __tablename__ = "next_calls"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    phone = Column(String, nullable=True)
    __table_args__ = (
        Index("idx_next_calls_chat_id", "chat_id"),
        Index("idx_next_calls_timestamp", "timestamp"),
    )

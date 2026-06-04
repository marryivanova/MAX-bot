from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String

from db.core import Base


class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_alpha = Column(Integer, nullable=True)
    id_lead = Column(Integer, nullable=True)
    id_contact = Column(Integer, nullable=True)

    name = Column(String(100), nullable=False)
    phone = Column(String(100), nullable=True, index=True)
    email = Column(String(100), nullable=True)
    messenger = Column(BigInteger, nullable=True)

    b_date = Column(Date, nullable=True)
    e_date = Column(Date, nullable=True)
    next_lesson_date = Column(DateTime, nullable=True, index=True)
    last_lesson_date = Column(Date, nullable=True)
    end_subscribe_date = Column(Date, nullable=True, index=True)
    end_timetable = Column(Date, nullable=True)
    date_update = Column(Date, nullable=True)

    is_study = Column(Integer, nullable=False, default=False)
    tariff = Column(Integer, nullable=True)
    timezone = Column(String(32), nullable=True, default="Europe/Moscow")

    teachers_ids = Column(String(100), nullable=True)
    subscription_id = Column(Integer, nullable=True, index=True)

    balance = Column(Integer, nullable=True, default=0)
    balance_user = Column(Integer, nullable=True, default=0)
    balance_bonus_lessons = Column(Integer, nullable=True, default=0)

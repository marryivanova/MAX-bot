from sqlalchemy import Column, DateTime, Integer, String

from db.core import Base


class LeadsUser(Base):
    __tablename__ = "leads"

    ID = Column(Integer, primary_key=True, autoincrement=True)
    STATUS_ID = Column(Integer, nullable=True)
    EMAIL = Column(String(255), nullable=True)
    PHONE = Column(String(50), nullable=True)
    ASSIGNED_BY_ID = Column(Integer, nullable=True)
    UTM_SOURCE = Column(String(255), nullable=True)
    UTM_MEDIUM = Column(String(255), nullable=True)
    UTM_CAMPAIGN = Column(String(255), nullable=True)
    UTM_CONTENT = Column(String(255), nullable=True)
    UTM_TERM = Column(String(255), nullable=True)
    DATE_CREATE = Column(DateTime, nullable=True)
    REJECTION_REASON = Column(String(255), nullable=True)
    direction = Column(String(100), nullable=True)
    LANDING = Column(String(255), nullable=True)
    TIME_CREATE = Column(DateTime, nullable=True)
    TITLE = Column(String(255), nullable=True)
    ID_NDZ = Column(Integer, nullable=True)

from sqlalchemy import BigInteger, Column, Date, Integer, String

from db.core import Base


class TeachersVacationModel(Base):
    """Table teachers_for_vacation_send."""

    __tablename__ = "teachers_for_vacation_send"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, nullable=False)
    start_vacation = Column(Date, nullable=False)
    end_vacation = Column(Date, nullable=False)
    vacation_id = Column(String(32), nullable=True)

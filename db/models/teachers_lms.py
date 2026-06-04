from sqlalchemy import BigInteger, Column, Date, Integer, String

from db.core import Base


class LMSTeacher(Base):
    __tablename__ = "teachers"

    id_lms = Column(Integer, primary_key=True)
    id_bx = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    ru_courses = Column(String(500), nullable=True)
    en_courses = Column(String(500), nullable=True)
    entry_lesson = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    birthday = Column(Date, nullable=True)
    id_out = Column(Integer, nullable=True)
    id_curator = Column(Integer, nullable=True)
    curator_name = Column(String(255), nullable=True)
    id_curator_jr = Column(Integer, nullable=True)
    curator_jr_name = Column(String(255), nullable=True)
    zoom_id = Column(BigInteger, nullable=True)
    currency_id = Column(Integer, nullable=True)

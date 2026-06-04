from sqlalchemy import BigInteger, Column, Integer, String

from db.core import Base


class MaxUser(Base):
    __tablename__ = "max_user"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    lead_id = Column(Integer, nullable=True)
    contact_id = Column(Integer, nullable=True)
    lms_id = Column(Integer, nullable=True)

    def __repr__(self):
        return f"MaxUser(id={self.id}, chat_id={self.chat_id}, phone={self.phone})"

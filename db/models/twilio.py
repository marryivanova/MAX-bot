from sqlalchemy import Column, String, Text

from db.core import Base


class TwilioTemplate(Base):
    __tablename__ = "template"

    am = Column(String(255), nullable=False)
    sid = Column(String(255), nullable=False, primary_key=True)
    источник = Column(String(255), nullable=True)
    текст = Column(Text, nullable=False)
    место_использования = Column(String(500), nullable=True)

    def __repr__(self):
        return f"Twilio(am={self.am}, sid={self.sid}, текст={self.текст})"

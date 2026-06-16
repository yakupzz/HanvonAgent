"""Setting model — Anahtar-değer ayarları."""

from sqlalchemy import Column, String, DateTime
from datetime import datetime
from models.base import Base


class Setting(Base):
    """Uygulama ayarları (key-value store)."""

    __tablename__ = "settings"

    key = Column(String(255), primary_key=True, index=True)
    value = Column(String(1000), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Setting(key='{self.key}', value='{self.value}')>"

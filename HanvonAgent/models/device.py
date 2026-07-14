"""Device model — Hanvon cihazları."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from models.base import Base


class Device(Base):
    """Hanvon F710 cihaz kaydı."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    ip = Column(String(50), unique=True, index=True, nullable=False)
    port = Column(Integer, default=9922, nullable=False)  # TCP port (varsayılan 9922)
    comm_key_encrypted = Column(String(500), nullable=True)  # Encrypted CommKey
    enabled = Column(Boolean, default=True, index=True)
    last_connected = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    employees = relationship("Employee", back_populates="device", cascade="all, delete-orphan")
    records = relationship("Record", back_populates="device", cascade="all, delete-orphan")

    @property
    def comm_key(self):
        """Çözülmüş CommKey (DPAPI). Legacy düz metin değerler de desteklenir."""
        from core.secret_store import decrypt_secret
        return decrypt_secret(self.comm_key_encrypted)

    def set_comm_key(self, value):
        """CommKey'i DPAPI ile şifreleyerek sakla. None/boş → temizle."""
        from core.secret_store import encrypt_secret
        self.comm_key_encrypted = encrypt_secret(value) if value else None

    def __repr__(self):
        return f"<Device(id={self.id}, name='{self.name}', ip='{self.ip}')>"

"""Record model — Giriş-çıkış kaydı."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from models.base import Base


class Record(Base):
    """Erişim kaydı (giriş-çıkış)."""

    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint('record_time', 'employee_device_id', name='uq_time_emp'),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    employee_device_id = Column(String(20), nullable=True)  # Cihazdan çekilen personel ID (direct)
    record_time = Column(String(50), index=True, nullable=False)  # YYYY-MM-DD HH:MM:SS
    status = Column(String(10))  # 1, 2, vb.
    card_src = Column(String(50))  # from_door, from_check, NULL
    file_path = Column(String(500), nullable=True)  # data/YYYY/MM/DD.json
    source = Column(String(50), default="device")  # device, manual
    push_status = Column(String(20), default="pending", index=True)  # pending, sent, failed
    pushed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    device = relationship("Device", back_populates="records")
    employee = relationship("Employee", back_populates="records")

    def __repr__(self):
        return f"<Record(id={self.id}, record_time='{self.record_time}', push_status='{self.push_status}')>"

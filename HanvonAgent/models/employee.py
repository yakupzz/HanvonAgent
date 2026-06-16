"""Employee model — Personel kaydı."""

import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from models.base import Base


class Employee(Base):
    """Personel kaydı (cihazdan çekilen)."""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_device_id = Column(Integer, index=True, nullable=False)  # Cihazdan gelen ID
    name = Column(String(255), index=True)  # Boş olabilir
    card_num = Column(String(50), nullable=True)
    check_type = Column(String(50), default="face")  # face, card, face&card
    authority = Column(String(50), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    last_synced = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Sync durumu (cihaza gönderilmeyi bekleyen değişiklikler)
    sync_status = Column(String(20), default="ok", index=True)  # "ok" | "yeni"
    pending_name = Column(String(255), nullable=True)  # Cihaza gönderilecek yeni isim

    # Biometrik yedek — cihaz sıfırlanırsa geri yüklenebilir
    face_data_json = Column(Text, nullable=True)          # JSON array (18 base64 template)
    calid = Column(String(50), nullable=True)             # Cihaz iç değeri
    opendoor_type = Column(String(50), nullable=True)     # face / card / face&card
    biometric_synced_at = Column(DateTime, nullable=True) # Face_data son çekilme zamanı

    # Relationships
    device = relationship("Device", back_populates="employees")
    records = relationship("Record", back_populates="employee")

    @property
    def face_data(self):
        """face_data_json → List[str]. Boşsa [] döner."""
        if not self.face_data_json:
            return []
        try:
            return json.loads(self.face_data_json)
        except (ValueError, TypeError):
            return []

    @face_data.setter
    def face_data(self, value):
        """List[str] veya None → face_data_json."""
        if value:
            self.face_data_json = json.dumps(value)
            self.biometric_synced_at = datetime.utcnow()
        else:
            self.face_data_json = None
            self.biometric_synced_at = None

    @property
    def has_biometric(self) -> bool:
        """DB'de kayıtlı biometrik veri var mı?"""
        return bool(self.face_data_json)

    @property
    def display_name(self):
        """Gösterilecek isim — pending varsa onu, yoksa name'i döner."""
        if self.pending_name:
            return self.pending_name
        return self.name

    def __repr__(self):
        return f"<Employee(id={self.id}, device_id={self.employee_device_id}, name='{self.name}')>"

"""
DevicePushWorker — Personel isim güncellemesini cihaza gönderen QThread.

UI'yı bloklamamak için cihaz TCP işlemi ayrı thread'de yapılır.
run() içinde yeni bir DB session açılır (thread güvenliği için), employee
ve device id'lerden yüklenir, employee_sync_service.push_employee çağrılır.

Sinyal:
    finished(bool, str): (başarı, mesaj). Main thread bunu dinleyip UI günceller.
"""

import logging
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from models import Employee, Device, SessionLocal
from services.employee_sync_service import push_employee

logger = logging.getLogger("HanvonAgent.DevicePushWorker")


class DevicePushWorker(QThread):
    """Tek bir personeli cihaza gönderen worker thread."""

    # (success, message)
    finished = Signal(bool, str)

    def __init__(
        self,
        employee_id: int,
        device_id: int,
        session_factory: Optional[Callable] = None,
        parent=None,
    ):
        """
        Args:
            employee_id: Employee.id (DB primary key).
            device_id: Device.id (DB primary key).
            session_factory: Yeni session üreten çağrılabilir (test için).
                             None ise SessionLocal kullanılır.
            parent: Qt parent.
        """
        super().__init__(parent)
        self.employee_id = employee_id
        self.device_id = device_id
        self._session_factory = session_factory or SessionLocal

    def run(self):
        """Thread gövdesi — kendi session'ında çalışır."""
        session = self._session_factory()
        try:
            employee = session.query(Employee).filter_by(id=self.employee_id).first()
            device = session.query(Device).filter_by(id=self.device_id).first()

            if employee is None or device is None:
                self.finished.emit(False, "Personel veya cihaz bulunamadı")
                return

            success, message = push_employee(session, employee, device)
            self.finished.emit(bool(success), message or "")
        except Exception as e:  # noqa: BLE001 — thread'i çökertmeden hatayı bildir
            logger.error("DevicePushWorker hatası: %s", e, exc_info=True)
            self.finished.emit(False, str(e))
        finally:
            try:
                session.close()
            except Exception:
                pass

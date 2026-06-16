"""
DevicePushWorker (QThread) testleri — pytest-qt ile.

Worker, push_employee'i kendi session'ında çalıştırır ve
finished(bool, str) sinyali emit eder. UI'yı bloklamamak için QThread.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models import Device, Employee
from services.device_push_worker import DevicePushWorker


@pytest.fixture
def session_factory(tmp_path):
    """Dosya-tabanlı SQLite (thread'ler arası paylaşılabilir)."""
    db_file = tmp_path / "worker_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def seeded(session_factory):
    """Bekleyen değişikliği olan bir personel oluştur."""
    Session = session_factory
    s = Session()
    device = Device(name="Cihaz", ip="172.16.1.218", enabled=True)
    s.add(device)
    s.flush()
    emp = Employee(
        employee_device_id=237,
        name="Eski",
        pending_name="Yeni İsim",
        sync_status="yeni",
        device_id=device.id,
    )
    s.add(emp)
    s.commit()
    ids = (emp.id, device.id)
    s.close()
    return ids


class TestDevicePushWorker:
    def test_emits_finished_on_success(self, qtbot, session_factory, seeded):
        emp_id, device_id = seeded

        with patch("services.device_push_worker.push_employee", return_value=(True, "")) as mock_push:
            worker = DevicePushWorker(emp_id, device_id, session_factory=session_factory)

            with qtbot.waitSignal(worker.finished, timeout=3000) as blocker:
                worker.start()

            assert blocker.args[0] is True
            assert mock_push.called

        worker.wait()

    def test_emits_finished_on_failure(self, qtbot, session_factory, seeded):
        emp_id, device_id = seeded

        with patch(
            "services.device_push_worker.push_employee",
            return_value=(False, "cihaza ulaşılamadı"),
        ):
            worker = DevicePushWorker(emp_id, device_id, session_factory=session_factory)

            with qtbot.waitSignal(worker.finished, timeout=3000) as blocker:
                worker.start()

            assert blocker.args[0] is False
            assert "cihaza ulaşılamadı" in blocker.args[1]

        worker.wait()

    def test_unexpected_exception_emits_failure(self, qtbot, session_factory, seeded):
        emp_id, device_id = seeded

        with patch(
            "services.device_push_worker.push_employee",
            side_effect=RuntimeError("beklenmeyen"),
        ):
            worker = DevicePushWorker(emp_id, device_id, session_factory=session_factory)

            with qtbot.waitSignal(worker.finished, timeout=3000) as blocker:
                worker.start()

            assert blocker.args[0] is False
            assert "beklenmeyen" in blocker.args[1]

        worker.wait()

    def test_missing_employee_emits_failure(self, qtbot, session_factory):
        """Var olmayan personel ID -> hata sinyali (crash yok)."""
        worker = DevicePushWorker(9999, 8888, session_factory=session_factory)

        with qtbot.waitSignal(worker.finished, timeout=3000) as blocker:
            worker.start()

        assert blocker.args[0] is False

        worker.wait()

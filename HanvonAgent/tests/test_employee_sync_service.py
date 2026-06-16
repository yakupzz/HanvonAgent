"""
EmployeeSyncService testleri — inline edit / cihaza gönderme iş mantığı.

Mock HanvonClient (unittest.mock) ile cihaz etkileşimi izole edilir.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models import Device, Employee
from services import employee_sync_service as svc


@pytest.fixture
def db_engine():
    """In-memory SQLite."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Database session."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def sample_device(db_session):
    device = Device(name="Test Cihaz", ip="172.16.1.218", enabled=True)
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def sample_employee(db_session, sample_device):
    emp = Employee(
        employee_device_id=237,
        name="Eski İsim",
        card_num="0X123",
        check_type="face",
        device_id=sample_device.id,
    )
    db_session.add(emp)
    db_session.commit()
    return emp


class TestComputeSyncStatus:
    """compute_sync_status() — saf fonksiyon."""

    def test_no_pending_returns_ok(self, sample_employee):
        sample_employee.pending_name = None
        assert svc.compute_sync_status(sample_employee) == "ok"

    def test_pending_returns_yeni(self, sample_employee):
        sample_employee.pending_name = "Yeni İsim"
        assert svc.compute_sync_status(sample_employee) == "yeni"

    def test_empty_pending_returns_ok(self, sample_employee):
        sample_employee.pending_name = ""
        assert svc.compute_sync_status(sample_employee) == "ok"


class TestMarkPending:
    """mark_pending() — inline edit sonrası bekleyen değişikliği işaretle."""

    def test_sets_pending_name_and_status(self, db_session, sample_employee):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.pending_name == "Yeni İsim"
        assert refreshed.sync_status == "yeni"
        # Orijinal name değişmemeli (cihaza gönderilene kadar)
        assert refreshed.name == "Eski İsim"

    def test_same_as_current_name_clears_pending(self, db_session, sample_employee):
        """Mevcut isimle aynı yazılırsa bekleyen değişiklik temizlenir."""
        svc.mark_pending(db_session, sample_employee, "Eski İsim")

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.pending_name is None
        assert refreshed.sync_status == "ok"

    def test_strips_whitespace(self, db_session, sample_employee):
        svc.mark_pending(db_session, sample_employee, "  Boşluklu  ")

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.pending_name == "Boşluklu"

    def test_empty_name_raises(self, db_session, sample_employee):
        with pytest.raises(ValueError):
            svc.mark_pending(db_session, sample_employee, "   ")

    def test_too_long_name_raises(self, db_session, sample_employee):
        """255 karakterden uzun isim ValueError fırlatır (pending_name String(255))."""
        with pytest.raises(ValueError):
            svc.mark_pending(db_session, sample_employee, "A" * 256)

    def test_exactly_255_chars_allowed(self, db_session, sample_employee):
        """Tam 255 karakter sınırı kabul edilir."""
        name = "A" * 255
        svc.mark_pending(db_session, sample_employee, name)
        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.pending_name == name


class TestPushEmployee:
    """push_employee() — bekleyen ismi cihaza gönder."""

    def test_success_applies_pending_and_clears(self, db_session, sample_employee, sample_device):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")

        client = MagicMock()
        client.set_name_table.return_value = True

        ok, msg = svc.push_employee(db_session, sample_employee, sample_device, client=client)

        assert ok is True
        client.set_name_table.assert_called_once_with({"237": "Yeni İsim"})

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.name == "Yeni İsim"
        assert refreshed.pending_name is None
        assert refreshed.sync_status == "ok"

    def test_failure_keeps_pending(self, db_session, sample_employee, sample_device):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")

        client = MagicMock()
        client.set_name_table.return_value = False

        ok, msg = svc.push_employee(db_session, sample_employee, sample_device, client=client)

        assert ok is False
        assert msg  # hata mesajı dolu

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        # Pending korunur, name değişmez
        assert refreshed.name == "Eski İsim"
        assert refreshed.pending_name == "Yeni İsim"
        assert refreshed.sync_status == "yeni"

    def test_exception_returns_error_tuple(self, db_session, sample_employee, sample_device):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")

        client = MagicMock()
        client.set_name_table.side_effect = ConnectionError("cihaza ulaşılamadı")

        ok, msg = svc.push_employee(db_session, sample_employee, sample_device, client=client)

        assert ok is False
        assert "cihaza ulaşılamadı" in msg

        refreshed = db_session.query(Employee).filter_by(id=sample_employee.id).first()
        assert refreshed.sync_status == "yeni"

    def test_no_pending_is_noop(self, db_session, sample_employee, sample_device):
        """Bekleyen değişiklik yoksa cihaza gitmeden başarı döner."""
        client = MagicMock()

        ok, msg = svc.push_employee(db_session, sample_employee, sample_device, client=client)

        assert ok is True
        client.set_employee.assert_not_called()

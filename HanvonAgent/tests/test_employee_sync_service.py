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


# ─────────────────────────────────────────────────────────────────────────────
# Kardeş kayıtlar — aynı personel ID'si başka cihazlarda
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def second_device(db_session):
    device = Device(name="Yonetim", ip="172.16.1.219", enabled=True)
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def sibling(db_session, second_device):
    """sample_employee (ID 237) ile aynı ID, ikinci cihazda, eski isimle."""
    emp = Employee(employee_device_id=237, name="Eski İsim", device_id=second_device.id)
    db_session.add(emp)
    db_session.commit()
    return emp


class TestFindSiblings:
    def test_returns_same_id_on_other_devices(self, db_session, sample_employee, sibling):
        other_id = Employee(employee_device_id=999, name="Baska", device_id=sibling.device_id)
        db_session.add(other_id)
        db_session.commit()
        assert svc.find_siblings(db_session, sample_employee) == [sibling]

    def test_no_siblings(self, db_session, sample_employee):
        assert svc.find_siblings(db_session, sample_employee) == []


class TestSiblingsToUpdate:
    def test_sibling_with_old_name_needs_update(self, db_session, sample_employee, sibling):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")
        assert svc.siblings_to_update(db_session, sample_employee) == [sibling]

    def test_sibling_already_has_new_name_skipped(self, db_session, sample_employee, sibling):
        sibling.name = "Yeni İsim"
        db_session.commit()
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")
        assert svc.siblings_to_update(db_session, sample_employee) == []

    def test_no_pending_means_nothing_to_update(self, db_session, sample_employee, sibling):
        assert svc.siblings_to_update(db_session, sample_employee) == []


class TestPropagatePending:
    def test_marks_siblings_pending_with_same_name(self, db_session, sample_employee, sibling):
        svc.mark_pending(db_session, sample_employee, "Yeni İsim")
        result = svc.propagate_pending(db_session, sample_employee)
        assert result == [sibling]
        db_session.refresh(sibling)
        assert sibling.pending_name == "Yeni İsim"
        assert sibling.sync_status == "yeni"
        assert sibling.name == "Eski İsim"  # cihaz onaylayana kadar name değişmez

    def test_nothing_to_propagate_without_pending(self, db_session, sample_employee, sibling):
        assert svc.propagate_pending(db_session, sample_employee) == []
        db_session.refresh(sibling)
        assert sibling.pending_name is None


# ─────────────────────────────────────────────────────────────────────────────
# Cihazlar arası isim farkı — aynı ID, farklı cihazda farklı isim
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeName:
    def test_turkish_case_and_spaces_ignored(self):
        # Uygulama cihaza ASCII gönderdiği için bu farklar "fark" sayılmaz
        assert svc.normalize_name("  GÖRKEM   serbes ") == svc.normalize_name("GORKEM SERBES")
        assert svc.normalize_name("ÇAĞLAR ŞİŞMAN") == svc.normalize_name("CAGLAR SISMAN")

    def test_different_names_differ(self):
        assert svc.normalize_name("YELDA") != svc.normalize_name("BENSU")

    def test_none_is_empty(self):
        assert svc.normalize_name(None) == ""


class TestDifferingNames:
    def test_other_device_with_different_name(self, db_session, sample_employee, sibling):
        sibling.name = "BAŞKA İSİM"
        db_session.commit()
        names = svc.cross_device_names(db_session)
        diffs = svc.differing_names(sample_employee, names[237])
        assert diffs == {sibling.device_id: "BAŞKA İSİM"}

    def test_same_name_on_other_device_is_not_a_difference(self, db_session, sample_employee, sibling):
        names = svc.cross_device_names(db_session)
        assert svc.differing_names(sample_employee, names[237]) == {}

    def test_own_device_excluded(self, db_session, sample_employee):
        names = svc.cross_device_names(db_session)
        assert names[237] == {sample_employee.device_id: "Eski İsim"}
        assert svc.differing_names(sample_employee, names[237]) == {}

    def test_empty_name_on_other_device_is_a_difference(self, db_session, sample_employee, sibling):
        sibling.name = None
        db_session.commit()
        names = svc.cross_device_names(db_session)
        assert svc.differing_names(sample_employee, names[237]) == {sibling.device_id: ""}

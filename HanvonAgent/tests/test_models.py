"""
SQLAlchemy model testleri.

Referans: proje.md veritabanı şeması
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models.base import Base
from models.device import Device
from models.employee import Employee
from models.record import Record
from models.setting import Setting


@pytest.fixture
def db_engine():
    """In-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Database session for testing."""
    with Session(db_engine) as session:
        yield session


class TestDeviceModel:
    """Device tablosu testleri."""

    def test_create_device(self, db_session):
        """Cihaz oluştur."""
        device = Device(
            name="Lab Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="encrypted_key_here",
            enabled=True,
        )
        db_session.add(device)
        db_session.commit()

        # Veritabanından oku
        device_db = db_session.query(Device).filter_by(ip="172.16.1.218").first()
        assert device_db is not None
        assert device_db.name == "Lab Cihaz"
        assert device_db.enabled is True

    def test_device_optional_fields(self, db_session):
        """Cihaz optional alanlar (last_connected)."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.219",
            comm_key_encrypted=None,
            enabled=True,
        )
        db_session.add(device)
        db_session.commit()

        device_db = db_session.query(Device).filter_by(ip="172.16.1.219").first()
        assert device_db.last_connected is None

    def test_device_default_port(self, db_session):
        """Cihaz port belirtilmezse varsayılan 9922 kullanılır."""
        device = Device(name="Cihaz", ip="172.16.1.230", enabled=True)
        db_session.add(device)
        db_session.commit()

        device_db = db_session.query(Device).filter_by(ip="172.16.1.230").first()
        assert device_db.port == 9922

    def test_device_custom_port(self, db_session):
        """Cihaz özel port ile kaydedilebilir ve okunabilir."""
        device = Device(name="Cihaz", ip="172.16.1.231", port=19922, enabled=True)
        db_session.add(device)
        db_session.commit()

        device_db = db_session.query(Device).filter_by(ip="172.16.1.231").first()
        assert device_db.port == 19922

    def test_device_timestamps(self, db_session):
        """Cihaz created_at otomatik."""
        before = datetime.utcnow()
        device = Device(
            name="Cihaz",
            ip="172.16.1.220",
            comm_key_encrypted="key",
            enabled=False,
        )
        db_session.add(device)
        db_session.commit()
        after = datetime.utcnow()

        device_db = db_session.query(Device).filter_by(ip="172.16.1.220").first()
        assert before <= device_db.created_at <= after


class TestEmployeeModel:
    """Employee tablosu testleri."""

    def test_create_employee(self, db_session):
        """Personel oluştur."""
        # Önce cihaz oluştur (FK)
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=237,
            name="Huseyin S.",
            card_num="0X12345678",
            check_type="face",
            authority="0X1",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        emp_db = db_session.query(Employee).filter_by(employee_device_id=237).first()
        assert emp_db is not None
        assert emp_db.name == "Huseyin S."
        assert emp_db.device_id == device.id

    def test_employee_empty_name(self, db_session):
        """Personel boş isim (bazı kayıtlarda boştur)."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=177,
            name="",
            card_num="0Xffffffff",
            check_type="face",
            authority="0X0",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        emp_db = db_session.query(Employee).filter_by(employee_device_id=177).first()
        assert emp_db.name == ""

    def test_employee_device_relationship(self, db_session):
        """Employee → Device foreign key."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=237,
            name="Test",
            card_num="0X123",
            check_type="face",
            authority="0X0",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        # Relationship test
        emp_db = db_session.query(Employee).filter_by(employee_device_id=237).first()
        assert emp_db.device.ip == "172.16.1.218"

    def test_employee_sync_defaults(self, db_session):
        """Yeni personel default sync_status='ok', pending_name=None."""
        device = Device(name="Cihaz", ip="172.16.1.221", enabled=True)
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=300,
            name="Sync Test",
            card_num="0X300",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        emp_db = db_session.query(Employee).filter_by(employee_device_id=300).first()
        assert emp_db.sync_status == "ok"
        assert emp_db.pending_name is None

    def test_employee_display_name_uses_name_when_no_pending(self, db_session):
        """display_name pending_name yoksa name döner."""
        device = Device(name="Cihaz", ip="172.16.1.222", enabled=True)
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=301,
            name="Ahmet",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        assert employee.display_name == "Ahmet"

    def test_employee_display_name_uses_pending_when_set(self, db_session):
        """display_name pending_name varsa onu döner."""
        device = Device(name="Cihaz", ip="172.16.1.223", enabled=True)
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=302,
            name="Ahmet",
            pending_name="Mehmet",
            sync_status="yeni",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.commit()

        assert employee.display_name == "Mehmet"


class TestRecordModel:
    """Record tablosu testleri."""

    def test_create_record(self, db_session):
        """Kayıt oluştur."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=237,
            name="Huseyin S.",
            card_num="0X123",
            check_type="face",
            authority="0X0",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.flush()

        record = Record(
            device_id=device.id,
            employee_id=employee.id,
            record_time="2026-06-09 08:30:00",
            status="1",
            card_src="from_door",
            file_path="data/2026/06/09.json",
            source="device",
            push_status="pending",
        )
        db_session.add(record)
        db_session.commit()

        rec_db = db_session.query(Record).filter_by(record_time="2026-06-09 08:30:00").first()
        assert rec_db is not None
        assert rec_db.status == "1"
        assert rec_db.push_status == "pending"

    def test_record_push_tracking(self, db_session):
        """Kayıt push durumu takibi."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=237,
            name="Test",
            card_num="0X123",
            check_type="face",
            authority="0X0",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.flush()

        record = Record(
            device_id=device.id,
            employee_id=employee.id,
            record_time="2026-06-09 08:30:00",
            status="1",
            card_src="from_door",
            file_path="data/2026/06/09.json",
            source="manual",
            push_status="pending",
        )
        db_session.add(record)
        db_session.commit()

        # Push status güncelle
        rec_db = db_session.query(Record).filter_by(record_time="2026-06-09 08:30:00").first()
        rec_db.push_status = "sent"
        rec_db.pushed_at = datetime.utcnow()
        db_session.commit()

        rec_db = db_session.query(Record).filter_by(record_time="2026-06-09 08:30:00").first()
        assert rec_db.push_status == "sent"
        assert rec_db.pushed_at is not None

    def test_record_source_tracking(self, db_session):
        """Kayıt kaynağı (device vs manual)."""
        device = Device(
            name="Cihaz",
            ip="172.16.1.218",
            comm_key_encrypted="key",
            enabled=True,
        )
        db_session.add(device)
        db_session.flush()

        employee = Employee(
            employee_device_id=237,
            name="Test",
            card_num="0X123",
            check_type="face",
            authority="0X0",
            device_id=device.id,
        )
        db_session.add(employee)
        db_session.flush()

        # Cihazdan gelen kayıt
        record1 = Record(
            device_id=device.id,
            employee_id=employee.id,
            record_time="2026-06-09 08:30:00",
            status="1",
            card_src="from_door",
            file_path="data/2026/06/09.json",
            source="device",
            push_status="pending",
        )

        # Manuel import edilen kayıt
        record2 = Record(
            device_id=device.id,
            employee_id=employee.id,
            record_time="2026-06-09 09:00:00",
            status="1",
            card_src="from_door",
            file_path="data/2026/06/09.json",
            source="manual",
            push_status="pending",
        )

        db_session.add_all([record1, record2])
        db_session.commit()

        device_records = db_session.query(Record).filter_by(device_id=device.id, source="device").all()
        manual_records = db_session.query(Record).filter_by(device_id=device.id, source="manual").all()

        assert len(device_records) == 1
        assert len(manual_records) == 1


class TestEmployeeMigration:
    """init_db() additive migration testleri (mevcut DB'ye sütun ekleme)."""

    def test_init_db_adds_sync_columns_to_existing_db(self, tmp_path, monkeypatch):
        """Eski şemalı DB'de init_db() sync_status + pending_name ekler."""
        import importlib
        from sqlalchemy import create_engine, text, inspect

        db_file = tmp_path / "legacy.db"

        # Tam şemayı oluştur, sonra sync sütunlarını DROP ederek eski DB simüle et
        legacy_engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(legacy_engine)
        with legacy_engine.connect() as conn:
            conn.execute(text("DROP INDEX IF EXISTS ix_employees_sync_status"))
            conn.execute(text("ALTER TABLE employees DROP COLUMN sync_status"))
            conn.execute(text("ALTER TABLE employees DROP COLUMN pending_name"))
            conn.execute(text(
                "INSERT INTO employees (employee_device_id, name, device_id) "
                "VALUES (5, 'Eski Personel', 1)"
            ))
            conn.commit()
        legacy_engine.dispose()

        # init_db'yi bu DB'ye yönlendir (modülü taze import et)
        monkeypatch.setenv("HANVON_DB_PATH", str(db_file))
        import models.base as base_module
        importlib.reload(base_module)
        try:
            base_module.init_db()

            inspector = inspect(base_module.engine)
            cols = [c["name"] for c in inspector.get_columns("employees")]
            assert "sync_status" in cols
            assert "pending_name" in cols

            # Mevcut satır 'ok' default'a sahip olmalı
            with base_module.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT sync_status, pending_name FROM employees "
                    "WHERE employee_device_id=5"
                )).fetchone()
            assert row[0] == "ok"
            assert row[1] is None
        finally:
            base_module.engine.dispose()
            # Modülü orijinal haline döndür (diğer testleri etkilememesi için)
            monkeypatch.delenv("HANVON_DB_PATH", raising=False)
            importlib.reload(base_module)


class TestDeviceMigration:
    """init_db() additive migration testi — devices.port sütunu."""

    def test_init_db_adds_port_column_to_existing_db(self, tmp_path, monkeypatch):
        """Eski şemalı DB'de init_db() port sütununu 9922 default ile ekler."""
        import importlib
        from sqlalchemy import create_engine, text, inspect

        db_file = tmp_path / "legacy_port.db"

        legacy_engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(legacy_engine)
        with legacy_engine.connect() as conn:
            conn.execute(text("ALTER TABLE devices DROP COLUMN port"))
            conn.execute(text(
                "INSERT INTO devices (name, ip, enabled) VALUES ('Eski Cihaz', '172.16.1.240', 1)"
            ))
            conn.commit()
        legacy_engine.dispose()

        monkeypatch.setenv("HANVON_DB_PATH", str(db_file))
        import models.base as base_module
        importlib.reload(base_module)
        try:
            base_module.init_db()

            inspector = inspect(base_module.engine)
            cols = [c["name"] for c in inspector.get_columns("devices")]
            assert "port" in cols

            with base_module.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT port FROM devices WHERE ip='172.16.1.240'"
                )).fetchone()
            assert row[0] == 9922
        finally:
            base_module.engine.dispose()
            monkeypatch.delenv("HANVON_DB_PATH", raising=False)
            importlib.reload(base_module)


class TestSettingModel:
    """Setting tablosu testleri."""

    def test_create_setting(self, db_session):
        """Ayar oluştur (key-value)."""
        setting = Setting(
            key="api_endpoint",
            value="https://api.example.com/records"
        )
        db_session.add(setting)
        db_session.commit()

        setting_db = db_session.query(Setting).filter_by(key="api_endpoint").first()
        assert setting_db is not None
        assert setting_db.value == "https://api.example.com/records"

    def test_setting_update(self, db_session):
        """Ayar güncelle."""
        setting = Setting(
            key="poll_interval",
            value="1800"
        )
        db_session.add(setting)
        db_session.commit()

        setting_db = db_session.query(Setting).filter_by(key="poll_interval").first()
        setting_db.value = "3600"
        db_session.commit()

        setting_db = db_session.query(Setting).filter_by(key="poll_interval").first()
        assert setting_db.value == "3600"

    def test_setting_boolean_as_string(self, db_session):
        """Boolean ayarlar string olarak (key-value store)."""
        setting = Setting(
            key="auto_push_enabled",
            value="true"
        )
        db_session.add(setting)
        db_session.commit()

        setting_db = db_session.query(Setting).filter_by(key="auto_push_enabled").first()
        assert setting_db.value == "true"

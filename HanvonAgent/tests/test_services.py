"""
Service testleri — RecordService, PushService, SchedulerService.
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models import Device, Employee, Record, Setting, SessionLocal
from services.record_service import RecordService
from services.push_service import PushService


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
    """Sample device."""
    device = Device(
        name="Test Cihaz",
        ip="172.16.1.218",
        comm_key_encrypted="12345678",
        enabled=True,
    )
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def sample_employee(db_session, sample_device):
    """Sample employee."""
    emp = Employee(
        employee_device_id=237,
        name="Test Personel",
        card_num="0X123456",
        check_type="face",
        device_id=sample_device.id,
    )
    db_session.add(emp)
    db_session.commit()
    return emp


class TestRecordService:
    """RecordService testleri."""

    @patch('services.record_service.HanvonClient')
    def test_fetch_records(self, mock_client_class, db_session, sample_device, sample_employee):
        """Cihazdan kayıtları çek ve DB'ye kaydet."""
        # Mock GetRecord yanıtı
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_record.return_value = [
            {
                'time': '2026-06-09 08:30:00',
                'id': '237',
                'name': 'Test Personel',
                'status': '1',
                'card_src': 'from_door'
            }
        ]

        service = RecordService(db_session)
        result = service.fetch_records(sample_device, "2026-6-9", "2026-6-9")

        assert result['new_count'] == 1
        assert result['total_count'] == 1
        records = result['records']
        assert len(records) == 1
        assert records[0].record_time == '2026-06-09 08:30:00'
        assert records[0].push_status == 'pending'
        assert records[0].source == 'device'

    def test_save_records_to_file(self, db_session, sample_device, sample_employee, tmp_path):
        """Kayıtları yerel JSON dosyasına kaydet."""
        # Veritabanına kayıt ekle
        record = Record(
            device_id=sample_device.id,
            employee_id=sample_employee.id,
            record_time='2026-06-09 08:30:00',
            status='1',
            card_src='from_door',
            source='device',
            push_status='pending',
        )
        db_session.add(record)
        db_session.commit()

        # Service'i kullan (tmp_path ile override)
        service = RecordService(db_session, data_dir=tmp_path)
        service.save_records_to_file([record])

        # Dosya kontrol et
        file_path = tmp_path / "2026" / "06" / "09.json"
        assert file_path.exists()

        with open(file_path) as f:
            data = json.load(f)

        assert len(data) > 0
        assert data[0]['device_ip'] == sample_device.ip
        assert data[0]['records'][0]['time'] == '2026-06-09 08:30:00'

    def test_duplicate_detection(self, db_session, sample_device, sample_employee):
        """Duplicate kayıt tespit et (device + time + employee_device_id)."""
        # İlk kayıt
        record1 = Record(
            device_id=sample_device.id,
            employee_id=sample_employee.id,
            employee_device_id='237',
            record_time='2026-06-09 08:30:00',
            status='1',
            card_src='from_door',
            source='device',
            push_status='pending',
        )
        db_session.add(record1)
        db_session.commit()

        service = RecordService(db_session)

        # Duplicate kontrol
        is_duplicate = service.is_duplicate(
            device_id=sample_device.id,
            record_time='2026-06-09 08:30:00',
            employee_device_id='237',
        )
        assert is_duplicate is True

        # Farklı record
        is_duplicate = service.is_duplicate(
            device_id=sample_device.id,
            record_time='2026-06-09 09:00:00',
            employee_device_id='237',
        )
        assert is_duplicate is False


class TestPushService:
    """PushService testleri."""

    @patch('services.push_service.httpx.post')
    def test_push_pending_records(self, mock_post, db_session, sample_device, sample_employee):
        """Pending kayıtları API'ye gönder."""
        # Pending kayıt
        record = Record(
            device_id=sample_device.id,
            employee_id=sample_employee.id,
            record_time='2026-06-09 08:30:00',
            status='1',
            card_src='from_door',
            source='device',
            push_status='pending',
        )
        db_session.add(record)
        db_session.commit()

        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Setting'i ayarla (API endpoint)
        from models import Setting
        setting = Setting(
            key='api_endpoint',
            value='http://localhost:8000/api/records'
        )
        db_session.add(setting)
        db_session.commit()

        service = PushService(db_session)
        pushed = service.push_pending_records()

        assert pushed > 0
        assert mock_post.called

        # Record durumu kontrol et
        rec = db_session.query(Record).first()
        assert rec.push_status == 'sent'
        assert rec.pushed_at is not None

    @patch('services.push_service.httpx.post')
    def test_push_with_retry(self, mock_post, db_session, sample_device, sample_employee):
        """Başarısız push'ta retry (exponential backoff)."""
        # Başarısız olacak API
        mock_post.side_effect = Exception("Connection error")

        record = Record(
            device_id=sample_device.id,
            employee_id=sample_employee.id,
            record_time='2026-06-09 08:30:00',
            status='1',
            card_src='from_door',
            source='device',
            push_status='pending',
        )
        db_session.add(record)
        db_session.commit()

        from models import Setting
        setting = Setting(
            key='api_endpoint',
            value='http://localhost:8000/api/records'
        )
        db_session.add(setting)
        db_session.commit()

        service = PushService(db_session, max_retries=2)
        pushed = service.push_pending_records()

        assert pushed == 0

        # Record hala pending (failed)
        rec = db_session.query(Record).first()
        assert rec.push_status in ['pending', 'failed']

    def test_payload_format(self, db_session, sample_device, sample_employee):
        """Push payload formatı doğru mu?"""
        record = Record(
            device_id=sample_device.id,
            employee_id=sample_employee.id,
            record_time='2026-06-09 08:30:00',
            status='1',
            card_src='from_door',
            source='device',
            push_status='pending',
        )
        db_session.add(record)
        db_session.commit()

        service = PushService(db_session)
        payload = service._build_payload([record])

        assert 'records' in payload
        assert len(payload['records']) == 1
        assert payload['records'][0]['device_ip'] == sample_device.ip
        assert payload['records'][0]['record_time'] == '2026-06-09 08:30:00'

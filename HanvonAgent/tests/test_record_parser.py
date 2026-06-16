"""
GetRecord ve GetEmployee yanıt parse testleri.

Referans:
- D:\Projeler\F710\referans\lib\hanvon\client.rb (parse_response)
- D:\Projeler\F710\test-extract-data.js (gerçek veri örnekleri)
"""

import pytest
from core.record_parser import RecordParser


class TestRecordParserGetRecord:
    """GetRecord() yanıtı parse testleri."""

    def test_parse_getrecord_simple(self):
        """Basit GetRecord yanıtı (1 kayıt)."""
        response = (
            'Return(result="success" dev_id="0" '
            'time="2026-06-09 08:30:00" id="8" name="YAKUP T." '
            'workcode="" status="1" card_src="from_door")'
        )
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 1
        assert records[0]['time'] == "2026-06-09 08:30:00"
        assert records[0]['id'] == "8"
        assert records[0]['name'] == "YAKUP T."
        assert records[0]['status'] == "1"
        assert records[0]['card_src'] == "from_door"

    def test_parse_getrecord_multiple(self):
        """Çoklu kayıt (time= ile ayrılmış)."""
        response = (
            'Return(result="success" dev_id="0" '
            'time="2026-06-09 08:30:00" id="8" name="YAKUP T." status="1" card_src="from_door" '
            'time="2026-06-09 12:00:00" id="232" name="OTHER" status="2" card_src="from_check")'
        )
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 2
        assert records[0]['id'] == "8"
        assert records[1]['id'] == "232"
        assert records[1]['status'] == "2"

    def test_parse_getrecord_empty(self):
        """Boş yanıt (kayıt yok)."""
        response = 'Return(result="success" dev_id="0")'
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 0

    def test_parse_getrecord_failed(self):
        """Başarısız yanıt."""
        response = 'Return(result="failed" reason="invalid time")'
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 0

    def test_parse_getrecord_with_long_name(self):
        """Uzun isim (Türkçe karakterler)."""
        response = (
            'Return(result="success" dev_id="0" '
            'time="2026-06-09 08:30:00" id="10" name="Hüseyin Şahin" status="1")'
        )
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 1
        assert records[0]['name'] == 'Hüseyin Şahin'

    def test_parse_getrecord_empty_fields(self):
        """Boş alanlar (workcode="" vb.)."""
        response = (
            'Return(result="success" dev_id="0" '
            'time="2026-06-09 08:30:00" id="8" name="YAKUP T." '
            'workcode="" status="1" card_src="")'
        )
        parser = RecordParser()
        records = parser.parse_get_record(response)

        assert len(records) == 1
        assert records[0]['workcode'] == ""
        assert records[0]['card_src'] == ""


class TestRecordParserGetEmployee:
    """GetEmployee() yanıtı parse testleri."""

    def test_parse_getemployee_simple(self):
        """Basit GetEmployee yanıtı."""
        response = (
            'Return(result="success" id="237" '
            'name="h" card_num="0Xffffffff" authority="0X0" check_type="face")'
        )
        parser = RecordParser()
        employee = parser.parse_get_employee(response)

        assert employee['id'] == "237"
        assert employee['name'] == "h"
        assert employee['card_num'] == "0Xffffffff"
        assert employee['check_type'] == "face"

    def test_parse_getemployee_with_face_data(self):
        """GetEmployee yüz verisi ile (BASE64)."""
        response = (
            'Return(result="success" id="237" '
            'name="Huseyin S." card_num="0X12345678" '
            'authority="0X1" check_type="face&card" '
            'face_data="ABCDEF...LONG_BASE64_STRING...")'
        )
        parser = RecordParser()
        employee = parser.parse_get_employee(response)

        assert employee['id'] == "237"
        assert employee['name'] == "Huseyin S."
        assert 'face_data' in employee

    def test_parse_getemployee_failed(self):
        """GetEmployee başarısız."""
        response = 'Return(result="failed" reason="unknown id")'
        parser = RecordParser()
        employee = parser.parse_get_employee(response)

        assert employee is None or employee.get('result') == 'failed'

    def test_parse_getemployee_empty_name(self):
        """GetEmployee boş isim."""
        response = (
            'Return(result="success" id="177" '
            'name="" card_num="0Xffffffff" authority="0X0" check_type="face")'
        )
        parser = RecordParser()
        employee = parser.parse_get_employee(response)

        assert employee['id'] == "177"
        assert employee['name'] == ""


class TestRecordParserGetEmployeeID:
    """GetEmployeeID() yanıtı parse testleri."""

    def test_parse_getemployeeid_simple(self):
        """Basit GetEmployeeID yanıtı."""
        response = (
            'Return(result="success" total="5" '
            'id="237" id="177" id="5" id="274" id="253")'
        )
        parser = RecordParser()
        ids = parser.parse_get_employee_id(response)

        assert len(ids) == 5
        assert "237" in ids
        assert "177" in ids
        assert "5" in ids

    def test_parse_getemployeeid_empty(self):
        """Boş personel listesi."""
        response = 'Return(result="success" total="0")'
        parser = RecordParser()
        ids = parser.parse_get_employee_id(response)

        assert len(ids) == 0

    def test_parse_getemployeeid_large(self):
        """364 personel (gerçek veri)."""
        # Sadece başı ve sonu test et
        response = (
            'Return(result="success" total="364" '
            'id="237" id="177" id="5" '
        )
        # ... (Gerçek testde tam liste olur)
        response += 'id="509")'
        parser = RecordParser()
        ids = parser.parse_get_employee_id(response)

        assert len(ids) >= 3


class TestRecordParserGetDeviceInfo:
    """GetDeviceInfo() yanıtı parse testleri."""

    def test_parse_getdeviceinfo_simple(self):
        """Basit GetDeviceInfo yanıtı."""
        response = (
            'Return(result="success" dev_id="6710511030000079" '
            'time="2026-6-9 13:28:45" edition="3.006.089" '
            'volume="1" ip="172.16.1.218" '
            'gateway="172.16.1.254" netmask="255.255.255.0")'
        )
        parser = RecordParser()
        device_info = parser.parse_get_device_info(response)

        assert device_info['dev_id'] == "6710511030000079"
        assert device_info['time'] == "2026-6-9 13:28:45"
        assert device_info['edition'] == "3.006.089"
        assert device_info['ip'] == "172.16.1.218"

    def test_parse_getdeviceinfo_failed(self):
        """GetDeviceInfo başarısız."""
        response = 'Return(result="failed")'
        parser = RecordParser()
        device_info = parser.parse_get_device_info(response)

        assert device_info is None or device_info.get('result') == 'failed'


class TestRecordParserEdgeCases:
    """Edge case ve protokol testleri."""

    def test_parse_wait_response(self):
        """Wait() geçiş yanıtı (asenkron operasyon)."""
        response = 'Wait(wait_time="120")'
        parser = RecordParser()
        # Wait() yanıtını tanı, gerçek cevap bekle demektir
        is_wait = parser.is_wait_response(response)
        assert is_wait is True

    def test_parse_multiline_response(self):
        """Çok satırlı yanıt (SetNameTable vb.)."""
        response = (
            'Return(result="success" notify="updated"\n'
            'id="237" status="ok"\n'
            'id="5" status="ok")'
        )
        parser = RecordParser()
        # Parse edilebilmelidir
        result = parser.parse_response(response)
        assert result is not None

    def test_parse_response_without_newlines(self):
        """Yeni satır olmayan yanıt (normal TCP)."""
        response = 'Return(result="success" dev_id="123")'
        parser = RecordParser()
        result = parser.parse_response(response)
        assert result is not None

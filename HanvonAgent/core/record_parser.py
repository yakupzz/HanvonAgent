"""
Hanvon F710 TCP protokol yanıt parse işlemleri.

Referans: D:\Projeler\F710\referans\lib\hanvon\client.rb
"""

import re
from typing import List, Dict, Optional, Any


class RecordParser:
    """Hanvon protokol yanıtlarını parse eder."""

    @staticmethod
    def is_wait_response(response: str) -> bool:
        """Wait() yanıtını kontrol et (asenkron operasyon)."""
        return response.strip().startswith('Wait(')

    @staticmethod
    def parse_response(response: str) -> Optional[Dict[str, Any]]:
        """
        Genel yanıt parse (Return(...) formatı).

        Return(result="success" field1="value1" field2="value2" ...)

        Returns:
            Alanlar dict'i veya None (başarısız)
        """
        if not response.strip().startswith('Return('):
            return None

        # Return(...) içerisini al
        match = re.match(r'Return\((.*)\)\s*$', response.strip(), re.DOTALL)
        if not match:
            return None

        content = match.group(1)

        # Key="value" çiftlerini ayıkla
        fields = {}
        # Pattern: key="value" (value içinde escape edilmiş tırnak olabilir)
        pattern = r'(\w+)="([^"]*(?:\\"[^"]*)*)"'
        for key_match in re.finditer(pattern, content):
            key = key_match.group(1)
            value = key_match.group(2)
            # Escaped tırnak kaldır
            value = value.replace('\\"', '"')
            fields[key] = value

        return fields if fields else None

    @staticmethod
    def parse_get_record(response: str) -> List[Dict[str, str]]:
        """
        GetRecord() yanıtını parse.

        Return(result="success" dev_id="0"
          time="..." id="..." name="..." ...
          time="..." id="..." name="..." ...
        )

        Returns:
            Kayıt listesi
        """
        fields = RecordParser.parse_response(response)
        if not fields or fields.get('result') != 'success':
            return []

        # time= alanlarını kayıtlar olarak ayıkla
        records = []
        # response içinde time=" ile başlayan bölümleri bul
        time_pattern = r'time="([^"]*)"'
        time_matches = list(re.finditer(time_pattern, response))

        for i, time_match in enumerate(time_matches):
            # time_match başından bir sonraki time_match'e kadar (ya da sona kadar) olan substring
            start = time_match.start()
            if i + 1 < len(time_matches):
                end = time_matches[i + 1].start()
            else:
                end = response.rfind(')')

            record_str = response[start:end]

            # Bu record_str'den alanları çıkar
            record = {}
            pattern = r'(\w+)="([^"]*)"'
            for field_match in re.finditer(pattern, record_str):
                key = field_match.group(1)
                value = field_match.group(2).replace('\\"', '"')
                record[key] = value

            if 'time' in record:
                records.append(record)

        return records

    @staticmethod
    def parse_get_employee(response: str) -> Optional[Dict]:
        """
        GetEmployee() yanıtını parse.

        Cihaz 18 adet face_data alanı döner — parse_response() bunları
        dict'e yazarken üst üste yazar ve son değeri tutar. Bu metod
        *_data alanlarını (face_data, finger_data vb.) liste olarak toplar;
        her tür kendi anahtarı altında List[str] olarak döner.

        Returns:
            Personel dict'i; *_data anahtarları List[str] (18 öğe veya daha az).
            Başarısız ise None.
        """
        if not response.strip().startswith('Return('):
            return None

        match = re.match(r'Return\((.*)\)\s*$', response.strip(), re.DOTALL)
        if not match:
            return None

        content = match.group(1)
        fields: Dict[str, Any] = {}
        biometric: Dict[str, List[str]] = {}  # key → templates

        pattern = r'(\w+)="([^"]*(?:\\"[^"]*)*)"'
        for m in re.finditer(pattern, content):
            key = m.group(1)
            value = m.group(2).replace('\\"', '"')
            if key.endswith('_data'):
                biometric.setdefault(key, []).append(value)
            else:
                fields[key] = value

        if fields.get('result') != 'success':
            return None

        fields.update(biometric)  # face_data, finger_data vb. List[str] olarak eklenir

        return fields

    @staticmethod
    def parse_get_employee_id(response: str) -> List[str]:
        """
        GetEmployeeID() yanıtını parse.

        Return(result="success" total="364" id="237" id="177" id="5" ...)

        Returns:
            Personel ID listesi
        """
        fields = RecordParser.parse_response(response)
        if not fields or fields.get('result') != 'success':
            return []

        # response içinde tüm id="..." alanlarını bul
        ids = []
        pattern = r'id="(\d+)"'
        for match in re.finditer(pattern, response):
            employee_id = match.group(1)
            if employee_id not in ids:
                ids.append(employee_id)

        return ids

    @staticmethod
    def parse_get_device_info(response: str) -> Optional[Dict[str, str]]:
        """
        GetDeviceInfo() yanıtını parse.

        Return(result="success"
          dev_id="6710511030000079"
          time="2026-6-9 13:28:45"
          edition="3.006.089"
          ...
        )

        Returns:
            Cihaz bilgileri dict'i veya None (başarısız)
        """
        fields = RecordParser.parse_response(response)
        if not fields or fields.get('result') != 'success':
            return None

        return fields

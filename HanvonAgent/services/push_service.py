"""
Push servisi — Kayıtları harici API'ye gönder.
"""

import httpx
import time
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from models import Record, Setting


class PushService:
    """Kayıtları harici API'ye gönder (retry dahil)."""

    def __init__(
        self,
        session: Session,
        max_retries: int = 3,
        timeout: int = 10,
    ):
        self.session = session
        self.max_retries = max_retries
        self.timeout = timeout

    def push_pending_records(self) -> int:
        """
        Tüm pending kayıtları API'ye gönder.

        Returns:
            Başarıyla gönderilen kayıt sayısı
        """
        # API durumu pasifse gönderme
        if not self._is_api_active():
            return 0

        pending_records = self.session.query(Record).filter_by(
            push_status='pending'
        ).all()

        if not pending_records:
            return 0

        # API endpoint'i oku
        api_endpoint = self._get_api_endpoint()
        if not api_endpoint:
            return 0

        pushed_count = 0

        # Batch'ler halinde gönder (device bazlı)
        by_device = {}
        for record in pending_records:
            device_id = record.device_id
            if device_id not in by_device:
                by_device[device_id] = []
            by_device[device_id].append(record)

        for device_id, device_records in by_device.items():
            if self._push_batch(device_records, api_endpoint):
                pushed_count += len(device_records)

        return pushed_count

    def _push_batch(self, records: List[Record], api_endpoint: str) -> bool:
        """
        Batch kayıtları gönder.

        Returns:
            Başarı durumu
        """
        payload = self._build_payload(records)

        headers = {}
        api_token = self._get_api_token()
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                response = httpx.post(
                    api_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    # Başarılı
                    for record in records:
                        record.push_status = 'sent'
                        record.pushed_at = datetime.utcnow()

                    self.session.commit()
                    return True
                else:
                    # 4xx/5xx — retry
                    raise Exception(f"HTTP {response.status_code}")

            except Exception as e:
                retry_count += 1
                if retry_count > self.max_retries:
                    # Başarısız
                    for record in records:
                        record.push_status = 'failed'

                    self.session.commit()
                    return False

                # Exponential backoff
                wait_time = 2 ** (retry_count - 1)
                time.sleep(wait_time)

        return False

    def _build_payload(self, records: List[Record]) -> Dict[str, Any]:
        """
        Push payload oluştur.

        Format:
        {
            "records": [
                {
                    "device_ip": "...",
                    "record_time": "...",
                    "employee_id": "...",
                    "status": "...",
                    "card_src": "...",
                    "source": "device|manual"
                },
                ...
            ]
        }
        """
        payload = {
            'records': []
        }

        for record in records:
            payload['records'].append({
                'device_ip': record.device.ip,
                'record_time': record.record_time,
                'employee_id': record.employee.employee_device_id if record.employee else None,
                'employee_name': record.employee.name if record.employee else '',
                'status': record.status,
                'card_src': record.card_src,
                'source': record.source,
            })

        return payload

    def _get_api_endpoint(self) -> str:
        """Setting'den API endpoint'i oku."""
        setting = self.session.query(Setting).filter_by(key='api_endpoint').first()
        return setting.value if setting else None

    def _get_api_token(self) -> str:
        """Setting'den API token'ı oku."""
        setting = self.session.query(Setting).filter_by(key='api_token').first()
        return setting.value if setting else None

    def _is_api_active(self) -> bool:
        """api_status=1 ise True, aksi hâlde False."""
        setting = self.session.query(Setting).filter_by(key='api_status').first()
        return setting is not None and setting.value == '1'

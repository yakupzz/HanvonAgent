"""
Kayıt çekme ve dosyaya yazma servisi.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from models import Device, Employee, Record
from core.hanvon_client import HanvonClient


class RecordService:
    """Cihazdan kayıtları çek ve dosyaya kaydet."""

    def __init__(self, session: Session, data_dir: str = "data"):
        self.session = session
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def fetch_records(
        self,
        device: Device,
        start_date: str,
        end_date: str,
        reprocess: bool = False,
    ) -> dict:
        """
        Cihazdan kayıtları çek ve DB'ye kaydet.

        Args:
            device: Device nesnesi
            start_date: YYYY-M-D (ör. 2026-6-9)
            end_date: YYYY-M-D
            reprocess: True ise duplicate kontrol yap X, aynı verileri UPDATE et

        Returns:
            {'old_count': 0, 'new_count': N, 'total_count': N, 'records': [...]}
        """
        client = HanvonClient(
            device.ip,
            port=device.port,
            comm_key=device.comm_key,
        )

        try:
            client.connect()
            remote_records = client.get_record(
                start_time=f"{start_date} 0:0:0",
                end_time=f"{end_date} 23:59:59",
            )
            client.disconnect()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch records from {device.ip}: {str(e)}")

        # Dosya path'ı hazırla
        import logging
        logger = logging.getLogger("HanvonAgent.RecordService")

        today = datetime.now()
        pull_date = today.strftime("%Y-%m-%d")
        file_path = self.data_dir / today.strftime("%Y") / today.strftime("%m") / f"{today.strftime('%d')}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        created_records = []
        for remote_rec in remote_records:
            # Personel ID'ye göre employee bul
            emp_id = int(remote_rec.get('id', 0))
            employee = self.session.query(Employee).filter_by(
                device_id=device.id,
                employee_device_id=emp_id,
            ).first()

            # Cihazdan gelen ismi DB'ye yaz (boşsa veya farklıysa)
            remote_name = remote_rec.get('name', '').strip()
            if employee and remote_name and employee.name != remote_name:
                employee.name = remote_name
                self.session.add(employee)

            # Duplicate kontrol (reprocess ise geç)
            emp_id_str = str(emp_id) if emp_id > 0 else '?'
            if not reprocess and self.is_duplicate(
                device_id=device.id,
                record_time=remote_rec['time'],
                employee_device_id=emp_id_str,
            ):
                continue

            # Reprocess ise eski kaydı bul ve update et
            if reprocess:
                emp_id_str = str(emp_id) if emp_id > 0 else None
                existing = self.session.query(Record).filter(
                    Record.device_id == device.id,
                    Record.record_time == remote_rec['time'],
                    Record.employee_device_id == emp_id_str,
                ).first()

                if existing:
                    # Update et
                    existing.employee_id = employee.id if employee else None
                    existing.status = remote_rec.get('status', '')
                    existing.card_src = remote_rec.get('card_src', '')
                    existing.push_status = 'pending'
                    self.session.add(existing)
                    created_records.append(existing)
                    continue

            # Record oluştur + file_path ayarla
            record = Record(
                device_id=device.id,
                employee_id=employee.id if employee else None,
                employee_device_id=str(emp_id) if emp_id > 0 else None,
                record_time=remote_rec['time'],
                status=remote_rec.get('status', ''),
                card_src=remote_rec.get('card_src', ''),
                source='device',
                push_status='pending',
                file_path=str(file_path),
                pull_date=pull_date,
            )
            self.session.add(record)
            created_records.append(record)

        # ÖNCE: DB'ye commit (lazy load için)
        self.session.commit()

        # SONRA: Dosyaya kaydet
        if created_records:
            self.save_records_to_file(created_records)

        # Döndür
        return {
            "old_count": 0,
            "new_count": len(created_records),
            "total_count": len(created_records),
            "records": created_records
        }

    def save_records_to_file(self, record_objects: List[Record]) -> Path:
        """
        Kayıtları JSON dosyasına kaydet.

        Dosya: data/YYYY/MM/DD.json
        """
        if not record_objects:
            return None

        # Tarihe göre grupla
        by_date = {}
        for record in record_objects:
            date_str = record.record_time.split()[0]
            year, month, day = date_str.split('-')

            if date_str not in by_date:
                by_date[date_str] = {
                    'device_ip': record.device.ip,
                    'device_name': record.device.name,
                    'pulled_at': datetime.now().isoformat(),
                    'records': []
                }

            by_date[date_str]['records'].append({
                'time': record.record_time,
                'id': record.employee_device_id if record.employee_device_id else '?',
                'name': record.employee.name if record.employee else '',
                'status': record.status,
                'card_src': record.card_src,
            })

        # Dosyalara yaz
        for date_str, data in by_date.items():
            year, month, day = date_str.split('-')
            file_path = self.data_dir / year / month / f"{day}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Mevcut dosya varsa merge et
            if file_path.exists():
                with open(file_path, encoding='utf-8-sig') as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            else:
                existing = []

            # Yeni veriyi ekle
            device_data = next(
                (d for d in existing if d['device_ip'] == data['device_ip']),
                None
            )
            if device_data:
                # Mevcut kayıtları koru, sadece yeni olanları ekle (by time dedup)
                existing_times = {r['time'] for r in device_data['records']}
                for rec in data['records']:
                    if rec['time'] not in existing_times:
                        device_data['records'].append(rec)
                device_data['records'].sort(key=lambda x: x['time'])
                device_data['pulled_at'] = data['pulled_at']
                device_data['device_name'] = data['device_name']
            else:
                existing.append(data)

            # Manuel JSON: device pretty, records compact
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('[\n')
                for i, device_entry in enumerate(existing):
                    f.write('  {\n')
                    f.write(f'    "device_ip": "{device_entry["device_ip"]}",\n')
                    f.write(f'    "device_name": "{device_entry.get("device_name", "")}",\n')
                    f.write(f'    "pulled_at": "{device_entry["pulled_at"]}",\n')
                    f.write('    "records": [\n')

                    records = device_entry.get('records', [])
                    for j, rec in enumerate(records):
                        rec_json = json.dumps(rec, separators=(',', ':'))
                        f.write(f'      {rec_json}')
                        if j < len(records) - 1:
                            f.write(',')
                        f.write('\n')

                    f.write('    ]\n')
                    f.write('  }')
                    if i < len(existing) - 1:
                        f.write(',')
                    f.write('\n')
                f.write(']\n')

            # Record'ın file_path'ını güncelle
            for record in record_objects:
                if record.record_time.startswith(date_str):
                    record.file_path = str(file_path)

        self.session.commit()

    def is_duplicate(
        self,
        device_id: int,
        record_time: str,
        employee_device_id: str,
    ) -> bool:
        """
        Duplicate kayıt kontrol et.

        Unique: (device_id, record_time, employee_device_id)
        """
        existing = self.session.query(Record).filter_by(
            device_id=device_id,
            record_time=record_time,
            employee_device_id=employee_device_id,
        ).first()

        return existing is not None

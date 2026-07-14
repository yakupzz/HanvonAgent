"""
Device Transfer Service — Cihazdan cihaza personel aktarımı (biometrik ile).

Akış (personel başına):
1. Kaynak cihazdan GetEmployee → ad, kart, yüz verisi
   Cihaz offline/hata ise → DB'deki yerel biyometrik yedeğe fallback
2. Hedef cihazda GetEmployee → mevcut mu?
3. Hedefe SetEmployee → seçeneklere göre ad / biometrik gönder
4. DB'ye upsert + audit log

UI bloklamamak için DeviceTransferWorker (QThread) kullanılır.
"""

import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from core import app_paths
from core.hanvon_client import HanvonClient
from models import Device, Employee, SessionLocal

logger = logging.getLogger("HanvonAgent.DeviceTransfer")


def _get_audit_logger() -> logging.Logger:
    """Transfer audit logger — ayrı dosyaya yazar."""
    audit = logging.getLogger("HanvonAgent.TransferAudit")
    if audit.handlers:
        return audit

    audit.setLevel(logging.INFO)
    audit.propagate = False

    log_dir = app_paths.logs_dir()
    log_file = log_dir / "transfer_audit.log"

    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    audit.addHandler(handler)
    return audit


def _audit(msg: str) -> None:
    _get_audit_logger().info(msg)


def _db_upsert(session, target_device_id, employee_id, name, card_num,
               check_type, authority, calid, opendoor_type, face_data):
    """Hedef cihazın DB kaydını oluştur veya güncelle."""
    existing = session.query(Employee).filter_by(
        device_id=target_device_id,
        employee_device_id=int(employee_id),
    ).first()
    if existing:
        existing.name          = name
        existing.card_num      = card_num
        existing.check_type    = check_type
        existing.authority     = authority
        existing.calid         = calid
        existing.opendoor_type = opendoor_type
        existing.sync_status   = 'ok'
        existing.pending_name  = None
        existing.last_synced   = datetime.utcnow()
        if face_data:
            existing.face_data = face_data
    else:
        new_emp = Employee(
            device_id=target_device_id,
            employee_device_id=int(employee_id),
            name=name,
            card_num=card_num,
            check_type=check_type,
            authority=authority,
            calid=calid,
            opendoor_type=opendoor_type,
            sync_status='ok',
            last_synced=datetime.utcnow(),
        )
        if face_data:
            new_emp.face_data = face_data
        session.add(new_emp)
    session.commit()


def _employee_to_dict(emp: Employee) -> Optional[Dict]:
    """DB Employee nesnesini transfer_employee'nin beklediği dict formatına çevirir."""
    if not emp:
        return None
    return {
        'name':         emp.name or '',
        'card_num':     emp.card_num or '',
        'check_type':   emp.check_type or 'face',
        'authority':    emp.authority or '0X0',
        'calid':        emp.calid or '',
        'opendoor_type': emp.opendoor_type or (emp.check_type or 'face'),
        'face_data':    emp.face_data,  # List[str] — property
    }


def transfer_employee(
    source_client: HanvonClient,
    target_client: HanvonClient,
    employee_id: str,
    source_device_id: int,
    target_device_id: int,
    session,
    update_name: bool = True,
    update_biometric: bool = True,
) -> tuple:
    """
    Bir personeli kaynak cihazdan hedef cihaza aktar.

    source_client offline ise DB'deki yerel biyometrik yedeğe fallback yapılır.

    Returns:
        (success: bool, message: str)
    """
    source_ip = source_client.ip if source_client else "?"
    target_ip = target_client.ip if target_client else "?"
    prefix = f"src={source_ip} dst={target_ip} id={employee_id}"

    # 1. Kaynak verisi — cihazdan canlı, offline ise DB fallback
    source_data = None
    data_source = "cihaz"

    if source_client:
        try:
            source_data = source_client.get_employee(employee_id)
        except Exception as e:
            logger.warning("GetEmployee başarısız (%s): %s", employee_id, e)

    if not source_data:
        # DB'deki yerel yedek
        db_emp = session.query(Employee).filter_by(
            device_id=source_device_id,
            employee_device_id=int(employee_id),
        ).first()
        source_data = _employee_to_dict(db_emp)
        if source_data:
            data_source = "yerel_yedek"
            _audit(f"FALLBACK | {prefix} | kaynak offline, DB yedeği kullanılıyor")

    if not source_data:
        _audit(f"HATA | {prefix} | kaynak cihazda ve DB'de bulunamadı")
        return False, "kaynak cihazda ve yerel yedekte bulunamadı"

    _audit(f"KAYNAK | {prefix} | veri alındı ({data_source})"
           f" name='{source_data.get('name')}'"
           f" face_templates={len(source_data.get('face_data') or [])}")

    # 2. Hedefte var mı? — exception'ı yut ama nedeni logla
    target_data = None
    target_get_error = None
    try:
        target_data = target_client.get_employee(employee_id)
    except Exception as e:
        target_get_error = str(e)
        logger.warning("Hedef GetEmployee başarısız (%s): %s", employee_id, e)
    existed_on_target = target_data is not None

    if target_get_error and not existed_on_target:
        _audit(f"UYARI | {prefix} | hedef GetEmployee başarısız: {target_get_error} — yeni kayıt gibi işlenecek")

    # 3. Gönderilecek alanları hazırla
    target_current_name = (target_data.get('name', '') if target_data else None)

    if update_name:
        name = source_data.get('name', '')
    elif existed_on_target:
        name = target_current_name
    else:
        name = source_data.get('name', '')

    card_num      = source_data.get('card_num', '')
    authority     = source_data.get('authority', '0X0')
    check_type    = source_data.get('check_type', 'face')
    opendoor_type = source_data.get('opendoor_type', check_type)
    calid         = source_data.get('calid', '')
    face_data     = (source_data.get('face_data') or []) if update_biometric else []

    # Hiçbir şey değişmiyorsa gereksiz komut gönderme
    name_changed = update_name and (name != target_current_name)
    bio_changed  = update_biometric and bool(face_data)

    if existed_on_target and not name_changed and not bio_changed:
        _audit(f"ATLA | {prefix} | isim ve biyometrik zaten güncel ('{name}')")
        # DB'yi de güncelle (last_synced)
        _db_upsert(session, target_device_id, employee_id, name, card_num,
                   check_type, authority, calid, opendoor_type, face_data)
        return True, "değişiklik yok — atlandı"

    _audit(
        f"GÖNDER | {prefix}"
        f" | isim: '{target_current_name}' → '{name}'"
        f" | face={len(face_data)} templates"
        f" | hedefte_mevcut={existed_on_target}"
    )

    # Mevcut kayıt, sadece isim değişiyor → SetNameTable (daha hafif komut)
    # Yeni kayıt veya biyometrik de gönderilecekse → SetEmployee
    if existed_on_target and name_changed and not bio_changed:
        success = target_client.set_name_table({employee_id: name})
        cmd_used = "SetNameTable"
    else:
        success = target_client.set_employee(
            employee_id=employee_id,
            name=name,
            calid=calid,
            card_num=card_num,
            authority=authority,
            check_type=check_type,
            opendoor_type=opendoor_type,
            face_data=face_data,
        )
        cmd_used = "SetEmployee"

    if not success:
        _audit(f"HATA | {prefix} | hedef cihaz reddetti ({cmd_used})")
        return False, "hedef cihaz komutu reddetti"

    # 4. Doğrulama — yeni kayıt için zorunlu, güncelleme için isim değiştiyse kontrol et
    if not existed_on_target:
        verify = None
        try:
            verify = target_client.get_employee(employee_id)
        except Exception:
            pass
        if not verify:
            _audit(f"HATA | {prefix} | hedef 'success' dedi ama kayıt oluşmadı")
            return False, "hedef 'success' dedi ama kaydı OLUŞTURMADI (cihazda kayıt yok)"
    elif name_changed:
        # Mevcut kayıtta isim güncellemesini doğrula
        verify = None
        try:
            verify = target_client.get_employee(employee_id)
        except Exception:
            pass
        if verify:
            actual_name = verify.get('name', '')
            expected_ascii = HanvonClient._ascii_name(name)
            if actual_name != expected_ascii:
                _audit(
                    f"UYARI | {prefix}"
                    f" | cihaz 'success' dedi ama isim değişmedi"
                    f" (beklenen='{expected_ascii}' gerçek='{actual_name}')"
                )
                return False, f"isim cihazda değişmedi: beklenen='{expected_ascii}' gerçek='{actual_name}'"
        else:
            _audit(f"UYARI | {prefix} | güncelleme sonrası doğrulama okunamadı")

    # 5. DB upsert
    _db_upsert(session, target_device_id, employee_id, name, card_num,
               check_type, authority, calid, opendoor_type, face_data)

    if existed_on_target:
        if name_changed:
            detail = f"isim güncellendi: '{target_current_name}' → '{name}'"
        else:
            detail = "güncellendi"
        if update_biometric and face_data:
            detail += " + yüz verisi"
    else:
        detail = "yeni oluşturuldu"
        if update_biometric and face_data:
            detail += " + yüz verisi"

    _audit(f"TAMAM | {prefix} | {detail} (kaynak: {data_source}, komut: {cmd_used})")
    return True, detail


class DeviceTransferWorker(QThread):
    """
    Transfer işlemini arka planda yürüten worker.

    Sinyaller:
        progress(str): Tek satırlık durum mesajı (UI'da log'a eklenir).
        finished_all(int, int): (başarılı, başarısız) sayıları.
    """

    progress = Signal(str)
    finished_all = Signal(int, int)

    def __init__(
        self,
        source_device_id: int,
        target_device_id: int,
        employee_device_ids: List[str],
        update_name: bool = True,
        update_biometric: bool = True,
        session_factory: Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.source_device_id = source_device_id
        self.target_device_id = target_device_id
        self.employee_device_ids = employee_device_ids
        self.update_name = update_name
        self.update_biometric = update_biometric
        self._session_factory = session_factory or SessionLocal

    def run(self):
        """Thread gövdesi — kendi DB session'ı ile çalışır."""
        session = self._session_factory()
        source_client = None
        target_client = None
        source_device = None
        target_device = None
        src_ip = "?"
        dst_ip = "?"
        successful = 0
        failed = 0
        total = len(self.employee_device_ids)

        try:
            source_device = session.query(Device).filter_by(id=self.source_device_id).first()
            target_device = session.query(Device).filter_by(id=self.target_device_id).first()

            if not source_device or not target_device:
                self.progress.emit("❌ Cihaz kaydı bulunamadı")
                self.finished_all.emit(0, total)
                return

            src_ip = source_device.ip
            dst_ip = target_device.ip

            _audit(
                f"BAŞLAT | src={source_device.ip} dst={target_device.ip}"
                f" | {total} personel"
                f" | update_name={self.update_name} update_bio={self.update_biometric}"
            )

            # Kaynak bağlantısı — offline ise fallback çalışacak
            try:
                source_client = HanvonClient(source_device.ip, port=source_device.port, comm_key=source_device.comm_key)
                source_client.connect()
                self.progress.emit(f"✓ Kaynak bağlandı: {source_device.ip}")
                _audit(f"BAĞLANTI | src={source_device.ip} | OK")
            except Exception as e:
                self.progress.emit(
                    f"⚠️ Kaynak bağlanamadı ({source_device.ip}): {e}\n"
                    f"   → DB'deki yerel yedek kullanılacak"
                )
                _audit(f"BAĞLANTI | src={source_device.ip} | HATA: {e} → DB fallback")
                source_client = None

            target_client = HanvonClient(target_device.ip, port=target_device.port, comm_key=target_device.comm_key)
            target_client.connect()
            self.progress.emit(f"✓ Hedef bağlandı: {target_device.ip}\n")
            _audit(f"BAĞLANTI | dst={target_device.ip} | OK")

            for idx, emp_id in enumerate(self.employee_device_ids, 1):
                try:
                    ok, msg = transfer_employee(
                        source_client=source_client,
                        target_client=target_client,
                        employee_id=emp_id,
                        source_device_id=self.source_device_id,
                        target_device_id=self.target_device_id,
                        session=session,
                        update_name=self.update_name,
                        update_biometric=self.update_biometric,
                    )
                except Exception as e:
                    ok, msg = False, str(e)[:80]
                    logger.error("Transfer hatası (ID %s): %s", emp_id, e, exc_info=True)
                    _audit(f"EXCEPTION | id={emp_id} | {e}")

                icon = "✅" if ok else "❌"
                self.progress.emit(f"{idx}/{total}: ID {emp_id} → {icon} {msg}")

                if ok:
                    successful += 1
                else:
                    failed += 1

        except Exception as e:
            logger.error("Transfer bağlantı hatası: %s", e, exc_info=True)
            self.progress.emit(f"\n❌ Bağlantı hatası: {str(e)}")
            _audit(f"FATAL | {e}")
            failed = total - successful

        finally:
            for client in (source_client, target_client):
                if client:
                    try:
                        client.disconnect()
                    except Exception:
                        pass
            try:
                session.close()
            except Exception:
                pass

        _audit(
            f"BİTTİ | src={src_ip} dst={dst_ip}"
            f" | başarılı={successful} başarısız={failed}"
        )
        self.finished_all.emit(successful, failed)

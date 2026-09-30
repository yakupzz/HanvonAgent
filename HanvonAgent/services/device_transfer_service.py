"""
Device Transfer Service — Cihazdan cihaza personel aktarımı (biometrik ile).

Akış (personel başına):
1. Kaynak cihazdan GetEmployee → ad, kart, yüz verisi
   Cihaz offline/hata ise → DB'deki yerel biyometrik yedeğe fallback
2. Hedef cihazda GetEmployee → mevcut mu? (okunamazsa DUR — üzerine yazma yok)
3. Hedefte aynı ID'de başka kişi varsa → açık izin yoksa atla
4. Yalnız değişen gönderilir: isim → SetNameTable, yeni kayıt/yüz → SetEmployee
5. Doğrulama + DB upsert + audit log

UI bloklamamak için DeviceTransferWorker (QThread) kullanılır.
"""

import logging
import logging.handlers
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from core import app_paths
from core.hanvon_client import HanvonClient
from models import Device, Employee, SessionLocal
from services.employee_sync_service import normalize_name

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


TRANSFER_OK = "ok"
TRANSFER_SKIPPED = "skipped"
TRANSFER_FAILED = "failed"

_STATUS_ICONS = {TRANSFER_OK: "✅", TRANSFER_SKIPPED: "⏭", TRANSFER_FAILED: "❌"}


@dataclass(frozen=True)
class TransferItem:
    """Aktarılacak tek personel ve ona özel seçenekler."""
    employee_id: str
    update_name: bool = True
    update_biometric: bool = True
    allow_overwrite_other_person: bool = False


def is_different_person(src_name, src_faces, tgt_name, tgt_faces) -> bool:
    """Aynı ID'de hedefte BAŞKA bir kişi mi kayıtlı?

    Yüz şablonları iki tarafta da varsa belirleyici onlardır: birebir aynıysa
    kayıt kopyalanmıştır → aynı kişi (yalnız etiket farklı olabilir). Farklıysa
    ve isimler de aynı kişiyi göstermiyorsa → başka kişi. Yüz yoksa: iki isim
    de dolu ve farklıysa başka kişi sayılır.
    """
    src_key, tgt_key = normalize_name(src_name), normalize_name(tgt_name)
    same_name = bool(src_key) and src_key == tgt_key
    if src_faces and tgt_faces:
        return list(src_faces) != list(tgt_faces) and not same_name
    return bool(src_key) and bool(tgt_key) and not same_name


def _reconnect(client: Optional[HanvonClient], label: str) -> None:
    """Hata/timeout sonrası akış kaymış olabilir — yeni bağlantı aç (BUG-014 dersi)."""
    if client is None:
        return
    try:
        client.disconnect()
        client.connect()
    except Exception as e:  # noqa: BLE001 — sonraki komutlar zaten hata verip raporlanır
        logger.warning("%s yeniden bağlanamadı: %s", label, e)


def _read_source(source_client, employee_id, source_device_id, session, prefix):
    """Kaynak verisi: cihazdan canlı; okunamazsa/yoksa DB'deki yerel yedek.

    Returns:
        (data | None, "cihaz" | "yerel_yedek" | None)
    """
    if source_client:
        try:
            data = source_client.get_employee(employee_id)
            if data:
                return data, "cihaz"
        except Exception as e:  # noqa: BLE001
            logger.warning("GetEmployee başarısız (%s): %s", employee_id, e)
            _reconnect(source_client, f"kaynak {source_client.ip}")

    db_emp = session.query(Employee).filter_by(
        device_id=source_device_id, employee_device_id=int(employee_id),
    ).first()
    data = _employee_to_dict(db_emp)
    if data:
        _audit(f"FALLBACK | {prefix} | kaynak cihazdan okunamadı, DB yedeği kullanılıyor")
        return data, "yerel_yedek"
    return None, None


def _plan(source_data, target_data, update_name, update_biometric):
    """Hedefe yazılacak isim/yüz ve neyin değiştiği.

    Kaynak isim boşsa hedefteki isim KORUNUR (ID 157 dersi). Karşılaştırma
    normalize_name ile — cihaz ASCII sakladığı için ÖNEM/ONEM değişiklik değil.
    """
    existed = target_data is not None
    target_name = target_data.get('name', '') if existed else ''
    target_faces = (target_data.get('face_data') or []) if existed else []
    src_name = source_data.get('name', '')

    if not existed or (update_name and normalize_name(src_name)):
        name = src_name
    else:
        name = target_name
    face_data = (source_data.get('face_data') or []) if update_biometric else []
    return {
        "existed": existed,
        "target_name": target_name,
        "name": name,
        "face_data": face_data,
        "name_changed": existed and normalize_name(name) != normalize_name(target_name),
        "bio_changed": bool(face_data) and (not existed or list(face_data) != list(target_faces)),
    }


def _send(target_client, employee_id, source_data, plan):
    """Mevcut kayıtta yalnız isim → SetNameTable; yeni kayıt veya yüz → SetEmployee."""
    if plan["existed"] and plan["name_changed"] and not plan["bio_changed"]:
        return target_client.set_name_table({employee_id: plan["name"]}), "SetNameTable"
    check_type = source_data.get('check_type', 'face')
    success = target_client.set_employee(
        employee_id=employee_id,
        name=plan["name"],
        calid=source_data.get('calid', ''),
        card_num=source_data.get('card_num', ''),
        authority=source_data.get('authority', '0X0'),
        check_type=check_type,
        opendoor_type=source_data.get('opendoor_type', check_type),
        face_data=plan["face_data"],
    )
    return success, "SetEmployee"


def _verify(target_client, employee_id, plan, prefix) -> Optional[str]:
    """Yazma sonrası doğrulama. Hata metni ya da None (tamam) döner."""
    if plan["existed"] and not plan["name_changed"]:
        return None
    try:
        verify = target_client.get_employee(employee_id)
    except Exception as e:  # noqa: BLE001
        _reconnect(target_client, f"hedef {target_client.ip}")
        if not plan["existed"]:
            return f"doğrulama okunamadı ({e}) — kayıt oluştu mu bilinmiyor"
        _audit(f"UYARI | {prefix} | güncelleme sonrası doğrulama okunamadı: {e}")
        return None

    if not plan["existed"]:
        return None if verify else "hedef 'success' dedi ama kaydı OLUŞTURMADI (cihazda kayıt yok)"
    if verify is None:
        _audit(f"UYARI | {prefix} | güncelleme sonrası doğrulama okunamadı")
        return None
    expected = plan["name"]  # cihaz ASCII saklar; normalize_name ikisini de katlar
    actual = verify.get('name', '')
    if normalize_name(actual) != normalize_name(expected):
        _audit(f"UYARI | {prefix} | cihaz 'success' dedi ama isim değişmedi"
               f" (beklenen='{expected}' gerçek='{actual}')")
        return f"isim cihazda değişmedi: beklenen='{expected}' gerçek='{actual}'"
    return None


def _upsert(session, target_device_id, employee_id, data, name, face_data):
    _db_upsert(
        session, target_device_id, employee_id, name,
        data.get('card_num', ''), data.get('check_type', 'face'), data.get('authority', '0X0'),
        data.get('calid', ''), data.get('opendoor_type', data.get('check_type', 'face')), face_data,
    )


def _detail(plan) -> str:
    if not plan["existed"]:
        detail = "yeni oluşturuldu"
    elif plan["name_changed"]:
        detail = f"isim güncellendi: '{plan['target_name']}' → '{plan['name']}'"
    else:
        detail = "güncellendi"
    if plan["bio_changed"]:
        detail += " + yüz verisi"
    return detail


def transfer_employee(
    source_client: Optional[HanvonClient],
    target_client: HanvonClient,
    employee_id: str,
    source_device_id: int,
    target_device_id: int,
    session,
    update_name: bool = True,
    update_biometric: bool = True,
    allow_overwrite_other_person: bool = False,
) -> Tuple[str, str]:
    """
    Bir personeli kaynak cihazdan hedef cihaza aktar.

    Güvenlik kuralları (BUG-017/018):
    - Hedef okunamazsa ASLA "yeni kayıt" sayılıp üzerine yazılmaz → başarısız.
    - Hedefte aynı ID'de başka kişi varsa (is_different_person) açık izin
      olmadan dokunulmaz → atlandı.

    Returns:
        (TRANSFER_OK | TRANSFER_SKIPPED | TRANSFER_FAILED, mesaj)
    """
    target_ip = target_client.ip if target_client else "?"
    prefix = f"src={source_client.ip if source_client else '?'} dst={target_ip} id={employee_id}"

    source_data, data_source = _read_source(source_client, employee_id, source_device_id, session, prefix)
    if not source_data:
        _audit(f"HATA | {prefix} | kaynak cihazda ve DB'de bulunamadı")
        return TRANSFER_FAILED, "kaynak cihazda ve yerel yedekte bulunamadı"
    _audit(f"KAYNAK | {prefix} | veri alındı ({data_source}) name='{source_data.get('name')}'"
           f" face_templates={len(source_data.get('face_data') or [])}")

    try:
        target_data = target_client.get_employee(employee_id)
    except Exception as e:  # noqa: BLE001
        _reconnect(target_client, f"hedef {target_ip}")
        _audit(f"ATLA | {prefix} | hedef okunamadı: {e} — üzerine yazılmadı")
        return TRANSFER_FAILED, f"hedef okunamadı ({e}) — üzerine yazılmadı"

    if target_data is not None and is_different_person(
            source_data.get('name', ''), source_data.get('face_data') or [],
            target_data.get('name', ''), target_data.get('face_data') or []):
        if not allow_overwrite_other_person:
            _audit(f"ÇAKIŞMA | {prefix} | hedefte başka kişi: '{target_data.get('name', '')}' — atlandı")
            return TRANSFER_SKIPPED, (f"ÇAKIŞMA — hedefte bu ID'de başka kişi var "
                                      f"('{target_data.get('name', '')}'), atlandı")
        _audit(f"ÜZERİNE YAZ | {prefix} | hedefteki '{target_data.get('name', '')}' kullanıcı onayıyla değiştiriliyor")

    plan = _plan(source_data, target_data, update_name, update_biometric)
    if plan["existed"] and not plan["name_changed"] and not plan["bio_changed"]:
        _audit(f"ATLA | {prefix} | isim ve biyometrik zaten aynı ('{plan['target_name']}')")
        _upsert(session, target_device_id, employee_id, target_data, plan["target_name"],
                target_data.get('face_data') or [])
        return TRANSFER_OK, "zaten aynı — komut gönderilmedi"

    _audit(f"GÖNDER | {prefix} | isim: '{plan['target_name']}' → '{plan['name']}'"
           f" | face={len(plan['face_data'])} | hedefte_mevcut={plan['existed']}")
    try:
        success, cmd_used = _send(target_client, employee_id, source_data, plan)
    except Exception as e:  # noqa: BLE001
        _reconnect(target_client, f"hedef {target_ip}")
        _audit(f"HATA | {prefix} | gönderim hatası: {e}")
        return TRANSFER_FAILED, f"gönderim hatası: {e}"
    if not success:
        _audit(f"HATA | {prefix} | hedef cihaz reddetti ({cmd_used})")
        return TRANSFER_FAILED, "hedef cihaz komutu reddetti"

    error = _verify(target_client, employee_id, plan, prefix)
    if error:
        return TRANSFER_FAILED, error

    _upsert(session, target_device_id, employee_id, source_data, plan["name"], plan["face_data"])
    detail = _detail(plan)
    _audit(f"TAMAM | {prefix} | {detail} (kaynak: {data_source}, komut: {cmd_used})")
    return TRANSFER_OK, detail


class DeviceTransferWorker(QThread):
    """
    Transfer işlemini arka planda yürüten worker.

    Sinyaller:
        progress(str): Tek satırlık durum mesajı (UI'da log'a eklenir).
        finished_all(int, int, int): (başarılı, başarısız, atlanan) sayıları.
    """

    progress = Signal(str)
    finished_all = Signal(int, int, int)

    def __init__(
        self,
        source_device_id: int,
        target_device_id: int,
        employee_device_ids: Optional[List[str]] = None,
        update_name: bool = True,
        update_biometric: bool = True,
        session_factory: Optional[Callable] = None,
        parent=None,
        items: Optional[List[TransferItem]] = None,
    ):
        """items verilirse kişi bazında seçenek kullanılır; verilmezse
        employee_device_ids + genel update_name/update_biometric bayrakları."""
        super().__init__(parent)
        self.source_device_id = source_device_id
        self.target_device_id = target_device_id
        if items is None:
            items = [TransferItem(str(i), update_name, update_biometric)
                     for i in (employee_device_ids or [])]
        self.items = list(items)
        self._session_factory = session_factory or SessionLocal

    def _connect_source(self, device) -> Optional[HanvonClient]:
        """Kaynak bağlantısı — olmazsa None (DB yedeği kullanılır)."""
        try:
            client = HanvonClient(device.ip, port=device.port, comm_key=device.comm_key)
            client.connect()
            self.progress.emit(f"✓ Kaynak bağlandı: {device.ip}")
            _audit(f"BAĞLANTI | src={device.ip} | OK")
            return client
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"⚠️ Kaynak bağlanamadı ({device.ip}): {e}\n   → DB'deki yerel yedek kullanılacak")
            _audit(f"BAĞLANTI | src={device.ip} | HATA: {e} → DB fallback")
            return None

    def _transfer_all(self, session, source_client, target_client) -> Dict[str, int]:
        counts = {TRANSFER_OK: 0, TRANSFER_FAILED: 0, TRANSFER_SKIPPED: 0}
        total = len(self.items)
        for idx, item in enumerate(self.items, 1):
            try:
                status, msg = transfer_employee(
                    source_client, target_client, item.employee_id,
                    self.source_device_id, self.target_device_id, session,
                    update_name=item.update_name,
                    update_biometric=item.update_biometric,
                    allow_overwrite_other_person=item.allow_overwrite_other_person,
                )
            except Exception as e:  # noqa: BLE001
                status, msg = TRANSFER_FAILED, str(e)[:80]
                logger.error("Transfer hatası (ID %s): %s", item.employee_id, e, exc_info=True)
                _audit(f"EXCEPTION | id={item.employee_id} | {e}")
                _reconnect(source_client, "kaynak")
                _reconnect(target_client, "hedef")
            counts[status] += 1
            self.progress.emit(f"{idx}/{total}: ID {item.employee_id} → {_STATUS_ICONS[status]} {msg}")
        return counts

    def run(self):
        """Thread gövdesi — kendi DB session'ı ile çalışır."""
        session = self._session_factory()
        source_client = target_client = None
        counts = {TRANSFER_OK: 0, TRANSFER_FAILED: 0, TRANSFER_SKIPPED: 0}
        src_ip = dst_ip = "?"
        try:
            source_device = session.query(Device).filter_by(id=self.source_device_id).first()
            target_device = session.query(Device).filter_by(id=self.target_device_id).first()
            if not source_device or not target_device:
                self.progress.emit("❌ Cihaz kaydı bulunamadı")
                counts[TRANSFER_FAILED] = len(self.items)
                return
            src_ip, dst_ip = source_device.ip, target_device.ip
            _audit(f"BAŞLAT | src={src_ip} dst={dst_ip} | {len(self.items)} personel")

            source_client = self._connect_source(source_device)
            target_client = HanvonClient(target_device.ip, port=target_device.port,
                                         comm_key=target_device.comm_key)
            target_client.connect()
            self.progress.emit(f"✓ Hedef bağlandı: {target_device.ip}\n")
            _audit(f"BAĞLANTI | dst={dst_ip} | OK")

            counts = self._transfer_all(session, source_client, target_client)
        except Exception as e:  # noqa: BLE001
            logger.error("Transfer bağlantı hatası: %s", e, exc_info=True)
            self.progress.emit(f"\n❌ Bağlantı hatası: {str(e)}")
            _audit(f"FATAL | {e}")
            done = counts[TRANSFER_OK] + counts[TRANSFER_SKIPPED]
            counts[TRANSFER_FAILED] = len(self.items) - done
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
            _audit(f"BİTTİ | src={src_ip} dst={dst_ip} | başarılı={counts[TRANSFER_OK]}"
                   f" başarısız={counts[TRANSFER_FAILED]} atlanan={counts[TRANSFER_SKIPPED]}")
            self.finished_all.emit(counts[TRANSFER_OK], counts[TRANSFER_FAILED], counts[TRANSFER_SKIPPED])

"""
EmployeeSyncService — Personel inline edit ve cihaza gönderme iş mantığı.

Akış:
1. Kullanıcı tabloda ismi değiştirir -> mark_pending() çağrılır
   (pending_name set edilir, sync_status="yeni", orijinal name korunur).
2. Kullanıcı "Gönder" (📤) butonuna basar -> push_employee() çağrılır
   (cihaza SetNameTable gönderilir; başarılıysa pending -> name, sync="ok").
3. Aynı personel ID'si başka cihazlarda da kayıtlıysa (her cihazın ayrı
   Employee satırı var) propagate_pending() bekleyen ismi o satırlara da
   işaretler; her biri kendi cihazına ayrıca push edilir.

MVC: Bu modül saf iş mantığıdır; UI veya QThread bilgisi içermez.
HanvonClient dışarıdan enjekte edilebilir (test için mock'lanır).
"""

import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Employee, Device
from core.hanvon_client import HanvonClient

logger = logging.getLogger("HanvonAgent.EmployeeSync")


def compute_sync_status(employee: Employee) -> str:
    """Bekleyen değişiklik durumuna göre sync_status hesapla.

    Returns:
        "yeni" eğer gönderilmeyi bekleyen bir isim varsa, aksi halde "ok".
    """
    if employee.pending_name:
        return "yeni"
    return "ok"


def mark_pending(session: Session, employee: Employee, new_name: str) -> Employee:
    """İnline edit sonrası bekleyen isim değişikliğini işaretle.

    Args:
        session: Aktif DB oturumu.
        employee: Düzenlenen personel.
        new_name: Kullanıcının girdiği yeni isim.

    Returns:
        Güncellenmiş Employee.

    Raises:
        ValueError: new_name boş ise veya 255 karakterden uzunsa.
    """
    cleaned = (new_name or "").strip()
    if not cleaned:
        raise ValueError("İsim boş olamaz")
    if len(cleaned) > 255:
        raise ValueError("İsim 255 karakterden uzun olamaz")

    current = (employee.name or "").strip()
    if cleaned == current:
        # Mevcut isimle aynı -> bekleyen değişikliği temizle
        employee.pending_name = None
        employee.sync_status = "ok"
    else:
        employee.pending_name = cleaned
        employee.sync_status = "yeni"

    session.commit()
    return employee


def find_siblings(session: Session, employee: Employee) -> List[Employee]:
    """Aynı personel ID'siyle (employee_device_id) BAŞKA cihazlarda kayıtlı satırlar."""
    return (
        session.query(Employee)
        .filter(
            Employee.employee_device_id == employee.employee_device_id,
            Employee.device_id != employee.device_id,
        )
        .order_by(Employee.device_id)
        .all()
    )


def siblings_to_update(session: Session, employee: Employee) -> List[Employee]:
    """Bekleyen yeni isme henüz sahip olmayan kardeş satırlar.

    employee'de bekleyen isim yoksa boş liste döner. Cihazdaki ismi zaten
    yeni isimle aynı olan kardeşler atlanır (gönderilecek bir şey yok).
    """
    target = (employee.pending_name or "").strip()
    if not target:
        return []
    return [s for s in find_siblings(session, employee) if (s.name or "").strip() != target]


def propagate_pending(session: Session, employee: Employee) -> List[Employee]:
    """employee'nin bekleyen ismini kardeş satırlara bekleyen değişiklik olarak işaretle.

    Returns:
        İşaretlenen (kendi cihazlarına gönderilmesi gereken) kardeş satırlar.
    """
    siblings = siblings_to_update(session, employee)
    for sibling in siblings:
        mark_pending(session, sibling, employee.pending_name)
    return siblings


def push_employee(
    session: Session,
    employee: Employee,
    device: Device,
    client: Optional[HanvonClient] = None,
) -> Tuple[bool, str]:
    """Bekleyen isim değişikliğini cihaza gönder (SetNameTable, tek kayıt).

    Başarılıysa pending_name -> name uygulanır, sync_status "ok" olur.
    Başarısızsa bekleyen değişiklik korunur ve hata mesajı döner.

    Args:
        session: Aktif DB oturumu.
        employee: Gönderilecek personel.
        device: Hedef cihaz (ip + comm_key).
        client: Enjekte edilen HanvonClient (test için). None ise oluşturulur.

    Returns:
        (success, message) tuple'ı.
    """
    if not employee.pending_name:
        # Gönderilecek bir şey yok -> no-op başarı
        return True, ""

    pending = employee.pending_name
    owns_client = client is None

    try:
        if client is None:
            client = HanvonClient(device.ip, port=device.port, comm_key=device.comm_key)
            client.connect()

        # SetNameTable kullan (SetEmployee yerine)
        success = client.set_name_table({
            str(employee.employee_device_id): pending
        })
    except Exception as e:  # noqa: BLE001 — kullanıcıya gösterilecek tüm hatalar
        logger.error(
            "push_employee başarısız (emp=%s): %s",
            employee.employee_device_id, e,
        )
        return False, str(e)
    finally:
        if owns_client and client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    if not success:
        msg = f"Cihaz {device.ip} isim güncellemesini reddetti"
        logger.warning("push_employee reddedildi (emp=%s)", employee.employee_device_id)
        return False, msg

    # Başarılı: bekleyen ismi kalıcı yap
    employee.name = pending
    employee.pending_name = None
    employee.sync_status = "ok"
    session.commit()
    logger.info(
        "push_employee başarılı (emp=%s -> '%s')",
        employee.employee_device_id, pending,
    )
    return True, ""

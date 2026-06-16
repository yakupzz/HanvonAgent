"""
Zamanlama servisi — APScheduler ile cihaz bazlı otomatik çekme.

Ayar formatı (Setting tablosu):
  key  : schedule_{device_id}
  value: "frequency|HH:MM,HH:MM,...|durum"
         durum: 1=açık, 0=kapalı
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core import app_paths
from models import Device, Setting, get_session
from services.record_service import RecordService
from services.push_service import PushService

logger = logging.getLogger(__name__)


class SchedulerService:
    """APScheduler wrapper — cihaz bazlı otomatik çekme ve push."""

    def __init__(self, session=None):
        # session parametresi geriye dönük uyumluluk için tutulur, kullanılmaz.
        self.scheduler = BackgroundScheduler()

    # ------------------------------------------------------------------
    # Yaşam döngüsü
    # ------------------------------------------------------------------

    def start(self):
        """Scheduler'ı başlat; zaten çalışıyorsa yeniden başlatma."""
        if self.scheduler.running:
            return
        self._load_device_jobs()
        self._schedule_push()
        self.scheduler.start()
        logger.info("[ZAMANLAMA] SchedulerService başlatıldı")

    def stop(self):
        """Scheduler'ı durdur."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[ZAMANLAMA] SchedulerService durduruldu")

    # ------------------------------------------------------------------
    # Dinamik yeniden yükleme (ayarlar değiştiğinde çağrılır)
    # ------------------------------------------------------------------

    def reload_schedules(self):
        """
        Settings sekmesinden kaydedildiğinde çağrılır.
        Mevcut cihaz job'larını temizler ve DB'den yeniden yükler.
        """
        for job in self.scheduler.get_jobs():
            if job.id.startswith("device_"):
                try:
                    self.scheduler.remove_job(job.id)
                except Exception:
                    pass
        self._load_device_jobs()
        logger.info("[ZAMANLAMA] Cihaz job'ları yeniden yüklendi")

    # ------------------------------------------------------------------
    # İç yükleme
    # ------------------------------------------------------------------

    def _load_device_jobs(self):
        """
        DB'deki schedule_{device_id} ayarlarını oku.
        Her etkin cihaz için belirlenen saatlerde CronTrigger job ekle.
        """
        session = get_session()
        try:
            devices = session.query(Device).all()
            job_count = 0

            for device in devices:
                setting = session.query(Setting).filter_by(
                    key=f"schedule_{device.id}"
                ).first()
                if not setting:
                    continue

                # Format: "frequency|HH:MM,HH:MM,...|durum"
                parts = setting.value.split("|")
                if len(parts) < 3:
                    continue

                try:
                    freq = int(parts[0])
                except ValueError:
                    continue

                times_list = parts[1].split(",")[:freq]
                is_enabled = parts[2] == "1"

                if not is_enabled:
                    logger.debug(f"[ZAMANLAMA] {device.name} devre dışı, atlandı")
                    continue

                for i, time_str in enumerate(times_list):
                    time_str = time_str.strip()
                    if ":" not in time_str:
                        continue
                    try:
                        hour, minute = map(int, time_str.split(":"))
                    except ValueError:
                        continue

                    self.scheduler.add_job(
                        _run_auto_fetch,
                        CronTrigger(hour=hour, minute=minute),
                        args=[device.id],
                        id=f"device_{device.id}_slot_{i}",
                        name=f"[OtoCekme] {device.name} {time_str}",
                        replace_existing=True,
                    )
                    job_count += 1
                    logger.info(
                        f"[ZAMANLAMA] {device.name} ({device.ip}) → her gün {time_str}"
                    )

            logger.info(f"[ZAMANLAMA] {job_count} otomatik çekme job'u yüklendi")

        except Exception as e:
            logger.error(f"[ZAMANLAMA] Job yükleme hatası: {e}", exc_info=True)
        finally:
            session.close()

    def _schedule_push(self):
        """Push job'unu zamanla (push_status / push_interval ayarları)."""
        session = get_session()
        try:
            push_status_row = session.query(Setting).filter_by(key="push_status").first()
            push_interval_row = session.query(Setting).filter_by(key="push_interval").first()

            is_enabled = push_status_row and push_status_row.value == "1"
            interval_min = int(push_interval_row.value) if push_interval_row else 5

            if not is_enabled:
                logger.info("[ZAMANLAMA] Push servisi devre dışı")
                return

            self.scheduler.add_job(
                _run_auto_push,
                "interval",
                minutes=interval_min,
                id="auto_push",
                name="[AutoPush]",
                replace_existing=True,
            )
            logger.info(f"[ZAMANLAMA] Auto push → her {interval_min} dakika")

        except Exception as e:
            logger.error(f"[ZAMANLAMA] Push job hatası: {e}", exc_info=True)
        finally:
            session.close()

    def get_jobs(self):
        """Aktif job listesi."""
        return self.scheduler.get_jobs()


# ------------------------------------------------------------------
# Arka plan thread işlevleri (module-level → picklable)
# ------------------------------------------------------------------

def _run_auto_fetch(device_id: int):
    """
    Zamanlanmış otomatik çekme.
    Kendi SQLAlchemy oturumunu oluşturur (thread-safe).
    """
    session = get_session()
    try:
        device = session.query(Device).filter_by(id=device_id).first()
        if not device:
            logger.error(
                f"[OTOMATIK CEKME LOGU] Cihaz bulunamadı: id={device_id}"
            )
            return

        today = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        logger.info(
            f"[OTOMATIK CEKME LOGU] ===== BAŞLADI ===== "
            f"{device.name} ({device.ip}) | {now_str}"
        )

        data_dir = str(app_paths.data_dir())
        record_service = RecordService(session, data_dir=data_dir)
        result = record_service.fetch_records(
            device, start_date=today, end_date=today
        )

        new_count = result.get("new_count", 0)

        logger.info(
            f"[OTOMATIK CEKME LOGU] {device.name} ({device.ip}): "
            f"{new_count} yeni kayıt | {today}"
        )

        # Çekme sonrası cihazdan silme ayarı kontrol et
        delete_setting = session.query(Setting).filter_by(
            key=f"delete_after_pull_{device_id}"
        ).first()
        if delete_setting and delete_setting.value == "1":
            from core.hanvon_client import HanvonClient
            try:
                client = HanvonClient(device.ip, comm_key=device.comm_key)
                client.connect()
                ok = client.delete_all_records_now()
                client.disconnect()
                if ok:
                    logger.info(
                        f"[OTOMATIK CEKME LOGU] {device.name}: cihazdaki G/C kayıtları silindi"
                    )
                else:
                    logger.warning(
                        f"[OTOMATIK CEKME LOGU] {device.name}: DeleteAllRecord başarısız"
                    )
            except Exception as del_err:
                logger.error(
                    f"[OTOMATIK CEKME LOGU] {device.name}: silme hatası — {del_err}"
                )

    except Exception as e:
        logger.error(
            f"[OTOMATIK CEKME LOGU] HATA — device_id={device_id}: {e}",
            exc_info=True,
        )
    finally:
        session.close()


def _run_auto_push():
    """Auto push — kendi oturumunu oluşturur (thread-safe)."""
    session = get_session()
    try:
        push_service = PushService(session)
        count = push_service.push_pending_records()
        logger.info(f"[AUTO PUSH] {count} kayıt gönderildi")
    except Exception as e:
        logger.error(f"[AUTO PUSH] Hata: {e}", exc_info=True)
    finally:
        session.close()

"""
HanvonAgent — Ana uygulama başlatıcısı.

Masaüstü uygulaması (PySide6 + System Tray)
"""

import sys
import logging
import os
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QApplication
from core import app_paths
from models import init_db
from ui.main_window import MainWindow
from services.service_manager import ServiceManager, build_default_config


def setup_console_logging():
    """Exe klasöründe logs klasörü aç, stdout/stderr'ı buraya redirect et."""
    # Exe klasöründe logs klasörü
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller bundled exe
        exe_dir = Path(sys._MEIPASS).parent
    else:
        # Dev mode
        exe_dir = Path(__file__).parent.parent

    logs_dir = exe_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Log dosyası
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"hanvon_app_{timestamp}.log"

    # Dosya açık tut
    try:
        log_fp = open(log_file, 'a', encoding='utf-8', buffering=1)
        # stdout ve stderr'ı redirect etme — console'da görmek istiyoruz
        # sys.stdout = log_fp
        # sys.stderr = log_fp
        print(f"[LOG] Logging başladı: {log_file}")
        return log_fp
    except Exception as e:
        print(f"[ERROR] Log dosyası açılamadı: {e}")
        return None

#: Service admin subcommands recognised on the ``--svc-admin`` branch.
_SVC_ADMIN_ACTIONS = ("install", "remove", "start", "stop")


# ANSI renk kodları
class ColorFormatter(logging.Formatter):
    """Renkli logging formatter."""

    # Renk kodları
    RESET = '\033[0m'
    BOLD = '\033[1m'

    # Ön renk kodları
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Level renkler
    LEVEL_COLORS = {
        'DEBUG': CYAN,
        'INFO': GREEN,
        'WARNING': YELLOW,
        'ERROR': RED,
        'CRITICAL': RED + BOLD,
    }

    def format(self, record):
        # Önce formatTime çağır
        if not hasattr(record, 'asctime'):
            record.asctime = self.formatTime(record, self.datefmt)

        # Level rengi
        levelname = record.levelname
        if levelname in self.LEVEL_COLORS:
            color = self.LEVEL_COLORS[levelname]
            record.levelname = f"{color}{levelname}{self.RESET}"

        # Timestamp (gri)
        record.asctime = f"{self.CYAN}{record.asctime}{self.RESET}"

        # Mesaj renglendirme
        msg = record.msg

        # Giden veri (yeşil) - → veya "Gönderiliyor"
        if '→' in msg or 'gönderiliyor' in msg.lower():
            record.msg = f"{self.GREEN}{msg}{self.RESET}"
        # Gelen veri (sarı) - ← veya "Alındı"
        elif '←' in msg or 'alindi' in msg.lower() or 'chunk' in msg.lower():
            record.msg = f"{self.YELLOW}{msg}{self.RESET}"
        # Hata (kırmızı)
        elif 'hata' in msg.lower() or 'error' in msg.lower():
            record.msg = f"{self.RED}{msg}{self.RESET}"
        # Başarı (yeşil)
        elif 'ok' in msg.lower() or 'basarili' in msg.lower():
            record.msg = f"{self.GREEN}{msg}{self.RESET}"

        return super().format(record)


def setup_logging():
    """Logging konfigürasyonu — file only, no console output."""
    # File handler — persist GUI logs to %PROGRAMDATA%\HanvonAgent\logs\hanvon_gui.log
    try:
        log_dir = app_paths.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_dir / "hanvon_gui.log", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_handler.setFormatter(
            logging.Formatter(
                fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
        )

        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

        # HanvonAgent logger
        logger = logging.getLogger("HanvonAgent")
        logger.setLevel(logging.DEBUG)

        return logger
    except Exception as e:
        print(f"[ERROR] Logging setup failed: {e}")
        # Return a basic logger that does nothing if file logging fails
        return logging.getLogger("HanvonAgent")


def run_service_entry() -> int:
    """
    Headless service entry point (``--run-service``).

    Delegates to service_runner without touching Qt. Returns a process exit
    code. service_runner.main() blocks until the service stops.
    """
    from service_runner import main as service_main

    try:
        service_main()
        return 0
    except SystemExit as exc:  # service_runner may sys.exit on failure
        return int(exc.code or 0)
    except Exception:  # noqa: BLE001
        logging.getLogger("HanvonAgent").error(
            "Servis çalışırken hata", exc_info=True
        )
        return 1


def run_svc_admin(action: str) -> int:
    """
    Elevated service admin subcommand (``--svc-admin <action>``).

    Runs without Qt. Returns:
      * 0 on success,
      * 1 on a service operation error,
      * 2 for an unknown action.
    """
    logger = logging.getLogger("HanvonAgent")

    if action not in _SVC_ADMIN_ACTIONS:
        logger.error("Bilinmeyen servis aksiyonu: %s", action)
        return 2

    try:
        manager = ServiceManager(build_default_config())
        if action == "install":
            manager.install()
        elif action == "remove":
            manager.remove(confirm=True)
        elif action == "start":
            manager.start()
        elif action == "stop":
            manager.stop()
        logger.info("Servis aksiyonu başarılı: %s", action)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Servis aksiyonu hatası (%s): %s", action, exc, exc_info=True)
        return 1


def qt_exception_hook(exctype, value, traceback_obj):
    """Qt exception hook — tüm exception'ları logla."""
    import traceback as tb
    tb_lines = tb.format_exception(exctype, value, traceback_obj)
    tb_str = ''.join(tb_lines)
    print(f"[CRITICAL] UNHANDLED EXCEPTION IN QT:\n{tb_str}")
    logging.getLogger("HanvonAgent").critical(f"UNHANDLED EXCEPTION IN QT:\n{tb_str}")
    sys.__excepthook__(exctype, value, traceback_obj)


def main():
    """Uygulama başlatıcı."""
    # Qt exception hook'unu kur
    sys.excepthook = qt_exception_hook

    argv = sys.argv

    # --- CLI dispatch (no Qt on these branches) ----------------------------
    # NOTE: explicit ``return`` after sys.exit so that when sys.exit is mocked
    # in tests it does not fall through into the GUI branch.
    if "--run-service" in argv:
        sys.exit(run_service_entry())
        return

    if "--svc-admin" in argv:
        idx = argv.index("--svc-admin")
        action = argv[idx + 1] if idx + 1 < len(argv) else ""
        sys.exit(run_svc_admin(action))
        return

    try:
        # Setup logging (file only, no console redirect)
        logger = setup_logging()

        logger.info("=" * 70)
        logger.info("HanvonAgent Baslatiliyor...")
        logger.info(f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        try:
            # Veritabanını başlat
            init_db()
            logger.info("[OK] Veritabani hazir")

            # Qt uygulaması
            app = QApplication(sys.argv)
            logger.info("[OK] Qt uygulamasi hazir")

            # Ana pencere
            try:
                window = MainWindow()
                logger.info("[OK] MainWindow olusturuldu")
            except Exception as e:
                logger.error(f"MainWindow olusturma hatasi: {str(e)}", exc_info=True)
                raise

            # Minimize to tray on startup (--minimized flag)
            if "--minimized" in sys.argv:
                window.hide()
            else:
                try:
                    window.show()
                except Exception as e:
                    logger.warning(f"window.show() hatası: {e}")
                    window.hide()

            logger.info("[OK] GUI olusturuldu")

            # Window'u göstermek için event loop başlamadan hemen önce bir timer kur
            # Böylece Qt tam hazır olur
            from PySide6.QtCore import QTimer
            def show_window_delayed():
                try:
                    if not "--minimized" in sys.argv and not window.isVisible():
                        window.show()
                except Exception as e:
                    logger.warning(f"Gecikmeli window.show() hatası: {e}")

            if not "--minimized" in sys.argv:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(show_window_delayed)
                timer.start(100)

            logger.info("HanvonAgent calismaya basladi")

            logger.info("Event loop starting")
            try:
                exit_code = app.exec()
                logger.info(f"Event loop exited with code: {exit_code}")
                print(f"[INFO] Event loop kapandi, cikis kodu: {exit_code}")
                sys.exit(exit_code)
            except Exception as e:
                logger.critical(f"Event loop exception: {e}", exc_info=True)
                logger.critical(f"Event loop'da exception: {str(e)}", exc_info=True)
                sys.exit(1)

        except Exception as e:
            logger.error(f"KRITIK HATA: {str(e)}", exc_info=True)
            sys.exit(1)

    except Exception as e:
        logger.error(f"Baslangic hatasi: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

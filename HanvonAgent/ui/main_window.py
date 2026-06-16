"""
Ana pencere — Tab navigasyon + System Tray.

Tabs:
- Dashboard: Genel durum
- Settings: Cihaz & API ayarları
- Records: Kayıt tablosu
- Device Management: Cihaz yönetimi
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QSystemTrayIcon, QMenu, QMessageBox, QApplication
)
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtCore import Qt, QTimer
from ui.tabs.settings_tab import SettingsTab
from ui.tabs.dashboard_tab import DashboardTab
from ui.tabs.records_tab import RecordsTab
from ui.tabs.device_mgmt_tab import DeviceMgmtTab
from ui.service_controller import ServiceWorker
from services.service_manager import ServiceState
from services.scheduler_service import SchedulerService
from __version__ import get_version


#: Human-readable Turkish labels for each service state (used in the tray
#: status line).
_STATE_LABELS = {
    ServiceState.RUNNING: "Çalışıyor",
    ServiceState.STOPPED: "Durduruldu",
    ServiceState.START_PENDING: "Başlatılıyor...",
    ServiceState.STOP_PENDING: "Durduruluyor...",
    ServiceState.NOT_INSTALLED: "Kurulu değil",
    ServiceState.UNKNOWN: "Bilinmiyor",
}


class MainWindow(QMainWindow):
    """Ana uygulama penceresi."""

    def __init__(self):
        super().__init__()
        import logging
        logger = logging.getLogger("HanvonAgent.MainWindow")

        try:
            from __version__ import get_version
            version = get_version()
            self.setWindowTitle(f"HanvonAgent - Hanvon F710 Yonetim ({version})")
            self.setGeometry(100, 100, 1000, 640)
            self.setFixedSize(1000, 640)
            self._allow_close = False  # X basıldığında gizle (True ise kapat)

            # Icon set (PyInstaller bundled ve dev mode desteği)
            import sys
            from pathlib import Path

            # PyInstaller temp path (bundled)
            if hasattr(sys, '_MEIPASS'):
                icon_path = Path(sys._MEIPASS) / "HanvonAgent" / "hanvon.ico"
            else:
                # Dev mode
                icon_path = Path(__file__).parent.parent / "hanvon.ico"

            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            # Central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

            layout = QVBoxLayout(central_widget)

            # Tab widget
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)

            # Initialize tabs
            self._init_tabs()

            # Otomatik çekme scheduler — GUI açıkken çalışır
            self._scheduler = SchedulerService()
            self._scheduler.start()
            self.settings_tab.schedules_saved.connect(self._scheduler.reload_schedules)
            logger.info("[OK] SchedulerService baslatildi")

            # System Tray
            self._init_tray()

            # Service control submenu (depends on tray being initialized).
            self._service_workers = []
            self._init_service_menu()

            # Periodically check device status (mock for now)
            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self._update_device_status)
            self.status_timer.start(5000)  # 5 saniye

            # Periodically refresh service state (every 10 s) + once at startup.
            self.service_status_timer = QTimer()
            self.service_status_timer.timeout.connect(self._refresh_service_state)
            self.service_status_timer.start(10000)  # 10 saniye
            self._refresh_service_state()

        except Exception as e:
            logger.error(f"MainWindow initialization hatası: {str(e)}", exc_info=True)
            raise

        logger.info("MainWindow olusturuldu")

    def _init_tabs(self):
        """Tab sekmelerini baslat."""
        self.dashboard_tab = DashboardTab()
        self.tabs.addTab(self.dashboard_tab, "Panolar")

        self.records_tab = RecordsTab()
        self.tabs.addTab(self.records_tab, "Kayitlar")

        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.settings_tab, "Ayarlar")

        self.device_mgmt_tab = DeviceMgmtTab()
        self.tabs.addTab(self.device_mgmt_tab, "Cihaz Yonetimi")

    def _init_tray(self):
        """System Tray başlat."""
        import sys
        from pathlib import Path

        self.tray_icon = QSystemTrayIcon(self)

        # Tray icon'ü (PyInstaller bundled ve dev mode desteği)
        if hasattr(sys, '_MEIPASS'):
            icon_path = Path(sys._MEIPASS) / "HanvonAgent" / "hanvon.ico"
        else:
            icon_path = Path(__file__).parent.parent / "hanvon.ico"

        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
            print(f"[INFO] Tray icon yüklendi: {icon_path}")
        else:
            print(f"[WARNING] Tray icon bulunamadı: {icon_path}")

        # Tray menüsü
        tray_menu = QMenu()

        show_action = QAction("HanvonAgent", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)

        about_action = QAction("Hakkımızda", self)
        about_action.triggered.connect(self._show_about)
        tray_menu.addAction(about_action)

        tray_menu.addSeparator()

        exit_action = QAction("Çıkış", self)
        exit_action.triggered.connect(self._real_close)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def _init_service_menu(self):
        """'Servis' alt menüsünü tray menüsüne ekle."""
        self._service_menu = QMenu("Servis", self)
        self._service_actions = {}

        specs = [
            ("install", "Kur"),
            ("remove", "Kaldır"),
            ("start", "Başlat"),
            ("stop", "Durdur"),
        ]
        for key, label in specs:
            action = QAction(label, self)
            action.triggered.connect(
                lambda _checked=False, k=key: self._on_service_action(k)
            )
            self._service_menu.addAction(action)
            self._service_actions[key] = action

        self._service_menu.addSeparator()

        # Disabled, non-triggerable status line.
        self._service_status_action = QAction("Durum: Bilinmiyor", self)
        self._service_status_action.setEnabled(False)
        self._service_menu.addAction(self._service_status_action)

        # Insert the submenu into the tray context menu (above the separator
        # before Çıkış, if present; otherwise just append).
        tray_menu = self.tray_icon.contextMenu()
        if tray_menu is not None:
            tray_menu.addSeparator()
            tray_menu.addMenu(self._service_menu)

        # Default disabled until the first status query resolves.
        self._apply_service_state(ServiceState.UNKNOWN)

    def _apply_service_state(self, state):
        """Servis durumuna göre menü aksiyonlarını etkinleştir/devre dışı bırak."""
        actions = self._service_actions
        installed = state not in (
            ServiceState.NOT_INSTALLED,
            ServiceState.UNKNOWN,
        )

        actions["install"].setEnabled(state == ServiceState.NOT_INSTALLED)
        actions["remove"].setEnabled(installed)
        actions["start"].setEnabled(state == ServiceState.STOPPED)
        actions["stop"].setEnabled(state == ServiceState.RUNNING)

        label = _STATE_LABELS.get(state, "Bilinmiyor")
        self._service_status_action.setText(f"Durum: {label}")

    def _on_service_action(self, action):
        """Bir servis aksiyonu tetiklendiğinde worker başlat, menüyü kilitle."""
        self._service_menu.setEnabled(False)
        worker = ServiceWorker(action)
        worker.finished.connect(self._on_service_worker_finished)
        self._service_workers.append(worker)
        worker.start()

    def _on_service_worker_finished(self, ok, msg, state):
        """Worker tamamlandığında sonucu UI'ya yansıt ve menüyü çöz."""
        self._service_menu.setEnabled(True)
        self._apply_service_state(state)

        if ok:
            self.tray_icon.showMessage(
                "HanvonAgent Servis",
                msg,
                QSystemTrayIcon.Information,
                4000,
            )
        else:
            QMessageBox.warning(self, "HanvonAgent Servis", msg)

        self._reap_finished_workers()

    def _refresh_service_state(self):
        """Servis durumunu non-blocking olarak sorgula (status worker)."""
        worker = ServiceWorker("status")
        worker.finished.connect(self._on_service_status_refreshed)
        self._service_workers.append(worker)
        worker.start()

    def _on_service_status_refreshed(self, ok, msg, state):
        """Periyodik durum sorgusunun sonucu — sadece menü durumunu günceller."""
        self._apply_service_state(state)
        self._reap_finished_workers()

    def _reap_finished_workers(self):
        """Biten worker'ları listeden temizle (GC için tutuluyordu)."""
        self._service_workers = [
            w for w in self._service_workers if w.isRunning()
        ]

    def _update_device_status(self):
        """Cihaz durumunu güncelle (mock)."""
        # TODO: Gerçek cihaz durumu kontrolü
        pass

    def _show_about(self):
        """Hakkımızda diyalogu göster."""
        QMessageBox.about(
            self,
            "HanvonAgent Hakkında",
            f"HanvonAgent - Hanvon F710 Yönetim\nVersiyon: {get_version()}\n\n"
            "Hanvon F710 cihaz yönetimi ve kayıt alımı için masaüstü uygulaması."
        )

    def _real_close(self):
        """Uygulamayı tamamen kapat."""
        self._allow_close = True
        self.close()

    def closeEvent(self, event):
        """Kapatma event — tray'e gizle veya kapat."""
        if not self._allow_close:
            # X'e basıldı → tray'e gizle
            event.ignore()
            self.hide()
        else:
            # "Çıkış" menüsünden → gerçekten kapat.
            self.service_status_timer.stop()
            self.status_timer.stop()
            if hasattr(self, "_scheduler"):
                self._scheduler.stop()
            for worker in list(getattr(self, "_service_workers", [])):
                try:
                    if worker.isRunning():
                        worker.wait(5000)
                except RuntimeError:
                    pass
            event.accept()
            QApplication.quit()

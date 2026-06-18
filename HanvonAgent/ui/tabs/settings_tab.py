"""
Ayarlar sekmesi — Modern Tab-based UI.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QTabWidget,
    QPushButton, QTimeEdit, QMessageBox, QCheckBox, QScrollArea, QLineEdit, QSpinBox
)
from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtGui import QFont
from models import Device, Setting, get_session


class SettingsTab(QWidget):
    """Ayarlar sekmesi — Modern Tab UI."""

    schedules_saved = Signal()  # Zamanlama kaydedildiğinde scheduler'ı tetikler

    def __init__(self):
        super().__init__()
        self.session = get_session()
        self.device_schedules = {}
        self._create_ui_first = True
        self.setStyleSheet("""
            QWidget { background-color: #fafafa; }
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background-color: #f0f0f0;
                border: none;
                padding: 10px 20px;
                margin-right: 2px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 3px solid #2196F3;
            }
            QGroupBox {
                border: 1px solid #e0e0e0;
                background-color: white;
                border-radius: 4px;
                margin-top: 8px;
                padding: 12px;
                font-weight: 500;
            }
            QLineEdit, QComboBox, QTimeEdit, QSpinBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 10px;
                background-color: #fafafa;
                font-size: 10pt;
            }
            QLineEdit:focus, QComboBox:focus, QTimeEdit:focus {
                border: 2px solid #2196F3;
                background-color: white;
            }
            QPushButton {
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                color: white;
                background-color: #2196F3;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QCheckBox {
                spacing: 6px;
                font-size: 10pt;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        """Modern Tab UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tab Widget
        tabs = QTabWidget()
        tabs.addTab(self._create_schedule_tab(), "⏰ Otomatik Çekme")
        tabs.addTab(self._create_api_tab(), "🌐 API Ayarları")
        main_layout.addWidget(tabs)

        # Zamanlamaları ve API ayarlarını DB'den yükle
        self._load_schedules()
        self._load_api_settings()

    def _create_schedule_tab(self):
        """Zamanlama sekmesi."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Başlık
        title = QLabel("Cihazlar için otomatik çekme zamanı ayarlayın")
        title_font = QFont("Arial", 11)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Cihaz listesi (scroll)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical { width: 8px; }
            QScrollBar::handle:vertical { background-color: #bbb; border-radius: 4px; }
        """)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        devices = self.session.query(Device).all()
        if not devices:
            scroll_layout.addWidget(QLabel("📭 Cihaz bulunamadı"))
        else:
            for device in devices:
                self._add_device_card(scroll_layout, device)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Kaydet butonu
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("💾 Ayarları Kaydet")
        save_btn.setMinimumWidth(150)
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save_all_schedules)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        return widget

    def _create_api_tab(self):
        """API Ayarları sekmesi."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Başlık
        title = QLabel("Harici API sunucusu ayarlarını yapılandırın")
        title_font = QFont("Arial", 11)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # API Kart
        api_card = QGroupBox("API Sunucu Bilgileri")
        api_layout = QVBoxLayout(api_card)
        api_layout.setSpacing(12)

        # Endpoint
        api_layout.addWidget(QLabel("API Endpoint:"))
        self.api_endpoint_input = QLineEdit()
        self.api_endpoint_input.setPlaceholderText("https://api.example.com/records")
        self.api_endpoint_input.setMinimumHeight(36)
        api_layout.addWidget(self.api_endpoint_input)

        # Token
        api_layout.addWidget(QLabel("Auth Token:"))
        self.api_token_input = QLineEdit()
        self.api_token_input.setPlaceholderText("Bearer token veya API key")
        self.api_token_input.setEchoMode(QLineEdit.Password)
        self.api_token_input.setMinimumHeight(36)
        api_layout.addWidget(self.api_token_input)

        # Durum Toggle
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Durum:"))

        self.api_status_toggle = QPushButton("🟢 Aktif")
        self.api_status_toggle.setCheckable(True)
        self.api_status_toggle.setChecked(False)  # Başlangıçta kapalı (kırmızı)
        self.api_status_toggle.setMinimumHeight(32)
        self.api_status_toggle.setMinimumWidth(100)
        self.api_status_toggle.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #da190b; }
            QPushButton:!checked {
                background-color: #4CAF50;
            }
            QPushButton:!checked:hover {
                background-color: #45a049;
            }
        """)

        def update_api_toggle_text():
            self.api_status_toggle.setText("🟢 Aktif" if not self.api_status_toggle.isChecked() else "🔴 Pasif")

        self.api_status_toggle.clicked.connect(update_api_toggle_text)
        self.api_status_toggle.setText("🟢 Aktif")
        status_layout.addWidget(self.api_status_toggle)
        status_layout.addStretch()
        api_layout.addLayout(status_layout)

        layout.addWidget(api_card)

        # ===== PUSH SERVİSİ =====
        push_card = QGroupBox("📤 API Çalıştırma Takvimi")
        push_layout = QVBoxLayout(push_card)
        push_layout.setSpacing(10)

        # Push Durum
        push_status_h = QHBoxLayout()
        push_status_h.addWidget(QLabel("Durum:"))
        self.push_status_toggle = QPushButton("🔴 Pasif")
        self.push_status_toggle.setCheckable(True)
        self.push_status_toggle.setChecked(True)
        self.push_status_toggle.setMinimumHeight(32)
        self.push_status_toggle.setMinimumWidth(100)
        self.push_status_toggle.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #da190b; }
            QPushButton:!checked { background-color: #4CAF50; }
            QPushButton:!checked:hover { background-color: #45a049; }
        """)
        def update_push_toggle():
            self.push_status_toggle.setText("🟢 Aktif" if not self.push_status_toggle.isChecked() else "🔴 Pasif")
        self.push_status_toggle.clicked.connect(update_push_toggle)
        push_status_h.addWidget(self.push_status_toggle)
        push_status_h.addStretch()
        push_layout.addLayout(push_status_h)

        # Push Aralığı
        interval_h = QHBoxLayout()
        interval_h.addWidget(QLabel("Aralık:"))
        self.push_interval = QSpinBox()
        self.push_interval.setMinimum(1)
        self.push_interval.setMaximum(60)
        self.push_interval.setValue(5)
        self.push_interval.setMinimumHeight(32)
        self.push_interval.setMinimumWidth(80)
        interval_h.addWidget(self.push_interval)
        interval_h.addWidget(QLabel("dakika"))
        interval_h.addStretch()
        push_layout.addLayout(interval_h)

        # Max Retry
        retry_h = QHBoxLayout()
        retry_h.addWidget(QLabel("Max Retry:"))
        self.push_retry = QSpinBox()
        self.push_retry.setMinimum(1)
        self.push_retry.setMaximum(10)
        self.push_retry.setValue(3)
        self.push_retry.setMinimumHeight(32)
        self.push_retry.setMinimumWidth(80)
        retry_h.addWidget(self.push_retry)
        retry_h.addWidget(QLabel("kez"))
        retry_h.addStretch()
        push_layout.addLayout(retry_h)

        layout.addWidget(push_card)
        layout.addStretch()

        # Butonlar
        btn_layout = QHBoxLayout()
        test_btn = QPushButton("🔗 Bağlantı Testi")
        test_btn.setMinimumHeight(40)
        test_btn.clicked.connect(self._test_api)
        btn_layout.addWidget(test_btn)

        save_btn = QPushButton("💾 Ayarları Kaydet")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save_api_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        return widget

    def _add_device_card(self, layout, device):
        """Cihaz zamanlama kartı."""
        card = QGroupBox(f"📱 {device.name}")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        # Üst satır: Çekme Sıklığı + Toggle
        top_h_layout = QHBoxLayout()

        top_h_layout.addWidget(QLabel("Günde çekme sıklığı:"))
        frequency = QSpinBox()
        frequency.setMinimum(1)
        frequency.setMaximum(3)
        frequency.setValue(2)
        frequency.setMinimumHeight(32)
        frequency.setMinimumWidth(60)
        top_h_layout.addWidget(frequency)
        top_h_layout.addWidget(QLabel("kez"))

        top_h_layout.addSpacing(20)

        # Toggle Button (başlangıçta KAPAL = checked)
        toggle = QPushButton("🔴 Kapalı")
        toggle.setCheckable(True)
        toggle.setChecked(True)  # checked = kapalı (kırmızı)
        toggle.setMinimumHeight(32)
        toggle.setMinimumWidth(100)
        toggle.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #da190b; }
            QPushButton:pressed { background-color: #ba0000; }
            QPushButton:!checked {
                background-color: #4CAF50;
            }
            QPushButton:!checked:hover {
                background-color: #45a049;
            }
        """)

        def update_toggle_text():
            toggle.setText("🟢 Açık" if not toggle.isChecked() else "🔴 Kapalı")

        toggle.clicked.connect(update_toggle_text)
        top_h_layout.addWidget(toggle)
        top_h_layout.addStretch()
        card_layout.addLayout(top_h_layout)
        self.device_schedules[f"{device.id}_frequency"] = frequency
        self.device_schedules[f"{device.id}_toggle"] = toggle

        # Saat alanları container
        times_container = QVBoxLayout()
        times_container.setSpacing(8)
        times_container.setContentsMargins(0, 0, 0, 0)

        # Saat 1, 2, 3 widgets
        time_widgets = []
        for i in range(1, 4):
            saat_h_layout = QHBoxLayout()
            saat_h_layout.addWidget(QLabel(f"  └─ Saat {i}:"))
            time_input = QTimeEdit()
            default_hours = [10, 14, 18]
            time_input.setTime(QTime(default_hours[i-1], 0))
            time_input.setMinimumHeight(32)
            saat_h_layout.addWidget(time_input)
            saat_h_layout.addStretch()

            # Widget'ı container'a ekle
            saat_widget = QWidget()
            saat_widget.setLayout(saat_h_layout)
            times_container.addWidget(saat_widget)
            time_widgets.append((saat_widget, time_input))
            self.device_schedules[f"{device.id}_{i}"] = time_input

        # Dinamik göster/gizle
        def update_time_visibility():
            freq = frequency.value()
            for idx, (widget, _) in enumerate(time_widgets):
                widget.setVisible(idx < freq)

        frequency.valueChanged.connect(update_time_visibility)
        update_time_visibility()

        card_layout.addLayout(times_container)
        layout.addWidget(card)

    def _load_schedules(self):
        """DB'den zamanlamaları yükle."""
        try:
            devices = self.session.query(Device).all()

            for device in devices:
                dev_id = device.id
                setting = self.session.query(Setting).filter_by(key=f"schedule_{dev_id}").first()

                if not setting:
                    continue

                # Format: "frequency|saat1,saat2,saat3|durum"
                parts = setting.value.split("|")
                if len(parts) < 3:
                    continue

                freq_val = int(parts[0])
                times = parts[1].split(",")
                is_open = parts[2] == "1"  # 1=açık, 0=kapalı

                # UI güncelle
                if f"{dev_id}_frequency" in self.device_schedules:
                    self.device_schedules[f"{dev_id}_frequency"].setValue(freq_val)

                if f"{dev_id}_toggle" in self.device_schedules:
                    toggle = self.device_schedules[f"{dev_id}_toggle"]
                    # toggle.isChecked() = True ise KAPAL, False ise AÇ
                    toggle.setChecked(not is_open)
                    toggle.setText("🟢 Açık" if is_open else "🔴 Kapalı")

                for i, time_str in enumerate(times):
                    if f"{dev_id}_{i+1}" in self.device_schedules:
                        hour, minute = map(int, time_str.split(":"))
                        self.device_schedules[f"{dev_id}_{i+1}"].setTime(QTime(hour, minute))

        except Exception as e:
            print(f"[AYARLAR] Yükleme hatası: {str(e)}")

    def _save_all_schedules(self):
        """Tüm zamanlamaları kaydet."""
        try:
            devices = self.session.query(Device).all()

            for device in devices:
                dev_id = device.id
                freq = self.device_schedules.get(f"{dev_id}_frequency")
                toggle = self.device_schedules.get(f"{dev_id}_toggle")

                if not freq or not toggle:
                    continue

                # Ayarları kaydet
                frequency_val = freq.value()
                # toggle.isChecked() = True ise KAPAL (kırmızı), False ise AÇ (yeşil)
                is_open = not toggle.isChecked()

                # Setting tablosuna kaydet (key: device_{id}_schedule)
                times = []
                for i in range(1, 4):
                    time_widget = self.device_schedules.get(f"{dev_id}_{i}")
                    if time_widget:
                        times.append(time_widget.time().toString("HH:mm"))

                # Format: "frequency|saat1,saat2|durum" (durum: 1=açık, 0=kapalı)
                status = "1" if is_open else "0"
                schedule_data = f"{frequency_val}|{','.join(times[:frequency_val])}|{status}"

                # DB'ye kaydet (Setting)
                self.session.query(Setting).filter_by(key=f"schedule_{dev_id}").delete()
                setting = Setting(key=f"schedule_{dev_id}", value=schedule_data)
                self.session.add(setting)

            self.session.commit()
            self.schedules_saved.emit()
            QMessageBox.information(self, "✓ Başarılı", "Zamanlama ayarları kaydedildi")

        except Exception as e:
            QMessageBox.critical(self, "❌ Hata", f"Kaydetme başarısız:\n{str(e)}")

    def _test_api(self):
        """API bağlantısı testi — gerçek HTTP isteği atar."""
        import httpx
        endpoint = self.api_endpoint_input.text().strip()
        token = self.api_token_input.text().strip()
        if not endpoint:
            QMessageBox.warning(self, "⚠ Hata", "API endpoint adresini giriniz")
            return

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = httpx.post(
                endpoint,
                json={"devices": []},
                headers=headers,
                timeout=5,
            )
            if resp.status_code < 500:
                QMessageBox.information(
                    self, "✓ Bağlantı Başarılı",
                    f"Sunucu yanıt verdi.\nHTTP {resp.status_code}: {resp.text[:200]}"
                )
            else:
                QMessageBox.warning(
                    self, "⚠ Sunucu Hatası",
                    f"Sunucu hata döndürdü.\nHTTP {resp.status_code}: {resp.text[:200]}"
                )
        except httpx.ConnectError:
            QMessageBox.critical(self, "❌ Bağlanamadı", f"Sunucuya ulaşılamadı:\n{endpoint}")
        except httpx.TimeoutException:
            QMessageBox.critical(self, "❌ Zaman Aşımı", "Sunucu 5 saniye içinde yanıt vermedi.")
        except Exception as e:
            QMessageBox.critical(self, "❌ Hata", str(e))

    def _load_api_settings(self):
        """API ayarlarını DB'den yükle."""
        try:
            endpoint_setting = self.session.query(Setting).filter_by(key="api_endpoint").first()
            token_setting = self.session.query(Setting).filter_by(key="api_token").first()
            api_status_setting = self.session.query(Setting).filter_by(key="api_status").first()
            push_status_setting = self.session.query(Setting).filter_by(key="push_status").first()
            push_interval_setting = self.session.query(Setting).filter_by(key="push_interval").first()
            push_retry_setting = self.session.query(Setting).filter_by(key="push_retry").first()

            if endpoint_setting:
                self.api_endpoint_input.setText(endpoint_setting.value)

            if token_setting:
                self.api_token_input.setText(token_setting.value)

            if api_status_setting:
                is_active = api_status_setting.value == "1"
                self.api_status_toggle.setChecked(not is_active)
                self.api_status_toggle.setText("🟢 Aktif" if is_active else "🔴 Pasif")

            if push_status_setting:
                is_active = push_status_setting.value == "1"
                self.push_status_toggle.setChecked(not is_active)
                self.push_status_toggle.setText("🟢 Aktif" if is_active else "🔴 Pasif")

            if push_interval_setting:
                self.push_interval.setValue(int(push_interval_setting.value))

            if push_retry_setting:
                self.push_retry.setValue(int(push_retry_setting.value))

        except Exception as e:
            print(f"[API] Yükleme hatası: {str(e)}")

    def _save_api_settings(self):
        """API ve Push ayarlarını DB'ye kaydet."""
        try:
            endpoint = self.api_endpoint_input.text().strip()
            token = self.api_token_input.text().strip()

            if not endpoint or not token:
                QMessageBox.warning(self, "⚠ Hata", "Endpoint ve Token alanlarını doldurunuz")
                return

            # API durum
            api_is_active = not self.api_status_toggle.isChecked()
            api_status = "1" if api_is_active else "0"

            # Push durum
            push_is_active = not self.push_status_toggle.isChecked()
            push_status = "1" if push_is_active else "0"
            push_interval = str(self.push_interval.value())
            push_retry = str(self.push_retry.value())

            # DB'ye kaydet (Setting)
            self.session.query(Setting).filter_by(key="api_endpoint").delete()
            self.session.query(Setting).filter_by(key="api_token").delete()
            self.session.query(Setting).filter_by(key="api_status").delete()
            self.session.query(Setting).filter_by(key="push_status").delete()
            self.session.query(Setting).filter_by(key="push_interval").delete()
            self.session.query(Setting).filter_by(key="push_retry").delete()

            self.session.add(Setting(key="api_endpoint", value=endpoint))
            self.session.add(Setting(key="api_token", value=token))
            self.session.add(Setting(key="api_status", value=api_status))
            self.session.add(Setting(key="push_status", value=push_status))
            self.session.add(Setting(key="push_interval", value=push_interval))
            self.session.add(Setting(key="push_retry", value=push_retry))

            self.session.commit()
            QMessageBox.information(self, "✓ Başarılı", "Tüm ayarlar kaydedildi")

        except Exception as e:
            QMessageBox.critical(self, "❌ Hata", f"Kaydetme başarısız:\n{str(e)}")

"""
Dashboard sekmesi — Output alanı + Cihaz seçimi + Çekme işlemi.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QCheckBox,
    QLineEdit, QSpinBox, QGroupBox, QFormLayout, QDateEdit
)
from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QFont, QCursor
from datetime import datetime, timedelta
from models import Device, Record, get_session
from services.record_service import RecordService
import logging

logger = logging.getLogger("HanvonAgent.Dashboard")


class DashboardTab(QWidget):
    """Dashboard sekmesi — Cihaz çekme işlemleri."""

    def __init__(self):
        super().__init__()
        self.session = get_session()
        self.editing_device_id = None  # Hangi cihaz düzenleniyor
        self._init_ui()
        self._refresh_device_list()

    def _init_ui(self):
        """Dashboard layout — Ortada metin, sağda cihaz listesi."""
        main_layout = QHBoxLayout(self)

        # ========== ORTADA: OUTPUT ALANI ==========
        left_layout = QVBoxLayout()

        # Başlık
        title = QLabel("Çekme İşlemleri")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        left_layout.addWidget(title)

        # Metin alanı (output - HTML desteği)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Courier New", 9))
        self.output_text.setStyleSheet(
            "QTextEdit { background-color: #0a0e27; color: #00ff00; border: 1px solid #333; }"
        )
        left_layout.addWidget(self.output_text, 1)

        # ========== SAĞDA: CİHAZ LİSTESİ ==========
        right_layout = QVBoxLayout()

        # Başlık
        dev_title = QLabel("Cihazlar")
        dev_title.setFont(title_font)
        right_layout.addWidget(dev_title)

        # Cihaz tablosu
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(5)
        self.device_table.setHorizontalHeaderLabels(["", "Cihaz Adi", "IP", "Edit", "Sil"])
        self.device_table.setColumnWidth(0, 25)
        self.device_table.setColumnWidth(1, 90)
        self.device_table.setColumnWidth(2, 100)
        self.device_table.setColumnWidth(3, 45)
        self.device_table.setColumnWidth(4, 45)
        self.device_table.setMinimumWidth(330)
        right_layout.addWidget(self.device_table, 1)

        # ========== BUTON ALANI ==========
        button_layout = QVBoxLayout()

        # Tarih aralığı
        date_range_group = QGroupBox("Tarih Aralığı")
        date_range_group.setFont(QFont("Arial", 9))
        date_range_layout = QHBoxLayout()

        date_range_layout.addWidget(QLabel("Başlangıç:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))
        date_range_layout.addWidget(self.start_date_edit)

        date_range_layout.addWidget(QLabel("Bitiş:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.end_date_edit.setDate(QDate.currentDate())
        date_range_layout.addWidget(self.end_date_edit)

        date_range_group.setLayout(date_range_layout)
        button_layout.addWidget(date_range_group)

        # CheckBox - Tekrar Çek
        self.reprocess_check = QCheckBox("Tekrar Çek (Eski Verileri Update Et)")
        self.reprocess_check.setFont(QFont("Arial", 10))
        button_layout.addWidget(self.reprocess_check)

        # Buton row
        btn_row = QHBoxLayout()

        self.fetch_btn = QPushButton("📥 VERİLERİ ÇEK")
        self.fetch_btn.setMinimumHeight(50)
        self.fetch_btn.setFont(QFont("Arial", 10, QFont.Bold))
        self.fetch_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #4CAF50;"
            "color: white;"
            "border-radius: 5px;"
            "font-weight: bold;"
            "padding: 8px;"
            "}"
            "QPushButton:hover {"
            "background-color: #45a049;"
            "}"
        )
        self.fetch_btn.clicked.connect(self._fetch_selected_devices)
        btn_row.addWidget(self.fetch_btn)

        self.add_device_btn = QPushButton("➕ CİHAZ EKLE")
        self.add_device_btn.setMinimumHeight(50)
        self.add_device_btn.setFont(QFont("Arial", 10, QFont.Bold))
        self.add_device_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #2196F3;"
            "color: white;"
            "border-radius: 5px;"
            "font-weight: bold;"
            "padding: 8px;"
            "}"
            "QPushButton:hover {"
            "background-color: #0b7dda;"
            "}"
        )
        self.add_device_btn.clicked.connect(self._toggle_add_device_form)
        btn_row.addWidget(self.add_device_btn)

        button_layout.addLayout(btn_row)

        # ========== CİHAZ EKLEME FORMU (Gizli) ==========
        self.device_form_group = QGroupBox("Yeni Cihaz Ekle")
        self.device_form_group.setFont(QFont("Arial", 10, QFont.Bold))
        form_layout = QFormLayout()

        self.device_name_input = QLineEdit()
        self.device_name_input.setPlaceholderText("Örn: ANA GIRIS")
        form_layout.addRow("Cihaz Adı:", self.device_name_input)

        self.device_ip_input = QLineEdit()
        self.device_ip_input.setPlaceholderText("Örn: 172.16.1.218")
        form_layout.addRow("IP Adresi:", self.device_ip_input)

        self.device_commkey_input = QLineEdit()
        self.device_commkey_input.setPlaceholderText("Örn: 12345678 (boş bırakabilir)")
        form_layout.addRow("CommKey (Şifre):", self.device_commkey_input)

        self.delete_after_pull_cb = QCheckBox("G/C verisi çekilen personelin verisini cihazdan temizle")
        self.delete_after_pull_cb.setChecked(False)
        self.delete_after_pull_cb.setStyleSheet("QCheckBox { color: red; }")
        form_layout.addRow("", self.delete_after_pull_cb)

        # Form butonlari
        form_btn_layout = QHBoxLayout()

        test_btn = QPushButton("Test Baglanti")
        test_btn.setFont(QFont("Arial", 9))
        test_btn.clicked.connect(self._test_device_connection)
        form_btn_layout.addWidget(test_btn)

        sync_time_btn = QPushButton("Saat Sync")
        sync_time_btn.setFont(QFont("Arial", 9))
        sync_time_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; padding: 3px; border-radius: 3px; }"
        )
        sync_time_btn.clicked.connect(self._sync_device_time)
        form_btn_layout.addWidget(sync_time_btn)

        save_btn = QPushButton("Kaydet")
        save_btn.setFont(QFont("Arial", 9, QFont.Bold))
        save_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 5px; border-radius: 3px; }"
        )
        save_btn.clicked.connect(self._save_device)
        form_btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Iptal")
        cancel_btn.setFont(QFont("Arial", 9))
        cancel_btn.clicked.connect(self._toggle_add_device_form)
        form_btn_layout.addWidget(cancel_btn)

        form_layout.addRow("", form_btn_layout)
        self.device_form_group.setLayout(form_layout)
        self.device_form_group.setVisible(False)
        button_layout.addWidget(self.device_form_group)

        # ========== LAYOUT KOMBİNASYONU ==========
        right_layout.addLayout(button_layout)

        main_layout.addLayout(left_layout, 2)
        main_layout.addLayout(right_layout, 1)

    def _refresh_device_list(self):
        """Cihaz tablosunu yukle (Checkbox + Edit/Delete)."""
        self.device_table.setRowCount(0)
        devices = self.session.query(Device).all()

        for row, device in enumerate(devices):
            self.device_table.insertRow(row)

            # CheckBox
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.Checked if device.enabled else Qt.Unchecked)
            check_item.setData(Qt.UserRole, device.id)
            self.device_table.setItem(row, 0, check_item)

            # Cihaz Adi
            name_item = QTableWidgetItem(device.name)
            self.device_table.setItem(row, 1, name_item)

            # IP
            ip_item = QTableWidgetItem(device.ip)
            self.device_table.setItem(row, 2, ip_item)

            # Edit Button
            edit_btn = QPushButton("✏")
            edit_btn.setFont(QFont("Arial", 11))
            edit_btn.setMaximumWidth(40)
            edit_btn.setMaximumHeight(32)
            edit_btn.setCursor(QCursor(Qt.PointingHandCursor))
            edit_btn.setStyleSheet(
                "QPushButton {"
                "background-color: #2196F3;"
                "border: none;"
                "border-radius: 4px;"
                "padding: 4px;"
                "color: white;"
                "font-weight: bold;"
                "}"
                "QPushButton:hover {"
                "background-color: #1976D2;"
                "}"
                "QPushButton:pressed {"
                "background-color: #0D47A1;"
                "}"
            )
            edit_btn.clicked.connect(lambda checked, dev_id=device.id: self._edit_device(dev_id))
            self.device_table.setCellWidget(row, 3, edit_btn)

            # Delete Button
            delete_btn = QPushButton("🗑")
            delete_btn.setFont(QFont("Arial", 11))
            delete_btn.setMaximumWidth(40)
            delete_btn.setMaximumHeight(32)
            delete_btn.setCursor(QCursor(Qt.PointingHandCursor))
            delete_btn.setStyleSheet(
                "QPushButton {"
                "background-color: #f44336;"
                "border: none;"
                "border-radius: 4px;"
                "padding: 4px;"
                "color: white;"
                "font-weight: bold;"
                "}"
                "QPushButton:hover {"
                "background-color: #d32f2f;"
                "}"
                "QPushButton:pressed {"
                "background-color: #b71c1c;"
                "}"
            )
            delete_btn.clicked.connect(lambda checked, dev_id=device.id: self._delete_device(dev_id))
            self.device_table.setCellWidget(row, 4, delete_btn)

    def _fetch_selected_devices(self):
        """Secili cihazlardan veri cek (checkbox basinda)."""
        # Checkbox ile secili cihazlari al
        selected_ids = []
        for i in range(self.device_table.rowCount()):
            item = self.device_table.item(i, 0)
            if item and item.checkState() == Qt.Checked:
                dev_id = item.data(Qt.UserRole)
                selected_ids.append(dev_id)

        if not selected_ids:
            QMessageBox.warning(self, "Bilgi", "En az bir cihaz seciniz")
            return

        # Output temizle
        self.output_text.clear()

        # Çekme işlemi başla
        logger.info("=" * 70)
        logger.info("[BAŞLAT] Veri çekme işlemi başladı")
        logger.info("=" * 70)

        self.output_text.append("[BAŞLAT] Veri çekme işlemi başladı\n")

        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")

        if self.start_date_edit.date() > self.end_date_edit.date():
            QMessageBox.warning(self, "Hata", "Başlangıç tarihi bitiş tarihinden büyük olamaz")
            return

        record_service = RecordService(self.session)
        total_records = 0
        reprocess = self.reprocess_check.isChecked()

        if reprocess:
            self.output_text.append("[UYARI] Tekrar çekme modu - Eski veriler UPDATE edilecek\n")
            logger.warning("[UYARI] Tekrar çekme modu aktif")

        for device_id in selected_ids:
            device = self.session.query(Device).filter_by(id=device_id).first()
            if not device:
                continue

            try:
                # Bağlanıyor
                msg = f"\n[BAGLANTI] {device.name} ({device.ip}) bağlanıyor..."
                self.output_text.append(msg)
                logger.info(msg.strip())
                self._process_events()

                # Veri çek
                msg = f"[CEKILIYOR] Veriler çekiliyor ({start_date} → {end_date})..."
                self.output_text.append(msg)
                logger.debug(msg)
                self._process_events()

                result = record_service.fetch_records(
                    device,
                    start_date=start_date,
                    end_date=end_date,
                    reprocess=reprocess
                )

                # Çekilen kayıtlar
                new_count = result.get("new_count", 0)
                total_count = result.get("total_count", 0)

                # Basarı
                msg = f"[BASARILI] {device.name}: {new_count} kayıt çekildi"
                self.output_text.append(msg)
                logger.info(msg)

                total_records += total_count

                # Özetleyen satır
                summary = f"\n➜ {device.name} | {start_date} → {end_date} | {total_count} kayıt | Veritabanına kaydedildi"
                self._append_output(summary, color="white")
                logger.info(f"[OZET] {summary.strip()}")

                # Cihazdan sil ayarı kontrol et
                from models import Setting
                del_setting = self.session.query(Setting).filter_by(
                    key=f"delete_after_pull_{device.id}"
                ).first()
                if del_setting and del_setting.value == "1":
                    try:
                        from core.hanvon_client import HanvonClient
                        client = HanvonClient(device.ip, comm_key=device.comm_key)
                        client.connect()
                        ok = client.delete_all_records_now()
                        client.disconnect()
                        if ok:
                            self._append_output(f"[SİLİNDİ] {device.name}: cihazdaki G/C kayıtları temizlendi", color="yellow")
                            logger.info(f"[SİLİNDİ] {device.name}: DeleteAllRecord OK")
                        else:
                            self._append_output(f"[UYARI] {device.name}: DeleteAllRecord başarısız", color="red")
                    except Exception as del_err:
                        self._append_output(f"[HATA] {device.name}: silme hatası — {del_err}", color="red")
                        logger.error(f"[DELETE] {device.name}: {del_err}")

            except Exception as e:
                msg = f"[HATA] {device.name}: {str(e)}"
                self._append_output(msg, color="red")
                logger.error(msg)

            self._process_events()

        # Final özet (parlak beyaz)
        final = f"\n\n[SON] Toplam {total_records} kayıt çekildi"
        self._append_output(final, color="white")
        logger.info(f"[SON] Toplam {total_records} kayıt çekildi")

        QMessageBox.information(self, "Başarı", f"✓ {total_records} kayıt çekildi")

    def _process_events(self):
        """UI responsif tut."""
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

    def _append_output(self, text, color="green"):
        """Output'a renkli metin ekle."""
        color_map = {
            "green": "#00FF00",
            "red": "#FF0000",
            "yellow": "#FFFF00",
            "white": "#FFFFFF",
        }
        hex_color = color_map.get(color, "#00FF00")
        # \n karakterlerini <br>'ye dönüştür
        text = text.replace('\n', '<br>')
        html = f'<span style="color: {hex_color};">{text}</span><br>'
        self.output_text.insertHtml(html)

    def _toggle_add_device_form(self):
        """Cihaz ekleme formu göster/gizle."""
        is_visible = self.device_form_group.isVisible()
        self.device_form_group.setVisible(not is_visible)

        if not is_visible:
            # Form açılıyorsa temizle
            self.editing_device_id = None
            self.device_name_input.clear()
            self.device_ip_input.clear()
            self.device_commkey_input.clear()
            self.delete_after_pull_cb.setChecked(False)
            self.device_form_group.setTitle("Yeni Cihaz Ekle")

    def _test_device_connection(self):
        """Cihaz baglantisini test et."""
        ip = self.device_ip_input.text().strip()
        commkey = self.device_commkey_input.text().strip() or None

        if not ip:
            QMessageBox.warning(self, "Uyarı", "IP adresi giriniz")
            return

        msg = f"\n[TEST] {ip} ile baglanti sinanıyor..."
        self.output_text.append(msg)
        logger.info(msg.strip())
        self._process_events()

        try:
            from core.hanvon_client import HanvonClient
            client = HanvonClient(ip, comm_key=commkey)
            client.connect()
            info = client.get_device_info()
            client.disconnect()

            if info:
                result = f"[BASARILI] Baglanti OK\nCihaz ID: {info.get('dev_id', 'N/A')}\nIP: {info.get('ip', 'N/A')}"
                self.output_text.append(result)
                logger.info(f"[BASARILI] Cihaz test edildi: {ip}")
                QMessageBox.information(self, "Basarı", f"Cihaza baglandi!\n{result}")
            else:
                self.output_text.append("[HATA] GetDeviceInfo basarısız")
                QMessageBox.warning(self, "Hata", "GetDeviceInfo basarısız")
        except Exception as e:
            error_msg = f"[HATA] Test basarısız: {str(e)}"
            self.output_text.append(error_msg)
            logger.error(error_msg)
            QMessageBox.critical(self, "Hata", f"Baglanti test basarısız:\n{str(e)}")

    def _sync_device_time(self):
        """Cihazin saatini sorgula, goster, sonra guncelle."""
        ip = self.device_ip_input.text().strip()
        commkey = self.device_commkey_input.text().strip() or None

        if not ip:
            QMessageBox.warning(self, "Uyarı", "IP adresi giriniz")
            return

        msg = f"\n[SAAT] {ip} mevcut saat sorgulanıyor..."
        self.output_text.append(msg)
        logger.info(msg.strip())
        self._process_events()

        try:
            from core.hanvon_client import HanvonClient
            from datetime import datetime

            client = HanvonClient(ip, comm_key=commkey)
            client.connect()

            # 1. Mevcut saati sor
            info = client.get_device_info()
            current_time = info.get('time', 'Bilinmiyor') if info else 'Bilinmiyor'

            msg_current = f"[MEVCUT] Cihaz saati: {current_time}"
            self.output_text.append(msg_current)
            logger.info(msg_current)
            self._process_events()

            # 2. Sunucu saatini al
            now = datetime.now()
            day_of_week = now.strftime("%w")

            msg_update = f"[GUNCELLEME] Yeni saat: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            self.output_text.append(msg_update)
            logger.info(msg_update)
            self._process_events()

            # 3. SetDeviceInfo ile saat guncelle
            response = client.send_command(
                f'SetDeviceInfo(time="{now.strftime("%Y-%m-%d %H:%M:%S")}" week="{day_of_week}")'
            )

            client.disconnect()

            if "success" in response.lower():
                result = f"\n[BASARILI] Saat senkronize edildi!\nEski: {current_time}\nYeni: {now.strftime('%Y-%m-%d %H:%M:%S')}"
                self.output_text.append(result)
                logger.info(f"[BASARILI] Saat guncellendi")
                QMessageBox.information(self, "Basarı", f"Saat guncellemesi basarılı!\nEski: {current_time}\nYeni: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                self.output_text.append("[HATA] Saat guncelleme basarısız")
                logger.error("[HATA] Saat guncelleme basarısız")
                QMessageBox.warning(self, "Hata", "Saat guncelleme basarısız")
        except Exception as e:
            error_msg = f"[HATA] Saat senkronizasyonu basarısız: {str(e)}"
            self.output_text.append(error_msg)
            logger.error(error_msg)
            QMessageBox.critical(self, "Hata", f"Saat senkronizasyonu basarısız:\n{str(e)}")

    def _edit_device(self, device_id):
        """Cihaz duzenlemeye ac."""
        device = self.session.query(Device).filter_by(id=device_id).first()
        if not device:
            return

        self.editing_device_id = device_id
        self.device_form_group.setVisible(True)
        self.device_form_group.setTitle(f"Cihazi Duzenle: {device.name}")
        self.device_name_input.setText(device.name)
        self.device_ip_input.setText(device.ip)
        self.device_commkey_input.setText(device.comm_key or "")

        # delete_after_pull ayarını DB'den oku
        from models import Setting
        setting = self.session.query(Setting).filter_by(key=f"delete_after_pull_{device_id}").first()
        self.delete_after_pull_cb.setChecked(setting is not None and setting.value == "1")

        msg = f"\n[EDIT] {device.name} duzenlemeye acildi"
        self.output_text.append(msg)
        logger.info(msg.strip())

    def _save_device(self):
        """Cihaz kaydet (Yeni = INSERT, Duzenle = UPDATE)."""
        name = self.device_name_input.text().strip()
        ip = self.device_ip_input.text().strip()
        commkey = self.device_commkey_input.text().strip() or None

        if not name or not ip:
            QMessageBox.warning(self, "Uyarı", "Cihaz adi ve IP adresi zorunludur")
            return

        try:
            from models import Device

            if self.editing_device_id:
                # UPDATE
                device = self.session.query(Device).filter_by(id=self.editing_device_id).first()
                if not device:
                    QMessageBox.warning(self, "Uyarı", "Cihaz bulunamadi")
                    return

                device.name = name
                device.ip = ip
                device.set_comm_key(commkey)

                msg = f"\n[BASARILI] Cihaz güncellendi: {name} ({ip})"
                action = "güncellendi"
            else:
                # INSERT
                existing = self.session.query(Device).filter_by(ip=ip).first()
                if existing:
                    QMessageBox.warning(self, "Uyarı", f"Bu IP zaten kayitli: {existing.name}")
                    return

                device = Device(
                    name=name,
                    ip=ip,
                    enabled=True
                )
                device.set_comm_key(commkey)
                msg = f"\n[BASARILI] Cihaz eklendi: {name} ({ip})"
                action = "eklendi"

            self.session.add(device)
            self.session.flush()  # ID'yi al

            # delete_after_pull ayarını kaydet
            from models import Setting
            delete_val = "1" if self.delete_after_pull_cb.isChecked() else "0"
            self.session.query(Setting).filter_by(key=f"delete_after_pull_{device.id}").delete()
            self.session.add(Setting(key=f"delete_after_pull_{device.id}", value=delete_val))
            self.session.commit()

            self.output_text.append(msg)
            logger.info(msg.strip())

            QMessageBox.information(self, "Basarı", f"Cihaz {action}: {name}")

            self._toggle_add_device_form()
            self._refresh_device_list()

        except Exception as e:
            error_msg = f"[HATA] Kayit basarısız: {str(e)}"
            self.output_text.append(error_msg)
            logger.error(error_msg)
            QMessageBox.critical(self, "Hata", f"Kayit basarısız:\n{str(e)}")

    def _delete_device(self, device_id):
        """Cihazi sil (Confirmation ile)."""
        device = self.session.query(Device).filter_by(id=device_id).first()
        if not device:
            return

        reply = QMessageBox.warning(
            self,
            "Onayla",
            f"Cihazi silmek istediginizden emin misiniz?\n\n{device.name} ({device.ip})",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        try:
            self.session.delete(device)
            self.session.commit()

            msg = f"\n[SILINDI] Cihaz silindi: {device.name} ({device.ip})"
            self.output_text.append(msg)
            logger.info(msg.strip())

            QMessageBox.information(self, "Basarı", f"Cihaz silindi: {device.name}")
            self._refresh_device_list()

        except Exception as e:
            error_msg = f"[HATA] Cihaz silemedi: {str(e)}"
            self.output_text.append(error_msg)
            logger.error(error_msg)
            QMessageBox.critical(self, "Hata", f"Silme basarısız:\n{str(e)}")

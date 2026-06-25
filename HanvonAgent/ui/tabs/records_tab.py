"""
Kayıtlar sekmesi — Kayıt tablosu, filtre, push durumu.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QDateEdit, QMessageBox, QInputDialog,
    QStyledItemDelegate, QStyle, QDialog, QTimeEdit, QDialogButtonBox, QFormLayout
)
import httpx
from PySide6.QtCore import Qt, QDate, QTime, Signal
from PySide6.QtGui import QColor, QFont, QCursor
from datetime import datetime
from models import Record, Device, Employee, get_session


class ManualRecordDialog(QDialog):
    """Insert tuşu ile açılan manuel kayıt giriş diyaloğu."""

    def __init__(self, session, date_str: str, parent=None):
        super().__init__(parent)
        self.session = session
        self.date_str = date_str
        self.setWindowTitle("Manuel Kayıt Ekle")
        self.setMinimumWidth(360)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Cihaz
        self.device_combo = QComboBox()
        devices = self.session.query(Device).all()
        for d in devices:
            self.device_combo.addItem(f"{d.name} ({d.ip})", d.id)
        form.addRow("Cihaz:", self.device_combo)

        # Personel ID
        self.emp_id_input = QLineEdit()
        self.emp_id_input.setPlaceholderText("Personel ID girin...")
        self.emp_id_input.textChanged.connect(self._lookup_name)
        form.addRow("Personel ID:", self.emp_id_input)

        # Personel Adı (otomatik dolar)
        self.emp_name_input = QLineEdit()
        self.emp_name_input.setPlaceholderText("ID girilince otomatik dolar")
        form.addRow("Personel Adı:", self.emp_name_input)

        # Tarih
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.fromString(self.date_str, "yyyy-MM-dd"))
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.setCalendarPopup(True)
        form.addRow("Tarih:", self.date_input)

        # Saat
        self.time_input = QTimeEdit()
        self.time_input.setTime(QTime.currentTime())
        self.time_input.setDisplayFormat("HH:mm:ss")
        form.addRow("Saat:", self.time_input)

        # Status
        self.status_combo = QComboBox()
        self.status_combo.addItem("1 — Giriş", "1")
        self.status_combo.addItem("2 — Çıkış", "2")
        form.addRow("Durum:", self.status_combo)

        # Card Src
        self.card_src_combo = QComboBox()
        self.card_src_combo.addItem("from_check", "from_check")
        self.card_src_combo.addItem("from_door", "from_door")
        self.card_src_combo.addItem("NULL", "NULL")
        form.addRow("Kart Kaynağı:", self.card_src_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _lookup_name(self, text):
        """Personel ID girilince DB'den isim ara."""
        emp_id = text.strip()
        if not emp_id.isdigit():
            return
        device_id = self.device_combo.currentData()
        emp = self.session.query(Employee).filter_by(
            device_id=device_id,
            employee_device_id=int(emp_id)
        ).first()
        if emp and emp.name:
            self.emp_name_input.setText(emp.name)
        else:
            self.emp_name_input.clear()

    def get_values(self):
        return {
            "device_id":          self.device_combo.currentData(),
            "employee_device_id": self.emp_id_input.text().strip(),
            "employee_name":      self.emp_name_input.text().strip(),
            "date":               self.date_input.date().toString("yyyy-MM-dd"),
            "time":               self.time_input.time().toString("HH:mm:ss"),
            "status":             self.status_combo.currentData(),
            "card_src":           self.card_src_combo.currentData(),
        }


class RecordTable(QTableWidget):
    """Insert×3 ve Delete×3 gizli tuşlarını destekleyen tablo."""

    insert_triple = Signal()
    delete_triple = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        import time as _time
        self._time = _time
        self._ins_count = 0
        self._ins_last = 0.0
        self._del_count = 0
        self._del_last = 0.0

    def keyPressEvent(self, event):
        now = self._time.time()

        if event.key() == Qt.Key_Insert:
            if now - self._ins_last > 0.6:
                self._ins_count = 0
            self._ins_count += 1
            self._ins_last = now
            if self._ins_count >= 3:
                self._ins_count = 0
                self.insert_triple.emit()
            event.accept()
            return

        if event.key() == Qt.Key_Delete:
            if now - self._del_last > 0.6:
                self._del_count = 0
            self._del_count += 1
            self._del_last = now
            if self._del_count >= 3:
                self._del_count = 0
                self.delete_triple.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class PushStatusDelegate(QStyledItemDelegate):
    """Push durumu sütunu için renkli boyama — stylesheet override sorununu aşar."""

    COLORS = {
        'sent':    QColor(0, 200, 0),
        'pending': QColor(255, 255, 0),
        'failed':  QColor(255, 100, 100),
    }

    def paint(self, painter, option, index):
        value = index.data(Qt.DisplayRole) or ''
        color = self.COLORS.get(value)

        if color:
            painter.fillRect(option.rect, color)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(option.rect, Qt.AlignCenter, value)
        else:
            super().paint(painter, option, index)


class RecordsTab(QWidget):
    """Kayıtlar sekmesi."""

    def __init__(self):
        super().__init__()
        self.session = get_session()

        # Sorting state
        self.sort_column = None
        self.sort_ascending = True
        self.current_records = []


        self._init_ui()
        self._refresh_devices()
        self._load_records()

    def _init_ui(self):
        """Records layout."""
        layout = QVBoxLayout(self)

        # Filtre
        filter_group = QGroupBox("Filtreler")
        filter_layout = QHBoxLayout()

        self.date_mode_combo = QComboBox()
        self.date_mode_combo.addItem("Çekme Tarihi", "pull_date")
        self.date_mode_combo.addItem("Kayıt Tarihi", "record_time")
        self.date_mode_combo.currentIndexChanged.connect(self._load_records)
        filter_layout.addWidget(self.date_mode_combo)

        filter_layout.addWidget(QLabel("Tarih:"))
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.dateChanged.connect(self._load_records)
        filter_layout.addWidget(self.date_input)

        filter_layout.addWidget(QLabel("Cihaz:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self._load_records)
        filter_layout.addWidget(self.device_combo)

        filter_layout.addWidget(QLabel("Push Durumu:"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("Tumü", None)
        self.status_combo.addItem("Beklemede", "pending")
        self.status_combo.addItem("Gonderildi", "sent")
        self.status_combo.addItem("Basarısız", "failed")
        self.status_combo.currentIndexChanged.connect(self._load_records)
        filter_layout.addWidget(self.status_combo)

        filter_layout.addWidget(QLabel("Personel ID:"))
        self.personel_id_input = QLineEdit()
        self.personel_id_input.setPlaceholderText("ID giriniz...")
        self.personel_id_input.setMaximumWidth(100)
        self.personel_id_input.textChanged.connect(self._load_records)
        filter_layout.addWidget(self.personel_id_input)

        filter_layout.addStretch()

        resend_btn = QPushButton("ReSend")
        resend_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; font-weight: bold;"
            " border: none; border-radius: 4px; padding: 5px 12px; }"
            "QPushButton:hover { background-color: #F57C00; }"
            "QPushButton:pressed { background-color: #E65100; }"
        )
        resend_btn.clicked.connect(self._resend_records)
        filter_layout.addWidget(resend_btn)

        refresh_btn = QPushButton("Yenile")
        refresh_btn.clicked.connect(self._load_records)
        filter_layout.addWidget(refresh_btn)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Kayit tablosu (alternating row colors)
        self.record_table = RecordTable()
        self.record_table.setColumnCount(8)
        self.record_table.setHorizontalHeaderLabels([
            "Zaman", "Cihaz IP", "Personel ID", "Personel Adi", "Status", "Push", "Tarih", "Islem"
        ])
        self.record_table.setColumnWidth(0, 150)
        self.record_table.setColumnWidth(1, 120)
        self.record_table.setColumnWidth(2, 100)
        self.record_table.setColumnWidth(3, 120)
        self.record_table.setColumnWidth(4, 60)
        self.record_table.setColumnWidth(5, 80)
        self.record_table.setColumnWidth(6, 120)
        self.record_table.setColumnWidth(7, 50)

        self.record_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #E0E0E0;
                selection-background-color: #e8e8e8;
                selection-color: #000000;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:hover {
                background-color: #e8e8e8;
            }
        """)

        self.record_table.setAlternatingRowColors(True)
        self.record_table.setEditTriggers(self.record_table.EditTrigger.NoEditTriggers)

        # Push sütunu delegate — stylesheet'i bypass eder, renk garantili
        self.record_table.setItemDelegateForColumn(5, PushStatusDelegate(self))

        # Header click for sorting
        self.record_table.horizontalHeader().sectionClicked.connect(self._on_header_click)

        # Gizli tuş sinyalleri
        self.record_table.insert_triple.connect(self._open_manual_record)
        self.record_table.delete_triple.connect(self._delete_selected_record)

        layout.addWidget(self.record_table)

        # Istatistikler
        stats_group = QGroupBox("Istatistikler ve Dosya Yolu")
        stats_layout = QVBoxLayout()

        # Durum satiri
        self.stats_label = QLabel("Toplam: 0 | Gonderildi: 0 | Beklemede: 0")
        stats_layout.addWidget(self.stats_label)

        # JSON dosya yolu
        self.json_path_label = QLabel("JSON Dosya: -")
        self.json_path_label.setStyleSheet("color: #666; font-family: Courier New; font-size: 9pt;")
        stats_layout.addWidget(self.json_path_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

    def _refresh_devices(self):
        """Cihaz listesini yenile."""
        devices = self.session.query(Device).all()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Tümü", None)
        for device in devices:
            self.device_combo.addItem(f"{device.name} ({device.ip})", device.id)
        self.device_combo.blockSignals(False)

    def _load_records(self):
        """Kayıtları filtrele, cache'le ve render et."""
        try:
            date_str = self.date_input.date().toString("yyyy-MM-dd")
            device_id = self.device_combo.currentData()
            push_status = self.status_combo.currentData()
            personel_id = self.personel_id_input.text().strip()

            date_mode = self.date_mode_combo.currentData()
            if date_mode == "record_time":
                query = self.session.query(Record).filter(
                    Record.record_time.like(f"{date_str}%")
                )
            else:
                query = self.session.query(Record).filter(
                    Record.pull_date == date_str
                )

            if device_id:
                query = query.filter(Record.device_id == device_id)

            if push_status:
                query = query.filter(Record.push_status == push_status)

            if personel_id:
                query = query.filter(Record.employee_device_id == personel_id)

            # Cache'le ve render et
            self.current_records = query.all()
            self._render_records()

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kayit yukleme basarısız:\n{str(e)}")

    def _render_records(self):
        """Cached kayıtları sırala ve tablo'ya yükle."""
        # Sıralama uygula
        records = self.current_records
        if self.sort_column is not None:
            records = self._sort_records(records, self.sort_column, self.sort_ascending)

        # Tablo
        self.record_table.setRowCount(len(records))

        for row, record in enumerate(records):
            self.record_table.setItem(row, 0, QTableWidgetItem(record.record_time))

            device_ip = record.device.ip if record.device else "—"
            self.record_table.setItem(row, 1, QTableWidgetItem(device_ip))

            emp_id = record.employee_device_id if record.employee_device_id else "—"
            self.record_table.setItem(row, 2, QTableWidgetItem(emp_id))

            emp_name = record.employee.name if record.employee else "—"
            self.record_table.setItem(row, 3, QTableWidgetItem(emp_name))

            self.record_table.setItem(row, 4, QTableWidgetItem(record.status))

            # Push durumu — delegate ile renklendirilir
            push_item = QTableWidgetItem(record.push_status)
            self.record_table.setItem(row, 5, push_item)

            pushed_time = record.pushed_at.strftime("%Y-%m-%d %H:%M") if record.pushed_at else "—"
            self.record_table.setItem(row, 6, QTableWidgetItem(pushed_time))

            # Edit Button
            edit_btn = QPushButton("✏")
            edit_btn.setFont(QFont("Arial", 10))
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
            edit_btn.clicked.connect(lambda checked, rec_id=record.id: self._edit_record(rec_id))
            self.record_table.setCellWidget(row, 7, edit_btn)

        # İstatistikler
        total = len(records)
        sent = sum(1 for r in records if r.push_status == 'sent')
        pending = sum(1 for r in records if r.push_status == 'pending')

        self.stats_label.setText(f"Toplam: {total} | Gonderildi: {sent} | Beklemede: {pending}")

        # JSON dosya yolunu goster (en son kaydedilen)
        latest_record = records[0] if records else None

        if latest_record and latest_record.file_path:
            self.json_path_label.setText(f"JSON Dosya: {latest_record.file_path}")
        else:
            self.json_path_label.setText("JSON Dosya: -")

    def _edit_record(self, record_id):
        """Kayıt detaylarını goster."""
        record = self.session.query(Record).filter_by(id=record_id).first()
        if not record:
            return

        device_name = record.device.name if record.device else "Bilinmiyor"
        emp_name = record.employee.name if record.employee else "Bilinmiyor"

        details = (
            f"Kayıt Detayları\n"
            f"{'='*50}\n\n"
            f"Zaman: {record.record_time}\n"
            f"Cihaz: {device_name} ({record.device.ip if record.device else 'N/A'})\n"
            f"Personel ID: {record.employee_device_id if record.employee_device_id else '-'}\n"
            f"Personel Adı: {emp_name}\n"
            f"Status: {record.status}\n"
            f"Push Durumu: {record.push_status}\n"
            f"Gonderildi: {record.pushed_at.strftime('%Y-%m-%d %H:%M') if record.pushed_at else 'Henüz gonderilmedi'}\n"
            f"JSON Dosya: {record.file_path if record.file_path else '-'}\n"
        )

        QMessageBox.information(self, "Kayit Detayları", details)

    def _resend_records(self):
        """Mevcut filtredeki kayıtları push_status ne olursa olsun API'ye tekrar gönder."""
        from models import Setting

        if not self.current_records:
            QMessageBox.information(self, "Bilgi", "Gönderilecek kayıt yok.")
            return

        setting_status = self.session.query(Setting).filter_by(key="api_status").first()
        if not setting_status or setting_status.value != "1":
            QMessageBox.warning(self, "API Pasif", "API durumu Pasif.\nAyarlar sekmesinden Aktif yapın.")
            return

        setting_ep = self.session.query(Setting).filter_by(key="api_endpoint").first()
        setting_tk = self.session.query(Setting).filter_by(key="api_token").first()
        endpoint = setting_ep.value if setting_ep else None
        token = setting_tk.value if setting_tk else None

        if not endpoint:
            QMessageBox.warning(self, "Hata", "API endpoint ayarlanmamış.\nAyarlar sekmesinden girin.")
            return

        # Cihaza göre grupla
        by_device = {}
        for r in self.current_records:
            ip = r.device.ip if r.device else ""
            if ip not in by_device:
                by_device[ip] = {"device_ip": ip, "device_name": r.device.name if r.device else "", "records": []}
            by_device[ip]["records"].append({
                "time": r.record_time,
                "id": r.employee_device_id or "",
                "name": r.employee.name if r.employee else "",
                "status": str(r.status),
                "card_src": r.card_src or "",
            })
        payload = {"devices": list(by_device.values())}

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = httpx.post(endpoint, json=payload, headers=headers, timeout=15)

            if resp.status_code < 400:
                from datetime import datetime
                for r in self.current_records:
                    r.push_status = "sent"
                    r.pushed_at = datetime.utcnow()
                self.session.commit()
                self._render_records()
                QMessageBox.information(
                    self, "Başarılı",
                    f"{len(self.current_records)} kayıt gönderildi.\nHTTP {resp.status_code}: {resp.text[:100]}"
                )
            else:
                QMessageBox.warning(
                    self, "Sunucu Hatası",
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
        except httpx.ConnectError:
            QMessageBox.critical(self, "Bağlantı Hatası", f"Sunucuya ulaşılamadı:\n{endpoint}")
        except httpx.TimeoutException:
            QMessageBox.critical(self, "Zaman Aşımı", "Sunucu 15 saniye içinde yanıt vermedi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _on_header_click(self, col):
        """Header'a tıklandı — sıralama yap."""
        # Sıralama yapılamayan sütunlar
        if col in (7,):  # İşlem butonu
            return

        # Aynı sütuna tekrar tıklandıysa → ters sırala
        if self.sort_column == col:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_column = col
            self.sort_ascending = True

        # Tabloyu yeniden çiz
        self._render_records()
        self._update_header_indicator()

    def _update_header_indicator(self):
        """Header'da sıralama yönünü göster (▲▼)."""
        header = self.record_table.horizontalHeader()
        headers = [
            "Zaman", "Cihaz IP", "Personel ID", "Personel Adi", "Status", "Push", "Tarih", "Islem"
        ]

        for col, title in enumerate(headers):
            if col == self.sort_column:
                arrow = "▲" if self.sort_ascending else "▼"
                header.model().setHeaderData(col, Qt.Horizontal, f"{title} {arrow}")
            else:
                header.model().setHeaderData(col, Qt.Horizontal, title)

    def _sort_records(self, records, col, ascending):
        """Kayıt listesini verilen sütuna göre sırala."""
        if col == 0:  # Zaman
            return sorted(records, key=lambda r: r.record_time or '', reverse=not ascending)
        elif col == 1:  # Cihaz IP
            return sorted(records, key=lambda r: (r.device.ip if r.device else '').lower(), reverse=not ascending)
        elif col == 2:  # Personel ID
            return sorted(records, key=lambda r: int(r.employee_device_id or 0), reverse=not ascending)
        elif col == 3:  # Personel Adı
            return sorted(records, key=lambda r: (r.employee.name if r.employee else '').lower(), reverse=not ascending)
        elif col == 4:  # Status
            return sorted(records, key=lambda r: r.status or '', reverse=not ascending)
        elif col == 5:  # Push Durumu
            return sorted(records, key=lambda r: r.push_status or '', reverse=not ascending)
        elif col == 6:  # Tarih (Push Tarih)
            return sorted(records, key=lambda r: r.pushed_at or '', reverse=not ascending)
        else:
            return records

    # ─── Insert tuşu — gizli manuel kayıt ───────────────────────────────────

    def _delete_selected_record(self):
        """Seçili satırı sil (3×Delete ile tetiklenir)."""
        row = self.record_table.currentRow()
        if row < 0 or row >= len(self.current_records):
            return

        records = self.current_records
        if self.sort_column is not None:
            records = self._sort_records(list(records), self.sort_column, self.sort_ascending)
        record = records[row]

        emp_name = record.employee.name if record.employee else "—"
        confirm = QMessageBox.question(
            self, "Kaydı Sil",
            f"Bu kaydı silmek istediğinizden emin misiniz?\n\n"
            f"Zaman: {record.record_time}\n"
            f"Personel: {emp_name} (ID: {record.employee_device_id})\n\n"
            f"Not: Cihazda hâlâ varsa bir sonraki çekimde yeniden oluşur.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.session.delete(record)
        self.session.commit()
        self._load_records()

    def _open_manual_record(self):
        """Insert tuşu ile manuel kayıt ekle."""
        date_str = self.date_input.date().toString("yyyy-MM-dd")
        dlg = ManualRecordDialog(self.session, date_str, self)
        if dlg.exec() != QDialog.Accepted:
            return

        vals = dlg.get_values()

        device = self.session.query(Device).filter_by(id=vals['device_id']).first()
        if not device:
            return

        emp = None
        if vals['employee_device_id'].isdigit():
            emp = self.session.query(Employee).filter_by(
                device_id=device.id,
                employee_device_id=int(vals['employee_device_id'])
            ).first()

        from pathlib import Path
        record_date = vals['date']
        date_obj = QDate.fromString(record_date, "yyyy-MM-dd")
        data_dir = Path("data")
        file_path = (data_dir / str(date_obj.year())
                     / f"{date_obj.month():02d}" / f"{date_obj.day():02d}.json")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        record_time = f"{record_date} {vals['time']}"
        card_src = vals['card_src'] if vals['card_src'] != 'NULL' else None

        record = Record(
            device_id=device.id,
            employee_id=emp.id if emp else None,
            employee_device_id=vals['employee_device_id'] if vals['employee_device_id'] else None,
            record_time=record_time,
            status=vals['status'],
            card_src=card_src,
            source='device',
            push_status='pending',
            file_path=str(file_path),
            pull_date=record_date,
        )
        self.session.add(record)
        self.session.commit()

        self._append_to_json(file_path, device, record, vals['employee_name'])
        self._load_records()

    def _append_to_json(self, file_path, device, record, emp_name: str):
        """Manuel kaydı ilgili günün JSON dosyasına ekle."""
        import json
        from datetime import datetime

        new_rec = {
            "time": record.record_time,
            "id": record.employee_device_id or "?",
            "name": emp_name,
            "status": record.status,
            "card_src": record.card_src or "",
        }

        content = []
        if file_path.exists():
            try:
                content = json.loads(file_path.read_text(encoding="utf-8-sig"))
            except Exception:
                content = []

        device_entry = next((de for de in content if de.get('device_ip') == device.ip), None)
        if device_entry is None:
            device_entry = {
                "device_ip": device.ip,
                "device_name": device.name,
                "pulled_at": datetime.now().isoformat(),
                "records": [],
            }
            content.append(device_entry)

        device_entry["records"].append(new_rec)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("[\n")
            for i, de in enumerate(content):
                f.write("  {\n")
                f.write(f'    "device_ip": "{de["device_ip"]}",\n')
                f.write(f'    "device_name": "{de.get("device_name", "")}",\n')
                f.write(f'    "pulled_at": "{de["pulled_at"]}",\n')
                f.write('    "records": [\n')
                recs = de.get("records", [])
                for j, rec in enumerate(recs):
                    f.write(f'      {json.dumps(rec, ensure_ascii=False, separators=(",", ":"))}')
                    f.write(",\n" if j < len(recs) - 1 else "\n")
                f.write("    ]\n")
                f.write("  }")
                f.write(",\n" if i < len(content) - 1 else "\n")
            f.write("]\n")

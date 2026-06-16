"""
Cihazdan cihaza personel transferi dialog'u.

Personel listesi kaynak cihazdan canlı GetEmployeeID() ile çekilir (DeviceListFetchWorker).
Transfer işlemi DeviceTransferWorker (QThread) üzerinde çalışır — UI donmaz.
"""

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)

from core.hanvon_client import HanvonClient
from models import Device, Employee, get_session
from services.device_transfer_service import DeviceTransferWorker

logger = logging.getLogger("HanvonAgent.Transfer")

ID_ROLE = Qt.UserRole


class DeviceListFetchWorker(QThread):
    """Kaynak cihazdan GetEmployeeID() ile personel ID listesini çeker."""

    fetched = Signal(list)   # list[str]
    error = Signal(str)

    def __init__(self, ip: str, comm_key, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.comm_key = comm_key

    def run(self):
        client = None
        try:
            client = HanvonClient(self.ip, comm_key=self.comm_key)
            client.connect()
            ids = client.get_employee_id()
            self.fetched.emit([str(i) for i in ids])
        except Exception as e:
            logger.error("DeviceListFetchWorker hatası: %s", e, exc_info=True)
            self.error.emit(str(e))
        finally:
            if client:
                try:
                    client.disconnect()
                except Exception:
                    pass


class DeviceTransferDialog(QDialog):
    """Cihazdan cihaza personel transferi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = get_session()
        self._all_rows = []       # [{id, name, check_type}, ...]
        self._fetch_worker = None
        self._worker = None
        self._sort_col = 1        # varsayılan: ID
        self._sort_asc = True

        self.setWindowTitle("Cihaz Transferi - Personel Aktar")
        self.setGeometry(100, 100, 900, 680)
        self.setFixedSize(900, 680)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # --- Cihaz seçimi ---
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Kaynak Cihaz:"))
        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        device_layout.addWidget(self.source_combo)
        device_layout.addWidget(QLabel("Hedef Cihaz:"))
        self.target_combo = QComboBox()
        device_layout.addWidget(self.target_combo)
        device_layout.addStretch()
        layout.addLayout(device_layout)

        # --- Durum + filtre ---
        filter_layout = QHBoxLayout()
        self.status_label = QLabel("Cihaz seçiniz")
        filter_layout.addWidget(self.status_label)
        filter_layout.addStretch()
        filter_layout.addWidget(QLabel("Filtre:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("ID veya isim ara...")
        self.filter_input.setFixedWidth(200)
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)

        # --- Personel tablosu ---
        self.employee_table = QTableWidget()
        self.employee_table.setColumnCount(4)
        self.employee_table.setHorizontalHeaderLabels(["Seç", "ID", "İsim", "Tür"])
        self.employee_table.setColumnWidth(0, 50)
        self.employee_table.setColumnWidth(1, 70)
        self.employee_table.setColumnWidth(2, 300)
        self.employee_table.setColumnWidth(3, 100)
        self.employee_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.employee_table.setSelectionMode(QTableWidget.NoSelection)
        self.employee_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.employee_table.setAlternatingRowColors(True)
        self.employee_table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        self.employee_table.setStyleSheet("""
            QTableWidget { gridline-color: #d0d0d0; font-size: 13px; }
            QTableWidget::item { padding: 4px 8px; }
            QTableWidget::item:hover { background-color: #e8e8e8; }
            QHeaderView::section {
                background-color: #f5f5f5; padding: 6px;
                font-weight: bold; border: 1px solid #d0d0d0;
            }
        """)
        layout.addWidget(self.employee_table)

        # --- Güncelleme seçenekleri + toplu seç ---
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Mevcut personeli güncelle:"))
        self.update_name_check = QCheckBox("Ad/Soyad")
        self.update_name_check.setChecked(True)
        options_layout.addWidget(self.update_name_check)
        self.update_biometric_check = QCheckBox("Biometrik Veri")
        self.update_biometric_check.setChecked(True)
        options_layout.addWidget(self.update_biometric_check)
        options_layout.addStretch()
        select_all_btn = QPushButton("Tümünü Seç")
        select_all_btn.clicked.connect(self._select_all)
        options_layout.addWidget(select_all_btn)
        deselect_all_btn = QPushButton("Tümünü Bırak")
        deselect_all_btn.clicked.connect(self._deselect_all)
        options_layout.addWidget(deselect_all_btn)
        layout.addLayout(options_layout)

        # --- Alt butonlar ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.transfer_btn = QPushButton("📤 Transferi Başlat")
        self.transfer_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }"
        )
        self.transfer_btn.clicked.connect(self._start_transfer)
        self.transfer_btn.setEnabled(False)
        btn_layout.addWidget(self.transfer_btn)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._refresh_devices()

    # ------------------------------------------------------------------
    # Cihaz yükleme
    # ------------------------------------------------------------------

    def _refresh_devices(self):
        devices = self.session.query(Device).all()
        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        self.source_combo.clear()
        self.target_combo.clear()
        for device in devices:
            label = f"{device.name} ({device.ip})"
            self.source_combo.addItem(label, device.id)
            self.target_combo.addItem(label, device.id)
        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)
        self._on_source_changed()

    def _on_source_changed(self):
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()

        if source_id == target_id and target_id is not None:
            for i in range(self.target_combo.count()):
                if self.target_combo.itemData(i) != source_id:
                    self.target_combo.setCurrentIndex(i)
                    break

        if source_id is None:
            self._all_rows = []
            self.employee_table.setRowCount(0)
            self.status_label.setText("Cihaz seçiniz")
            self.transfer_btn.setEnabled(False)
            return

        device = self.session.query(Device).filter_by(id=source_id).first()
        if not device:
            return

        # Önceki fetch worker'ı durdur
        if self._fetch_worker and self._fetch_worker.isRunning():
            self._fetch_worker.terminate()
            self._fetch_worker.wait()

        self.employee_table.setRowCount(0)
        self._all_rows = []
        self.transfer_btn.setEnabled(False)
        self.status_label.setText(f"⏳ {device.name} ({device.ip}) bağlanılıyor...")

        self._fetch_worker = DeviceListFetchWorker(device.ip, device.comm_key)
        self._fetch_worker.fetched.connect(lambda ids: self._on_list_fetched(ids, source_id))
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_list_fetched(self, ids: list, source_device_id: int):
        """GetEmployeeID yanıtı — DB ile isim eşleştir, tabloya doldur."""
        employees = self.session.query(Employee).filter_by(device_id=source_device_id).all()
        name_map = {str(e.employee_device_id): (e.name or "—") for e in employees}
        type_map = {str(e.employee_device_id): (e.check_type or "—") for e in employees}

        self._all_rows = [
            {
                'id': eid,
                'name': name_map.get(eid, "—"),
                'check_type': type_map.get(eid, "—"),
            }
            for eid in ids
        ]

        self.status_label.setText(f"✓ {len(ids)} personel bulundu (cihazdan)")
        self.transfer_btn.setEnabled(True)
        self._apply_filter()

    def _on_fetch_error(self, error_msg: str):
        self.status_label.setText(f"❌ Bağlantı hatası: {error_msg[:80]}")
        self.employee_table.setRowCount(0)
        self._all_rows = []
        self.transfer_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Sorting + filter
    # ------------------------------------------------------------------

    def _on_header_click(self, col: int):
        if col == 0:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._apply_filter()

    def _apply_filter(self):
        text = self.filter_input.text().strip().lower()

        rows = self._all_rows
        if text:
            rows = [r for r in rows if text in r['id'] or text in r['name'].lower()]

        col_keys = {1: 'id', 2: 'name', 3: 'check_type'}
        key = col_keys.get(self._sort_col, 'id')

        if key == 'id':
            rows = sorted(
                rows,
                key=lambda r: int(r['id']) if r['id'].isdigit() else 0,
                reverse=not self._sort_asc,
            )
        else:
            rows = sorted(rows, key=lambda r: r[key].lower(), reverse=not self._sort_asc)

        self._populate_table(rows)
        self._update_header_indicator()

    def _update_header_indicator(self):
        labels = {1: "ID", 2: "İsim", 3: "Tür"}
        for col, base in labels.items():
            item = self.employee_table.horizontalHeaderItem(col)
            if item is None:
                continue
            if col == self._sort_col:
                item.setText(base + (" ▲" if self._sort_asc else " ▼"))
            else:
                item.setText(base)

    def _populate_table(self, rows: list):
        self.employee_table.setRowCount(len(rows))
        for row_idx, row_data in enumerate(rows):
            cb = QCheckBox()
            cb.setChecked(True)
            self.employee_table.setCellWidget(row_idx, 0, cb)

            id_item = QTableWidgetItem(row_data['id'])
            id_item.setData(ID_ROLE, row_data['id'])
            self.employee_table.setItem(row_idx, 1, id_item)

            self.employee_table.setItem(row_idx, 2, QTableWidgetItem(row_data['name']))
            self.employee_table.setItem(row_idx, 3, QTableWidgetItem(row_data['check_type']))

    # ------------------------------------------------------------------
    # Toplu seç / bırak
    # ------------------------------------------------------------------

    def _select_all(self):
        for row in range(self.employee_table.rowCount()):
            cb = self.employee_table.cellWidget(row, 0)
            if cb:
                cb.setChecked(True)

    def _deselect_all(self):
        for row in range(self.employee_table.rowCount()):
            cb = self.employee_table.cellWidget(row, 0)
            if cb:
                cb.setChecked(False)

    # ------------------------------------------------------------------
    # Transfer
    # ------------------------------------------------------------------

    def _start_transfer(self):
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()

        if source_id is None or target_id is None:
            QMessageBox.warning(self, "Hata", "Cihaz seçiniz.")
            return

        if source_id == target_id:
            QMessageBox.warning(self, "Hata", "Farklı cihazlar seçiniz.")
            return

        selected_ids = []
        for row in range(self.employee_table.rowCount()):
            cb = self.employee_table.cellWidget(row, 0)
            if cb and cb.isChecked():
                item = self.employee_table.item(row, 1)
                if item:
                    selected_ids.append(item.data(ID_ROLE))

        if not selected_ids:
            QMessageBox.warning(self, "Hata", "Personel seçiniz.")
            return

        reply = QMessageBox.question(
            self,
            "Transfer Onayı",
            f"{len(selected_ids)} personel aktarılacak:\n\n"
            f"Kaynak: {self.source_combo.currentText()}\n"
            f"Hedef: {self.target_combo.currentText()}\n\n"
            f"Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Progress dialog
        self._progress_dialog = QDialog(self)
        self._progress_dialog.setWindowTitle("Transfer Yapılıyor...")
        self._progress_dialog.setFixedSize(600, 450)
        p_layout = QVBoxLayout(self._progress_dialog)

        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setFont(QFont("Consolas", 9))
        self._result_text.setText(f"Transfer başladı: {len(selected_ids)} personel\n")
        p_layout.addWidget(self._result_text)

        self._progress_close_btn = QPushButton("Kapat")
        self._progress_close_btn.setEnabled(False)
        self._progress_close_btn.clicked.connect(self._progress_dialog.accept)
        p_layout.addWidget(self._progress_close_btn)

        self.transfer_btn.setEnabled(False)

        self._worker = DeviceTransferWorker(
            source_device_id=source_id,
            target_device_id=target_id,
            employee_device_ids=selected_ids,
            update_name=self.update_name_check.isChecked(),
            update_biometric=self.update_biometric_check.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

        self._progress_dialog.exec()

    def _on_progress(self, message: str):
        self._result_text.append(message)
        sb = self._result_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, successful: int, failed: int):
        total = successful + failed
        self._result_text.append("\n" + "=" * 50)
        self._result_text.append(f"✅ Başarılı: {successful}/{total}")
        if failed > 0:
            self._result_text.append(f"❌ Başarısız: {failed}")
        self._progress_close_btn.setEnabled(True)
        self.transfer_btn.setEnabled(True)
        self._worker = None

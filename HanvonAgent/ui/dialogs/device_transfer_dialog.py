"""
Cihazdan cihaza personel transferi dialog'u (ve "İsimleri Eşitle" kipi).

Personel listesi kaynak cihazdan canlı GetEmployeeID() ile çekilir (DeviceListFetchWorker).
Her ID için hedefteki durum DB'den (son "Personelleri Getir") hesaplanır:
Yeni / Aynı / İsim farklı / Yüz farklı / ⚠ Başka kişi. Transfer işlemi
DeviceTransferWorker (QThread) üzerinde çalışır ve durumu cihazdan tekrar
doğrular — DB eski olsa bile başka kişinin üzerine izinsiz yazılmaz.

2026-09-30 (BUG-017/019): seçimler filtre/sıralamada korunur, varsayılan boş;
liste worker'ı terminate() ile öldürülmez (cihaz kilidi takılı kalırdı).
"""

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)

from core.hanvon_client import HanvonClient
from models import Device, Employee, get_session
from services.device_transfer_service import (
    DeviceTransferWorker, TransferItem, is_different_person,
)
from services.employee_sync_service import normalize_name

logger = logging.getLogger("HanvonAgent.Transfer")

ID_ROLE = Qt.UserRole

# Hedefteki durum (DB'ye göre)
STATUS_NEW = "Yeni"
STATUS_SAME = "Aynı"
STATUS_NAME = "İsim farklı"
STATUS_FACE = "Yüz farklı"
STATUS_OTHER = "⚠ Başka kişi"
STATUS_UNKNOWN = "Bilinmiyor"

STATUS_COLORS = {
    STATUS_NAME: QColor(255, 243, 205),   # sarı — isim düzeltilecek
    STATUS_FACE: QColor(227, 242, 253),   # mavi — aynı kişi, farklı kayıt
    STATUS_OTHER: QColor(255, 205, 210),  # kırmızı — başka kişi
    STATUS_NEW: QColor(232, 245, 233),    # yeşil — hedefte yok
}

# Durum filtresi: (etiket, kabul edilen durumlar | None = hepsi)
STATUS_FILTERS = [
    ("Tümü", None),
    ("Farklı olanlar", {STATUS_NAME, STATUS_FACE, STATUS_OTHER, STATUS_NEW}),
    (STATUS_NAME, {STATUS_NAME}),
    (STATUS_OTHER, {STATUS_OTHER}),
    (STATUS_NEW, {STATUS_NEW}),
]

COL_SELECT, COL_ID, COL_SRC, COL_TGT, COL_STATUS = range(5)


def classify(src_emp, tgt_emp) -> str:
    """Kaynak/hedef DB kayıtlarına göre hedefteki durum."""
    if src_emp is None:
        return STATUS_UNKNOWN
    if tgt_emp is None:
        return STATUS_NEW
    src_faces, tgt_faces = src_emp.face_data, tgt_emp.face_data
    if is_different_person(src_emp.name, src_faces, tgt_emp.name, tgt_faces):
        return STATUS_OTHER
    if normalize_name(src_emp.name) == normalize_name(tgt_emp.name):
        if src_faces and tgt_faces and src_faces != tgt_faces:
            return STATUS_FACE
        return STATUS_SAME
    return STATUS_NAME


class DeviceListFetchWorker(QThread):
    """Kaynak cihazdan GetEmployeeID() ile personel ID listesini çeker."""

    fetched = Signal(list)   # list[str]
    error = Signal(str)

    def __init__(self, ip: str, comm_key, port: int = HanvonClient.DEFAULT_PORT, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.comm_key = comm_key
        self.port = port

    def run(self):
        client = None
        try:
            client = HanvonClient(self.ip, port=self.port, comm_key=self.comm_key)
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
    """Cihazdan cihaza personel transferi / isim eşitleme."""

    def __init__(self, parent=None, target_device_id=None, equalize=False):
        """
        Args:
            target_device_id: Hedef olarak önceden seçilecek cihaz.
            equalize: True → "İsimleri Eşitle" kipi: yalnız isim gönderilir,
                      "İsim farklı" satırlar önceden seçili, "Farklı olanlar" filtresi.
        """
        super().__init__(parent)
        self.session = get_session()
        self.equalize = equalize
        self._initial_target_id = target_device_id
        self._ids = []            # kaynak cihazdan gelen ID'ler
        self._all_rows = []       # [{id, src_name, tgt_name, status}, ...]
        self._selected = set()    # seçili ID'ler — filtre/sıralamadan bağımsız
        self._fetch_worker = None
        self._fetch_gen = 0       # eski liste sonuçlarını ayırt etmek için
        self._running_fetches = []  # bitene kadar referans (GC olmasın)
        self._worker = None
        self._sort_col = COL_ID
        self._sort_asc = True

        self.setWindowTitle("İsimleri Eşitle" if equalize else "Cihaz Transferi - Personel Aktar")
        self.setGeometry(100, 100, 1000, 700)
        self.setFixedSize(1000, 700)

        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.addLayout(self._build_device_row())
        layout.addLayout(self._build_filter_row())
        self._build_table()
        layout.addWidget(self.employee_table)
        layout.addLayout(self._build_options_row())
        layout.addLayout(self._build_buttons_row())

        self.status_filter.setCurrentIndex(1 if self.equalize else 0)
        self._refresh_devices()

    def _build_device_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Referans (kaynak):" if self.equalize else "Kaynak Cihaz:"))
        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        row.addWidget(self.source_combo)
        row.addWidget(QLabel("Hedef Cihaz:"))
        self.target_combo = QComboBox()
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        row.addWidget(self.target_combo)
        row.addStretch()
        return row

    def _build_filter_row(self):
        row = QHBoxLayout()
        self.status_label = QLabel("Cihaz seçiniz")
        row.addWidget(self.status_label)
        row.addStretch()
        row.addWidget(QLabel("Durum:"))
        self.status_filter = QComboBox()
        for label, _ in STATUS_FILTERS:
            self.status_filter.addItem(label)
        self.status_filter.currentIndexChanged.connect(self._apply_filter)
        row.addWidget(self.status_filter)
        row.addWidget(QLabel("Filtre:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("ID veya isim ara...")
        self.filter_input.setFixedWidth(200)
        self.filter_input.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter_input)
        return row

    def _build_table(self):
        self.employee_table = QTableWidget()
        self.employee_table.setColumnCount(5)
        self.employee_table.setHorizontalHeaderLabels(
            ["Seç", "ID", "Kaynaktaki İsim", "Hedefteki İsim", "Durum"])
        for col, width in ((COL_SELECT, 50), (COL_ID, 70), (COL_SRC, 280), (COL_TGT, 280), (COL_STATUS, 120)):
            self.employee_table.setColumnWidth(col, width)
        self.employee_table.horizontalHeader().setSectionResizeMode(COL_TGT, QHeaderView.Stretch)
        self.employee_table.setSelectionMode(QTableWidget.NoSelection)
        self.employee_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.employee_table.horizontalHeader().sectionClicked.connect(self._on_header_click)
        self.employee_table.setStyleSheet("""
            QTableWidget { gridline-color: #d0d0d0; font-size: 13px; }
            QTableWidget::item { padding: 4px 8px; }
            QHeaderView::section {
                background-color: #f5f5f5; padding: 6px;
                font-weight: bold; border: 1px solid #d0d0d0;
            }
        """)

    def _build_options_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Mevcut personeli güncelle:"))
        self.update_name_check = QCheckBox("Ad/Soyad")
        self.update_name_check.setChecked(True)
        row.addWidget(self.update_name_check)
        self.update_biometric_check = QCheckBox("Biometrik Veri")
        self.update_biometric_check.setChecked(not self.equalize)  # eşitleme = yalnız isim
        row.addWidget(self.update_biometric_check)
        self.overwrite_other_check = QCheckBox("⚠ Başka kişi olanların üzerine yaz")
        self.overwrite_other_check.setToolTip(
            "Hedefte aynı ID'de BAŞKA bir kişi kayıtlıysa (isim ve yüz farklı) o kişi\n"
            "kaynaktaki kişiyle değiştirilir — hedefteki kişi o cihazdan giremez.\n"
            "Kapalıyken bu satırlar atlanır.")
        self.overwrite_other_check.setStyleSheet("QCheckBox { color: #c62828; }")
        row.addWidget(self.overwrite_other_check)
        row.addStretch()
        self.selected_label = QLabel("Seçili: 0")
        row.addWidget(self.selected_label)
        select_all_btn = QPushButton("Görünenleri Seç")
        select_all_btn.clicked.connect(self._select_all)
        row.addWidget(select_all_btn)
        deselect_all_btn = QPushButton("Görünenleri Bırak")
        deselect_all_btn.clicked.connect(self._deselect_all)
        row.addWidget(deselect_all_btn)
        return row

    def _build_buttons_row(self):
        row = QHBoxLayout()
        row.addStretch()
        self.transfer_btn = QPushButton("⇄ İsimleri Gönder" if self.equalize else "📤 Transferi Başlat")
        self.transfer_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        self.transfer_btn.clicked.connect(self._start_transfer)
        self.transfer_btn.setEnabled(False)
        row.addWidget(self.transfer_btn)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return row

    # ------------------------------------------------------------------
    # Cihaz yükleme
    # ------------------------------------------------------------------

    def _refresh_devices(self):
        devices = self.session.query(Device).all()
        for combo in (self.source_combo, self.target_combo):
            combo.blockSignals(True)
            combo.clear()
            for device in devices:
                combo.addItem(f"{device.name} ({device.ip})", device.id)
        if self._initial_target_id is not None:
            idx = self.target_combo.findData(self._initial_target_id)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)
            # Kaynak: hedeften farklı ilk cihaz
            for i in range(self.source_combo.count()):
                if self.source_combo.itemData(i) != self._initial_target_id:
                    self.source_combo.setCurrentIndex(i)
                    break
        for combo in (self.source_combo, self.target_combo):
            combo.blockSignals(False)
        self._on_source_changed()

    def _ensure_different_target(self):
        source_id = self.source_combo.currentData()
        if source_id is not None and self.target_combo.currentData() == source_id:
            for i in range(self.target_combo.count()):
                if self.target_combo.itemData(i) != source_id:
                    self.target_combo.blockSignals(True)
                    self.target_combo.setCurrentIndex(i)
                    self.target_combo.blockSignals(False)
                    break

    def _on_source_changed(self):
        self._ensure_different_target()
        source_id = self.source_combo.currentData()
        self._fetch_gen += 1  # önceki (hâlâ çalışıyor olabilecek) okumanın sonucu yok sayılır
        self._ids, self._all_rows = [], []
        self._selected.clear()
        self.employee_table.setRowCount(0)
        self.transfer_btn.setEnabled(False)
        self._update_selected_label()

        device = self.session.get(Device, source_id) if source_id is not None else None
        if device is None:
            self.status_label.setText("Cihaz seçiniz")
            return

        self.status_label.setText(f"⏳ {device.name} ({device.ip}) bağlanılıyor...")
        gen = self._fetch_gen
        worker = DeviceListFetchWorker(device.ip, device.comm_key, port=device.port)
        worker.fetched.connect(lambda ids, g=gen, sid=source_id: self._on_list_fetched(ids, sid, g))
        worker.error.connect(lambda msg, g=gen: self._on_fetch_error(msg, g))
        worker.finished.connect(lambda w=worker: self._forget_fetch(w))
        self._running_fetches.append(worker)
        self._fetch_worker = worker
        worker.start()

    def _forget_fetch(self, worker):
        if worker in self._running_fetches:
            self._running_fetches.remove(worker)

    def _on_target_changed(self):
        self._ensure_different_target()
        if self._ids:
            self._rebuild_rows()

    def _on_list_fetched(self, ids: list, source_device_id: int, gen: int = None):
        """GetEmployeeID yanıtı — eski bir okumaya aitse yok sayılır."""
        if gen is not None and gen != self._fetch_gen:
            return
        if source_device_id != self.source_combo.currentData():
            return
        self._ids = list(ids)
        self._rebuild_rows()
        if self.equalize:
            # Referansta isim varsa ve yüz aynı kişiyi gösteriyorsa (İsim farklı) önceden seç
            self._selected = {r['id'] for r in self._all_rows
                              if r['status'] == STATUS_NAME and r['src_has_name']}
        self.status_label.setText(f"✓ {len(ids)} personel bulundu (cihazdan)")
        self.transfer_btn.setEnabled(True)
        self._apply_filter()

    def _on_fetch_error(self, error_msg: str, gen: int = None):
        if gen is not None and gen != self._fetch_gen:
            return
        self.status_label.setText(f"❌ Bağlantı hatası: {error_msg[:80]}")
        self.employee_table.setRowCount(0)
        self._ids, self._all_rows = [], []
        self.transfer_btn.setEnabled(False)

    def _rebuild_rows(self):
        """Kaynak ID listesi + DB (her iki cihaz) → satırlar ve durumlar."""
        self.session.expire_all()  # transfer worker kendi session'ında yazmış olabilir
        source_id, target_id = self.source_combo.currentData(), self.target_combo.currentData()
        src = {str(e.employee_device_id): e for e in
               self.session.query(Employee).filter_by(device_id=source_id).all()}
        tgt = {str(e.employee_device_id): e for e in
               self.session.query(Employee).filter_by(device_id=target_id).all()}
        self._all_rows = []
        for eid in self._ids:
            s, t = src.get(eid), tgt.get(eid)
            self._all_rows.append({
                'id': eid,
                'src_name': (s.name or "—") if s else "—",
                'src_has_name': bool(s is not None and normalize_name(s.name)),
                'tgt_name': (t.name or "(boş)") if t else "—",
                'status': classify(s, t),
            })
        self._apply_filter()

    # ------------------------------------------------------------------
    # Sıralama + filtre
    # ------------------------------------------------------------------

    def _on_header_click(self, col: int):
        if col == COL_SELECT:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col, self._sort_asc = col, True
        self._apply_filter()

    def _visible_rows(self):
        text = self.filter_input.text().strip().lower()
        allowed = STATUS_FILTERS[max(self.status_filter.currentIndex(), 0)][1]
        rows = [
            r for r in self._all_rows
            if (allowed is None or r['status'] in allowed)
            and (not text or text in r['id'] or text in r['src_name'].lower() or text in r['tgt_name'].lower())
        ]
        if self._sort_col == COL_ID:
            key = lambda r: int(r['id']) if r['id'].isdigit() else 0  # noqa: E731
        else:
            field = {COL_SRC: 'src_name', COL_TGT: 'tgt_name', COL_STATUS: 'status'}[self._sort_col]
            key = lambda r: r[field].lower()  # noqa: E731
        return sorted(rows, key=key, reverse=not self._sort_asc)

    def _apply_filter(self):
        self._populate_table(self._visible_rows())
        self._update_header_indicator()
        self._update_selected_label()

    def _update_header_indicator(self):
        labels = {COL_ID: "ID", COL_SRC: "Kaynaktaki İsim", COL_TGT: "Hedefteki İsim", COL_STATUS: "Durum"}
        for col, base in labels.items():
            item = self.employee_table.horizontalHeaderItem(col)
            if item is not None:
                arrow = (" ▲" if self._sort_asc else " ▼") if col == self._sort_col else ""
                item.setText(base + arrow)

    def _populate_table(self, rows: list):
        self.employee_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            cb = QCheckBox()
            cb.setChecked(row['id'] in self._selected)
            cb.toggled.connect(lambda checked, eid=row['id']: self._on_toggled(eid, checked))
            self.employee_table.setCellWidget(row_idx, COL_SELECT, cb)

            id_item = QTableWidgetItem(row['id'])
            id_item.setData(ID_ROLE, row['id'])
            self.employee_table.setItem(row_idx, COL_ID, id_item)
            self.employee_table.setItem(row_idx, COL_SRC, QTableWidgetItem(row['src_name']))
            self.employee_table.setItem(row_idx, COL_TGT, QTableWidgetItem(row['tgt_name']))
            status_item = QTableWidgetItem(row['status'])
            color = STATUS_COLORS.get(row['status'])
            if color is not None:
                status_item.setBackground(color)
            self.employee_table.setItem(row_idx, COL_STATUS, status_item)

    # ------------------------------------------------------------------
    # Seçim
    # ------------------------------------------------------------------

    def _on_toggled(self, employee_id: str, checked: bool):
        if checked:
            self._selected.add(employee_id)
        else:
            self._selected.discard(employee_id)
        self._update_selected_label()

    def _update_selected_label(self):
        self.selected_label.setText(f"Seçili: {len(self._selected)}")

    def _set_visible_checked(self, checked: bool):
        for row in range(self.employee_table.rowCount()):
            cb = self.employee_table.cellWidget(row, COL_SELECT)
            if cb:
                cb.setChecked(checked)  # toggled → _selected güncellenir

    def _select_all(self):
        self._set_visible_checked(True)

    def _deselect_all(self):
        self._set_visible_checked(False)

    # ------------------------------------------------------------------
    # Transfer
    # ------------------------------------------------------------------

    def _selected_rows(self):
        return [r for r in self._all_rows if r['id'] in self._selected]

    def _build_items(self, rows):
        allow_other = self.overwrite_other_check.isChecked()
        return [
            TransferItem(
                employee_id=r['id'],
                update_name=self.update_name_check.isChecked(),
                update_biometric=self.update_biometric_check.isChecked(),
                allow_overwrite_other_person=allow_other and r['status'] == STATUS_OTHER,
            )
            for r in rows
        ]

    def _confirm(self, rows) -> bool:
        counts = {}
        for r in rows:
            counts[r['status']] = counts.get(r['status'], 0) + 1
        summary = "\n".join(f"  • {status}: {n}" for status, n in sorted(counts.items()))
        others = [r for r in rows if r['status'] == STATUS_OTHER]
        if others and self.overwrite_other_check.isChecked():
            names = "\n".join(f"  ID {r['id']}: {r['tgt_name']} → {r['src_name']}" for r in others[:15])
            warn = (f"\n\n⚠ {len(others)} kişinin ÜZERİNE YAZILACAK — hedefteki kişi o cihazdan giremez:\n{names}")
        elif others:
            warn = f"\n\n⏭ {len(others)} '⚠ Başka kişi' satırı atlanacak (üzerine yazma kapalı)."
        else:
            warn = ""
        what = []
        if self.update_name_check.isChecked():
            what.append("isim")
        if self.update_biometric_check.isChecked():
            what.append("yüz verisi")
        reply = QMessageBox.question(
            self, "Transfer Onayı",
            f"{len(rows)} personel işlenecek ({' + '.join(what) or 'yalnız yeni kayıtlar'}):\n\n"
            f"Kaynak: {self.source_combo.currentText()}\n"
            f"Hedef: {self.target_combo.currentText()}\n\n{summary}{warn}\n\n"
            "Transfer süresince bu iki cihazla başka işlem yapılamaz. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _start_transfer(self):
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()
        if source_id is None or target_id is None:
            QMessageBox.warning(self, "Hata", "Cihaz seçiniz.")
            return
        if source_id == target_id:
            QMessageBox.warning(self, "Hata", "Farklı cihazlar seçiniz.")
            return
        rows = self._selected_rows()
        if not rows:
            QMessageBox.warning(self, "Hata", "Personel seçiniz.")
            return
        if not self._confirm(rows):
            return

        self._open_progress_dialog(len(rows))
        self.transfer_btn.setEnabled(False)
        self._worker = DeviceTransferWorker(
            source_device_id=source_id,
            target_device_id=target_id,
            items=self._build_items(rows),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()
        self._progress_dialog.exec()

    def _open_progress_dialog(self, count: int):
        self._progress_dialog = QDialog(self)
        self._progress_dialog.setWindowTitle("Transfer Yapılıyor...")
        self._progress_dialog.setFixedSize(700, 480)
        p_layout = QVBoxLayout(self._progress_dialog)
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setFont(QFont("Consolas", 9))
        self._result_text.setText(f"Transfer başladı: {count} personel\n")
        p_layout.addWidget(self._result_text)
        self._progress_close_btn = QPushButton("Kapat")
        self._progress_close_btn.setEnabled(False)
        self._progress_close_btn.clicked.connect(self._progress_dialog.accept)
        p_layout.addWidget(self._progress_close_btn)

    def _on_progress(self, message: str):
        self._result_text.append(message)
        sb = self._result_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, successful: int, failed: int, skipped: int = 0):
        total = successful + failed + skipped
        self._result_text.append("\n" + "=" * 50)
        self._result_text.append(f"✅ Başarılı: {successful}/{total}")
        if skipped:
            self._result_text.append(f"⏭ Atlanan: {skipped} (hedefte başka kişi — üzerine yazılmadı)")
        if failed:
            self._result_text.append(f"❌ Başarısız: {failed}")
        self._progress_close_btn.setEnabled(True)
        self.transfer_btn.setEnabled(True)
        self._worker = None
        self._selected.clear()
        if self._ids:
            self._rebuild_rows()  # durumlar değişti (hedef DB güncellendi)

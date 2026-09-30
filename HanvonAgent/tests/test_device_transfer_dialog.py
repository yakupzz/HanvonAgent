"""
DeviceTransferDialog testleri — durum sınıflandırma, seçim koruma, eşitleme kipi,
eski liste sonuçları, onay ve worker'a giden kişi bazlı seçenekler.

Cihaz ağı yok: DeviceListFetchWorker ve DeviceTransferWorker sahteleriyle değiştirilir.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models import Device, Employee
from ui.dialogs import device_transfer_dialog as dlg_mod
from ui.dialogs.device_transfer_dialog import (
    COL_ID, COL_SELECT, COL_STATUS, STATUS_FACE, STATUS_NAME, STATUS_NEW,
    STATUS_OTHER, STATUS_SAME, DeviceTransferDialog,
)

FACES_A = [f"A{i}" for i in range(18)]
FACES_B = [f"B{i}" for i in range(18)]
IDS = ["3", "5", "7", "9", "68", "190"]


class FakeFetch(QObject):
    """DeviceListFetchWorker yerine: start() çağrılınca kaydedilir, testte elle tetiklenir."""
    fetched = Signal(list)
    error = Signal(str)
    finished = Signal()
    instances = []

    def __init__(self, ip, comm_key, port=None, parent=None):
        super().__init__()
        self.ip = ip
        FakeFetch.instances.append(self)

    def start(self):
        pass


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dlg.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _add(session, device, emp_id, name, faces):
    e = Employee(employee_device_id=emp_id, name=name, device_id=device.id)
    e.face_data = faces
    session.add(e)


@pytest.fixture
def devices(session):
    ref = Device(name="YONETIM", ip="172.16.1.219", enabled=True)
    tgt = Device(name="ANA GIRIS", ip="172.16.1.218", enabled=True)
    session.add_all([ref, tgt])
    session.commit()
    # 3: isim farklı/yüz aynı · 5: aynı · 7: aynı isim/yüz farklı · 9: hedefte yok
    # 68: başka kişi · 190: hedefte isim boş/yüz aynı
    for emp_id, ref_name, tgt_name, ref_f, tgt_f in [
        (3, "YELDA EKINCI", "BENSU YANAR", FACES_A, FACES_A),
        (5, "AYŞE KAYA", "AYSE KAYA", FACES_A, FACES_A),
        (7, "ALI VELI", "ALI VELI", FACES_A, FACES_B),
        (68, "FATEMEH AHMADI", "AYTEKIN URKMEZ", FACES_A, FACES_B),
        (190, "HASAN ALI SAHAN", "", FACES_A, FACES_A),
    ]:
        _add(session, ref, emp_id, ref_name, ref_f)
        _add(session, tgt, emp_id, tgt_name, tgt_f)
    _add(session, ref, 9, "YENI KISI", FACES_A)
    session.commit()
    return ref, tgt


@pytest.fixture
def make_dialog(qtbot, session, devices, monkeypatch):
    """Sahte worker ve session dialog'un TÜM ömrü boyunca geçerli (monkeypatch) —
    kaynak değişince açılan yeni okuma da sahte olmalı, gerçek cihaza gidilmemeli."""
    FakeFetch.instances = []
    monkeypatch.setattr(dlg_mod, "get_session", lambda: session)
    monkeypatch.setattr(dlg_mod, "DeviceListFetchWorker", FakeFetch)

    def factory(**kwargs):
        d = DeviceTransferDialog(**kwargs)
        qtbot.addWidget(d)
        return d
    return factory


def _deliver(dialog, ids=IDS):
    """Son liste okumasının sonucunu teslim et."""
    FakeFetch.instances[-1].fetched.emit(list(ids))


def _status_of(dialog, emp_id):
    for r in dialog._all_rows:
        if r['id'] == emp_id:
            return r['status']
    raise AssertionError(emp_id)


def _visible_ids(dialog):
    return [dialog.employee_table.item(r, COL_ID).text() for r in range(dialog.employee_table.rowCount())]


class TestClassification:
    def test_statuses(self, make_dialog, devices):
        ref, tgt = devices
        d = make_dialog(target_device_id=tgt.id)
        _deliver(d)
        assert _status_of(d, "3") == STATUS_NAME
        assert _status_of(d, "5") == STATUS_SAME     # Türkçe harf farkı sayılmaz
        assert _status_of(d, "7") == STATUS_FACE
        assert _status_of(d, "9") == STATUS_NEW
        assert _status_of(d, "68") == STATUS_OTHER
        assert _status_of(d, "190") == STATUS_NAME   # hedefte isim boş, yüz aynı

    def test_source_is_the_other_device(self, make_dialog, devices):
        ref, tgt = devices
        d = make_dialog(target_device_id=tgt.id)
        assert d.source_combo.currentData() == ref.id
        assert d.target_combo.currentData() == tgt.id


class TestSelection:
    def test_nothing_selected_by_default(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        assert d._selected == set()
        assert d.selected_label.text() == "Seçili: 0"

    def test_selection_survives_filter_and_sort(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        row = _visible_ids(d).index("68")
        d.employee_table.cellWidget(row, COL_SELECT).setChecked(True)
        d.filter_input.setText("YELDA")
        d.filter_input.setText("")
        d._on_header_click(COL_ID)
        assert d._selected == {"68"}
        row = _visible_ids(d).index("68")
        assert d.employee_table.cellWidget(row, COL_SELECT).isChecked()
        other = _visible_ids(d).index("3")
        assert not d.employee_table.cellWidget(other, COL_SELECT).isChecked()

    def test_select_visible_only(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        d.status_filter.setCurrentIndex(d.status_filter.findText(STATUS_NAME))
        d._select_all()
        assert d._selected == {"3", "190"}


class TestEqualizeMode:
    def test_preselects_name_differences_only_names(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id, equalize=True)
        _deliver(d)
        assert d._selected == {"3", "190"}
        assert d.update_name_check.isChecked()
        assert not d.update_biometric_check.isChecked()
        assert not d.overwrite_other_check.isChecked()
        assert set(_visible_ids(d)) == {"3", "7", "9", "68", "190"}  # "Farklı olanlar"


class TestStaleFetch:
    def test_source_change_does_not_terminate_and_ignores_old_result(self, make_dialog, devices, monkeypatch):
        monkeypatch.setattr(QThread, "terminate", MagicMock(side_effect=AssertionError("terminate yok")))
        ref, tgt = devices
        d = make_dialog(target_device_id=tgt.id)
        old = FakeFetch.instances[-1]
        d.source_combo.setCurrentIndex(d.source_combo.findData(tgt.id))  # kaynak değişti
        old.fetched.emit(IDS)  # eski okuma geç geldi → yok sayılmalı
        assert d._all_rows == []
        _deliver(d, ["1"])
        assert [r['id'] for r in d._all_rows] == ["1"]


class TestStartTransfer:
    def _start(self, d, answer=QMessageBox.Yes):
        created = {}

        def fake_worker(**kwargs):
            w = MagicMock()
            created.update(kwargs)
            return w
        with patch.object(dlg_mod, "DeviceTransferWorker", side_effect=fake_worker), \
                patch.object(dlg_mod.QMessageBox, "question", return_value=answer) as ask, \
                patch.object(QDialog, "exec", lambda self: None):
            d._start_transfer()
        return created, ask

    def test_other_person_not_overwritten_by_default(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        d._selected = {"3", "68"}
        created, ask = self._start(d)
        items = {i.employee_id: i for i in created["items"]}
        assert items["68"].allow_overwrite_other_person is False
        assert "atlanacak" in ask.call_args.args[2]

    def test_overwrite_checkbox_applies_only_to_other_person_rows(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id, equalize=True)
        _deliver(d)
        d._selected = {"3", "68"}
        d.overwrite_other_check.setChecked(True)
        created, ask = self._start(d)
        items = {i.employee_id: i for i in created["items"]}
        assert items["68"].allow_overwrite_other_person is True
        assert items["3"].allow_overwrite_other_person is False
        assert all(i.update_name and not i.update_biometric for i in items.values())
        text = ask.call_args.args[2]
        assert "ÜZERİNE YAZILACAK" in text and "AYTEKIN URKMEZ" in text

    def test_cancel_starts_nothing(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        d._selected = {"3"}
        created, _ = self._start(d, answer=QMessageBox.No)
        assert created == {}

    def test_finished_reports_skipped(self, make_dialog, devices):
        d = make_dialog(target_device_id=devices[1].id)
        _deliver(d)
        d._selected = {"3"}
        self._start(d)
        d._on_finished(1, 0, 1)
        assert "Atlanan: 1" in d._result_text.toPlainText()
        assert d._selected == set()

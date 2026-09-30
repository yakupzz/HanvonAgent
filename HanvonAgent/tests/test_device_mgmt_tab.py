"""
DeviceMgmtTab widget testleri — pytest-qt.

Tablo render, SYNC sütunu renkleri, inline edit -> mark_pending,
📤 buton görünürlüğü ve cihaza gönderme akışı test edilir.

Cihaz combosu boş başlatılır (DB'de cihaz yok); testler current_employees
listesini doğrudan enjekte eder.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from models.base import Base
from models import Device, Employee
from ui.tabs.device_mgmt_tab import DeviceMgmtTab, SYNC_OK_COLOR, SYNC_PENDING_COLOR


# Sütun index'leri (8 sütunlu tabloda)
SYNC_COL = 5
DEVICES_COL = 6
ACTION_COL = 7
NAME_COL = 2


@pytest.fixture
def session_factory(tmp_path):
    db_file = tmp_path / "tab_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def session(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def device(session):
    d = Device(name="Cihaz", ip="172.16.1.218", enabled=True)
    session.add(d)
    session.commit()
    return d


@pytest.fixture
def employees(session, device):
    """İki personel: biri 'ok', biri 'yeni' (pending)."""
    ok_emp = Employee(
        employee_device_id=100, name="Ahmet", card_num="0X100",
        check_type="face", sync_status="ok", device_id=device.id,
    )
    pending_emp = Employee(
        employee_device_id=200, name="Eski", pending_name="Yeni İsim",
        card_num="0X200", check_type="face", sync_status="yeni",
        device_id=device.id,
    )
    session.add_all([ok_emp, pending_emp])
    session.commit()
    return [ok_emp, pending_emp]


@pytest.fixture
def tab(qtbot, session, device):
    """DeviceMgmtTab — kendi session'ı test session'ı ile değiştirilir."""
    widget = DeviceMgmtTab()
    qtbot.addWidget(widget)
    widget.session = session
    return widget


@pytest.fixture(autouse=True)
def _no_info_popups():
    """Başarı mesajı (QMessageBox.information) testleri modal pencereyle kilitlemesin.
    Mesajı doğrulayan testler kendi patch'leriyle bunu ezer."""
    with patch("ui.tabs.device_mgmt_tab.QMessageBox.information"):
        yield


def _load(tab, employees, device):
    """Tabloyu verilen personellerle doldur."""
    tab.current_device_id = device.id
    tab.current_employees = employees
    tab._filter_employees()


class TestTableStructure:
    def test_has_eight_columns(self, tab):
        assert tab.employee_table.columnCount() == 8

    def test_devices_header_present(self, tab):
        header = tab.employee_table.horizontalHeaderItem(DEVICES_COL).text()
        assert header.startswith("Cihazlar")

    def test_sync_header_present(self, tab):
        headers = [
            tab.employee_table.horizontalHeaderItem(i).text().lower()
            for i in range(tab.employee_table.columnCount())
        ]
        assert "sync" in headers

    def test_stylesheet_set(self, tab):
        assert tab.employee_table.styleSheet().strip() != ""


class TestSyncColumnRendering:
    def test_row_count_matches(self, tab, employees, device):
        _load(tab, employees, device)
        assert tab.employee_table.rowCount() == 2

    def test_ok_employee_sync_text_and_color(self, tab, employees, device):
        _load(tab, employees, device)
        # employees[0] = ok -> "Senkron" etiketi
        item = tab.employee_table.item(0, SYNC_COL)
        assert item is not None
        assert item.text() == "Senkron"
        assert item.background().color() == SYNC_OK_COLOR

    def test_pending_employee_sync_text_and_color(self, tab, employees, device):
        _load(tab, employees, device)
        # employees[1] = yeni -> "Düzenlendi" etiketi
        item = tab.employee_table.item(1, SYNC_COL)
        assert item.text() == "Düzenlendi"
        assert item.background().color() == SYNC_PENDING_COLOR

    def test_pending_employee_shows_display_name(self, tab, employees, device):
        _load(tab, employees, device)
        # pending -> display_name = "Yeni İsim"
        assert tab.employee_table.item(1, NAME_COL).text() == "Yeni İsim"


class TestSendButtonVisibility:
    def test_send_button_only_for_pending_rows(self, tab, employees, device):
        _load(tab, employees, device)
        # ok satırında 📤 yok, yeni satırında var
        ok_widget = tab.employee_table.cellWidget(0, ACTION_COL)
        pending_widget = tab.employee_table.cellWidget(1, ACTION_COL)

        def has_send(widget):
            if widget is None:
                return False
            return any(
                "📤" in btn.text()
                for btn in widget.findChildren(type(widget.findChild(object)))
                if hasattr(btn, "text")
            )

        from PySide6.QtWidgets import QPushButton
        def send_buttons(widget):
            return [b for b in widget.findChildren(QPushButton) if "📤" in b.text()]

        assert len(send_buttons(ok_widget)) == 0
        assert len(send_buttons(pending_widget)) == 1


class TestInlineEdit:
    def test_name_cell_is_editable(self, tab, employees, device):
        _load(tab, employees, device)
        item = tab.employee_table.item(0, NAME_COL)
        assert item.flags() & Qt.ItemIsEditable

    def test_id_cell_not_editable(self, tab, employees, device):
        _load(tab, employees, device)
        item = tab.employee_table.item(0, 1)
        assert not (item.flags() & Qt.ItemIsEditable)

    def test_editing_name_calls_mark_pending(self, tab, employees, device):
        _load(tab, employees, device)
        ok_emp = employees[0]

        with patch("ui.tabs.device_mgmt_tab.mark_pending") as mock_mark:
            # cellChanged'i tetikle: 0. satır, NAME_COL hücresini değiştir
            new_item = tab.employee_table.item(0, NAME_COL)
            new_item.setText("Ahmet Yeni")  # cellChanged sinyalini tetikler

        mock_mark.assert_called_once()
        # mark_pending(session, employee, new_name)
        args = mock_mark.call_args.args
        assert args[1] is ok_emp
        assert args[2] == "Ahmet Yeni"

    def test_programmatic_rebuild_does_not_call_mark_pending(self, tab, employees, device):
        """_filter_employees yeniden çizimi cellChanged'i tetiklememeli."""
        with patch("ui.tabs.device_mgmt_tab.mark_pending") as mock_mark:
            _load(tab, employees, device)
        mock_mark.assert_not_called()


class TestSendFlow:
    def test_send_creates_worker_and_starts(self, tab, employees, device):
        _load(tab, employees, device)
        pending_emp = employees[1]

        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker") as MockWorker:
            instance = MagicMock()
            MockWorker.return_value = instance
            tab._send_employee_to_device(pending_emp)

            MockWorker.assert_called_once()
            instance.start.assert_called_once()

    def test_on_push_finished_success_reloads(self, tab, employees, device):
        _load(tab, employees, device)
        pending_emp = employees[1]

        with patch.object(tab, "_load_employees") as mock_load:
            tab.on_push_finished(True, "", pending_emp)
        mock_load.assert_called()

    def test_on_push_finished_failure_shows_error(self, tab, employees, device):
        _load(tab, employees, device)
        pending_emp = employees[1]

        with patch("ui.tabs.device_mgmt_tab.QMessageBox.critical") as mock_crit:
            tab.on_push_finished(False, "cihaza ulaşılamadı", pending_emp)
        mock_crit.assert_called_once()

    def test_on_push_finished_success_expires_session(self, tab, employees, device):
        """Başarılı gönderimden sonra identity map flush edilmeli (stale cache fix)."""
        _load(tab, employees, device)
        pending_emp = employees[1]

        with patch.object(tab.session, "expire_all") as mock_expire, \
                patch.object(tab, "_load_employees"):
            tab.on_push_finished(True, "", pending_emp)
        mock_expire.assert_called_once()


class TestDeleteFlow:
    def test_delete_cancelled_keeps_employee(self, tab, employees, device):
        """Onay diyalogunda 'Hayır' seçilirse silme yapılmaz."""
        _load(tab, employees, device)
        emp = employees[0]
        from PySide6.QtWidgets import QMessageBox

        with patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                   return_value=QMessageBox.No) as mock_q, \
                patch.object(tab.session, "delete") as mock_delete:
            tab._delete_employee(emp)

        mock_q.assert_called_once()
        mock_delete.assert_not_called()

    def test_delete_confirmed_removes_employee(self, tab, employees, device):
        """Çift onayda 1. Evet (DB sil) + 2. Hayır (cihaza dokunma) — DB'den silinir."""
        _load(tab, employees, device)
        emp = employees[0]
        from PySide6.QtWidgets import QMessageBox

        with patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                   side_effect=[QMessageBox.Yes, QMessageBox.No]) as mock_q, \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.information"), \
                patch.object(tab, "_load_employees"):
            tab._delete_employee(emp)

        assert mock_q.call_count == 2  # çift onay soruldu
        remaining = tab.session.query(Employee).filter_by(id=emp.id).first()
        assert remaining is None


class TestFetchAllEmployeesFromDevice:
    """'Cihazdan Personelleri Getir' — display_name eski pending'i gizlememeli."""

    def _run_fetch(self, tab, device_id, get_employee_return):
        from PySide6.QtWidgets import QDialog

        tab.device_combo.addItem("test", device_id)
        tab.device_combo.setCurrentIndex(tab.device_combo.count() - 1)

        mock_client = MagicMock()
        mock_client.get_employee_id.return_value = ["100"]
        mock_client.get_employee.return_value = get_employee_return

        with patch("ui.tabs.device_mgmt_tab.HanvonClient", return_value=mock_client), \
                patch.object(QDialog, "exec", lambda self: None):
            tab._fetch_all_employees()

    def test_stale_pending_name_cleared_when_device_name_differs(self, tab, session, device):
        """Cihazda isim doğrudan değiştirilmişse (bizim pending'imizden bağımsız),
        taze çekilen isim gösterilmeli — eski pending_name display_name'i
        gizlemeye devam etmemeli."""
        emp = Employee(
            employee_device_id=100, name="Eski Isim", pending_name="Bekleyen Isim",
            card_num="0X100", check_type="face", sync_status="yeni",
            device_id=device.id,
        )
        session.add(emp)
        session.commit()

        self._run_fetch(tab, device.id, {
            "result": "success", "name": "Cihazdaki Guncel Isim", "card_num": "0X100",
        })

        session.refresh(emp)
        assert emp.name == "Cihazdaki Guncel Isim"
        assert emp.pending_name is None
        assert emp.sync_status == "ok"
        assert emp.display_name == "Cihazdaki Guncel Isim"

    def test_pending_name_kept_when_device_unchanged(self, tab, session, device):
        """Cihaz hala eski ismi döndürüyorsa (push henüz yapılmadıysa), bekleyen
        yeniden adlandırma korunmalı."""
        emp = Employee(
            employee_device_id=100, name="Eski Isim", pending_name="Bekleyen Isim",
            card_num="0X100", check_type="face", sync_status="yeni",
            device_id=device.id,
        )
        session.add(emp)
        session.commit()

        self._run_fetch(tab, device.id, {
            "result": "success", "name": "Eski Isim", "card_num": "0X100",
        })

        session.refresh(emp)
        assert emp.name == "Eski Isim"
        assert emp.pending_name == "Bekleyen Isim"
        assert emp.sync_status == "yeni"
        assert emp.display_name == "Bekleyen Isim"

    def test_name_change_updates_db_and_warns(self, tab, session, device):
        """Cihazdaki isim DB'dekinden farklıysa: DB güncellenmeli VE
        logger.warning ile [İSİM DEĞİŞTİ] uyarısı verilmeli."""
        emp = Employee(
            employee_device_id=100, name="Eski Isim",
            card_num="0X100", check_type="face", sync_status="ok",
            device_id=device.id,
        )
        session.add(emp)
        session.commit()

        with patch("ui.tabs.device_mgmt_tab.logger.warning") as mock_warn:
            self._run_fetch(tab, device.id, {
                "result": "success", "name": "Yeni Isim", "card_num": "0X100",
            })

        session.refresh(emp)
        assert emp.name == "Yeni Isim"

        warned_name_change = any(
            call.args and call.args[0] == "[İSİM DEĞİŞTİ] %s"
            for call in mock_warn.call_args_list
        )
        assert warned_name_change

    def test_no_name_change_no_warning_state(self, tab, session, device):
        """İsim aynıysa DB değişmemeli, isim değişikliği listesine girmemeli."""
        emp = Employee(
            employee_device_id=100, name="Ayni Isim",
            card_num="0X100", check_type="face", sync_status="ok",
            device_id=device.id,
        )
        session.add(emp)
        session.commit()

        self._run_fetch(tab, device.id, {
            "result": "success", "name": "Ayni Isim", "card_num": "0X100",
        })

        session.refresh(emp)
        assert emp.name == "Ayni Isim"
        assert emp.sync_status == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# "Cihazlar" sütunu — personel (employee_device_id) hangi cihazlarda kayıtlı
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def two_devices(session, device):
    """device = 'Cihaz' (218), ikinci = 'Yonetim' (219).
    100 → iki cihazda da, 200 → yalnız ilk cihazda."""
    second = Device(name="Yonetim", ip="172.16.1.219", enabled=True)
    session.add(second)
    session.commit()
    emps = [
        Employee(employee_device_id=100, name="Ahmet", device_id=device.id),
        Employee(employee_device_id=200, name="Mehmet", device_id=device.id),
        Employee(employee_device_id=100, name="Ahmet", device_id=second.id),
    ]
    session.add_all(emps)
    session.commit()
    return device, second, emps[:2]


def _row_of(tab, emp_device_id):
    from ui.tabs.device_mgmt_tab import COL_ID
    for r in range(tab.employee_table.rowCount()):
        if tab.employee_table.item(r, COL_ID).text() == str(emp_device_id):
            return r
    raise AssertionError(f"ID {emp_device_id} tabloda yok")


class TestDevicesColumn:
    def test_lists_all_devices_holding_employee(self, tab, two_devices):
        dev1, _, emps = two_devices
        _load(tab, emps, dev1)
        text = tab.employee_table.item(_row_of(tab, 100), DEVICES_COL).text()
        assert text == "Cihaz, Yonetim"

    def test_employee_on_single_device(self, tab, two_devices):
        dev1, _, emps = two_devices
        _load(tab, emps, dev1)
        item = tab.employee_table.item(_row_of(tab, 200), DEVICES_COL)
        assert item.text() == "Cihaz"
        assert "Yonetim" in item.toolTip()  # eksik olduğu cihaz tooltip'te

    def test_devices_cell_not_editable(self, tab, two_devices):
        dev1, _, emps = two_devices
        _load(tab, emps, dev1)
        item = tab.employee_table.item(0, DEVICES_COL)
        assert not (item.flags() & Qt.ItemIsEditable)

    def test_missing_filter_shows_only_incomplete(self, tab, two_devices):
        dev1, _, emps = two_devices
        tab.current_device_id = dev1.id
        tab.current_employees = emps
        idx = tab.filter_devices.findData("missing")
        tab.filter_devices.setCurrentIndex(idx)
        assert tab.employee_table.rowCount() == 1
        assert tab.employee_table.item(0, DEVICES_COL).text() == "Cihaz"

    def test_sort_by_devices_column(self, tab, two_devices):
        dev1, _, emps = two_devices
        _load(tab, emps, dev1)
        tab._on_header_click(DEVICES_COL)  # artan: az cihazlı önce
        assert tab.employee_table.item(0, DEVICES_COL).text() == "Cihaz"


# ─────────────────────────────────────────────────────────────────────────────
# Personelleri Getir → satır bazında ✅ güncellendi / ❌ başarısız ikonu
# ─────────────────────────────────────────────────────────────────────────────

def _status_icon(tab, row):
    from PySide6.QtWidgets import QLabel
    widget = tab.employee_table.cellWidget(row, ACTION_COL)
    label = widget.findChild(QLabel, "fetchStatusIcon")
    return label.text() if label else None


class TestFetchStatusIcons:
    def _run_fetch(self, tab, device_id, ids, get_employee):
        from PySide6.QtWidgets import QDialog
        tab.device_combo.addItem("test", device_id)
        tab.device_combo.setCurrentIndex(tab.device_combo.count() - 1)
        mock_client = MagicMock()
        mock_client.get_employee_id.return_value = ids
        mock_client.get_employee.side_effect = get_employee
        with patch("ui.tabs.device_mgmt_tab.HanvonClient", return_value=mock_client),                 patch.object(QDialog, "exec", lambda self: None):
            tab._fetch_all_employees()

    def test_no_icon_before_fetch(self, tab, employees, device):
        _load(tab, employees, device)
        assert _status_icon(tab, 0) is None

    def test_updated_and_failed_icons(self, tab, session, employees, device):
        def get_employee(emp_id):
            if emp_id == "100":
                return {"result": "success", "name": "Ahmet", "card_num": "0X100"}
            raise TimeoutError("cihaz yanıt vermedi")

        self._run_fetch(tab, device.id, ["100", "200"], get_employee)
        assert _status_icon(tab, _row_of(tab, 100)) == "✅"
        assert _status_icon(tab, _row_of(tab, 200)) == "❌"

    def test_non_success_result_counts_as_failed(self, tab, session, employees, device):
        def get_employee(emp_id):
            return {"result": "fail"}

        self._run_fetch(tab, device.id, ["100"], get_employee)
        assert _status_icon(tab, _row_of(tab, 100)) == "❌"

    def test_new_employee_gets_success_icon(self, tab, session, device):
        self._run_fetch(tab, device.id, ["300"],
                        lambda _id: {"result": "success", "name": "Yeni", "card_num": ""})
        assert _status_icon(tab, _row_of(tab, 300)) == "✅"

    def test_status_cleared_on_device_change(self, tab, session, employees, device):
        self._run_fetch(tab, device.id, ["100"],
                        lambda _id: {"result": "success", "name": "Ahmet", "card_num": ""})
        tab.device_combo.setCurrentIndex(0)  # "Cihaz Seçiniz"
        tab.device_combo.setCurrentIndex(tab.device_combo.count() - 1)
        assert _status_icon(tab, _row_of(tab, 100)) is None


# ─────────────────────────────────────────────────────────────────────────────
# Diğer cihazlara da gönder — aynı personel ID'si başka cihazlarda kayıtlıysa
# ─────────────────────────────────────────────────────────────────────────────

from PySide6.QtWidgets import QMessageBox


@pytest.fixture
def pending_with_sibling(session, device):
    """dev1'de ID 218 bekleyen isimle; dev2'de aynı ID eski isimle."""
    dev2 = Device(name="Yonetim", ip="172.16.1.219", enabled=True)
    session.add(dev2)
    session.commit()
    emp = Employee(employee_device_id=218, name="GORKEM SERBES KAYM",
                   pending_name="GORKEM SERBES", sync_status="yeni", device_id=device.id)
    sib = Employee(employee_device_id=218, name="GORKEM SERBES KAYM", device_id=dev2.id)
    session.add_all([emp, sib])
    session.commit()
    return emp, sib, dev2


def _workers_mock():
    """Her çağrıda ayrı worker mock'u döndüren DevicePushWorker yerine geçen."""
    created = []

    def factory(employee_id, device_id):
        w = MagicMock()
        w.args = (employee_id, device_id)
        created.append(w)
        return w
    return created, factory


def _finish(worker, success, msg=""):
    """Worker'ın finished sinyaline bağlanan callback'i elle tetikle."""
    callback = worker.finished.connect.call_args.args[0]
    callback(success, msg)


class TestSendToOtherDevices:
    def test_yes_sends_to_all_devices(self, tab, session, device, pending_with_sibling):
        emp, sib, dev2 = pending_with_sibling
        _load(tab, [emp], device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                      return_value=QMessageBox.Yes) as ask:
            tab._send_employee_to_device(emp)
        ask.assert_called_once()
        assert "Yonetim" in ask.call_args.args[2]
        assert sorted(w.args for w in created) == sorted([(emp.id, device.id), (sib.id, dev2.id)])
        assert all(w.start.called for w in created)
        session.refresh(sib)
        assert sib.pending_name == "GORKEM SERBES"

    def test_no_sends_only_current_device(self, tab, session, device, pending_with_sibling):
        emp, sib, _ = pending_with_sibling
        _load(tab, [emp], device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question", return_value=QMessageBox.No):
            tab._send_employee_to_device(emp)
        assert [w.args for w in created] == [(emp.id, device.id)]
        session.refresh(sib)
        assert sib.pending_name is None

    def test_cancel_sends_nothing(self, tab, session, device, pending_with_sibling):
        emp, _, _ = pending_with_sibling
        _load(tab, [emp], device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                      return_value=QMessageBox.Cancel):
            tab._send_employee_to_device(emp)
        assert created == []

    def test_no_question_when_sibling_already_has_name(self, tab, session, device,
                                                       pending_with_sibling):
        emp, sib, _ = pending_with_sibling
        sib.name = "GORKEM SERBES"
        session.commit()
        _load(tab, [emp], device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question") as ask:
            tab._send_employee_to_device(emp)
        ask.assert_not_called()
        assert len(created) == 1

    def test_multi_device_summary_reports_each_device(self, tab, session, device,
                                                      pending_with_sibling):
        emp, _, _ = pending_with_sibling
        _load(tab, [emp], device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question", return_value=QMessageBox.Yes):
            tab._send_employee_to_device(emp)

        by_device = {w.args[1]: w for w in created}
        with patch("ui.tabs.device_mgmt_tab.QMessageBox.warning") as warn, \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.information") as info, \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.critical") as crit:
            _finish(by_device[device.id], True)
            warn.assert_not_called()  # grup bitmeden özet yok
            _finish([w for d, w in by_device.items() if d != device.id][0], False, "zaman aşımı")
        info.assert_not_called()
        crit.assert_not_called()  # tek tek hata kutusu yerine tek özet
        warn.assert_called_once()
        text = warn.call_args.args[2]
        assert "✅ Cihaz" in text and "❌ Yonetim" in text and "zaman aşımı" in text
        assert tab._active_workers == []

    def test_success_reloads_current_device_not_sibling_device(self, tab, session, device,
                                                               pending_with_sibling):
        emp, sib, _ = pending_with_sibling
        _load(tab, [emp], device)
        with patch.object(tab, "_load_employees") as mock_load:
            tab.on_push_finished(True, "", sib)
        mock_load.assert_called_once_with(device.id)


class TestBulkSendToOtherDevices:
    def _run_bulk(self, tab, answer):
        from PySide6.QtWidgets import QDialog
        clients = {}

        def client_factory(ip, port=None, comm_key=None):
            c = MagicMock()
            c.set_name_table.return_value = True
            clients[ip] = c
            return c

        with patch("ui.tabs.device_mgmt_tab.HanvonClient", side_effect=client_factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                      side_effect=[QMessageBox.Yes, answer]), \
                patch.object(QDialog, "exec", lambda self: None):
            tab._bulk_send_employees()
        return clients

    def _select(self, tab, device):
        tab.device_combo.addItem("test", device.id)
        tab.device_combo.setCurrentIndex(tab.device_combo.count() - 1)

    def test_yes_sends_to_both_devices(self, tab, session, device, pending_with_sibling):
        emp, sib, dev2 = pending_with_sibling
        self._select(tab, device)
        clients = self._run_bulk(tab, QMessageBox.Yes)
        assert set(clients) == {device.ip, dev2.ip}
        for c in clients.values():
            c.set_name_table.assert_called_once_with({"218": "GORKEM SERBES"})
        session.refresh(emp)
        session.refresh(sib)
        assert emp.name == sib.name == "GORKEM SERBES"
        assert emp.sync_status == sib.sync_status == "ok"

    def test_no_sends_only_current_device(self, tab, session, device, pending_with_sibling):
        emp, sib, _ = pending_with_sibling
        self._select(tab, device)
        clients = self._run_bulk(tab, QMessageBox.No)
        assert set(clients) == {device.ip}
        session.refresh(sib)
        assert sib.name == "GORKEM SERBES KAYM"
        assert sib.pending_name is None

    def test_other_device_unreachable_keeps_its_pending(self, tab, session, device,
                                                        pending_with_sibling):
        """İkinci cihaza bağlanılamazsa: ilk cihaz güncellenir, kardeş 'Düzenlendi' kalır."""
        from PySide6.QtWidgets import QDialog
        emp, sib, dev2 = pending_with_sibling
        self._select(tab, device)

        def client_factory(ip, port=None, comm_key=None):
            c = MagicMock()
            c.set_name_table.return_value = True
            if ip == dev2.ip:
                c.connect.side_effect = ConnectionError("cihaza ulaşılamadı")
            return c

        with patch("ui.tabs.device_mgmt_tab.HanvonClient", side_effect=client_factory), \
                patch("ui.tabs.device_mgmt_tab.QMessageBox.question",
                      side_effect=[QMessageBox.Yes, QMessageBox.Yes]), \
                patch.object(QDialog, "exec", lambda self: None):
            tab._bulk_send_employees()

        session.refresh(emp)
        session.refresh(sib)
        assert emp.name == "GORKEM SERBES" and emp.sync_status == "ok"
        assert sib.name == "GORKEM SERBES KAYM"
        assert sib.pending_name == "GORKEM SERBES" and sib.sync_status == "yeni"



# ─────────────────────────────────────────────────────────────────────────────
# Çift tıklama koruması — gönderim sürerken ⏳, ikinci 📤 yok sayılır
# ─────────────────────────────────────────────────────────────────────────────

def _action_texts(tab, row):
    from PySide6.QtWidgets import QPushButton
    widget = tab.employee_table.cellWidget(row, ACTION_COL)
    return {b.text(): b.isEnabled() for b in widget.findChildren(QPushButton)}


class TestDoubleClickGuard:
    def test_second_click_while_sending_is_ignored(self, tab, employees, device):
        _load(tab, employees, device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory):
            tab._send_employee_to_device(employees[1])
            tab._send_employee_to_device(employees[1])
        assert len(created) == 1

    def test_row_shows_disabled_hourglass_while_sending(self, tab, employees, device):
        _load(tab, employees, device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory):
            tab._send_employee_to_device(employees[1])
        texts = _action_texts(tab, _row_of(tab, 200))
        assert texts.get("⏳") is False  # görünür ama tıklanamaz
        assert "📤" not in texts

    def test_failure_restores_send_button_and_allows_retry(self, tab, employees, device):
        _load(tab, employees, device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory),                 patch("ui.tabs.device_mgmt_tab.QMessageBox.critical"):
            tab._send_employee_to_device(employees[1])
            _finish(created[0], False, "zaman aşımı")
            texts = _action_texts(tab, _row_of(tab, 200))
            assert "📤" in texts and "⏳" not in texts
            tab._send_employee_to_device(employees[1])
        assert len(created) == 2
        assert tab._active_workers == [created[1]]

    def test_bulk_send_skips_employee_already_sending(self, tab, session, employees, device):
        from PySide6.QtWidgets import QDialog
        tab.device_combo.addItem("test", device.id)
        tab.device_combo.setCurrentIndex(tab.device_combo.count() - 1)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory):
            tab._send_employee_to_device(tab.current_employees[1])
        with patch("ui.tabs.device_mgmt_tab.HanvonClient") as client_cls,                 patch("ui.tabs.device_mgmt_tab.QMessageBox.information") as info,                 patch.object(QDialog, "exec", lambda self: None):
            tab._bulk_send_employees()
        client_cls.assert_not_called()  # tek bekleyen zaten gönderiliyor
        info.assert_called_once()


class TestSendSuccessMessage:
    def test_single_success_names_device(self, tab, employees, device):
        _load(tab, employees, device)
        created, factory = _workers_mock()
        with patch("ui.tabs.device_mgmt_tab.DevicePushWorker", side_effect=factory):
            tab._send_employee_to_device(employees[1])
        with patch("ui.tabs.device_mgmt_tab.QMessageBox.information") as info:
            _finish(created[0], True)
        info.assert_called_once()
        text = info.call_args.args[2]
        assert "Cihaz (172.16.1.218)" in text and "200" in text

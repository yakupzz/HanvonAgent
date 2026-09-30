"""
SettingsTab — Otomatik Çekme zamanlama testleri.

Günlük çekme sıklığı 3 → 6 → 10'a çıkarıldı; saat girişleri 5 satır x 2 sütun
olarak (aynı satırda 2 saat) düzenleniyor.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from PySide6.QtWidgets import QVBoxLayout, QTimeEdit

from models.base import Base
from models import Device, Setting
from ui.tabs.settings_tab import SettingsTab, MAX_DAILY_PULLS


@pytest.fixture
def session_factory(tmp_path):
    db_file = tmp_path / "settings_test.db"
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
def tab(qtbot, session):
    """SettingsTab — kendi session'ı test session'ı ile değiştirilir."""
    widget = SettingsTab()
    qtbot.addWidget(widget)
    widget.session = session
    return widget


def _add_card(tab, device):
    """Cihaz zamanlama kartını boş bir layout'a ekler (device_schedules'i doldurur).

    Layout referansı tab üzerinde tutulur — yoksa Python GC edip altındaki
    Qt widget'larını (spinbox, time edit'ler) da C++ tarafında yok eder.
    """
    layout = QVBoxLayout()
    tab._add_device_card(layout, device)
    tab._test_schedule_layout = layout


class TestScheduleSlotCount:
    def test_max_daily_pulls_is_ten(self):
        assert MAX_DAILY_PULLS == 10

    def test_frequency_max_is_ten(self, tab, device):
        _add_card(tab, device)
        frequency = tab.device_schedules[f"{device.id}_frequency"]
        assert frequency.maximum() == 10

    def test_ten_time_widgets_registered(self, tab, device):
        _add_card(tab, device)
        for i in range(1, 11):
            widget = tab.device_schedules.get(f"{device.id}_{i}")
            assert isinstance(widget, QTimeEdit), f"Saat {i} widget'ı eksik"

    def test_no_eleventh_slot(self, tab, device):
        _add_card(tab, device)
        assert f"{device.id}_11" not in tab.device_schedules

    def test_first_six_defaults_unchanged(self, tab, device):
        """Mevcut 6 varsayılan saat (08..18) korunur; yeni 4 slot ekleniyor."""
        _add_card(tab, device)
        hours = [tab.device_schedules[f"{device.id}_{i}"].time().hour() for i in range(1, 11)]
        assert hours[:6] == [8, 10, 12, 14, 16, 18]
        assert len(set(hours)) == 10  # tekrar eden varsayılan saat yok


class TestScheduleVisibility:
    def test_all_ten_visible_when_frequency_ten(self, tab, device):
        _add_card(tab, device)
        frequency = tab.device_schedules[f"{device.id}_frequency"]
        frequency.setValue(10)
        for i in range(1, 11):
            time_input = tab.device_schedules[f"{device.id}_{i}"]
            assert not time_input.parentWidget().isHidden()

    def test_only_first_two_visible_when_frequency_two(self, tab, device):
        _add_card(tab, device)
        frequency = tab.device_schedules[f"{device.id}_frequency"]
        frequency.setValue(2)
        for i in range(1, 11):
            time_input = tab.device_schedules[f"{device.id}_{i}"]
            expected_hidden = i > 2
            assert time_input.parentWidget().isHidden() == expected_hidden


class TestSaveTenSlots:
    def test_save_all_schedules_persists_ten_times(self, tab, session, device):
        _add_card(tab, device)
        frequency = tab.device_schedules[f"{device.id}_frequency"]
        frequency.setValue(10)

        from PySide6.QtCore import QTime
        for i in range(1, 11):
            tab.device_schedules[f"{device.id}_{i}"].setTime(QTime(i, 0))

        with patch("ui.tabs.settings_tab.QMessageBox.information"):
            tab._save_all_schedules()

        setting = session.query(Setting).filter_by(key=f"schedule_{device.id}").first()
        assert setting is not None
        freq_part, times_part, status_part = setting.value.split("|")
        assert freq_part == "10"
        assert times_part == ",".join(f"{i:02d}:00" for i in range(1, 11))

    def test_load_restores_ten_times(self, tab, session, device):
        """Kaydedilmiş 10 saatlik zamanlama geri yüklenir."""
        times = ",".join(f"{i:02d}:30" for i in range(1, 11))
        session.add(Setting(key=f"schedule_{device.id}", value=f"10|{times}|1"))
        session.commit()
        _add_card(tab, device)
        tab._load_schedules()
        assert tab.device_schedules[f"{device.id}_frequency"].value() == 10
        assert tab.device_schedules[f"{device.id}_10"].time().toString("HH:mm") == "10:30"

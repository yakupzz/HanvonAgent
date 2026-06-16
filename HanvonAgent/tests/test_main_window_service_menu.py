"""
Tests for the tray "Servis" submenu wired into MainWindow.

These tests construct MainWindow with the service status timer/worker mocked so
no real NSSM/UAC interaction occurs.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.service_manager import ServiceState


@pytest.fixture
def window(qtbot):
    # Patch out the auto status-refresh worker so MainWindow construction does
    # not spawn a real ServiceWorker / sc query.
    with patch(
        "ui.main_window.MainWindow._refresh_service_state", lambda self: None
    ):
        from ui.main_window import MainWindow

        w = MainWindow()
        qtbot.addWidget(w)
        yield w

    # Release any DB connections the tab widgets opened so the shared engine's
    # QueuePool is not exhausted by repeated MainWindow construction across the
    # full suite.
    from models.base import engine

    engine.dispose()


def _action_map(window):
    return window._service_actions


# ---------------------------------------------------------------------------
# Menu structure
# ---------------------------------------------------------------------------

def test_service_submenu_exists(window):
    assert window._service_menu is not None
    assert window._service_menu.title() == "Servis"


def test_service_menu_has_expected_actions(window):
    actions = _action_map(window)
    for key in ("install", "remove", "start", "stop"):
        assert key in actions


def test_service_menu_has_status_label(window):
    assert window._service_status_action is not None
    # The status label is a non-triggerable, disabled action.
    assert window._service_status_action.isEnabled() is False


# ---------------------------------------------------------------------------
# Enable/disable based on state
# ---------------------------------------------------------------------------

def test_not_installed_enables_only_install(window):
    window._apply_service_state(ServiceState.NOT_INSTALLED)
    actions = _action_map(window)
    assert actions["install"].isEnabled() is True
    assert actions["remove"].isEnabled() is False
    assert actions["start"].isEnabled() is False
    assert actions["stop"].isEnabled() is False


def test_running_enables_stop_not_start(window):
    window._apply_service_state(ServiceState.RUNNING)
    actions = _action_map(window)
    assert actions["install"].isEnabled() is False
    assert actions["remove"].isEnabled() is True
    assert actions["start"].isEnabled() is False
    assert actions["stop"].isEnabled() is True


def test_stopped_enables_start_not_stop(window):
    window._apply_service_state(ServiceState.STOPPED)
    actions = _action_map(window)
    assert actions["start"].isEnabled() is True
    assert actions["stop"].isEnabled() is False
    assert actions["remove"].isEnabled() is True


# ---------------------------------------------------------------------------
# Triggering an action spawns a worker and disables menu
# ---------------------------------------------------------------------------

def test_action_spawns_worker_and_disables_menu(window):
    with patch("ui.main_window.ServiceWorker") as WorkerCls:
        worker = MagicMock()
        WorkerCls.return_value = worker
        window._on_service_action("install")

    WorkerCls.assert_called_once_with("install")
    worker.start.assert_called_once()
    # Menu disabled while the action runs.
    assert window._service_menu.isEnabled() is False
    # Worker tracked to prevent GC.
    assert worker in window._service_workers


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------

def test_success_shows_balloon(window):
    window._service_menu.setEnabled(False)
    with patch.object(window.tray_icon, "showMessage") as show_msg:
        window._on_service_worker_finished(True, "Başarılı: install", ServiceState.STOPPED)
    show_msg.assert_called_once()
    # Menu re-enabled after completion.
    assert window._service_menu.isEnabled() is True


def test_failure_shows_messagebox(window):
    with patch("ui.main_window.QMessageBox") as MsgBox:
        window._on_service_worker_finished(False, "Hata: çıkış kodu 1", ServiceState.UNKNOWN)
    MsgBox.warning.assert_called_once()


# ---------------------------------------------------------------------------
# closeEvent stops timers before draining workers (prevents re-spawn/crash)
# ---------------------------------------------------------------------------

def test_real_close_stops_timers(window):
    """A genuine close must stop both periodic timers so no worker is spawned
    while Qt is tearing the window down."""
    event = MagicMock()
    window._allow_close = True

    with patch.object(window.status_timer, "stop") as status_stop, patch.object(
        window.service_status_timer, "stop"
    ) as service_stop, patch("ui.main_window.QApplication.quit"):
        window.closeEvent(event)

    status_stop.assert_called_once()
    service_stop.assert_called_once()
    event.accept.assert_called_once()


def test_hide_to_tray_does_not_stop_timers(window):
    """Hiding to tray (X button) must keep timers running."""
    event = MagicMock()
    window._allow_close = False

    with patch.object(window.status_timer, "stop") as status_stop, patch.object(
        window.service_status_timer, "stop"
    ) as service_stop:
        window.closeEvent(event)

    status_stop.assert_not_called()
    service_stop.assert_not_called()
    event.ignore.assert_called_once()

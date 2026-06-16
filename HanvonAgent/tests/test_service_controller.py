"""
Tests for ui.service_controller.ServiceWorker (QThread).

Covers:
  * ServiceWorker is a QThread subclass.
  * It emits finished(ok, msg, state) on completion.
  * Mutating actions (install/remove/start/stop) go through elevation.
  * The "status" action skips elevation and queries state directly.
  * start() returns immediately (non-blocking).

elevation.run_elevated and ServiceManager.status are patched so no real
NSSM/UAC interaction occurs.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.service_manager import ServiceState
from ui.service_controller import ServiceWorker


@pytest.fixture
def fake_manager():
    mgr = MagicMock()
    mgr.status.return_value = ServiceState.RUNNING
    return mgr


def _run_worker_sync(worker, qtbot):
    """Start the worker and block (in the test) until it emits finished."""
    with qtbot.waitSignal(worker.finished, timeout=3000) as blocker:
        worker.start()
    return blocker.args


# ---------------------------------------------------------------------------
# Type / signal shape
# ---------------------------------------------------------------------------

def test_worker_is_qthread():
    from PySide6.QtCore import QThread

    worker = ServiceWorker("status")
    assert isinstance(worker, QThread)


def test_status_action_skips_elevation(qtbot, fake_manager):
    worker = ServiceWorker("status", manager=fake_manager)

    with patch("ui.service_controller.elevation.run_elevated") as run_elev:
        ok, msg, state = _run_worker_sync(worker, qtbot)

    run_elev.assert_not_called()
    fake_manager.status.assert_called_once()
    assert state == ServiceState.RUNNING
    assert ok is True


# ---------------------------------------------------------------------------
# Mutating actions go through elevation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["install", "remove", "start", "stop"])
def test_mutating_action_calls_elevation(qtbot, fake_manager, action):
    worker = ServiceWorker(action, manager=fake_manager)

    with patch(
        "ui.service_controller.elevation.run_elevated",
        return_value=(True, f"Başarılı: {action}"),
    ) as run_elev:
        ok, msg, state = _run_worker_sync(worker, qtbot)

    run_elev.assert_called_once_with(action)
    assert ok is True
    # Final state is queried after the mutation.
    assert state == ServiceState.RUNNING


def test_elevation_failure_propagates(qtbot, fake_manager):
    worker = ServiceWorker("install", manager=fake_manager)

    with patch(
        "ui.service_controller.elevation.run_elevated",
        return_value=(False, "İptal edildi"),
    ):
        ok, msg, state = _run_worker_sync(worker, qtbot)

    assert ok is False
    assert "İptal" in msg


def test_exception_emits_failure(qtbot, fake_manager):
    worker = ServiceWorker("install", manager=fake_manager)

    with patch(
        "ui.service_controller.elevation.run_elevated",
        side_effect=RuntimeError("boom"),
    ):
        ok, msg, state = _run_worker_sync(worker, qtbot)

    assert ok is False
    assert state == ServiceState.UNKNOWN


# ---------------------------------------------------------------------------
# Non-blocking
# ---------------------------------------------------------------------------

def test_start_is_non_blocking(qtbot, fake_manager):
    worker = ServiceWorker("status", manager=fake_manager)
    worker.start()
    # start() must return immediately; thread may still be running.
    qtbot.waitSignal(worker.finished, timeout=3000).wait()
    assert True

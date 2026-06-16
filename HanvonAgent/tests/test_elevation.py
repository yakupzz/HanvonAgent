"""
Tests for core.elevation — UAC elevation via ShellExecuteW.

The Win32 surface (ShellExecuteW + wait handle) is fully mocked; tests run on
any platform.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import elevation


# ---------------------------------------------------------------------------
# Non-Windows guard
# ---------------------------------------------------------------------------

def test_non_windows_returns_guarded(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: False)
    ok, msg = elevation.run_elevated("install")
    assert ok is False
    assert "Windows" in msg


# ---------------------------------------------------------------------------
# Exe path resolution (frozen vs dev)
# ---------------------------------------------------------------------------

def test_exe_path_frozen_uses_app_paths_exe(monkeypatch):
    """Frozen build relaunches the bundled .exe."""
    from core import app_paths

    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(app_paths, "exe_path", lambda: Path("C:/app/HanvonAgent.exe"))

    assert elevation._exe_path() == str(Path("C:/app/HanvonAgent.exe"))


def test_exe_path_dev_uses_python_interpreter(monkeypatch):
    """
    Dev mode must relaunch the python interpreter, not main.py — Windows cannot
    ShellExecute a .py script with the 'runas' verb. main.py is injected as the
    first argument by _build_args instead.
    """
    from core import app_paths

    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(sys, "executable", r"C:\Python\python.exe")

    result = elevation._exe_path()

    assert result == r"C:\Python\python.exe"
    assert not result.lower().endswith(".py")


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------

def test_argv_contains_svc_admin_and_action(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)

    captured = {}

    def fake_shell_execute(exe, action_args):
        captured["exe"] = exe
        captured["args"] = action_args
        return (True, 0, None)  # launched, exit code 0, no message

    monkeypatch.setattr(elevation, "_shell_execute_and_wait", fake_shell_execute)

    ok, _msg = elevation.run_elevated("install")

    assert ok is True
    assert "--svc-admin" in captured["args"]
    assert "install" in captured["args"]


# ---------------------------------------------------------------------------
# Success / failure / cancel
# ---------------------------------------------------------------------------

def test_success_exit_zero(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)
    monkeypatch.setattr(
        elevation, "_shell_execute_and_wait", lambda exe, args: (True, 0, None)
    )
    ok, msg = elevation.run_elevated("start")
    assert ok is True
    assert "start" in msg


def test_nonzero_exit_reports_error(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)
    monkeypatch.setattr(
        elevation, "_shell_execute_and_wait", lambda exe, args: (True, 3, None)
    )
    ok, msg = elevation.run_elevated("install")
    assert ok is False
    assert "3" in msg


def test_uac_cancel_returns_false(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)
    # launched=False simulates ShellExecute <= 32 or exception.
    monkeypatch.setattr(
        elevation, "_shell_execute_and_wait", lambda exe, args: (False, None, None)
    )
    ok, msg = elevation.run_elevated("install")
    assert ok is False
    assert "İptal" in msg or "iptal" in msg.lower()


def test_shell_execute_exception_treated_as_cancel(monkeypatch):
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)

    def boom(exe, args):
        raise OSError("ShellExecute failed")

    monkeypatch.setattr(elevation, "_shell_execute_and_wait", boom)
    ok, msg = elevation.run_elevated("install")
    assert ok is False


# ---------------------------------------------------------------------------
# Wait timeout (elevated subprocess hangs)
# ---------------------------------------------------------------------------

def test_wait_timeout_terminates_and_reports(monkeypatch):
    """If WaitForSingleObject returns WAIT_TIMEOUT the hung process is killed."""
    import ctypes

    # Fake Win32 surface: ShellExecuteExW succeeds and hands back a handle,
    # WaitForSingleObject reports WAIT_TIMEOUT (0x102) → the process hangs.
    shell32 = MagicMock()

    def fake_shell_execute_ex(info_ref):
        info = info_ref._obj
        info.hProcess = 12345  # non-null handle
        return 1  # success

    shell32.ShellExecuteExW.side_effect = fake_shell_execute_ex

    kernel32 = MagicMock()
    kernel32.WaitForSingleObject.return_value = 0x00000102  # WAIT_TIMEOUT

    fake_windll = MagicMock()
    fake_windll.shell32 = shell32
    fake_windll.kernel32 = kernel32

    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    launched, exit_code, message = elevation._shell_execute_and_wait(
        "app.exe", ["--svc-admin", "install"]
    )

    assert launched is False
    assert "Zaman aşımı" in message
    # The hung process must be force-terminated and its handle closed.
    kernel32.TerminateProcess.assert_called_once()
    kernel32.CloseHandle.assert_called_once()
    # GetExitCodeProcess must NOT be consulted on a timed-out (killed) process.
    kernel32.GetExitCodeProcess.assert_not_called()


def test_wait_timeout_surfaces_message(monkeypatch):
    """run_elevated reports a Turkish timeout message when the wait times out."""
    monkeypatch.setattr(elevation, "_is_windows", lambda: True)
    monkeypatch.setattr(
        elevation,
        "_shell_execute_and_wait",
        lambda exe, args: (False, None, "Zaman aşımı: işlem yanıt vermedi"),
    )
    ok, msg = elevation.run_elevated("install")
    assert ok is False
    assert "Zaman aşımı" in msg

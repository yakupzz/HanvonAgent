"""
Tests for services.service_manager — NSSM wrapper for the HanvonAgent
Windows service.

All subprocess execution is mocked so the suite never invokes nssm.exe or
sc.exe for real.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.service_manager import (
    ServiceConfig,
    ServiceError,
    ServiceManager,
    ServiceState,
    service_state_from_output,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path, frozen=False):
    nssm = tmp_path / "nssm.exe"
    nssm.write_text("x")
    return ServiceConfig(
        service_name="HanvonAgent",
        exe_path=tmp_path / "HanvonAgent.exe",
        runner_path=tmp_path / "service_runner.py",
        app_dir=tmp_path,
        nssm_path=nssm,
        frozen=frozen,
    )


def _completed(returncode=0, stdout="", stderr=""):
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


# ---------------------------------------------------------------------------
# install()
# ---------------------------------------------------------------------------

def test_install_dev_argv_uses_python_runner(tmp_path):
    cfg = _make_config(tmp_path, frozen=False)
    mgr = ServiceManager(cfg)

    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.install()

    # First call is the `nssm install` command.
    argv = run.call_args_list[0][0][0]
    assert argv[0] == str(cfg.nssm_path)
    assert argv[1] == "install"
    assert argv[2] == "HanvonAgent"
    # Dev mode → python exe + runner script, no --run-service flag.
    assert str(cfg.runner_path) in argv
    assert "--run-service" not in argv


def test_install_frozen_argv_uses_run_service_flag(tmp_path):
    cfg = _make_config(tmp_path, frozen=True)
    mgr = ServiceManager(cfg)

    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.install()

    argv = run.call_args_list[0][0][0]
    # Frozen mode → exe itself + --run-service flag.
    assert str(cfg.exe_path) in argv
    assert "--run-service" in argv


def test_install_raises_when_nssm_missing(tmp_path):
    cfg = ServiceConfig(
        service_name="HanvonAgent",
        exe_path=tmp_path / "HanvonAgent.exe",
        runner_path=tmp_path / "service_runner.py",
        app_dir=tmp_path,
        nssm_path=None,
        frozen=False,
    )
    mgr = ServiceManager(cfg)
    with pytest.raises(FileNotFoundError):
        mgr.install()


def test_install_nonzero_exit_raises_service_error(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(1, stderr="boom")
        with pytest.raises(ServiceError):
            mgr.install()


# ---------------------------------------------------------------------------
# remove()
# ---------------------------------------------------------------------------

def test_remove_with_confirm_appends_confirm(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.remove(confirm=True)

    argv = run.call_args[0][0]
    assert argv[:3] == [str(cfg.nssm_path), "remove", "HanvonAgent"]
    assert "confirm" in argv


def test_remove_without_confirm_omits_confirm(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.remove(confirm=False)

    argv = run.call_args[0][0]
    assert "confirm" not in argv


# ---------------------------------------------------------------------------
# start() / stop()
# ---------------------------------------------------------------------------

def test_start_builds_nssm_start(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.start()
    argv = run.call_args[0][0]
    assert argv == [str(cfg.nssm_path), "start", "HanvonAgent"]


def test_stop_builds_nssm_stop(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0)
        mgr.stop()
    argv = run.call_args[0][0]
    assert argv == [str(cfg.nssm_path), "stop", "HanvonAgent"]


def test_start_nonzero_raises(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(2, stderr="nope")
        with pytest.raises(ServiceError):
            mgr.start()


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status_running(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    out = "SERVICE_NAME: HanvonAgent\n   STATE : 4  RUNNING"
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0, stdout=out)
        assert mgr.status() == ServiceState.RUNNING
    # status uses sc query, not nssm
    argv = run.call_args[0][0]
    assert argv[0] == "sc"
    assert "query" in argv


def test_status_not_installed_on_1060(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(
            1060, stdout="", stderr="The specified service does not exist"
        )
        assert mgr.status() == ServiceState.NOT_INSTALLED


# ---------------------------------------------------------------------------
# Encoding — subprocess output must be decoded as UTF-8 with errors replaced
# so undefined cp1254 (Turkish locale) bytes (e.g. 0x81) never raise
# UnicodeDecodeError.
# ---------------------------------------------------------------------------

def test_run_command_decodes_utf8_with_replace(tmp_path):
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    with patch("services.service_manager.subprocess.run") as run:
        run.return_value = _completed(0, stdout="ok")
        mgr.status()
    kwargs = run.call_args.kwargs
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"


def test_run_command_survives_undecodable_locale_bytes(tmp_path):
    """A real subprocess emitting byte 0x81 must not raise UnicodeDecodeError."""
    cfg = _make_config(tmp_path)
    mgr = ServiceManager(cfg)
    # `cmd /c` echoes raw bytes; we feed a byte (0x81) that is undefined in
    # cp1254. With encoding=utf-8 + errors=replace this decodes to U+FFFD
    # instead of crashing. Using a python one-liner keeps it cross-shell.
    argv = [
        sys.executable,
        "-c",
        r"import sys; sys.stdout.buffer.write(b'\x81RUNNING')",
    ]
    exit_code, stdout, _stderr = mgr._run_command(argv)
    assert exit_code == 0
    assert "RUNNING" in stdout  # decoded without raising


# ---------------------------------------------------------------------------
# service_state_from_output() — pure parser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exit_code,output,expected",
    [
        (0, "STATE : 4  RUNNING", ServiceState.RUNNING),
        (0, "STATE : 1  STOPPED", ServiceState.STOPPED),
        (0, "STATE : 2  START_PENDING", ServiceState.START_PENDING),
        (0, "STATE : 3  STOP_PENDING", ServiceState.STOP_PENDING),
        (1060, "", ServiceState.NOT_INSTALLED),
        (0, "garbage with no state", ServiceState.UNKNOWN),
    ],
)
def test_service_state_from_output(exit_code, output, expected):
    assert service_state_from_output(exit_code, output) == expected

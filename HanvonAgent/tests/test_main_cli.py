"""
Tests for main.py CLI dispatch.

main() must branch on argv BEFORE creating a QApplication:
  * ``--run-service``      → run the headless service runner, no Qt.
  * ``--svc-admin <act>``  → run an elevated service admin subcommand, no Qt.
  * (no flag)              → launch the GUI.
"""

from unittest.mock import MagicMock, patch

import pytest

import main as main_module


# ---------------------------------------------------------------------------
# --run-service branch
# ---------------------------------------------------------------------------

def test_run_service_skips_qapplication(monkeypatch):
    monkeypatch.setattr(main_module.sys, "argv", ["main.py", "--run-service"])

    with patch("main.QApplication") as QApp, patch(
        "main.run_service_entry"
    ) as run_service, patch("main.sys.exit") as sys_exit:
        run_service.return_value = 0
        main_module.main()

    run_service.assert_called_once()
    QApp.assert_not_called()
    sys_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# --svc-admin branch
# ---------------------------------------------------------------------------

def test_svc_admin_install_calls_manager(monkeypatch):
    monkeypatch.setattr(
        main_module.sys, "argv", ["main.py", "--svc-admin", "install"]
    )

    with patch("main.QApplication") as QApp, patch(
        "main.run_svc_admin"
    ) as run_admin, patch("main.sys.exit") as sys_exit:
        run_admin.return_value = 0
        main_module.main()

    run_admin.assert_called_once_with("install")
    QApp.assert_not_called()
    sys_exit.assert_called_once_with(0)


def test_svc_admin_nonzero_exit_propagates(monkeypatch):
    monkeypatch.setattr(
        main_module.sys, "argv", ["main.py", "--svc-admin", "start"]
    )

    with patch("main.QApplication"), patch(
        "main.run_svc_admin", return_value=1
    ), patch("main.sys.exit") as sys_exit:
        main_module.main()

    sys_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# GUI branch (no flags)
# ---------------------------------------------------------------------------

def test_no_flag_launches_gui(monkeypatch):
    monkeypatch.setattr(main_module.sys, "argv", ["main.py"])

    fake_app = MagicMock()
    fake_app.exec.return_value = 0

    with patch("main.QApplication", return_value=fake_app) as QApp, patch(
        "main.MainWindow"
    ) as Window, patch("main.init_db"), patch("main.sys.exit"):
        main_module.main()

    QApp.assert_called_once()
    Window.assert_called_once()


# ---------------------------------------------------------------------------
# run_svc_admin helper
# ---------------------------------------------------------------------------

def test_run_svc_admin_install_returns_zero_on_success():
    fake_mgr = MagicMock()
    with patch("main.ServiceManager", return_value=fake_mgr), patch(
        "main.build_default_config"
    ):
        code = main_module.run_svc_admin("install")

    fake_mgr.install.assert_called_once()
    assert code == 0


def test_run_svc_admin_returns_one_on_error():
    fake_mgr = MagicMock()
    fake_mgr.start.side_effect = RuntimeError("boom")
    with patch("main.ServiceManager", return_value=fake_mgr), patch(
        "main.build_default_config"
    ):
        code = main_module.run_svc_admin("start")

    assert code == 1


def test_run_svc_admin_unknown_action_returns_two():
    with patch("main.ServiceManager"), patch("main.build_default_config"):
        code = main_module.run_svc_admin("frobnicate")
    assert code == 2

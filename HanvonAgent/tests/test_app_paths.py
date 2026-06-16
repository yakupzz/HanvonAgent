"""
Tests for core.app_paths — frozen/dev aware path resolution.

PyInstaller frozen mode is simulated via monkeypatching sys.frozen,
sys.executable and sys._MEIPASS.
"""

import os
import sys
from pathlib import Path

import pytest

from core import app_paths


# ---------------------------------------------------------------------------
# is_frozen
# ---------------------------------------------------------------------------

def test_is_frozen_false_by_default(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert app_paths.is_frozen() is False


def test_is_frozen_true_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert app_paths.is_frozen() is True


# ---------------------------------------------------------------------------
# exe_path
# ---------------------------------------------------------------------------

def test_exe_path_frozen_uses_sys_executable(monkeypatch):
    fake_exe = r"C:\Program Files\HanvonAgent\HanvonAgent.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_exe)

    assert app_paths.exe_path() == Path(fake_exe)


def test_exe_path_dev_is_under_project(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    result = app_paths.exe_path()
    # Dev exe path is derived from the package (project root area), absolute.
    assert result.is_absolute()


# ---------------------------------------------------------------------------
# app_dir
# ---------------------------------------------------------------------------

def test_app_dir_frozen_is_exe_dir(monkeypatch):
    fake_exe = r"C:\Program Files\HanvonAgent\HanvonAgent.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_exe)

    assert app_paths.app_dir() == Path(fake_exe).parent


def test_app_dir_dev_is_project_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    result = app_paths.app_dir()
    # Project root contains main.py
    assert (result / "main.py").exists()


# ---------------------------------------------------------------------------
# bundle_dir
# ---------------------------------------------------------------------------

def test_bundle_dir_frozen_uses_meipass(monkeypatch):
    fake_meipass = r"C:\Temp\_MEI123456"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", fake_meipass, raising=False)

    assert app_paths.bundle_dir() == Path(fake_meipass)


def test_bundle_dir_dev_is_project_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    result = app_paths.bundle_dir()
    assert (result / "main.py").exists()


# ---------------------------------------------------------------------------
# data_dir
# ---------------------------------------------------------------------------

def test_data_dir_frozen_is_next_to_exe(monkeypatch, tmp_path):
    # Frozen: data lives in <exe dir>/data
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    result = app_paths.data_dir()

    assert result == tmp_path / "data"
    assert result.is_absolute()


def test_data_dir_dev_is_under_project_root(monkeypatch):
    # Dev: data lives in <project root>/data
    monkeypatch.delattr(sys, "frozen", raising=False)

    result = app_paths.data_dir()

    assert result == app_paths.app_dir() / "data"
    assert (result.parent / "main.py").exists()
    assert result.is_absolute()


def test_data_dir_created_on_access(monkeypatch, tmp_path):
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    result = app_paths.data_dir()

    assert result.exists()
    assert result.is_dir()


# ---------------------------------------------------------------------------
# db_path
# ---------------------------------------------------------------------------

def test_db_path_default(monkeypatch, tmp_path):
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delenv("HANVON_DB_PATH", raising=False)

    result = app_paths.db_path()

    assert result == tmp_path / "data" / "hanvon_agent.db"
    assert result.is_absolute()


def test_db_path_env_override(monkeypatch, tmp_path):
    override = tmp_path / "custom.db"
    monkeypatch.setenv("HANVON_DB_PATH", str(override))

    result = app_paths.db_path()

    assert result == override


# ---------------------------------------------------------------------------
# logs_dir
# ---------------------------------------------------------------------------

def test_logs_dir_under_data_dir(monkeypatch, tmp_path):
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    result = app_paths.logs_dir()

    assert result == tmp_path / "data" / "logs"
    assert result.is_absolute()


def test_logs_dir_created_on_access(monkeypatch, tmp_path):
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    result = app_paths.logs_dir()

    assert result.exists()
    assert result.is_dir()


# ---------------------------------------------------------------------------
# nssm_path
# ---------------------------------------------------------------------------

def test_nssm_path_prefers_app_dir(monkeypatch, tmp_path):
    # Frozen so app_dir == exe dir == tmp_path
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    nssm = tmp_path / "nssm.exe"
    nssm.write_text("x")

    result = app_paths.nssm_path()

    assert result == nssm


def test_nssm_path_falls_back_to_venv_scripts(monkeypatch, tmp_path):
    # Dev mode, no nssm in app_dir; provide one in venv/Scripts.
    monkeypatch.delattr(sys, "frozen", raising=False)

    # app_dir'i boş bir klasöre yönlendir — proje kökündeki gerçek
    # nssm.exe testten bağımsız olsun.
    empty_app_dir = tmp_path / "app"
    empty_app_dir.mkdir()
    monkeypatch.setattr(app_paths, "app_dir", lambda: empty_app_dir)

    # sys.prefix is the venv root; Scripts/ lives directly beneath it.
    venv_root = tmp_path / "venv"
    venv_scripts = venv_root / "Scripts"
    venv_scripts.mkdir(parents=True)
    nssm = venv_scripts / "nssm.exe"
    nssm.write_text("x")

    # Point sys.prefix at the fake venv root.
    monkeypatch.setattr(sys, "prefix", str(venv_root))
    # Ensure PATH lookup yields nothing.
    monkeypatch.setenv("PATH", "")

    result = app_paths.nssm_path()

    assert result == nssm


def test_nssm_path_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)

    # app_dir'i boş klasöre yönlendir (proje kökündeki nssm.exe'den bağımsız)
    empty_app_dir = tmp_path / "app"
    empty_app_dir.mkdir()
    monkeypatch.setattr(app_paths, "app_dir", lambda: empty_app_dir)

    monkeypatch.setattr(sys, "prefix", str(tmp_path / "empty_prefix"))
    monkeypatch.setenv("PATH", "")

    assert app_paths.nssm_path() is None


# ---------------------------------------------------------------------------
# frozen vs dev differences
# ---------------------------------------------------------------------------

def test_frozen_vs_dev_app_dir_differ(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    dev_app_dir = app_paths.app_dir()

    fake_exe = r"C:\Program Files\HanvonAgent\HanvonAgent.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_exe)
    frozen_app_dir = app_paths.app_dir()

    assert dev_app_dir != frozen_app_dir

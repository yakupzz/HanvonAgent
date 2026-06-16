"""
Tests that the database path resolves consistently and absolutely.

The GUI (main.py) and the Windows service (service_runner.py) must point at
the SAME absolute database file. Both go through models.base which delegates
to core.app_paths.db_path().

These tests deliberately avoid reloading models.base (which would rebind the
shared engine/SessionLocal and break widget tests). Instead they verify:
  * models.base.DATABASE_PATH is absolute and derived from app_paths.db_path()
  * core.app_paths.db_path() honors HANVON_DB_PATH and %PROGRAMDATA%
"""

import os
import sys
from pathlib import Path

import pytest

import models.base as base
from core import app_paths


def test_database_path_is_absolute():
    assert Path(base.DATABASE_PATH).is_absolute()


def test_database_path_matches_app_paths_under_current_env():
    """
    models.base.DATABASE_PATH was computed at import from app_paths.db_path().
    Under the same env it must still equal app_paths.db_path().
    """
    assert Path(base.DATABASE_PATH) == app_paths.db_path()


def test_db_path_default_next_to_app(monkeypatch, tmp_path):
    # Frozen: db lives in <exe dir>/data/hanvon_agent.db
    fake_exe = tmp_path / "HanvonAgent.exe"
    fake_exe.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delenv("HANVON_DB_PATH", raising=False)

    expected = tmp_path / "data" / "hanvon_agent.db"
    assert app_paths.db_path() == expected
    assert app_paths.db_path().is_absolute()


def test_db_path_env_override(monkeypatch, tmp_path):
    override = tmp_path / "override.db"
    monkeypatch.setenv("HANVON_DB_PATH", str(override))

    assert app_paths.db_path() == override


def test_gui_and_service_resolve_identical_path():
    """
    Both entry points import models.base, so they share one DATABASE_PATH,
    which is itself app_paths.db_path(). Single source of truth.
    """
    assert Path(base.DATABASE_PATH) == app_paths.db_path()


# ---------------------------------------------------------------------------
# Legacy DB migration
#
# Old builds stored the database under %PROGRAMDATA%\HanvonAgent or in the
# project root. New builds use app_dir()/data/hanvon_agent.db. On first run at
# the new location we must copy the most recent legacy DB so data is not lost.
# ---------------------------------------------------------------------------


def _isolate_paths(monkeypatch, tmp_path):
    """
    Point every path-producing helper at tmp_path subfolders so a test never
    touches a real DB. Returns (new_db, programdata_db, projectroot_db).
    """
    new_dir = tmp_path / "app" / "data"
    programdata_dir = tmp_path / "programdata" / "HanvonAgent"
    projectroot_dir = tmp_path / "projectroot"
    for d in (new_dir, programdata_dir, projectroot_dir):
        d.mkdir(parents=True, exist_ok=True)

    new_db = new_dir / app_paths.DB_FILENAME
    programdata_db = programdata_dir / app_paths.DB_FILENAME
    projectroot_db = projectroot_dir / app_paths.DB_FILENAME

    monkeypatch.delenv("HANVON_DB_PATH", raising=False)
    monkeypatch.setattr(app_paths, "db_path", lambda: new_db)
    monkeypatch.setattr(
        app_paths, "legacy_db_paths", lambda: [programdata_db, projectroot_db]
    )
    return new_db, programdata_db, projectroot_db


def test_legacy_db_paths_are_absolute_paths():
    """legacy_db_paths() returns Path objects, all absolute (no hardcoded str)."""
    # conftest stubs app_paths.legacy_db_paths for isolation; reach the real one.
    paths = app_paths._real_legacy_db_paths()
    assert isinstance(paths, list)
    assert paths, "expected at least one legacy candidate"
    for p in paths:
        assert isinstance(p, Path)
        assert p.is_absolute()


def test_legacy_db_paths_includes_programdata_and_project_root(monkeypatch):
    """The two historical locations must be among the candidates."""
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    paths = [str(p).lower() for p in app_paths._real_legacy_db_paths()]
    joined = " ".join(paths)
    assert "programdata" in joined
    assert app_paths.DB_FILENAME.lower() in joined


def test_migrate_copies_legacy_when_new_missing(monkeypatch, tmp_path):
    """Test 1: new DB absent, legacy present -> legacy is copied over."""
    new_db, programdata_db, _ = _isolate_paths(monkeypatch, tmp_path)
    programdata_db.write_bytes(b"LEGACY-DATA")
    assert not new_db.exists()

    result = app_paths.migrate_legacy_db()

    assert result == programdata_db
    assert new_db.exists()
    assert new_db.read_bytes() == b"LEGACY-DATA"


def test_migrate_is_idempotent_when_new_exists(monkeypatch, tmp_path):
    """Test 2: new DB already present -> no copy, existing data untouched."""
    new_db, programdata_db, _ = _isolate_paths(monkeypatch, tmp_path)
    new_db.write_bytes(b"CURRENT-DATA")
    programdata_db.write_bytes(b"LEGACY-DATA")

    result = app_paths.migrate_legacy_db()

    assert result is None
    assert new_db.read_bytes() == b"CURRENT-DATA"


def test_migrate_noop_when_no_db_anywhere(monkeypatch, tmp_path):
    """Test 3: no DB anywhere -> nothing copied, fresh DB created later."""
    new_db, _, _ = _isolate_paths(monkeypatch, tmp_path)
    assert not new_db.exists()

    result = app_paths.migrate_legacy_db()

    assert result is None
    assert not new_db.exists()


def test_migrate_prefers_first_existing_legacy(monkeypatch, tmp_path):
    """When several legacy DBs exist, the first candidate wins (PROGRAMDATA)."""
    new_db, programdata_db, projectroot_db = _isolate_paths(monkeypatch, tmp_path)
    programdata_db.write_bytes(b"FROM-PROGRAMDATA")
    projectroot_db.write_bytes(b"FROM-PROJECTROOT")

    result = app_paths.migrate_legacy_db()

    assert result == programdata_db
    assert new_db.read_bytes() == b"FROM-PROGRAMDATA"


def test_migrate_falls_back_to_second_legacy(monkeypatch, tmp_path):
    """First candidate missing -> next existing legacy DB is used."""
    new_db, programdata_db, projectroot_db = _isolate_paths(monkeypatch, tmp_path)
    # programdata_db intentionally absent
    projectroot_db.write_bytes(b"FROM-PROJECTROOT")

    result = app_paths.migrate_legacy_db()

    assert result == projectroot_db
    assert new_db.read_bytes() == b"FROM-PROJECTROOT"


def test_init_db_triggers_migration(monkeypatch, tmp_path):
    """
    init_db() must perform the legacy copy before opening the engine so the
    GUI/service inherit existing data on first run at the new location.
    """
    import importlib
    from sqlalchemy import text

    legacy = tmp_path / "legacy" / app_paths.DB_FILENAME
    legacy.parent.mkdir(parents=True, exist_ok=True)
    new_db = tmp_path / "data" / app_paths.DB_FILENAME

    # Build a real legacy DB with one employee row.
    from sqlalchemy import create_engine
    import models.base as base_module

    legacy_engine = create_engine(f"sqlite:///{legacy}")
    base_module.Base.metadata.create_all(legacy_engine)
    with legacy_engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO employees (employee_device_id, name, device_id) "
            "VALUES (42, 'Migrated Person', 1)"
        ))
        conn.commit()
    legacy_engine.dispose()

    monkeypatch.setenv("HANVON_DB_PATH", str(new_db))
    monkeypatch.setattr(app_paths, "legacy_db_paths", lambda: [legacy])

    importlib.reload(base_module)
    try:
        assert not new_db.exists()
        base_module.init_db()

        assert new_db.exists()
        with base_module.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT name FROM employees WHERE employee_device_id=42"
            )).fetchone()
        assert row is not None
        assert row[0] == "Migrated Person"
    finally:
        base_module.engine.dispose()
        monkeypatch.delenv("HANVON_DB_PATH", raising=False)
        importlib.reload(base_module)

"""
Frozen/dev aware path resolution for HanvonAgent.

Handles two runtime modes:
  * Dev mode    — running from source (python main.py)
  * Frozen mode — running as a PyInstaller-built .exe

Path policy:
  * Persistent data (DB, logs) lives in a "data" folder next to the running
    application — the exe directory when frozen, the project root in dev mode.
    This keeps the install fully self-contained / portable.
  * Bundled read-only resources (icons, etc.) live next to the code in dev
    mode and under sys._MEIPASS when frozen.
"""

import os
import shutil
import sys
from pathlib import Path

# Project root in dev mode = parent of this package (core/ -> project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Application folder name.
APP_NAME = "HanvonAgent"

#: Sub-folder (under app_dir) that holds persistent, writable data.
DATA_DIRNAME = "data"

#: Default database filename.
DB_FILENAME = "hanvon_agent.db"


def is_frozen() -> bool:
    """True when running as a PyInstaller-frozen executable."""
    return bool(getattr(sys, "frozen", False))


def exe_path() -> Path:
    """
    Absolute path to the running executable.

    Frozen: sys.executable (the bundled .exe).
    Dev:    a notional path to main.py inside the project root.
    """
    if is_frozen():
        return Path(sys.executable)
    return _PROJECT_ROOT / "main.py"


def app_dir() -> Path:
    """
    Directory of the installed application.

    Frozen: folder containing the .exe.
    Dev:    project root.
    """
    if is_frozen():
        return Path(sys.executable).parent
    return _PROJECT_ROOT


def bundle_dir() -> Path:
    """
    Directory of bundled read-only resources.

    Frozen: PyInstaller's extraction dir (sys._MEIPASS).
    Dev:    project root.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return _PROJECT_ROOT


def data_dir() -> Path:
    """
    Persistent, writable data directory next to the application.

    Frozen: <exe dir>/data.
    Dev:    <project root>/data.

    The directory is created if it does not yet exist.
    """
    path = app_dir() / DATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """
    Absolute path to the SQLite database file.

    Honors the HANVON_DB_PATH environment override (used by tests and for
    custom deployments); otherwise data_dir()/hanvon_agent.db.
    """
    override = os.environ.get("HANVON_DB_PATH")
    if override:
        return Path(override)
    return data_dir() / DB_FILENAME


def legacy_db_paths() -> list[Path]:
    """
    Historical database locations from older builds, in migration priority
    order (most authoritative first).

    1. %PROGRAMDATA%\\HanvonAgent\\hanvon_agent.db
         The previous per-machine shared location used by GUI + service.
    2. <project root>\\hanvon_agent.db
         Early dev builds wrote the DB straight into the project root.

    All paths are built with pathlib (no hardcoded separators) and are
    absolute. Used by migrate_legacy_db() on first run at the new location.
    """
    candidates: list[Path] = []

    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        candidates.append(Path(programdata) / APP_NAME / DB_FILENAME)

    candidates.append(_PROJECT_ROOT / DB_FILENAME)

    # Resolve to absolute, de-duplicate while preserving order.
    seen: set[str] = set()
    resolved: list[Path] = []
    for path in candidates:
        absolute = path if path.is_absolute() else path.resolve()
        key = str(absolute).lower()
        if key not in seen:
            seen.add(key)
            resolved.append(absolute)
    return resolved


def migrate_legacy_db() -> Path | None:
    """
    One-shot data migration into the new data_dir() location.

    Behaviour:
      * New DB already exists  -> skip (migration already done / fresh install
        managed elsewhere). Idempotent: never overwrites current data.
      * New DB missing, a legacy DB exists -> copy the first existing legacy
        DB (see legacy_db_paths()) with shutil.copy2 to preserve timestamps.
        Returns the source Path that was copied.
      * No DB anywhere -> no-op; caller creates a fresh empty DB.

    Returns the legacy source Path when a copy happened, otherwise None.
    """
    new_db = db_path()
    if new_db.exists():
        return None

    for legacy in legacy_db_paths():
        if legacy.exists() and legacy != new_db:
            new_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, new_db)
            return legacy

    return None


def logs_dir() -> Path:
    """
    Absolute path to the logs directory under data_dir().

    The directory is created if it does not yet exist.
    """
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def nssm_path() -> Path | None:
    """
    Locate the nssm.exe helper used to manage the Windows service.

    Lookup order:
      1. app_dir()/nssm.exe       (shipped next to the exe / project root)
      2. <sys.prefix>/Scripts/nssm.exe  (installed into the venv)
      3. PATH lookup via shutil.which

    Returns None when nssm cannot be found.
    """
    candidate = app_dir() / "nssm.exe"
    if candidate.is_file():
        return candidate

    venv_candidate = Path(sys.prefix) / "Scripts" / "nssm.exe"
    if venv_candidate.is_file():
        return venv_candidate

    found = shutil.which("nssm")
    if found:
        return Path(found)

    return None

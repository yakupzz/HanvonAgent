"""
Shared pytest fixtures / test environment isolation.

This module sets HANVON_DB_PATH to a throwaway temp file BEFORE any project
module is imported, so that:

  * models.base resolves DATABASE_PATH to the temp DB (never the real
    %PROGRAMDATA%\\HanvonAgent\\hanvon_agent.db).
  * Widgets that open get_session() at construction time hit an initialized
    schema instead of an empty production database.

The schema is created via init_db() once the engine is available.
"""

import os
import tempfile
from pathlib import Path

# --- Must run at import time, before project modules are imported -----------
_TMP_DIR = Path(tempfile.gettempdir()) / "hanvon_agent_tests"
_TMP_DIR.mkdir(parents=True, exist_ok=True)
_TEST_DB = _TMP_DIR / "hanvon_agent_test.db"

# Start each test run from a clean database file.
if _TEST_DB.exists():
    try:
        _TEST_DB.unlink()
    except OSError:
        pass

os.environ["HANVON_DB_PATH"] = str(_TEST_DB)

# Tests must NEVER migrate a real legacy database into the throwaway test DB.
# Neutralize the legacy-DB lookup before any init_db() runs so the schema is
# created empty. Individual migration tests monkeypatch legacy_db_paths back
# to their own tmp_path fixtures, so this global stub does not hide them.
from core import app_paths  # noqa: E402

# Preserve the genuine implementation so tests that exercise the real
# legacy-path logic can reach it explicitly via app_paths._real_legacy_db_paths.
app_paths._real_legacy_db_paths = app_paths.legacy_db_paths  # type: ignore[attr-defined]

app_paths.legacy_db_paths = lambda: []  # type: ignore[assignment]

# Now that the env var is set, importing project modules picks up the temp DB.
from models import init_db  # noqa: E402

# Create the schema on the temp DB so widgets constructing get_session()
# at import/instantiation time find the expected tables.
init_db()

# --- Ağ güvenlik ağı --------------------------------------------------------
# Testler gerçek cihazlara (172.16.1.218/.219 — kapı erişim kontrolü yapan
# ÜRETİM cihazları) ASLA bağlanamasın. Bir test HanvonClient/worker'ı sahtesiyle
# değiştirmeyi unutursa bağlantı burada reddedilir (2026-09-30: patch kapsamı
# dar kalan bir dialog testi gerçek DeviceListFetchWorker'ı başlatmıştı).
# Oturum boyunca kalıcıdır — testten taşan thread'ler de engellenir.
import ipaddress  # noqa: E402
import socket as _socket  # noqa: E402

_real_connect = _socket.socket.connect


def _guarded_connect(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    try:
        allowed = ipaddress.ip_address(host).is_loopback
    except ValueError:
        allowed = host == "localhost"
    if not allowed:
        raise ConnectionRefusedError(f"Testlerde ağ erişimi yasak: {address!r}")
    return _real_connect(self, address, *args, **kwargs)


_socket.socket.connect = _guarded_connect

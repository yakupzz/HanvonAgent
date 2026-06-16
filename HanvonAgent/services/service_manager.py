"""
NSSM wrapper — install / remove / start / stop / query the HanvonAgent
Windows service.

Design notes
------------
* The class is configured via :class:`ServiceConfig` so it stays testable and
  decoupled from runtime path resolution. A convenience constructor
  :func:`build_default_config` wires it to ``core.app_paths``.
* ``install`` / ``remove`` / ``start`` / ``stop`` shell out to ``nssm.exe``.
* ``status`` uses Windows' built-in ``sc query`` (always present) so a missing
  nssm.exe does not prevent state inspection. ``sc`` exits 1060 when the
  service is not installed.
* All subprocess execution funnels through ``_run_command`` so tests can patch
  a single seam (``subprocess.run``).
"""

from __future__ import annotations

import enum
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

#: Windows error code returned by ``sc`` when the service is not installed.
ERROR_SERVICE_DOES_NOT_EXIST = 1060


class ServiceState(enum.Enum):
    """High-level lifecycle state of the Windows service."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    START_PENDING = "START_PENDING"
    STOP_PENDING = "STOP_PENDING"
    UNKNOWN = "UNKNOWN"
    NOT_INSTALLED = "NOT_INSTALLED"


class ServiceError(RuntimeError):
    """Raised when an nssm/sc command exits non-zero."""

    def __init__(self, message: str, exit_code: int = -1, stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass
class ServiceConfig:
    """Everything ServiceManager needs to build its command lines."""

    service_name: str
    exe_path: Path
    runner_path: Path
    app_dir: Path
    nssm_path: Optional[Path]
    frozen: bool = False
    #: Python interpreter used in dev mode to run ``runner_path``.
    python_exe: Optional[Path] = None


def build_default_config(service_name: str = "HanvonAgent") -> ServiceConfig:
    """Construct a :class:`ServiceConfig` from ``core.app_paths``."""
    from core import app_paths

    return ServiceConfig(
        service_name=service_name,
        exe_path=app_paths.exe_path(),
        runner_path=app_paths.app_dir() / "service_runner.py",
        app_dir=app_paths.app_dir(),
        nssm_path=app_paths.nssm_path(),
        frozen=app_paths.is_frozen(),
        python_exe=Path(sys.executable),
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def service_state_from_output(exit_code: int, stdout: str) -> ServiceState:
    """
    Parse the textual output of ``sc query <name>`` into a :class:`ServiceState`.

    A 1060 exit code means the service is not installed. Otherwise the STATE
    line (``STATE : 4  RUNNING``) is matched against the known keywords.
    """
    if exit_code == ERROR_SERVICE_DOES_NOT_EXIST:
        return ServiceState.NOT_INSTALLED

    text = (stdout or "").upper()
    if "RUNNING" in text:
        return ServiceState.RUNNING
    if "START_PENDING" in text:
        return ServiceState.START_PENDING
    if "STOP_PENDING" in text:
        return ServiceState.STOP_PENDING
    if "STOPPED" in text:
        return ServiceState.STOPPED
    return ServiceState.UNKNOWN


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ServiceManager:
    """Thin, testable wrapper around nssm.exe / sc.exe."""

    def __init__(self, config: ServiceConfig):
        self.config = config

    # -- public API ---------------------------------------------------------

    def install(self, account: Optional[str] = None) -> None:
        """
        Install the service via ``nssm install``.

        Frozen build: the exe runs itself with ``--run-service``.
        Dev build:    python interpreter runs ``service_runner.py``.
        """
        nssm = self._require_nssm()
        cfg = self.config

        if cfg.frozen:
            program = str(cfg.exe_path)
            program_args = ["--run-service"]
        else:
            python = str(cfg.python_exe or sys.executable)
            program = python
            program_args = [str(cfg.runner_path)]

        argv = [str(nssm), "install", cfg.service_name, program, *program_args]
        self._run_or_raise(argv, "Servis kurulamadı")

        # Set the working directory so relative resources resolve correctly.
        self._run_or_raise(
            [str(nssm), "set", cfg.service_name, "AppDirectory", str(cfg.app_dir)],
            "AppDirectory ayarlanamadı",
        )

        if account:
            self._run_or_raise(
                [str(nssm), "set", cfg.service_name, "ObjectName", account],
                "Servis hesabı ayarlanamadı",
            )

    def remove(self, confirm: bool = True) -> None:
        """Remove the service via ``nssm remove <name> [confirm]``."""
        nssm = self._require_nssm()
        argv = [str(nssm), "remove", self.config.service_name]
        if confirm:
            argv.append("confirm")
        self._run_or_raise(argv, "Servis kaldırılamadı")

    def start(self) -> None:
        """Start the service via ``nssm start``."""
        nssm = self._require_nssm()
        argv = [str(nssm), "start", self.config.service_name]
        self._run_or_raise(argv, "Servis başlatılamadı")

    def stop(self) -> None:
        """Stop the service via ``nssm stop``."""
        nssm = self._require_nssm()
        argv = [str(nssm), "stop", self.config.service_name]
        self._run_or_raise(argv, "Servis durdurulamadı")

    def status(self) -> ServiceState:
        """Query current state via ``sc query`` (does not require nssm)."""
        argv = ["sc", "query", self.config.service_name]
        exit_code, stdout, _stderr = self._run_command(argv)
        return service_state_from_output(exit_code, stdout)

    # -- internals ----------------------------------------------------------

    def _require_nssm(self) -> Path:
        if not self.config.nssm_path:
            raise FileNotFoundError(
                "nssm.exe bulunamadı. Lütfen nssm.exe'yi uygulama dizinine koyun."
            )
        return self.config.nssm_path

    def _run_command(self, argv) -> Tuple[int, str, str]:
        """Execute ``argv``; return (exit_code, stdout, stderr).

        Decoding is forced to UTF-8 with ``errors="replace"`` so that bytes
        which are undefined in the active locale codec (e.g. 0x81 under cp1254,
        the Turkish console codepage) never raise ``UnicodeDecodeError``.
        Invalid bytes are substituted with U+FFFD instead of crashing.
        """
        # Windows'ta subprocess penceresi gizle
        kwargs = {
            "capture_output": True,
            "text": True,
            "shell": False,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            import subprocess as sp
            kwargs["creationflags"] = sp.CREATE_NO_WINDOW  # 0x08000000

        completed = subprocess.run(argv, **kwargs)
        return completed.returncode, completed.stdout or "", completed.stderr or ""

    def _run_or_raise(self, argv, message: str) -> Tuple[int, str, str]:
        exit_code, stdout, stderr = self._run_command(argv)
        if exit_code != 0:
            raise ServiceError(
                f"{message} (exit {exit_code}): {stderr.strip()}",
                exit_code=exit_code,
                stderr=stderr,
            )
        return exit_code, stdout, stderr

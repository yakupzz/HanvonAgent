"""
ServiceWorker — QThread that performs Windows-service operations off the UI
thread.

Actions
-------
* ``install`` / ``remove`` / ``start`` / ``stop`` → require admin rights, so
  they are delegated to :func:`core.elevation.run_elevated`, which re-launches
  an elevated ``--svc-admin <action>`` subprocess. After the elevated call the
  worker re-queries state (unprivileged ``sc query``) for an up-to-date result.
* ``status`` → a cheap, unprivileged state query; elevation is skipped.

The worker emits ``finished(ok: bool, msg: str, state: ServiceState)`` exactly
once. Keeping all work in ``run()`` keeps the GUI responsive.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal

from core import elevation
from services.service_manager import (
    ServiceManager,
    ServiceState,
    build_default_config,
)

logger = logging.getLogger("HanvonAgent.ServiceWorker")

#: Actions that mutate service state and therefore require elevation.
_MUTATING_ACTIONS = frozenset({"install", "remove", "start", "stop"})


class ServiceWorker(QThread):
    """Run a single service action and report the result via ``finished``."""

    # (success, message, final_state)
    finished = Signal(bool, str, object)

    def __init__(
        self,
        action: str,
        manager: Optional[ServiceManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.action = action
        self._manager = manager

    # -- helpers ------------------------------------------------------------

    def _manager_or_default(self) -> ServiceManager:
        if self._manager is not None:
            return self._manager
        return ServiceManager(build_default_config())

    def _query_state(self, manager: ServiceManager) -> ServiceState:
        try:
            return manager.status()
        except Exception as exc:  # noqa: BLE001
            logger.error("Servis durumu sorgulanamadı: %s", exc, exc_info=True)
            return ServiceState.UNKNOWN

    # -- thread body --------------------------------------------------------

    def run(self):  # noqa: D401
        manager = self._manager_or_default()

        try:
            if self.action in _MUTATING_ACTIONS:
                ok, msg = elevation.run_elevated(self.action)
                state = self._query_state(manager)
                self.finished.emit(bool(ok), msg, state)
                return

            # Non-mutating status query.
            state = self._query_state(manager)
            self.finished.emit(True, "Durum güncellendi", state)
        except Exception as exc:  # noqa: BLE001
            logger.error("ServiceWorker hatası: %s", exc, exc_info=True)
            self.finished.emit(False, str(exc), ServiceState.UNKNOWN)

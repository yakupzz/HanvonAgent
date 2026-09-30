"""
Tek uygulama örneği (GUI).

İkinci açılış yeni kopya başlatmaz; açık olan örneğe "pencereyi göster"
mesajı gönderip kapanır. İki örnek aynı cihaza paralel bağlanıp birbirini
zaman aşımına düşürüyordu (2026-09-30).

- QLockFile gerçek kilittir. Windows'ta QLocalServer aynı isimle birden fazla
  dinleyiciye izin verebildiği için tek başına yetmez.
- Kilit yalnız PID ile bayat sayılır (sahibi ölmüşse geri alınır). Qt 6
  canlı sürecin kilidini yaşından bağımsız zaten çalmıyor (2026-09-30'da
  denendi); setStaleLockTime(0) uygulama günlerce açık kalırken bunu
  Qt sürümünden bağımsız garantiye alır.
- QLocalServer yalnız öne getirme mesajını taşır.
"""

import getpass
import logging
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger("HanvonAgent.SingleInstance")

ACTIVATE_MESSAGE = b"show"


def default_server_name() -> str:
    """Kullanıcı başına ayrı isim — aynı makinede farklı kullanıcılar çakışmasın."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 — isim üretilemezse sabit ek
        user = "user"
    return f"HanvonAgent-GUI-{user}"


class SingleInstance(QObject):
    """GUI örnek kilidi + öne getirme kanalı."""

    activated = Signal()  # başka bir açılış "pencereyi göster" dedi

    def __init__(
        self,
        lock_path: Union[str, Path],
        server_name: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.server_name = server_name or default_server_name()
        self._lock = QLockFile(str(lock_path))
        self._lock.setStaleLockTime(0)  # yalnız PID tabanlı bayatlık
        self._server: Optional[QLocalServer] = None

    def acquire(self) -> bool:
        """Kilidi al ve öne getirme sunucusunu başlat.

        Returns:
            True → bu ilk örnek; False → başka bir örnek zaten açık.
        """
        if not self._lock.tryLock(100):
            return False

        server = QLocalServer(self)
        QLocalServer.removeServer(self.server_name)  # Unix'te bayat soket kalıntısı
        server.newConnection.connect(self._on_new_connection)
        if not server.listen(self.server_name):
            # Kilit bizde; yalnız "öne getir" çalışmaz — uygulama yine açılır
            logger.warning("[TEK ÖRNEK] Öne getirme kanalı açılamadı: %s", server.errorString())
        self._server = server
        return True

    def notify_primary(self, timeout_ms: int = 1000) -> bool:
        """Açık olan örneğe 'pencereyi göster' gönder. True → mesaj ulaştı."""
        sock = QLocalSocket()
        sock.connectToServer(self.server_name)
        if not sock.waitForConnected(timeout_ms):
            return False
        sock.write(ACTIVATE_MESSAGE)
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        self._lock.unlock()

    def _on_new_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.disconnected.connect(conn.deleteLater)
        self.activated.emit()

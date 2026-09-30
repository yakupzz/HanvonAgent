"""conftest ağ güvenlik ağı — testler gerçek cihaza bağlanamaz."""

import socket

import pytest

from core.hanvon_client import HanvonClient


def test_real_device_connection_is_refused():
    client = HanvonClient("172.16.1.218", busy_wait=0.1, connect_timeout=1)
    with pytest.raises(ConnectionRefusedError, match="ağ erişimi yasak"):
        client.connect()
    client.disconnect()


def test_loopback_is_allowed_to_try():
    s = socket.socket()
    s.settimeout(0.5)
    try:
        with pytest.raises(OSError) as exc:
            s.connect(("127.0.0.1", 1))  # kapalı port — yasak değil, yalnız reddedilir
        assert "ağ erişimi yasak" not in str(exc.value)
    finally:
        s.close()

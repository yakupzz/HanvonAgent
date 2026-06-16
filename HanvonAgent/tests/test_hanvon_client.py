"""
TCP Client testleri (mock socket ile).

Referans:
- D:\Projeler\F710\referans\lib\hanvon\client.rb
- D:\Projeler\F710\test-correct-params.js (parametreler)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from core.hanvon_client import HanvonClient


class TestHanvonClientBasic:
    """Temel bağlantı testleri."""

    @patch('socket.socket')
    def test_connect_success(self, mock_socket_class):
        """Başarılı bağlantı."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket

        client = HanvonClient("172.16.1.218", 9922, None)
        client.connect()

        mock_socket.connect.assert_called_once_with(("172.16.1.218", 9922))

    @patch('socket.socket')
    def test_connect_timeout(self, mock_socket_class):
        """Bağlantı timeout."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = TimeoutError("Connection timeout")

        client = HanvonClient("172.16.1.218", 9922, None)
        with pytest.raises(TimeoutError):
            client.connect()

    @patch('socket.socket')
    def test_disconnect(self, mock_socket_class):
        """Bağlantı kesme."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket
        client.disconnect()

        mock_socket.close.assert_called_once()


class TestHanvonClientCommands:
    """Komut gönderme testleri."""

    @patch('socket.socket')
    def test_send_command_no_encryption(self, mock_socket_class):
        """Komut gönderme (şifreleme yok)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Return(result="success")'

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        response = client.send_command("GetDeviceInfo()")

        # TCP'ye gönderilen veri
        call_args = mock_socket.sendall.call_args[0][0]
        assert b"GetDeviceInfo()" in call_args
        assert call_args.endswith(b"\r\n")

    @patch('socket.socket')
    def test_send_command_with_encryption(self, mock_socket_class):
        """Komut gönderme (şifreleme ile)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'\x76\x56\x41\x7c\x58\x30\x3e\x1b\x54\x7a\x5b\x5e\x52\x6e\x7e'

        client = HanvonClient("172.16.1.218", 9922, "12345678")
        client.socket = mock_socket

        response = client.send_command("GetDeviceInfo()")

        # Şifreleme uygulanmış olmalı
        call_args = mock_socket.sendall.call_args[0][0]
        # "GetDeviceInfo()" → şifreli bytes
        assert call_args != b"GetDeviceInfo()\r\n"

    @patch('socket.socket')
    def test_send_command_with_wait_response(self, mock_socket_class):
        """Wait() yanıtı sonra gerçek cevap."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket

        # İlk recv: Wait(), ikinci recv: Return()
        mock_socket.recv.side_effect = [
            b'Wait(wait_time="120")',
            b'Return(result="success")'
        ]

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        response = client.send_command("SetNameTable(...)")

        # Wait() atlanıp, Return() alınmalı
        assert "success" in response


class TestHanvonClientParsed:
    """Parse edilmiş komut testleri."""

    @patch('socket.socket')
    def test_get_device_info(self, mock_socket_class):
        """GetDeviceInfo() komutu."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = (
            b'Return(result="success" dev_id="6710511030000079" '
            b'time="2026-6-9 13:28:45" edition="3.006.089" '
            b'ip="172.16.1.218")'
        )

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        device_info = client.get_device_info()

        assert device_info['dev_id'] == "6710511030000079"
        assert device_info['time'] == "2026-6-9 13:28:45"
        assert device_info['ip'] == "172.16.1.218"

    @patch('socket.socket')
    def test_get_record_with_dates(self, mock_socket_class):
        """GetRecord(start_time, end_time)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = (
            b'Return(result="success" dev_id="0" '
            b'time="2026-06-09 08:30:00" id="8" name="YAKUP T." status="1")'
        )

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        records = client.get_record(
            start_time="2026-6-9 0:0:0",
            end_time="2026-6-9 23:59:59"
        )

        # Komut parametreleri kontrol et
        call_args = mock_socket.sendall.call_args[0][0]
        assert b"start_time=" in call_args
        assert b"end_time=" in call_args

        # Sonuç
        assert len(records) == 1
        assert records[0]['name'] == "YAKUP T."

    @patch('socket.socket')
    def test_get_employee_id(self, mock_socket_class):
        """GetEmployeeID()."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = (
            b'Return(result="success" total="3" id="237" id="177" id="5")'
        )

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        ids = client.get_employee_id()

        assert len(ids) == 3
        assert "237" in ids

    @patch('socket.socket')
    def test_get_employee(self, mock_socket_class):
        """GetEmployee(id)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = (
            b'Return(result="success" id="237" name="Huseyin S." '
            b'card_num="0X12345678" check_type="face")'
        )

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        employee = client.get_employee("237")

        assert employee['id'] == "237"
        assert employee['name'] == "Huseyin S."

    @patch('socket.socket')
    def test_set_device_info(self, mock_socket_class):
        """SetDeviceInfo(time, week)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Return(result="success")'

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        result = client.set_device_info(
            time="2026-6-9 14:30:00",
            week="2"
        )

        # Komut kontrol
        call_args = mock_socket.sendall.call_args[0][0]
        assert b"time=" in call_args
        assert b"week=" in call_args

        assert result is True

    @patch('socket.socket')
    def test_set_name_table(self, mock_socket_class):
        """SetNameTable(id1="name1" id2="name2")."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Return(result="success")'

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        name_updates = {
            "237": "Huseyin S.",
            "177": "Ahmet K.",
            "5": "Fatima B."
        }

        result = client.set_name_table(name_updates)

        # Komut kontrol
        call_args = mock_socket.sendall.call_args[0][0]
        assert b"237=" in call_args
        assert b"Huseyin S." in call_args

        assert result is True


class TestHanvonClientErrors:
    """Hata durumları."""

    @patch('socket.socket')
    def test_command_failed_response(self, mock_socket_class):
        """Başarısız komut yanıtı."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Return(result="failed" reason="invalid id")'

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        employee = client.get_employee("999")

        assert employee is None

    @patch('socket.socket')
    def test_socket_error_during_receive(self, mock_socket_class):
        """Socket hatası alma sırasında."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.side_effect = ConnectionError("Connection lost")

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        with pytest.raises(ConnectionError):
            client.send_command("GetDeviceInfo()")


class TestSanitize:
    """Protokol injection koruması testleri."""

    def test_sanitize_removes_quotes(self):
        assert HanvonClient._sanitize('Ahmet "Apo" K.') == 'Ahmet Apo K.'

    def test_sanitize_removes_parens_and_newlines(self):
        assert HanvonClient._sanitize('x(y)\r\nz') == 'xyz'

    def test_sanitize_plain_value_unchanged(self):
        assert HanvonClient._sanitize('Huseyin S.') == 'Huseyin S.'

    def test_sanitize_non_string_coerced(self):
        assert HanvonClient._sanitize(237) == '237'

    @patch('socket.socket')
    def test_set_employee_injection_blocked(self, mock_socket_class):
        """İsimdeki tırnak komuta sızamaz."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Return(result="success")'

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        client.set_employee("5", name='Evil" card_num="123')

        sent = mock_socket.sendall.call_args[0][0].decode('utf-8')
        # Tırnaklar temizlendiği için injection parçalanmış olmalı
        assert 'name="Evil card_num=123"' in sent


class TestWaitLoopLimit:
    """Wait() sonsuz döngü koruması."""

    @patch('time.sleep')  # testte gerçek bekleme olmasın
    @patch('socket.socket')
    def test_wait_loop_raises_after_max_retries(self, mock_socket_class, mock_sleep):
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b'Wait()'  # cihaz hep Wait() dönüyor

        client = HanvonClient("172.16.1.218", 9922, None)
        client.socket = mock_socket

        with pytest.raises(TimeoutError):
            client.send_command("GetRecord()")

        # recv: 1 ilk + MAX_WAIT_RETRIES tekrar
        assert mock_socket.recv.call_count <= HanvonClient.MAX_WAIT_RETRIES + 2

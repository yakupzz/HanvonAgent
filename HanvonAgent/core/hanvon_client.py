"""
Hanvon F710 TCP protokol client.

Referans: D:\Projeler\F710\referans\lib\hanvon\client.rb
"""

import socket
import time
import logging
from typing import Optional, List, Dict, Any
from core.hanvon_crypto import HanvonCrypto
from core.record_parser import RecordParser

logger = logging.getLogger("HanvonAgent.TCP")


class HanvonClient:
    """Hanvon F710 TCP client."""

    DEFAULT_PORT = 9922
    DEFAULT_TIMEOUT = 10
    BUFFER_SIZE = 1024
    MAX_WAIT_RETRIES = 30  # Wait() döngü sınırı (30 × 2sn = 60sn)

    def __init__(
        self,
        ip: str,
        port: int = DEFAULT_PORT,
        comm_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Args:
            ip: Cihaz IP adresi
            port: TCP port (varsayılan 9922)
            comm_key: CommKey şifresi (1-8 rakam) veya None
            timeout: Socket timeout saniye cinsinden
        """
        self.ip = ip
        self.port = port
        self.comm_key = comm_key
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.crypto = HanvonCrypto(comm_key) if comm_key else None
        self.parser = RecordParser()

    def connect(self) -> bool:
        """
        Cihaza TCP bağlantı kur.

        Returns:
            Başarı durumu

        Raises:
            socket.error: Bağlantı hatası
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.ip, self.port))
        return True

    def disconnect(self) -> bool:
        """Bağlantıyı kapat."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        return True

    def send_command(self, command: str) -> str:
        """
        Komut gönder ve yanıt al.

        Args:
            command: Komut string'i (ör. "GetDeviceInfo()")

        Returns:
            Yanıt string'i

        Raises:
            RuntimeError: Socket bağlı değilse
            socket.error: TCP hatası
        """
        if not self.socket:
            raise RuntimeError("Not connected. Call connect() first.")

        # Debug: Gönderilen komut
        logger.info(f"→ [{self.ip}] Komut: {command}")

        # Komut şifrele (gerekirse)
        if self.crypto and self.comm_key:
            command_bytes = self.crypto.encrypt(command)
        else:
            command_bytes = command.encode('utf-8')

        # CRLF ekle
        command_bytes += b'\r\n'

        # Gönder
        try:
            self.socket.sendall(command_bytes)
        except Exception as e:
            logger.error(f"Gönderme hatası: {str(e)}")
            raise

        # Yanıt al (Wait() kontrol et)
        response = self._receive_response()

        # Wait() yanıtıysa, gerçek cevabı bekle (sınırlı — sonsuz döngü koruması)
        wait_count = 0
        while self.parser.is_wait_response(response):
            wait_count += 1
            if wait_count > self.MAX_WAIT_RETRIES:
                logger.error(
                    f"[{self.ip}] Wait() limiti aşıldı ({self.MAX_WAIT_RETRIES} deneme), komut: {command[:60]}"
                )
                raise TimeoutError(
                    f"Cihaz {self.MAX_WAIT_RETRIES * 2} saniyedir Wait() dönüyor, işlem iptal edildi"
                )
            time.sleep(2)
            response = self._receive_response()

        if wait_count > 0:
            logger.debug(f"Wait() yanıtı alındı, {wait_count} kez beklendi")

        logger.info(f"← [{self.ip}] Yanıt: {response[:150]}{'...' if len(response) > 150 else ''}")
        return response

    def _receive_response(self) -> str:
        """
        Yanıt al (TCP chunk'ları birleştir).

        ) karakterine kadar okur.

        Returns:
            Yanıt string'i
        """
        full_data = b''
        chunk_count = 0

        while True:
            chunk = self.socket.recv(self.BUFFER_SIZE)
            if not chunk:
                break

            chunk_count += 1

            # Şifreleme varsa chunk'ı decrypt et
            if self.crypto and self.comm_key:
                offset = len(full_data) % 8
                chunk = self.crypto.decrypt(chunk, offset=offset)

            full_data += chunk

            # ) ile bitmiş mi?
            if b')' in full_data:
                # Son ) 'e kadar al
                end_idx = full_data.rfind(b')') + 1
                response_bytes = full_data[:end_idx]
                return response_bytes.decode('utf-8')

        return full_data.decode('utf-8')

    # Komut wrappers

    def get_device_info(self) -> Optional[Dict[str, str]]:
        """
        GetDeviceInfo() — Cihaz bilgisi al.

        Returns:
            dev_id, time, edition, ip, vb. dict'i
        """
        response = self.send_command("GetDeviceInfo()")
        return self.parser.parse_get_device_info(response)

    def get_record(
        self,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, str]]:
        """
        GetRecord(start_time, end_time) — Erişim kayıtları al.

        Args:
            start_time: YYYY-M-D H:M:S formatında (ör. "2026-6-9 0:0:0")
            end_time: YYYY-M-D H:M:S formatında (ör. "2026-6-9 23:59:59")

        Returns:
            Kayıt listesi
        """
        command = (
            f'GetRecord(start_time="{start_time}" end_time="{end_time}")'
        )
        response = self.send_command(command)
        return self.parser.parse_get_record(response)

    def get_employee_id(self) -> List[str]:
        """
        GetEmployeeID() — Tüm personel ID'lerini al.

        Returns:
            Personel ID listesi
        """
        response = self.send_command("GetEmployeeID()")
        return self.parser.parse_get_employee_id(response)

    # Türkçe → ASCII (cihaz Türkçe karakter desteklemiyor)
    # ş→s  Ş→S  ç→c  Ç→C  ğ→g  Ğ→G  ı→i  İ→I  ö→o  Ö→O  ü→u  Ü→U
    _TR_ASCII = str.maketrans(
        'şŞçÇğĞıİöÖüÜ',
        'sScCgGiIoOuU',
    )

    @staticmethod
    def _ascii_name(name: str) -> str:
        """İsmi cihaza göndermeden önce Türkçe karakterleri ASCII'ye çevir.

        DB'de Türkçe saklanır; bu metot yalnızca cihaza yazılacak name
        parametresine uygulanır.
        """
        return (name or '').translate(HanvonClient._TR_ASCII)

    @staticmethod
    def _sanitize(value: str) -> str:
        """
        Komuta gömülecek değeri temizle (protokol injection koruması).

        Hanvon protokolünde escape mekanizması yok; tırnak, parantez ve
        satır sonu karakterleri komut yapısını bozabilir — kaldırılır.
        """
        if not isinstance(value, str):
            value = str(value)
        for ch in ('"', '(', ')', '\r', '\n'):
            value = value.replace(ch, '')
        return value

    def get_employee(self, employee_id: str) -> Optional[Dict[str, str]]:
        """
        GetEmployee(id) — Personel detaylarını al.

        Args:
            employee_id: Personel ID

        Returns:
            Personel dict'i (name, card_num, check_type, vb.)
        """
        command = f'GetEmployee(id="{self._sanitize(employee_id)}")'
        response = self.send_command(command)
        return self.parser.parse_get_employee(response)

    def set_device_info(self, time: str, week: str) -> bool:
        """
        SetDeviceInfo(time, week) — Cihaz saatini ayarla.

        Args:
            time: YYYY-M-D H:M:S formatında
            week: 1-7 (1=Pazartesi, ..., 7=Pazar)

        Returns:
            Başarı durumu
        """
        command = f'SetDeviceInfo(time="{self._sanitize(time)}" week="{self._sanitize(week)}")'
        response = self.send_command(command)
        fields = self.parser.parse_response(response)
        return fields is not None and fields.get('result') == 'success'

    def set_employee(
        self,
        employee_id: str,
        name: str = "",
        calid: str = "",
        card_num: str = "",
        authority: str = "0X0",
        check_type: str = "face",
        opendoor_type: str = "face",
        face_data=None,
    ) -> bool:
        """
        SetEmployee(...) — Personel oluştur veya güncelle.

        Args:
            employee_id: Personel ID
            name: İsim
            calid: Hesaplanmış ID (cihaz tarafından yönetilir, boş bırakılabilir)
            card_num: Kart numarası
            authority: Yetki kodu (varsayılan "0X0")
            check_type: "face" / "card" / "face&card"
            opendoor_type: "face" / "card" / "face&card"
            face_data: str (tek) veya List[str] (18 template) — GetEmployee'den gelen liste

        Returns:
            Başarı durumu
        """
        params = (
            f'id="{self._sanitize(employee_id)}"'
            f' name="{self._sanitize(self._ascii_name(name))}"'
            f' calid="{self._sanitize(calid)}"'
            f' card_num="{self._sanitize(card_num)}"'
            f' authority="{self._sanitize(authority)}"'
            f' check_type="{self._sanitize(check_type)}"'
            f' opendoor_type="{self._sanitize(opendoor_type)}"'
        )

        # face_data: str veya List[str] — her birini ayrı parametre olarak ekle
        if face_data:
            templates = face_data if isinstance(face_data, list) else [face_data]
            for template in templates:
                if template:
                    params += f' face_data="{self._sanitize(template)}"'

        command = f'SetEmployee({params})'
        response = self.send_command(command)
        fields = self.parser.parse_response(response)
        return fields is not None and fields.get('result') == 'success'

    def set_name_table(self, name_updates: Dict[str, str]) -> bool:
        """
        SetNameTable(id1="name1" ...) — İsim güncelle (tek kayıt önerilir).

        Timeout durumunda bir kez yeniden bağlanıp tekrar dener; hâlâ yanıt
        gelmezse GetEmployee ile güncellemenin gerçekleşip gerçekleşmediğini
        doğrular — cihaz bazen ACK göndermeden işlemi tamamlar.

        Args:
            name_updates: {employee_id: new_name} dict'i

        Returns:
            Başarı durumu
        """
        params = " ".join(
            f'{self._sanitize(emp_id)}="{self._sanitize(self._ascii_name(name))}"'
            for emp_id, name in name_updates.items()
        )
        command = f'SetNameTable({params})'

        try:
            response = self.send_command(command)
            fields = self.parser.parse_response(response)
            return fields is not None and fields.get('result') == 'success'

        except (socket.timeout, TimeoutError, OSError) as exc:
            logger.warning(
                "[%s] SetNameTable timeout (%s) — yeniden bağlanıp tekrar deneniyor",
                self.ip, exc,
            )

        # Yeniden bağlan ve bir kez daha dene
        try:
            self.disconnect()
            self.connect()
            response = self.send_command(command)
            fields = self.parser.parse_response(response)
            if fields is not None and fields.get('result') == 'success':
                logger.info("[%s] SetNameTable retry başarılı", self.ip)
                return True
        except (socket.timeout, TimeoutError, OSError) as exc2:
            logger.warning(
                "[%s] SetNameTable retry de timeout (%s) — GetEmployee ile doğrulanıyor",
                self.ip, exc2,
            )

        # İkinci timeout: cihaz ACK göndermeden işlemi tamamlamış olabilir.
        # Beklenen ismi GetEmployee ile doğrula.
        if len(name_updates) == 1:
            emp_id, expected_name = next(iter(name_updates.items()))
            expected_ascii = self._ascii_name(expected_name)
            try:
                verify = self.get_employee(emp_id)
                if verify and verify.get('name', '') == expected_ascii:
                    logger.info(
                        "[%s] SetNameTable ACK gelmedi ama GetEmployee doğruladı — başarılı sayılıyor",
                        self.ip,
                    )
                    return True
            except Exception as ve:
                logger.warning("[%s] SetNameTable doğrulama okuması başarısız: %s", self.ip, ve)

        return False

    def delete_all_record(self, time: str) -> bool:
        """
        DeleteAllRecord(time) — Belirli zamana kadarki kayıtları sil.

        Args:
            time: YYYY-M-D H:M:S formatında (bu zamana kadarını sil)

        Returns:
            Başarı durumu
        """
        command = f'DeleteAllRecord(time="{self._sanitize(time)}")'
        response = self.send_command(command)
        fields = self.parser.parse_response(response)
        return fields is not None and fields.get('result') == 'success'

    def delete_all_records_now(self) -> bool:
        """
        DeleteAllRecord() — Cihazdaki tüm G/C kayıtlarını sil (F710 formatı, parametre yok).

        SDK Manual §5.2: F710 için DeleteAllRecord() parametresiz çağrılır.
        Personel verisi (yüz/kart) silinmez, yalnızca kayıtlar temizlenir.

        Returns:
            Başarı durumu
        """
        response = self.send_command("DeleteAllRecord()")
        fields = self.parser.parse_response(response)
        return fields is not None and fields.get('result') == 'success'

    def delete_employee(self, employee_id: str) -> bool:
        """
        DeleteEmployee(id) — Personeli sil (geçmiş loglar kalır).

        Args:
            employee_id: Personel ID

        Returns:
            Başarı durumu
        """
        command = f'DeleteEmployee(id="{self._sanitize(employee_id)}")'
        response = self.send_command(command)
        fields = self.parser.parse_response(response)
        return fields is not None and fields.get('result') == 'success'

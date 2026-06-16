"""
CommKey XOR şifreleme (Ruby SDK'dan port).

Hanvon F710 protokolü XOR stream cipher kullanır.
Anahtar: CommKey (1-8 rakam) → 8-byte döngüsel anahtar.

Algoritma:
  - Şifre karakterleri: '0'-'9' (rakam)
  - Anahtar[pos] = password[pos].ord + (2^pos >> 1)
  - Eksik karakter: 0 (null)
  - Encrypt/Decrypt: XOR simetrik, offset ile başlangıç kontrolü
"""


class HanvonCrypto:
    """CommKey XOR şifreleme."""

    def __init__(self, password: str | None):
        """
        Args:
            password: CommKey (1-8 rakam) veya None (şifreleme yok)

        Raises:
            ValueError: password rakam değilse veya 9+ karakterse
        """
        self.password = password
        self.key = None

        if password is None:
            # Şifreleme yok
            return

        # Validasyon
        if not isinstance(password, str):
            raise ValueError("Password must be a string or None")

        if len(password) > 8:
            raise ValueError(f"Password must be 1-8 digits, got {len(password)}")

        if password and not password.isdigit():
            raise ValueError(f"Password must contain only digits, got '{password}'")

        # Anahtar hesapla
        self._compute_key(password)

    def _compute_key(self, password: str):
        """Anahtar hesaplama: key[pos] = password[pos].ord + (2^pos >> 1)."""
        self.key = []
        for pos in range(8):
            char_code = ord(password[pos]) if pos < len(password) else 0
            offset = (2 ** pos) >> 1  # 2^pos / 2
            self.key.append(char_code + offset)

    def encrypt(self, plaintext: str) -> bytes:
        """
        Metni şifrele.

        Args:
            plaintext: Açık metin

        Returns:
            Şifreli bytes
        """
        if self.key is None:
            # Şifreleme yok
            return plaintext.encode('utf-8')

        data = plaintext.encode('utf-8')
        ciphertext = bytearray()
        for pos, byte in enumerate(data):
            key_byte = self.key[pos % 8]
            ciphertext.append(byte ^ key_byte)

        return bytes(ciphertext)

    def decrypt(self, ciphertext: bytes, offset: int = 0) -> bytes:
        """
        Şifreli metni çöz.

        Args:
            ciphertext: Şifreli bytes
            offset: Anahtar başlangıç pozisyonu (mod 8)

        Returns:
            Açık metin bytes
        """
        if self.key is None:
            # Şifreleme yok
            return ciphertext

        plaintext = bytearray()
        for pos, byte in enumerate(ciphertext):
            key_idx = (pos + offset) % 8
            key_byte = self.key[key_idx]
            plaintext.append(byte ^ key_byte)

        return bytes(plaintext)

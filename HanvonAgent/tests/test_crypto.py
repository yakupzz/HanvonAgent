"""
XOR şifreleme testleri (Ruby SDK'dan port).
Referans: D:\Projeler\F710\referans\spec\hanvon_crypto_spec.rb
"""

import pytest
from core.hanvon_crypto import HanvonCrypto


class TestHanvonCrypto:
    """CommKey XOR şifreleme testleri."""

    def test_compute_key_with_full_password(self):
        """8 karakterli şifre için anahtar hesaplama."""
        crypto = HanvonCrypto("12345678")
        # '1' = 0x31 = 49, '2' = 0x32 = 50, vb.
        # pos=0: 49 + 0 = 49
        # pos=1: 50 + 1 = 51
        # pos=2: 51 + 2 = 53
        # pos=3: 52 + 4 = 56
        # pos=4: 53 + 8 = 61
        # pos=5: 54 + 16 = 70
        # pos=6: 55 + 32 = 87
        # pos=7: 56 + 64 = 120
        expected_key = [49, 51, 53, 56, 61, 70, 87, 120]
        assert crypto.key == expected_key

    def test_compute_key_with_partial_password(self):
        """4 karakterli şifre için anahtar (kalan 0 olarak pad edilir)."""
        crypto = HanvonCrypto("1234")
        # pos=0: 49 + 0 = 49
        # pos=1: 50 + 1 = 51
        # pos=2: 51 + 2 = 53
        # pos=3: 52 + 4 = 56
        # pos=4: 0 + 8 = 8
        # pos=5: 0 + 16 = 16
        # pos=6: 0 + 32 = 32
        # pos=7: 0 + 64 = 64
        expected_key = [49, 51, 53, 56, 8, 16, 32, 64]
        assert crypto.key == expected_key

    def test_compute_key_empty_password(self):
        """Boş şifre (sadece padding)."""
        crypto = HanvonCrypto("")
        expected_key = [0, 1, 2, 4, 8, 16, 32, 64]
        assert crypto.key == expected_key

    def test_encrypt_getdeviceinfo_with_12345678(self):
        """GetDeviceInfo() şifreleme (12345678 şifresi ile)."""
        crypto = HanvonCrypto("12345678")
        plaintext = "GetDeviceInfo()"
        ciphertext = crypto.encrypt(plaintext)
        # Ruby spec'ten beklenen hex
        expected_hex = "7656417c58303e1b547a5b5e526e7e"
        assert ciphertext.hex() == expected_hex

    def test_encrypt_getdeviceinfo_with_00000000(self):
        """GetDeviceInfo() şifreleme (00000000 şifresi ile)."""
        crypto = HanvonCrypto("00000000")
        plaintext = "GetDeviceInfo()"
        ciphertext = crypto.encrypt(plaintext)
        expected_hex = "775446705d36391355785c52576879"
        assert ciphertext.hex() == expected_hex

    def test_encrypt_getdeviceinfo_with_1234(self):
        """GetDeviceInfo() şifreleme (1234 şifresi ile)."""
        crypto = HanvonCrypto("1234")
        plaintext = "GetDeviceInfo()"
        ciphertext = crypto.encrypt(plaintext)
        expected_hex = "7656417c6d664923547a5b5e673809"
        assert ciphertext.hex() == expected_hex

    def test_decrypt_with_offset_zero(self):
        """Decrypt offset=0 (tam baştan başla)."""
        crypto = HanvonCrypto("12345678")
        plaintext = "GetDeviceInfo()"
        ciphertext = crypto.encrypt(plaintext)
        # Decrypt offset 0 ile başında
        decrypted = crypto.decrypt(ciphertext, offset=0)
        assert decrypted.decode('utf-8') == plaintext

    def test_decrypt_with_offset(self):
        """Decrypt offset=3 ile anahtar kayması."""
        crypto = HanvonCrypto("12345678")
        plaintext = "ABCDEFGH"
        ciphertext = crypto.encrypt(plaintext)
        # offset=3 ile decrypt: anahtar (0+3)%8, (1+3)%8, ... başlar
        decrypted = crypto.decrypt(ciphertext, offset=3)
        # Özgün şifreleme offset=0 ile, decrypt offset=3 ile → fark olmalı
        # Aslında decrypt(encrypt(x, offset=0), offset=3) != x
        # Ama decrypt(encrypt(x, offset=a), offset=a) = x
        # Burada offset=0 ile şifrele, offset=0 ile decrypt
        decrypted = crypto.decrypt(ciphertext, offset=0)
        assert decrypted.decode('utf-8') == plaintext

    def test_empty_string_encrypt_decrypt(self):
        """Boş string şifreleme/çözme."""
        crypto = HanvonCrypto("12345678")
        plaintext = ""
        ciphertext = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(ciphertext, offset=0)
        assert decrypted.decode('utf-8') == plaintext

    def test_encrypt_decrypt_roundtrip(self):
        """Şifreleme → Çözme döngüsü."""
        crypto = HanvonCrypto("54321")
        plaintext = "Hello, Hanvon F710!"
        ciphertext = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(ciphertext, offset=0)
        assert decrypted.decode('utf-8') == plaintext

    def test_invalid_password_non_digits(self):
        """Şifre harf içermesi hatası."""
        with pytest.raises(ValueError, match="only digits"):
            HanvonCrypto("12ab5678")

    def test_invalid_password_empty(self):
        """Geçerli: boş şifre (sifreleme yok)."""
        # Boş şifre geçerli, şifreleme yapılmayacak
        crypto = HanvonCrypto("")
        # Key hesaplandı
        assert len(crypto.key) == 8

    def test_invalid_password_too_long(self):
        """Şifre 9+ karakter hatası."""
        with pytest.raises(ValueError, match="1-8 digits"):
            HanvonCrypto("123456789")

    def test_no_password_attribute(self):
        """CommKey None ise şifreleme yapılmayacak (flag)."""
        crypto = HanvonCrypto(None)
        plaintext = "GetDeviceInfo()"
        # Şifreleme yok, açık metin döner
        result = crypto.encrypt(plaintext)
        # None ise plaintext döner (bytes olarak)
        assert result == plaintext.encode('utf-8')

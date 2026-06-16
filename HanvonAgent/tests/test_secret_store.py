"""Secret Store (DPAPI) testleri."""

import pytest
from core.secret_store import encrypt_secret, decrypt_secret, is_encrypted


class TestSecretStore:
    def test_roundtrip(self):
        """Şifrele → çöz → aynı değer."""
        encrypted = encrypt_secret("12345678")
        assert decrypt_secret(encrypted) == "12345678"

    def test_encrypted_format(self):
        """Şifreli değer dpapi: prefix'i taşır ve düz metni içermez."""
        encrypted = encrypt_secret("87654321")
        assert encrypted.startswith("dpapi:")
        assert "87654321" not in encrypted

    def test_legacy_plaintext_passthrough(self):
        """Prefix'siz (legacy) değer olduğu gibi döner."""
        assert decrypt_secret("12345678") == "12345678"

    def test_none_and_empty(self):
        assert decrypt_secret(None) is None
        assert decrypt_secret("") == ""
        assert encrypt_secret("") == ""

    def test_is_encrypted(self):
        assert is_encrypted(encrypt_secret("123"))
        assert not is_encrypted("123")
        assert not is_encrypted(None)
        assert not is_encrypted("")

    def test_unique_ciphertexts_decrypt_same(self):
        """DPAPI her seferinde farklı çıktı üretebilir; ikisi de çözülür."""
        e1 = encrypt_secret("555")
        e2 = encrypt_secret("555")
        assert decrypt_secret(e1) == decrypt_secret(e2) == "555"

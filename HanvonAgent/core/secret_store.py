"""
Secret Store — Windows DPAPI ile sır şifreleme (CommKey vb.).

Neden DPAPI:
- Anahtar yönetimi Windows'a ait; kod/dosya içinde anahtar tutulmaz.
- CRYPTPROTECT_LOCAL_MACHINE kapsamı sayesinde hem GUI (kullanıcı) hem
  NSSM servisi (SYSTEM) aynı veriyi çözebilir.
- DB dosyası başka makineye kopyalanırsa sırlar çözülemez.

Format: "dpapi:<base64>" — prefix'siz değerler legacy düz metin kabul edilir
ve olduğu gibi döner (geriye dönük uyumluluk + ilk açılışta migration).
"""

import base64
import ctypes
import ctypes.wintypes
import logging
import sys

logger = logging.getLogger("HanvonAgent.SecretStore")

_PREFIX = "dpapi:"

CRYPTPROTECT_UI_FORBIDDEN = 0x01
CRYPTPROTECT_LOCAL_MACHINE = 0x04


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _bytes_to_blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def is_encrypted(value: str | None) -> bool:
    """Değer DPAPI formatında mı?"""
    return bool(value) and value.startswith(_PREFIX)


def encrypt_secret(plaintext: str) -> str:
    """
    Düz metni DPAPI ile şifrele → "dpapi:<base64>".

    Windows dışı ortamda (test/CI) düz metin döner ve uyarı loglanır.
    """
    if not plaintext:
        return plaintext

    if sys.platform != "win32":
        logger.warning("DPAPI yok (platform=%s), sır düz metin saklanacak", sys.platform)
        return plaintext

    blob_in = _bytes_to_blob(plaintext.encode("utf-8"))
    blob_out = _DATA_BLOB()

    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData başarısız oldu")

    return _PREFIX + base64.b64encode(_blob_to_bytes(blob_out)).decode("ascii")


def decrypt_secret(stored: str | None) -> str | None:
    """
    Saklanan değeri çöz.

    - "dpapi:" prefix'li → DPAPI ile çözülür.
    - Prefix'siz (legacy düz metin) → olduğu gibi döner.
    """
    if not stored or not stored.startswith(_PREFIX):
        return stored

    raw = base64.b64decode(stored[len(_PREFIX):])
    blob_in = _bytes_to_blob(raw)
    blob_out = _DATA_BLOB()

    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData başarısız oldu (farklı makinede mi şifrelendi?)")

    return _blob_to_bytes(blob_out).decode("utf-8")

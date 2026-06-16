#!/usr/bin/env python3
"""
Versiyon bump script — Her geliştirme sonrası çalıştırın.
Versiyon şeması: ver.MAJOR.MINOR.PATCH

Kurallar:
- PATCH: 0-99 (99'a ulaştığında reset ve MINOR artar)
- MINOR: 0-99 (99'a ulaştığında reset ve MAJOR artar)
- MAJOR: sınırsız

Kullanım:
  python bump_version.py patch   # 0.1.0 -> 0.1.1
  python bump_version.py minor   # 0.1.99 -> 0.2.0
  python bump_version.py major   # 0.99.99 -> 1.0.0
"""

import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "HanvonAgent" / "__version__.py"


def read_version():
    """__version__.py dosyasından versiyon oku."""
    content = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'VERSION = "(\d+\.\d+\.\d+)"', content)
    if match:
        return match.group(1)
    raise ValueError(f"Versiyon bulunamadı: {VERSION_FILE}")


def bump_version(current, part="patch"):
    """Versiyon numarasını artır."""
    parts = current.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if part == "patch":
        patch += 1
        if patch > 99:
            patch = 0
            minor += 1
            if minor > 99:
                minor = 0
                major += 1
    elif part == "minor":
        minor += 1
        patch = 0
        if minor > 99:
            minor = 0
            major += 1
    elif part == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Geçersiz part: {part}")

    return f"{major}.{minor}.{patch}"


def update_version(new_version):
    """__version__.py dosyasını güncelle."""
    content = VERSION_FILE.read_text(encoding="utf-8")
    updated = re.sub(
        r'VERSION = "\d+\.\d+\.\d+"',
        f'VERSION = "{new_version}"',
        content
    )
    VERSION_FILE.write_text(updated, encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print(f"Kullanım: python {Path(__file__).name} <patch|minor|major>")
        print(f"Örnek: python {Path(__file__).name} patch")
        sys.exit(1)

    part = sys.argv[1].lower()

    if part not in ["patch", "minor", "major"]:
        print(f"Hata: {part} geçersiz. 'patch', 'minor' veya 'major' olmalı.")
        sys.exit(1)

    current = read_version()
    new_version = bump_version(current, part)

    print(f"Versiyon Bump: {current} -> {new_version}")
    update_version(new_version)
    print(f"OK {VERSION_FILE} guncellendi")


if __name__ == "__main__":
    main()

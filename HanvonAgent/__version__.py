"""
Uygulama versiyon bilgisi.
Versiyon şeması: ver.MAJOR.MINOR.PATCH
"""

VERSION = "0.3.2"

def get_version():
    """Versiyon bilgisini döndür."""
    return f"ver.{VERSION}"

def bump_version(part="patch"):
    """
    Versiyon numarasını artır.
    part: "patch", "minor", "major"

    Kural: patch 99'a ulaştığında minor artır, minor 99'a ulaştığında major artır.
    """
    parts = VERSION.split(".")
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
    elif part == "major":
        major += 1
        minor = 0
        patch = 0

    return f"{major}.{minor}.{patch}"

if __name__ == "__main__":
    print(f"Mevcut Versiyon: {get_version()}")

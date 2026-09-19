"""Generate a random 32-byte base64 ENCRYPTION_SECRET.

Usage:
    python -m src.keygen
"""
from . import secure


def main() -> None:
    print(secure.generate_secret())


if __name__ == "__main__":
    main()

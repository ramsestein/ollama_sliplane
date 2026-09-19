"""Generate a random 32-byte base64 ENCRYPTION_SECRET and store it in `.env`.

The secret is written straight to `.env` (owner-only permissions on POSIX) and
is never printed to stdout or written to logs, so it cannot leak through
terminal scrollback, CI logs or shell history.

Usage:
    python -m src.keygen
"""
import os
import pathlib

from . import secure

_ENV_PATH = pathlib.Path(".env")
_ENV_EXAMPLE = pathlib.Path(".env.example")
_KEY = "ENCRYPTION_SECRET"


def main() -> None:
    secret = secure.generate_secret()

    if not _ENV_PATH.exists() and _ENV_EXAMPLE.exists():
        _ENV_PATH.write_text(_ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    lines = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    written = False
    updated = []
    for line in lines:
        if line.strip().startswith(_KEY + "="):
            updated.append(f"{_KEY}={secret}")
            written = True
        else:
            updated.append(line)
    if not written:
        updated.append(f"{_KEY}={secret}")

    _ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
    try:
        os.chmod(_ENV_PATH, 0o600)
    except OSError:
        pass  # Windows: chmod is best-effort.

    print("ENCRYPTION_SECRET written to .env (value not shown).")


if __name__ == "__main__":
    main()

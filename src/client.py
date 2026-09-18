#!/usr/bin/env python3
"""Test client for the encrypted Ollama proxy."""
import argparse
import base64
import json
import os
import sys
import urllib.request

from . import secure


def _read_env(key):
    if os.environ.get(key):
        return os.environ[key]
    try:
        with open(".env", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1]
    except OSError:
        pass
    return ""


def load_secret(cli_secret):
    if cli_secret:
        return cli_secret
    value = _read_env("ENCRYPTION_SECRET")
    if value:
        return value
    sys.stderr.write("Missing ENCRYPTION_SECRET (pass it with --secret or in .env)\n")
    sys.exit(1)


def secure_request(secret, base_url, method, path, body, auth=None):
    inner = {"method": method, "path": path, "body": body}
    envelope = secure.encrypt(secret, json.dumps(inner).encode("utf-8"))
    data = json.dumps(envelope).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(
        base_url + "/secure/request",
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        resp_envelope = json.loads(resp.read().decode("utf-8"))
    return json.loads(secure.decrypt(secret, resp_envelope).decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Encrypted client for Ollama")
    parser.add_argument(
        "--url",
        default=os.environ.get("OLLAMA_URL", "https://ollama-sliplane.sliplane.app"),
    )
    parser.add_argument("--secret", help="Encryption secret (or ENCRYPTION_SECRET/.env)")
    parser.add_argument("--user", help="Username (or AUTH_USER/.env)")
    parser.add_argument("--password", help="Password (or AUTH_PASSWORD/.env)")
    parser.add_argument("--model", default="gemma3:270m")
    parser.add_argument("--prompt", default="Answer in one sentence: what is Ollama?")
    args = parser.parse_args()

    secret = load_secret(args.secret)
    base = args.url.rstrip("/")

    user = args.user or _read_env("AUTH_USER")
    password = args.password or _read_env("AUTH_PASSWORD")
    auth = None
    if user and password:
        token = base64.b64encode(("%s:%s" % (user, password)).encode("utf-8")).decode("ascii")
        auth = "Basic " + token

    # 1) health
    try:
        with urllib.request.urlopen(base + "/health", timeout=30) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        print("[OK] Proxy alive. Server window: %s" % health.get("window"))
    except Exception as exc:  # noqa: BLE001
        print("[WARN] /health did not respond: %s" % exc)

    # 2) chat cifrado
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": False,
    }
    result = secure_request(secret, base, "POST", "/v1/chat/completions", body, auth)
    if result.get("status") != 200:
        print("[FAIL] Server responded %s: %s" % (result.get("status"), result.get("body")))
        sys.exit(1)
    content = result["body"]["choices"][0]["message"]["content"]
    print("[OK] Response:")
    print(content)


if __name__ == "__main__":
    main()

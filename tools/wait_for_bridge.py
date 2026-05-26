from __future__ import annotations

import argparse
import os
import time
import urllib.error
import urllib.request

from session_discovery import resolve_connection


def token_from_args(args) -> str:
    return resolve_connection(args.host, args.port, args.token).get("token", "")


def request_status(host: str, port: int, token: str, timeout: float = 3) -> tuple[bool, str]:
    request = urllib.request.Request(
        f"http://{host}:{port}/status",
        headers={"Authorization": f"Bearer {token}"} if token else {},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default="")
    parser.add_argument("--pairing-code", default=None)
    parser.add_argument("--session-file", default=None)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    connection = resolve_connection(args.host, args.port, args.token, args.pairing_code, args.session_file)
    args.host = connection["host"]
    args.port = connection["port"]
    token = connection["token"]
    if connection.get("session_path"):
        print(f"Using session file: {connection['session_path']}")
    deadline = time.time() + args.timeout
    last_message = ""
    while time.time() < deadline:
        ok, message = request_status(args.host, args.port, token)
        if ok:
            print("SIGMAI bridge is online.")
            print(message)
            return 0
        last_message = message
        print(f"Waiting for bridge: {message}")
        time.sleep(2)
    print(f"Bridge did not become available. Last status: {last_message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

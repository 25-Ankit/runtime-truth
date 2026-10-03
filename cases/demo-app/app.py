"""Controlled deterministic demo application for Runtime Truth."""

import json
import os
from pathlib import Path
import socket
import subprocess

# Static environment declarations
APP_ENV = os.getenv("APP_ENV", "production")
PORT = int(os.getenv("PORT", "8080"))

# Static package declarations (imported when present in runtime environment)
try:
    import flask  # noqa: F401
except ImportError:
    pass

try:
    import requests  # noqa: F401
except ImportError:
    pass


def load_application_config() -> dict:
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {}


def resolve_and_connect(hostname: str, port: int) -> None:
    # Resolve through the system resolver (observed as DNS evidence when the
    # container uses the deterministic stub resolver), then connect to the
    # resolved address (observed as a connect syscall). No hardcoded IPs:
    # without resolution there is no connection attempt.
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except Exception:
        return
    for family, socktype, proto, _, sockaddr in resolved:
        try:
            s = socket.socket(family, socktype, proto)
            s.settimeout(0.2)
            s.connect(sockaddr)
            s.close()
            return
        except Exception:
            continue


def simulate_activity(endpoint: str):
    # 1. Process activity: execute standard child process
    try:
        subprocess.run(["echo", "runtime-truth demo process"], capture_output=True)
    except Exception:
        pass

    # 2. Network activity: resolve the declared endpoint hostname, then
    # attempt a short-timeout outbound connection to the resolved address.
    hostname = endpoint.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    resolve_and_connect(hostname, 443)


def main():
    config = load_application_config()
    service_name = config.get("service_name", "unknown-service")
    endpoint = config.get("api_endpoint", "https://api.example.com")
    simulate_activity(endpoint)
    print(f"[{service_name}] Running in {APP_ENV} on port {PORT}. Contacting {endpoint}...")


if __name__ == "__main__":
    main()

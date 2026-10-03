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


def simulate_activity():
    # 1. Process activity: execute standard child process
    try:
        subprocess.run(["echo", "runtime-truth demo process"], capture_output=True)
    except Exception:
        pass

    # 2. Network activity: non-blocking outbound socket connect attempt to api.example.com
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.2)
        s.connect(("93.184.216.34", 443))
        s.close()
    except Exception:
        pass


def main():
    config = load_application_config()
    service_name = config.get("service_name", "unknown-service")
    endpoint = config.get("api_endpoint", "https://api.example.com")
    simulate_activity()
    print(f"[{service_name}] Running in {APP_ENV} on port {PORT}. Contacting {endpoint}...")


if __name__ == "__main__":
    main()

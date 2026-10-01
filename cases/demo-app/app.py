"""Controlled deterministic demo application for Runtime Truth."""

import json
import os
from pathlib import Path

# Static environment declarations
APP_ENV = os.getenv("APP_ENV", "production")
PORT = int(os.getenv("PORT", "8080"))


def load_application_config() -> dict:
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {}


def main():
    config = load_application_config()
    service_name = config.get("service_name", "unknown-service")
    endpoint = config.get("api_endpoint", "https://api.example.com")
    print(f"[{service_name}] Running in {APP_ENV} on port {PORT}. Contacting {endpoint}...")


if __name__ == "__main__":
    main()

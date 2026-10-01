"""Safe JSON and YAML configuration parsers."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser

URL_PATTERN = re.compile(r"^https?://[a-zA-Z0-9\-\.]+(?::\d+)?(?:/.*)?$")


def _extract_from_data(
    data: Any,
    rel_path: str,
    run_id: str,
    current_key: str = "",
) -> List[DeclaredEntity]:
    """Recursively search structured config for network destinations, ports, and env vars."""
    entities: List[DeclaredEntity] = []

    if isinstance(data, dict):
        for k, v in data.items():
            key_name = f"{current_key}.{k}" if current_key else str(k)
            # Check if key implies environment variables
            if str(k).upper() in ("ENV", "ENVIRONMENT", "ENV_VARS"):
                if isinstance(v, dict):
                    for env_k, env_v in v.items():
                        entity_id = generate_entity_id(
                            DeclaredEntityType.ENVIRONMENT_VARIABLE.value, str(env_k)
                        )
                        entities.append(
                            DeclaredEntity(
                                entity_id=entity_id,
                                run_id=run_id,
                                entity_type=DeclaredEntityType.ENVIRONMENT_VARIABLE,
                                name=str(env_k),
                                normalized_value=str(env_k),
                                raw_value=str(env_v),
                                source=rel_path,
                                source_location=SourceLocation(file_path=rel_path),
                                metadata={"config_key": key_name},
                            )
                        )
            elif str(k).lower() in ("port", "listen_port", "server_port") and isinstance(v, (int, str)):
                port_str = str(v)
                if port_str.isdigit():
                    entity_id = generate_entity_id(
                        DeclaredEntityType.PORT.value, port_str
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.PORT,
                            name=f"port_{port_str}",
                            normalized_value=port_str,
                            raw_value=str(v),
                            source=rel_path,
                            source_location=SourceLocation(file_path=rel_path),
                            metadata={"config_key": key_name},
                        )
                    )
            elif isinstance(v, str) and URL_PATTERN.match(v.strip()):
                parsed = urlparse(v.strip())
                dest = parsed.netloc or parsed.path
                if dest:
                    host = dest.split(":")[0]
                    entity_id = generate_entity_id(
                        DeclaredEntityType.NETWORK_DESTINATION.value, host
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.NETWORK_DESTINATION,
                            name=host,
                            normalized_value=host.lower(),
                            raw_value=v.strip(),
                            source=rel_path,
                            source_location=SourceLocation(file_path=rel_path),
                            metadata={"config_key": key_name, "url": v.strip()},
                        )
                    )
            else:
                entities.extend(_extract_from_data(v, rel_path, run_id, key_name))

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            entities.extend(_extract_from_data(item, rel_path, run_id, f"{current_key}[{idx}]"))

    elif isinstance(data, str) and URL_PATTERN.match(data.strip()):
        parsed = urlparse(data.strip())
        dest = parsed.netloc or parsed.path
        if dest:
            host = dest.split(":")[0]
            entity_id = generate_entity_id(
                DeclaredEntityType.NETWORK_DESTINATION.value, host
            )
            entities.append(
                DeclaredEntity(
                    entity_id=entity_id,
                    run_id=run_id,
                    entity_type=DeclaredEntityType.NETWORK_DESTINATION,
                    name=host,
                    normalized_value=host.lower(),
                    raw_value=data.strip(),
                    source=rel_path,
                    source_location=SourceLocation(file_path=rel_path),
                    metadata={"config_key": current_key, "url": data.strip()},
                )
            )

    return entities


class JsonConfigParser(StaticParser):
    """Safely extracts network destinations and ports from JSON configuration files."""

    def can_parse(self, file_path: Path) -> bool:
        name = file_path.name.lower()
        if name in ("package.json", "package-lock.json", "tsconfig.json"):
            return False
        return name.endswith(".json")

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
        except Exception:
            return []

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        return _extract_from_data(data, rel_path, run_id)


class YamlConfigParser(StaticParser):
    """Safely extracts network destinations, ports, and env vars from YAML configuration files."""

    def can_parse(self, file_path: Path) -> bool:
        name = file_path.name.lower()
        return name.endswith(".yaml") or name.endswith(".yml")

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            data = yaml.safe_load(content)
        except Exception:
            return []

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        return _extract_from_data(data, rel_path, run_id)

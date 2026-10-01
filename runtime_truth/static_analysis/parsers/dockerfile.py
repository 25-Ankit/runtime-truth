"""Parser for Dockerfiles."""

import re
from pathlib import Path
from typing import List

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser


class DockerfileParser(StaticParser):
    """Parses Dockerfiles and extracts declared ports, environment vars, commands, and paths."""

    def can_parse(self, file_path: Path) -> bool:
        name = file_path.name.lower()
        return name == "dockerfile" or name.endswith(".dockerfile") or name.startswith("dockerfile.")

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        entities: List[DeclaredEntity] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return entities

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            parts = stripped.split(None, 1)
            if not parts:
                continue

            instruction = parts[0].upper()
            arguments = parts[1].strip() if len(parts) > 1 else ""

            if instruction == "EXPOSE":
                # EXPOSE 8080 or EXPOSE 8080/tcp
                for port_tok in arguments.split():
                    port_clean = port_tok.split("/")[0].strip()
                    entity_id = generate_entity_id(
                        DeclaredEntityType.PORT.value, port_clean
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.PORT,
                            name=f"port_{port_clean}",
                            normalized_value=port_clean,
                            raw_value=stripped,
                            source=rel_path,
                            source_location=SourceLocation(file_path=rel_path, line_number=line_num),
                            metadata={"instruction": "EXPOSE", "raw_token": port_tok},
                        )
                    )

            elif instruction == "ENV":
                # ENV KEY=VAL or ENV KEY VAL
                if "=" in arguments:
                    pairs = re.findall(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', arguments)
                    for key, v1, v2, v3 in pairs:
                        val = v1 or v2 or v3
                        entity_id = generate_entity_id(
                            DeclaredEntityType.ENVIRONMENT_VARIABLE.value, key
                        )
                        entities.append(
                            DeclaredEntity(
                                entity_id=entity_id,
                                run_id=run_id,
                                entity_type=DeclaredEntityType.ENVIRONMENT_VARIABLE,
                                name=key,
                                normalized_value=key,
                                raw_value=f"{key}={val}",
                                source=rel_path,
                                source_location=SourceLocation(file_path=rel_path, line_number=line_num),
                                metadata={"instruction": "ENV", "default_value": val},
                            )
                        )
                else:
                    env_parts = arguments.split(None, 1)
                    if env_parts:
                        key = env_parts[0].strip()
                        val = env_parts[1].strip() if len(env_parts) > 1 else ""
                        entity_id = generate_entity_id(
                            DeclaredEntityType.ENVIRONMENT_VARIABLE.value, key
                        )
                        entities.append(
                            DeclaredEntity(
                                entity_id=entity_id,
                                run_id=run_id,
                                entity_type=DeclaredEntityType.ENVIRONMENT_VARIABLE,
                                name=key,
                                normalized_value=key,
                                raw_value=stripped,
                                source=rel_path,
                                source_location=SourceLocation(file_path=rel_path, line_number=line_num),
                                metadata={"instruction": "ENV", "default_value": val},
                            )
                        )

            elif instruction in ("CMD", "ENTRYPOINT"):
                # Process command
                entity_id = generate_entity_id(
                    DeclaredEntityType.PROCESS.value, arguments
                )
                entities.append(
                    DeclaredEntity(
                        entity_id=entity_id,
                        run_id=run_id,
                        entity_type=DeclaredEntityType.PROCESS,
                        name=instruction.lower(),
                        normalized_value=arguments,
                        raw_value=stripped,
                        source=rel_path,
                        source_location=SourceLocation(file_path=rel_path, line_number=line_num),
                        metadata={"instruction": instruction},
                    )
                )

            elif instruction in ("WORKDIR", "VOLUME"):
                # Filesystem path
                entity_id = generate_entity_id(
                    DeclaredEntityType.FILESYSTEM_PATH.value, arguments
                )
                entities.append(
                    DeclaredEntity(
                        entity_id=entity_id,
                        run_id=run_id,
                        entity_type=DeclaredEntityType.FILESYSTEM_PATH,
                        name=instruction.lower(),
                        normalized_value=arguments,
                        raw_value=stripped,
                        source=rel_path,
                        source_location=SourceLocation(file_path=rel_path, line_number=line_num),
                        metadata={"instruction": instruction},
                    )
                )

        return entities

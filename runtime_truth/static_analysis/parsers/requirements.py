"""Parser for requirements.txt files."""

import re
from pathlib import Path
from typing import List, Optional

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser


class RequirementsTxtParser(StaticParser):
    """Parses Python requirements.txt files and extracts declared dependencies."""

    # Matches package_name[extras] and optional version specifier
    # e.g.: requests==2.31.0, flask[async]>=3.0.0, uvicorn
    PKG_REGEX = re.compile(
        r"^([a-zA-Z0-9_\-\.]+)(?:\[([a-zA-Z0-9_,\-\.]+)\])?\s*([<>=!~].*)?$"
    )

    def can_parse(self, file_path: Path) -> bool:
        name = file_path.name.lower()
        return (
            name == "requirements.txt"
            or (name.endswith(".txt") and "requirements" in name)
            or name.endswith(".pip")
        )

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
            # Ignore empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Ignore pip flags (-r, -i, -f, --find-links, etc.)
            if stripped.startswith("-"):
                continue

            # Strip inline comments and environment markers
            cleaned = stripped.split("#")[0].strip()
            if ";" in cleaned:
                cleaned = cleaned.split(";")[0].strip()

            if not cleaned:
                continue

            match = self.PKG_REGEX.match(cleaned)
            if match:
                raw_name = match.group(1)
                extras = match.group(2)
                specifier = match.group(3).strip() if match.group(3) else None
                normalized_name = raw_name.lower().replace("_", "-")

                entity_id = generate_entity_id(
                    entity_type=DeclaredEntityType.DEPENDENCY.value,
                    normalized_value=normalized_name,
                )

                entities.append(
                    DeclaredEntity(
                        entity_id=entity_id,
                        run_id=run_id,
                        entity_type=DeclaredEntityType.DEPENDENCY,
                        name=raw_name,
                        normalized_value=normalized_name,
                        raw_value=stripped,
                        source=rel_path,
                        source_location=SourceLocation(
                            file_path=rel_path,
                            line_number=line_num,
                        ),
                        metadata={
                            "version_specifier": specifier,
                            "extras": extras.split(",") if extras else [],
                        },
                    )
                )

        return entities

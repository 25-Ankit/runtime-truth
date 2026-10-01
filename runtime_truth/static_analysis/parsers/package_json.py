"""Parser for Node.js package.json files."""

import json
from pathlib import Path
from typing import List

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser


class PackageJsonParser(StaticParser):
    """Parses package.json files and extracts npm dependencies."""

    DEPENDENCY_SECTIONS = [
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.name.lower() == "package.json"

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        entities: List[DeclaredEntity] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
        except Exception:
            return entities

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        for section in self.DEPENDENCY_SECTIONS:
            deps = data.get(section, {})
            if isinstance(deps, dict):
                for pkg_name, version in deps.items():
                    norm_name = pkg_name.strip().lower()
                    entity_id = generate_entity_id(
                        DeclaredEntityType.DEPENDENCY.value, norm_name, qualifier="npm"
                    )
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.DEPENDENCY,
                            name=pkg_name,
                            normalized_value=norm_name,
                            raw_value=f"{pkg_name}: {version}",
                            source=rel_path,
                            source_location=SourceLocation(file_path=rel_path),
                            metadata={"ecosystem": "npm", "section": section, "version": str(version)},
                        )
                    )

        return entities

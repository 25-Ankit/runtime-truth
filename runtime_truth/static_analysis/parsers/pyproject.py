"""Parser for pyproject.toml files."""

import re
import tomllib
from pathlib import Path
from typing import Any, Dict, List

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, SourceLocation
from runtime_truth.static_analysis.base import StaticParser


class PyprojectTomlParser(StaticParser):
    """Parses pyproject.toml files and extracts dependencies (PEP 621 and Poetry)."""

    DEP_SPEC_REGEX = re.compile(
        r"^([a-zA-Z0-9_\-\.]+)(?:\[([a-zA-Z0-9_,\-\.]+)\])?\s*([<>=!~].*)?$"
    )

    def can_parse(self, file_path: Path) -> bool:
        return file_path.name.lower() == "pyproject.toml"

    def _parse_spec_string(self, dep_str: str) -> tuple[str, str, Optional[str], List[str]]:
        cleaned = dep_str.strip()
        if ";" in cleaned:
            cleaned = cleaned.split(";")[0].strip()
        match = self.DEP_SPEC_REGEX.match(cleaned)
        if match:
            raw_name = match.group(1)
            extras = match.group(2).split(",") if match.group(2) else []
            spec = match.group(3).strip() if match.group(3) else None
            return raw_name, raw_name.lower().replace("_", "-"), spec, extras
        return dep_str, dep_str.lower().replace("_", "-"), None, []

    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        entities: List[DeclaredEntity] = []
        try:
            content = file_path.read_bytes()
            data = tomllib.loads(content.decode("utf-8", errors="replace"))
        except Exception:
            return entities

        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        # 1. PEP 621 [project.dependencies]
        project_table = data.get("project", {})
        if isinstance(project_table, dict):
            deps = project_table.get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    if isinstance(dep, str):
                        raw_name, norm_name, spec, extras = self._parse_spec_string(dep)
                        entity_id = generate_entity_id(
                            DeclaredEntityType.DEPENDENCY.value, norm_name
                        )
                        entities.append(
                            DeclaredEntity(
                                entity_id=entity_id,
                                run_id=run_id,
                                entity_type=DeclaredEntityType.DEPENDENCY,
                                name=raw_name,
                                normalized_value=norm_name,
                                raw_value=dep,
                                source=rel_path,
                                source_location=SourceLocation(file_path=rel_path),
                                metadata={"section": "project.dependencies", "specifier": spec, "extras": extras},
                            )
                        )

            # PEP 621 [project.optional-dependencies]
            opt_deps = project_table.get("optional-dependencies", {})
            if isinstance(opt_deps, dict):
                for group, group_deps in opt_deps.items():
                    if isinstance(group_deps, list):
                        for dep in group_deps:
                            if isinstance(dep, str):
                                raw_name, norm_name, spec, extras = self._parse_spec_string(dep)
                                entity_id = generate_entity_id(
                                    DeclaredEntityType.DEPENDENCY.value, norm_name
                                )
                                entities.append(
                                    DeclaredEntity(
                                        entity_id=entity_id,
                                        run_id=run_id,
                                        entity_type=DeclaredEntityType.DEPENDENCY,
                                        name=raw_name,
                                        normalized_value=norm_name,
                                        raw_value=dep,
                                        source=rel_path,
                                        source_location=SourceLocation(file_path=rel_path),
                                        metadata={"section": f"project.optional-dependencies.{group}", "specifier": spec, "extras": extras},
                                    )
                                )

        # 2. Poetry [tool.poetry.dependencies]
        tool_poetry = data.get("tool", {}).get("poetry", {})
        if isinstance(tool_poetry, dict):
            poetry_deps = tool_poetry.get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for pkg_name, spec_val in poetry_deps.items():
                    if pkg_name.lower() == "python":
                        continue
                    norm_name = pkg_name.lower().replace("_", "-")
                    spec = spec_val if isinstance(spec_val, str) else str(spec_val)
                    entity_id = generate_entity_id(DeclaredEntityType.DEPENDENCY.value, norm_name)
                    entities.append(
                        DeclaredEntity(
                            entity_id=entity_id,
                            run_id=run_id,
                            entity_type=DeclaredEntityType.DEPENDENCY,
                            name=pkg_name,
                            normalized_value=norm_name,
                            raw_value=f"{pkg_name} = {spec}",
                            source=rel_path,
                            source_location=SourceLocation(file_path=rel_path),
                            metadata={"section": "tool.poetry.dependencies", "specifier": spec},
                        )
                    )

        return entities

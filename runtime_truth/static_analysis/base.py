"""Base abstractions and engine for static analysis."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Set

from runtime_truth.core.identifiers import generate_entity_id
from runtime_truth.core.models import DeclaredEntity, DeclaredModel


class StaticParser(ABC):
    """Protocol / base class for file-specific static analyzers."""

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Return True if this parser can analyze the given file."""

    @abstractmethod
    def parse(self, file_path: Path, run_id: str, project_root: Path) -> List[DeclaredEntity]:
        """Parse file and return discovered declared entities."""


class StaticAnalysisEngine:
    """Coordinates all registered parsers across a project directory."""

    # Default paths and directory names to ignore during scanning
    DEFAULT_IGNORES: Set[str] = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".runtimetruth",
        "dist",
        "build",
        ".eggs",
    }

    def __init__(self, parsers: List[StaticParser]):
        self.parsers = parsers

    def scan(self, project_path: Path, run_id: str) -> DeclaredModel:
        """Scan project_path using all available parsers and produce a DeclaredModel."""
        resolved_root = project_path.resolve()
        if not resolved_root.exists():
            raise FileNotFoundError(f"Project directory not found: {project_path}")

        entities: List[DeclaredEntity] = []

        if resolved_root.is_file():
            # Single file scan
            for parser in self.parsers:
                if parser.can_parse(resolved_root):
                    entities.extend(parser.parse(resolved_root, run_id, resolved_root.parent))
            return DeclaredModel(run_id=run_id, entities=entities)

        # Directory traversal
        for path in resolved_root.rglob("*"):
            # Check if any part of the path matches ignores
            relative_parts = set(path.relative_to(resolved_root).parts)
            if relative_parts & self.DEFAULT_IGNORES:
                continue

            if not path.is_file():
                continue

            for parser in self.parsers:
                if parser.can_parse(path):
                    parsed_entities = parser.parse(path, run_id, resolved_root)
                    entities.extend(parsed_entities)

        return DeclaredModel(run_id=run_id, entities=entities)

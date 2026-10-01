"""Static analysis subsystem for producing Declared Models."""

from runtime_truth.static_analysis.base import StaticAnalysisEngine, StaticParser
from runtime_truth.static_analysis.parsers import (
    DockerfileParser,
    JsonConfigParser,
    PackageJsonParser,
    PyprojectTomlParser,
    PythonAstParser,
    RequirementsTxtParser,
    YamlConfigParser,
)


def get_default_static_engine() -> StaticAnalysisEngine:
    """Return a StaticAnalysisEngine configured with all default parsers."""
    return StaticAnalysisEngine(
        parsers=[
            RequirementsTxtParser(),
            PyprojectTomlParser(),
            PackageJsonParser(),
            DockerfileParser(),
            PythonAstParser(),
            JsonConfigParser(),
            YamlConfigParser(),
        ]
    )


__all__ = [
    "DockerfileParser",
    "JsonConfigParser",
    "PackageJsonParser",
    "PyprojectTomlParser",
    "PythonAstParser",
    "RequirementsTxtParser",
    "StaticAnalysisEngine",
    "StaticParser",
    "YamlConfigParser",
    "get_default_static_engine",
]

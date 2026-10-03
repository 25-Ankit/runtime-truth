"""Docker tracer assets and environment management."""

from pathlib import Path


def get_tracer_dockerfile_path() -> Path:
    """Return the absolute path to the default tracer Dockerfile."""
    return Path(__file__).parent / "Dockerfile.tracer"

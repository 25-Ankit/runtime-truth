"""Shared fixtures for Runtime Truth tests."""

import subprocess
import shutil
import pytest
from pathlib import Path
from runtime_truth.storage.database import Database
from runtime_truth.static_analysis import get_default_static_engine


def is_docker_available() -> bool:
    """Return True if docker binary exists and daemon is responsive."""
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False


@pytest.fixture
def memory_db():
    """Provides an in-memory SQLite database instance."""
    return Database(":memory:")


@pytest.fixture
def static_engine():
    """Provides the default static analysis engine."""
    return get_default_static_engine()


@pytest.fixture
def demo_app_dir():
    """Returns the path to the cases/demo-app fixture directory."""
    return Path(__file__).parent.parent / "cases" / "demo-app"


@pytest.fixture
def docker_available():
    """Returns boolean indicating if docker daemon is responsive."""
    return is_docker_available()

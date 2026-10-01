"""Shared fixtures for Runtime Truth tests."""

import pytest
from pathlib import Path
from runtime_truth.storage.database import Database
from runtime_truth.static_analysis import get_default_static_engine


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

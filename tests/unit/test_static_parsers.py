"""Unit tests for all static analysis parsers."""

from pathlib import Path
import tempfile
import pytest

from runtime_truth.core.enums import DeclaredEntityType
from runtime_truth.static_analysis.parsers import (
    DockerfileParser,
    JsonConfigParser,
    PackageJsonParser,
    PyprojectTomlParser,
    PythonAstParser,
    RequirementsTxtParser,
    YamlConfigParser,
)


def test_requirements_txt_parser():
    content = """# Comment line
flask==3.0.0
requests[security]>=2.31.0 ; sys_platform == 'linux'
-r other.txt
--extra-index-url https://example.com/simple
celery~=5.3.0 # inline comment
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_text(content, encoding="utf-8")

        parser = RequirementsTxtParser()
        assert parser.can_parse(req_file)

        entities = parser.parse(req_file, run_id="r1", project_root=Path(tmpdir))
        assert len(entities) == 3

        names = {e.normalized_value: e for e in entities}
        assert "flask" in names
        assert names["flask"].source_location.line_number == 2
        assert names["flask"].metadata["version_specifier"] == "==3.0.0"

        assert "requests" in names
        assert names["requests"].metadata["extras"] == ["security"]

        assert "celery" in names


def test_pyproject_toml_parser():
    content = """[project]
name = "my-project"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn[standard]==0.25.0",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
]

[tool.poetry.dependencies]
python = "^3.12"
pydantic = "^2.0.0"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        pyproject_file = Path(tmpdir) / "pyproject.toml"
        pyproject_file.write_text(content, encoding="utf-8")

        parser = PyprojectTomlParser()
        assert parser.can_parse(pyproject_file)

        entities = parser.parse(pyproject_file, run_id="r1", project_root=Path(tmpdir))
        names = {e.normalized_value for e in entities}
        assert "fastapi" in names
        assert "uvicorn" in names
        assert "pytest" in names
        assert "pydantic" in names
        assert "python" not in names


def test_package_json_parser():
    content = """{
  "name": "sample-node-app",
  "dependencies": {
    "express": "^4.18.2",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}"""
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_file = Path(tmpdir) / "package.json"
        pkg_file.write_text(content, encoding="utf-8")

        parser = PackageJsonParser()
        assert parser.can_parse(pkg_file)

        entities = parser.parse(pkg_file, run_id="r1", project_root=Path(tmpdir))
        names = {e.normalized_value: e for e in entities}
        assert "express" in names
        assert "axios" in names
        assert "typescript" in names
        assert names["express"].metadata["ecosystem"] == "npm"


def test_dockerfile_parser():
    content = """FROM python:3.12-alpine
WORKDIR /app
ENV PORT=5000
ENV SERVICE_NAME="worker"
EXPOSE 5000 8080/tcp
CMD ["python", "main.py"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        df = Path(tmpdir) / "Dockerfile"
        df.write_text(content, encoding="utf-8")

        parser = DockerfileParser()
        assert parser.can_parse(df)

        entities = parser.parse(df, run_id="r1", project_root=Path(tmpdir))
        by_type = {}
        for e in entities:
            by_type.setdefault(e.entity_type, []).append(e)

        # Ports
        ports = [e.normalized_value for e in by_type[DeclaredEntityType.PORT]]
        assert "5000" in ports
        assert "8080" in ports

        # Env vars
        env_vars = [e.normalized_value for e in by_type[DeclaredEntityType.ENVIRONMENT_VARIABLE]]
        assert "PORT" in env_vars
        assert "SERVICE_NAME" in env_vars

        # Process
        procs = [e.normalized_value for e in by_type[DeclaredEntityType.PROCESS]]
        assert any('["python", "main.py"]' in p for p in procs)

        # Filesystem path
        paths = [e.normalized_value for e in by_type[DeclaredEntityType.FILESYSTEM_PATH]]
        assert "/app" in paths


def test_python_ast_parser():
    content = """import os
import sys
from urllib.parse import urlparse
import requests as req

DB_URL = os.getenv("DATABASE_URL")
API_KEY = os.environ.get("SECRET_KEY")
TOKEN = os.environ["AUTH_TOKEN"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        py_file = Path(tmpdir) / "app.py"
        py_file.write_text(content, encoding="utf-8")

        parser = PythonAstParser()
        assert parser.can_parse(py_file)

        entities = parser.parse(py_file, run_id="r1", project_root=Path(tmpdir))
        by_type = {}
        for e in entities:
            by_type.setdefault(e.entity_type, []).append(e)

        deps = {e.normalized_value: e for e in by_type[DeclaredEntityType.DEPENDENCY]}
        assert "os" in deps
        assert "sys" in deps
        assert "urllib" in deps
        assert "requests" in deps
        assert deps["requests"].source_location.line_number == 4

        envs = {e.normalized_value for e in by_type[DeclaredEntityType.ENVIRONMENT_VARIABLE]}
        assert "DATABASE_URL" in envs
        assert "SECRET_KEY" in envs
        assert "AUTH_TOKEN" in envs


def test_config_parsers():
    json_content = """{
  "api_url": "https://api.github.com/v3",
  "port": 9000,
  "env": {
    "LOG_LEVEL": "debug"
  }
}"""
    yaml_content = """
endpoint: https://api.stripe.com/v1
port: 4000
env_vars:
  STRIPE_KEY: sk_test_123
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        jfile = Path(tmpdir) / "app_config.json"
        yfile = Path(tmpdir) / "config.yaml"
        jfile.write_text(json_content, encoding="utf-8")
        yfile.write_text(yaml_content, encoding="utf-8")

        j_parser = JsonConfigParser()
        assert j_parser.can_parse(jfile)
        j_entities = j_parser.parse(jfile, run_id="r1", project_root=Path(tmpdir))
        j_names = {e.normalized_value for e in j_entities}
        assert "api.github.com" in j_names
        assert "9000" in j_names
        assert "LOG_LEVEL" in j_names

        y_parser = YamlConfigParser()
        assert y_parser.can_parse(yfile)
        y_entities = y_parser.parse(yfile, run_id="r1", project_root=Path(tmpdir))
        y_names = {e.normalized_value for e in y_entities}
        assert "api.stripe.com" in y_names
        assert "4000" in y_names
        assert "STRIPE_KEY" in y_names

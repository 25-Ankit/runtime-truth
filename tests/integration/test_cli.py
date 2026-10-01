"""Integration tests for Typer CLI commands."""

import json
from pathlib import Path
import tempfile
from typer.testing import CliRunner

from runtime_truth.cli.main import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Runtime Truth" in result.stdout
    assert "scan" in result.stdout
    assert "report" in result.stdout
    assert "diff" in result.stdout
    assert "baseline" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_scan_and_report_and_diff(demo_app_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "cli_test.db")
        log_file = str(demo_app_dir / "recorded_strace.log")

        # 1. Scan with JSON output
        scan_res = runner.invoke(
            app,
            [
                "scan",
                str(demo_app_dir),
                "--mode",
                "offline_events",
                "--offline-log",
                log_file,
                "--db",
                db_file,
                "--json",
            ],
        )
        assert scan_res.exit_code == 0
        data = json.loads(scan_res.stdout)
        run_id = data["meta"]["run_id"]
        assert run_id.startswith("run_")
        assert data["summary"]["total_findings"] > 0

        # 2. Report CLI
        report_res = runner.invoke(
            app,
            ["report", run_id, "--db", db_file],
        )
        assert report_res.exit_code == 0
        assert run_id in report_res.stdout

        # 3. Report JSON
        report_json_res = runner.invoke(
            app,
            ["report", run_id, "--db", db_file, "--format", "json"],
        )
        assert report_json_res.exit_code == 0
        json_data = json.loads(report_json_res.stdout)
        assert json_data["meta"]["run_id"] == run_id

        # 4. Baseline create
        baseline_res = runner.invoke(
            app,
            ["baseline", "create", run_id, "--name", "test-base", "--db", db_file],
        )
        assert baseline_res.exit_code == 0
        assert "Baseline 'test-base' created successfully" in baseline_res.stdout

        # 5. Diff
        diff_res = runner.invoke(
            app,
            ["diff", run_id, run_id, "--db", db_file],
        )
        assert diff_res.exit_code == 0
        assert "Common persistent findings" in diff_res.stdout

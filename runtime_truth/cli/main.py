"""Main CLI application using Typer."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from runtime_truth import __version__
from runtime_truth.config.loader import load_config
from runtime_truth.core.enums import RuntimeMode
from runtime_truth.core.models import DeclaredModel, ObservedModel
from runtime_truth.orchestrator.runner import Orchestrator
from runtime_truth.reporting.cli_report import CliReportFormatter
from runtime_truth.reporting.html_report import HtmlReportGenerator
from runtime_truth.reporting.json_report import JsonReportGenerator
from runtime_truth.static_analysis import get_default_static_engine
from runtime_truth.storage.artifacts import ArtifactExporter
from runtime_truth.storage.database import Database
from runtime_truth.storage.repositories import (
    DeclaredEntityRepository,
    EvidenceRepository,
    FindingRepository,
    ObservedEntityRepository,
    RunRepository,
)

app = typer.Typer(
    name="runtime-truth",
    help="Runtime Truth: Declared Software Model vs Observed Runtime Behavior",
    no_args_is_help=True,
    add_completion=False,
)
baseline_app = typer.Typer(
    name="baseline",
    help="Manage accepted baseline runs for regression detection.",
    no_args_is_help=True,
)
app.add_typer(baseline_app, name="baseline")

console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"[bold blue]Runtime Truth[/bold blue] version [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """Runtime Truth: Declared Software Model vs Observed Runtime Behavior."""


@app.command("scan")
def scan_cmd(
    path: Path = typer.Argument(
        ...,
        help="Path to project directory or file to analyze.",
        exists=True,
    ),
    mode: str = typer.Option(
        RuntimeMode.STATIC_ONLY.value,
        "--mode",
        "-m",
        help="Execution mode: static_only, offline_events, host_strace, container_strace",
    ),
    offline_log: Optional[Path] = typer.Option(
        None,
        "--offline-log",
        help="Path to raw strace log file for offline event replay.",
        exists=True,
    ),
    db_path: Optional[str] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file. Defaults to config or .runtimetruth/runtimetruth.db.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON report to stdout instead of formatted terminal tables.",
    ),
    output_html: Optional[Path] = typer.Option(
        None,
        "--output-html",
        help="Custom path to save the generated HTML report.",
    ),
):
    """Scan a project to compare declared models with observed runtime behavior."""
    config = load_config(path if path.is_dir() else path.parent)
    sqlite_path = db_path or config.db_path

    db = Database(sqlite_path)
    static_engine = get_default_static_engine()
    artifact_exporter = ArtifactExporter(base_dir=Path(config.artifacts_dir).parent)

    orchestrator = Orchestrator(
        db=db,
        static_engine=static_engine,
        artifact_exporter=artifact_exporter,
    )

    try:
        runtime_mode = RuntimeMode(mode)
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid mode '{mode}'. Choose from: static_only, offline_events, host_strace, container_strace")
        raise typer.Exit(code=1)

    with console.status("[bold green]Analyzing project declared and observed models..."):
        result = orchestrator.execute(
            project_path=path,
            runtime_mode=runtime_mode,
            offline_log_path=offline_log,
        )

    if output_html and result.html_report_path:
        output_html.parent.mkdir(parents=True, exist_ok=True)
        output_html.write_text(result.html_report_path.read_text(encoding="utf-8"), encoding="utf-8")

    if json_output:
        json_report = JsonReportGenerator().generate(
            run=result.run,
            declared_model=result.declared_model,
            observed_model=result.observed_model,
            findings=result.findings,
            evidence_list=result.evidence,
        )
        print(json_report)
    else:
        formatter = CliReportFormatter(console)
        formatter.print_run_summary(
            run=result.run,
            declared_count=len(result.declared_model.entities),
            observed_count=len(result.observed_model.entities),
            findings=result.findings,
            report_path=str(output_html or result.html_report_path),
        )


@app.command("report")
def report_cmd(
    run_id: str = typer.Argument(..., help="Run ID to retrieve and inspect."),
    format_type: str = typer.Option(
        "cli",
        "--format",
        "-f",
        help="Report format: cli, json, html",
    ),
    db_path: Optional[str] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file. Defaults to config or .runtimetruth/runtimetruth.db.",
    ),
):
    """Retrieve and display stored results for a past run."""
    config = load_config()
    sqlite_path = db_path or config.db_path
    db = Database(sqlite_path)

    run_repo = RunRepository(db)
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Error:[/red] Run '{run_id}' not found in database {sqlite_path}.")
        raise typer.Exit(code=1)

    declared_repo = DeclaredEntityRepository(db)
    observed_repo = ObservedEntityRepository(db)
    finding_repo = FindingRepository(db)
    evidence_repo = EvidenceRepository(db)

    declared = DeclaredModel(run_id=run_id, entities=declared_repo.get_by_run(run_id))
    observed = ObservedModel(run_id=run_id, entities=observed_repo.get_by_run(run_id))
    findings = finding_repo.get_by_run(run_id)
    evidence = evidence_repo.get_by_run(run_id)

    if format_type.lower() == "json":
        json_rep = JsonReportGenerator().generate(run, declared, observed, findings, evidence)
        print(json_rep)
    elif format_type.lower() == "html":
        html_rep = HtmlReportGenerator().generate(run, declared, observed, findings, evidence)
        print(html_rep)
    else:
        formatter = CliReportFormatter(console)
        report_file = Path(config.artifacts_dir) / run_id / "report.html"
        formatter.print_run_summary(
            run=run,
            declared_count=len(declared.entities),
            observed_count=len(observed.entities),
            findings=findings,
            report_path=str(report_file) if report_file.exists() else None,
        )


@app.command("diff")
def diff_cmd(
    run_a: str = typer.Argument(..., help="Baseline run ID (run A)"),
    run_b: str = typer.Argument(..., help="Comparison run ID (run B)"),
    db_path: Optional[str] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file.",
    ),
):
    """Compare findings between two runs to identify regressions or resolved issues."""
    config = load_config()
    sqlite_path = db_path or config.db_path
    db = Database(sqlite_path)

    finding_repo = FindingRepository(db)
    run_repo = RunRepository(db)

    ra = run_repo.get(run_a)
    rb = run_repo.get(run_b)
    if not ra:
        console.print(f"[red]Error:[/red] Run '{run_a}' not found.")
        raise typer.Exit(code=1)
    if not rb:
        console.print(f"[red]Error:[/red] Run '{run_b}' not found.")
        raise typer.Exit(code=1)

    findings_a = {f"{f.finding_type.value}:{f.subject.lower()}": f for f in finding_repo.get_by_run(run_a)}
    findings_b = {f"{f.finding_type.value}:{f.subject.lower()}": f for f in finding_repo.get_by_run(run_b)}

    keys_a = set(findings_a.keys())
    keys_b = set(findings_b.keys())

    new_in_b = keys_b - keys_a
    resolved_in_b = keys_a - keys_b
    common = keys_a & keys_b

    console.print(f"\n[bold]Diff between [cyan]{run_a}[/cyan] and [cyan]{run_b}[/cyan]:[/bold]\n")
    console.print(f"  • Common persistent findings: [bold]{len(common)}[/bold]")
    console.print(f"  • New findings in {run_b}: [bold red]{len(new_in_b)}[/bold red]")
    console.print(f"  • Resolved findings in {run_b}: [bold green]{len(resolved_in_b)}[/bold green]\n")

    if new_in_b:
        console.print("[bold red]New Findings:[/bold red]")
        for k in new_in_b:
            f = findings_b[k]
            console.print(f"  [red]+[/red] [{f.severity.value.upper()}] {f.finding_type.value}: {f.subject} &mdash; {f.explanation}")

    if resolved_in_b:
        console.print("\n[bold green]Resolved Findings:[/bold green]")
        for k in resolved_in_b:
            f = findings_a[k]
            console.print(f"  [green]-[/green] [{f.severity.value.upper()}] {f.finding_type.value}: {f.subject}")


@baseline_app.command("create")
def baseline_create_cmd(
    run_id: str = typer.Argument(..., help="Run ID to establish as an accepted baseline."),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Optional name for the baseline (defaults to run_id).",
    ),
    db_path: Optional[str] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file.",
    ),
):
    """Record a run as a named baseline for future diff comparison."""
    config = load_config()
    sqlite_path = db_path or config.db_path
    db = Database(sqlite_path)

    run_repo = RunRepository(db)
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Error:[/red] Run '{run_id}' not found.")
        raise typer.Exit(code=1)

    finding_repo = FindingRepository(db)
    findings = finding_repo.get_by_run(run_id)

    baseline_name = name or run_id
    baseline_dir = Path(".runtimetruth") / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = baseline_dir / f"{baseline_name}.json"

    data = {
        "baseline_name": baseline_name,
        "run_id": run_id,
        "created_at": run.started_at.isoformat(),
        "findings": [f.model_dump(mode="json") for f in findings],
    }
    baseline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[green]✔[/green] Baseline '[bold]{baseline_name}[/bold]' created successfully at {baseline_file}")


if __name__ == "__main__":
    app()

"""CLI terminal formatting and presentation."""

from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from runtime_truth.core.enums import FindingSeverity
from runtime_truth.core.models import Finding, Run
from runtime_truth.findings.engine import FindingEngine

SEV_STYLES = {
    FindingSeverity.HIGH: "bold red",
    FindingSeverity.MEDIUM: "bold yellow",
    FindingSeverity.LOW: "bold blue",
    FindingSeverity.INFO: "dim cyan",
}


class CliReportFormatter:
    """Renders formatted tables and summaries to the terminal."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.finding_engine = FindingEngine()

    def print_run_summary(
        self,
        run: Run,
        declared_count: int,
        observed_count: int,
        findings: List[Finding],
        report_path: Optional[str] = None,
    ) -> None:
        summary = self.finding_engine.summarize(findings)

        panel_content = (
            f"[bold]Run ID:[/bold] {run.run_id}\n"
            f"[bold]Status:[/bold] {run.status.value}\n"
            f"[bold]Mode:[/bold] {run.runtime_mode.value}\n"
            f"[bold]Declared Entities:[/bold] {declared_count}\n"
            f"[bold]Observed Entities:[/bold] {observed_count}\n"
            f"[bold]Total Discrepancies:[/bold] {summary.total_findings}"
        )
        if report_path:
            panel_content += f"\n[bold]Report:[/bold] {report_path}"

        self.console.print(Panel(panel_content, title="Runtime Truth &mdash; Run Summary", border_style="blue"))

        if not findings:
            self.console.print("[green]✔ No discrepancies detected between declared and observed models.[/green]\n")
            return

        table = Table(title="Reconciliation Findings", show_lines=True)
        table.add_column("Severity", justify="center", width=10)
        table.add_column("Category", width=12)
        table.add_column("Type", width=34)
        table.add_column("Subject", width=20)
        table.add_column("Explanation")

        for f in findings:
            style = SEV_STYLES.get(f.severity, "white")
            table.add_row(
                f"[{style}]{f.severity.value.upper()}[/{style}]",
                f.category.value,
                f"[dim]{f.finding_type.value}[/dim]",
                f"[bold]{f.subject}[/bold]",
                f.explanation,
            )

        self.console.print(table)
        self.console.print()

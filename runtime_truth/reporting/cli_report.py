"""CLI terminal formatting and presentation."""

from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from runtime_truth.core.enums import FindingSeverity, ObservedEntityType
from runtime_truth.core.models import Finding, ObservedEntity, Run
from runtime_truth.findings.engine import (
    ACTIONABLE_FINDING_TYPES,
    INFORMATIONAL_OBSERVATION_TYPES,
    UNRESOLVED_CORRELATION_TYPES,
    FindingEngine,
)

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
        raw_trace_path: Optional[str] = None,
        raw_dns_path: Optional[str] = None,
        observed_entities: Optional[List[ObservedEntity]] = None,
    ) -> None:
        summary = self.finding_engine.summarize(findings)

        panel_content = (
            f"[bold]Run ID:[/bold] {run.run_id}\n"
            f"[bold]Status:[/bold] {run.status.value}\n"
            f"[bold]Mode:[/bold] {run.runtime_mode.value}\n"
            f"[bold]Declared Entities:[/bold] {declared_count}\n"
            f"[bold]Observed Entities:[/bold] {observed_count}\n"
            f"[bold]Actionable Findings:[/bold] {summary.actionable_findings}\n"
            f"[bold]Informational Observations:[/bold] {summary.informational_observations}\n"
            f"[bold]Unresolved Correlations:[/bold] {summary.unresolved_correlations}"
        )
        if raw_trace_path:
            panel_content += f"\n[bold]Raw Evidence:[/bold] {raw_trace_path}"
        if raw_dns_path:
            panel_content += f"\n[bold]Raw DNS Evidence:[/bold] {raw_dns_path}"
        if report_path:
            panel_content += f"\n[bold]Report:[/bold] {report_path}"

        self.console.print(Panel(panel_content, title="Runtime Truth &mdash; Run Summary", border_style="blue"))

        actionable = [f for f in findings if f.finding_type in ACTIONABLE_FINDING_TYPES]
        unresolved = [f for f in findings if f.finding_type in UNRESOLVED_CORRELATION_TYPES]
        informational = [f for f in findings if f.finding_type in INFORMATIONAL_OBSERVATION_TYPES]

        if not actionable and not unresolved and not informational:
            self.console.print("[green]✔ No discrepancies detected between declared and observed models.[/green]\n")
            return

        if not actionable and not unresolved:
            self.console.print("[green]✔ No actionable discrepancies detected between declared and observed models.[/green]\n")

        def _render_table(title: str, items: list[Finding]) -> None:
            table = Table(title=title, show_lines=True)
            table.add_column("Severity", justify="center", width=10)
            table.add_column("Category", width=12)
            table.add_column("Type", width=34)
            table.add_column("Subject", width=20)
            table.add_column("Explanation")
            for f in items:
                style = SEV_STYLES.get(f.severity, "white")
                table.add_row(
                    f"[{style}]{f.severity.value.upper()}[/{style}]",
                    f.category.value,
                    f"[dim]{f.finding_type.value}[/dim]",
                    f"[bold]{f.subject}[/bold]",
                    f.explanation,
                )
            self.console.print(table)

        if actionable:
            _render_table("Actionable Findings", actionable)
        if unresolved:
            _render_table("Unresolved Correlations", unresolved)
        if informational:
            _render_table("Informational Observations", informational)
        self._render_network_identity(observed_entities)
        self.console.print()

    def _render_network_identity(
        self, observed_entities: Optional[List[ObservedEntity]]
    ) -> None:
        """Show per-destination network identity: matched, ambiguous, or unresolved."""
        if not observed_entities:
            return
        nets = [e for e in observed_entities if e.entity_type == ObservedEntityType.NETWORK_DESTINATION]
        if not nets:
            return
        table = Table(title="Network Identity", show_lines=True)
        table.add_column("Observed Connection", width=22)
        table.add_column("Candidates / DNS Identity", width=28)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Reason / Evidence")
        for ent in nets:
            hostnames = sorted(ent.attributes.get("correlated_hostnames") or [])
            port = ent.attributes.get("port", "")
            observed = f"{ent.name}:{port}" if port else ent.name
            status = ent.attributes.get("correlation_status")
            evidence_count = f"{len(ent.evidence_ids)} evidence item(s)"

            if len(hostnames) > 1 or status == "AMBIGUOUS":
                identity = "\n".join(hostnames) if hostnames else "ambiguous"
                status_display = "[bold yellow]AMBIGUOUS[/bold yellow]"
                reason_display = f"Multiple observed hostnames share destination IP\n[dim]{evidence_count}[/dim]"
            elif len(hostnames) == 1:
                identity = hostnames[0]
                if status == "MATCHED":
                    status_display = "[green]MATCHED[/green]"
                    reason_display = f"Declared destination matched via DNS\n[dim]{evidence_count}[/dim]"
                else:
                    status_display = "[cyan]RESOLVED[/cyan]"
                    reason_display = f"DNS identity resolved ({evidence_count})"
            else:
                identity = "unresolved"
                status_display = "[dim]UNRESOLVED[/dim]"
                reason_display = f"No valid DNS correlation ({evidence_count})"

            table.add_row(
                f"[bold]{observed}[/bold]",
                identity,
                status_display,
                reason_display,
            )
        self.console.print(table)

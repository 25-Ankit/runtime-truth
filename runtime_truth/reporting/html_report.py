"""HTML report generator using Jinja2."""

from typing import List, Optional
from jinja2 import Environment

from runtime_truth.core.models import (
    DeclaredModel,
    Evidence,
    Finding,
    ObservedModel,
    Run,
)
from runtime_truth.findings.engine import FindingEngine

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Runtime Truth Report &mdash; {{ run.run_id }}</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --text-bright: #f0f6fc;
      --accent: #58a6ff;
      --sev-high: #f85149;
      --sev-med: #d29922;
      --sev-low: #388bfd;
      --sev-info: #8b949e;
      --badge-bg: #21262d;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      margin: 0;
      padding: 24px;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
    }
    header {
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 24px;
    }
    h1 {
      color: var(--text-bright);
      margin: 0 0 8px 0;
      font-size: 24px;
    }
    .subtitle {
      color: var(--text-muted);
      font-size: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px;
    }
    .card-title {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
    }
    .card-value {
      font-size: 24px;
      font-weight: 600;
      color: var(--text-bright);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 16px;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
    }
    th {
      background-color: var(--card-bg);
      color: var(--text-muted);
      font-weight: 600;
    }
    tr:hover {
      background-color: rgba(255, 255, 255, 0.02);
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 12px;
      text-transform: uppercase;
    }
    .badge-high { background-color: rgba(248, 81, 73, 0.15); color: var(--sev-high); border: 1px solid var(--sev-high); }
    .badge-medium { background-color: rgba(210, 153, 34, 0.15); color: var(--sev-med); border: 1px solid var(--sev-med); }
    .badge-low { background-color: rgba(56, 139, 253, 0.15); color: var(--sev-low); border: 1px solid var(--sev-low); }
    .badge-info { background-color: rgba(139, 148, 158, 0.15); color: var(--sev-info); border: 1px solid var(--sev-info); }
    code {
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-size: 12px;
      background: var(--badge-bg);
      padding: 2px 4px;
      border-radius: 4px;
    }
    .meta-box {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }
    details {
      margin-top: 6px;
    }
    summary {
      cursor: pointer;
      color: var(--accent);
      font-size: 12px;
    }
  </style>
</head>
<body>
<div class="container">
  <header>
    <h1>Runtime Truth Report</h1>
    <div class="subtitle">
      Declared Software Model vs Observed Runtime Behavior &bull; Run <code>{{ run.run_id }}</code>
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="card-title">Total Findings</div>
      <div class="card-value">{{ summary.total_findings }}</div>
    </div>
    <div class="card">
      <div class="card-title">Declared Entities</div>
      <div class="card-value">{{ declared_model.entities|length }}</div>
    </div>
    <div class="card">
      <div class="card-title">Observed Entities</div>
      <div class="card-value">{{ observed_model.entities|length }}</div>
    </div>
    <div class="card">
      <div class="card-title">Execution Mode</div>
      <div class="card-value" style="font-size: 18px; line-height: 32px;">{{ run.runtime_mode.value }}</div>
    </div>
  </div>

  <h2>Findings</h2>
  {% if findings %}
  <table>
    <thead>
      <tr>
        <th>Severity</th>
        <th>Category</th>
        <th>Type</th>
        <th>Subject</th>
        <th>Explanation</th>
      </tr>
    </thead>
    <tbody>
      {% for f in findings %}
      <tr>
        <td>
          <span class="badge badge-{{ f.severity.value }}">{{ f.severity.value }}</span>
        </td>
        <td>{{ f.category.value }}</td>
        <td><code>{{ f.finding_type.value }}</code></td>
        <td><strong>{{ f.subject }}</strong></td>
        <td>
          {{ f.explanation }}
          {% if f.evidence_ids %}
          <details>
            <summary>{{ f.evidence_ids|length }} Evidence Item(s)</summary>
            <ul>
              {% for eid in f.evidence_ids %}
                {% set evi = evidence_map.get(eid) %}
                {% if evi %}
                  <li><code>{{ evi.collector }}</code>: {{ evi.description }} (<code>{{ evi.raw_evidence or '' }}</code>)</li>
                {% else %}
                  <li><code>{{ eid }}</code></li>
                {% endif %}
              {% endfor %}
            </ul>
          </details>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color: var(--text-muted);">No discrepancies detected between declared and observed models.</p>
  {% endif %}

  <footer style="margin-top: 40px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--text-muted);">
    Generated by Runtime Truth v{{ run.tool_version }} &bull; Project: <code>{{ run.project_path }}</code>
  </footer>
</div>
</body>
</html>
"""


class HtmlReportGenerator:
    """Produces clean, responsive standalone HTML reports."""

    def __init__(self, finding_engine: Optional[FindingEngine] = None):
        self.finding_engine = finding_engine or FindingEngine()
        self.env = Environment(autoescape=True)
        self.template = self.env.from_string(HTML_TEMPLATE)

    def generate(
        self,
        run: Run,
        declared_model: DeclaredModel,
        observed_model: ObservedModel,
        findings: List[Finding],
        evidence_list: List[Evidence],
    ) -> str:
        summary = self.finding_engine.summarize(findings)
        evidence_map = {e.evidence_id: e for e in evidence_list}

        return self.template.render(
            run=run,
            summary=summary,
            declared_model=declared_model,
            observed_model=observed_model,
            findings=findings,
            evidence_map=evidence_map,
        )

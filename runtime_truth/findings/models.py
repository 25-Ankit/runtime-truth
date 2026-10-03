"""Finding representations and summaries."""

from typing import List
from pydantic import BaseModel, Field

from runtime_truth.core.enums import FindingCategory, FindingSeverity, FindingType
from runtime_truth.core.models import Finding


class FindingSummary(BaseModel):
    """Statistical summary separating actionable findings from observations."""
    total_findings: int = 0
    actionable_findings: int = 0
    informational_observations: int = 0
    unresolved_correlations: int = 0
    by_category: dict[FindingCategory, int] = Field(default_factory=dict)
    by_severity: dict[FindingSeverity, int] = Field(default_factory=dict)
    by_type: dict[FindingType, int] = Field(default_factory=dict)

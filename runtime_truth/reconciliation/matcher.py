"""Entity matcher for comparing DeclaredModel against ObservedModel."""

from dataclasses import dataclass, field
from typing import Dict, Generic, List, Tuple, TypeVar

from runtime_truth.core.enums import DeclaredEntityType, ObservedEntityType
from runtime_truth.core.models import DeclaredEntity, DeclaredModel, ObservedEntity, ObservedModel


@dataclass
class MatchResult:
    """Outcome of comparing declared entities against observed entities for a category."""
    matched: List[Tuple[DeclaredEntity, ObservedEntity]] = field(default_factory=list)
    declared_only: List[DeclaredEntity] = field(default_factory=list)
    observed_only: List[ObservedEntity] = field(default_factory=list)


class EntityMatcher:
    """Matches declared and observed entities by normalized canonical values."""

    def match_category(
        self,
        declared_list: List[DeclaredEntity],
        observed_list: List[ObservedEntity],
    ) -> MatchResult:
        result = MatchResult()

        declared_by_val: Dict[str, DeclaredEntity] = {}
        for d in declared_list:
            # First declaration of normalized_value wins or collects
            val = d.normalized_value.strip().lower()
            if val not in declared_by_val:
                declared_by_val[val] = d

        observed_by_val: Dict[str, ObservedEntity] = {}
        for o in observed_list:
            val = o.normalized_value.strip().lower()
            if val not in observed_by_val:
                observed_by_val[val] = o

        matched_vals = set(declared_by_val.keys()) & set(observed_by_val.keys())

        for val in matched_vals:
            result.matched.append((declared_by_val[val], observed_by_val[val]))

        for val, d in declared_by_val.items():
            if val not in matched_vals:
                result.declared_only.append(d)

        for val, o in observed_by_val.items():
            if val not in matched_vals:
                result.observed_only.append(o)

        return result

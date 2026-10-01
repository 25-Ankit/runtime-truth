"""Base interfaces for event normalization and observed model building."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from runtime_truth.core.models import Evidence, ObservedModel, RuntimeEvent
from runtime_truth.runtime.base import RawEvent


class EventNormalizer(ABC):
    """Normalizes raw collector events into canonical RuntimeEvent objects."""

    @abstractmethod
    def normalize(self, raw_event: RawEvent, run_id: str) -> Optional[RuntimeEvent]:
        """Convert a raw event into a canonical RuntimeEvent, or None if skipped/unrecognized."""


class ObservedModelBuilder(ABC):
    """Synthesizes an ObservedModel and supporting Evidence records from canonical RuntimeEvents."""

    @abstractmethod
    def build(self, events: List[RuntimeEvent], run_id: str) -> Tuple[ObservedModel, List[Evidence]]:
        """Aggregate events into ObservedEntities and generate Evidence records."""

"""Runtime observer interfaces and raw event representations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_truth.core.errors import ObservationError


@dataclass
class RawEvent:
    """Unnormalized raw event emitted by a collector before normalization."""
    sequence: int
    collector: str
    raw_payload: str
    timestamp: datetime
    metadata: Dict[str, Any]


class RuntimeObserver(ABC):
    """Abstract interface for runtime observation backends (strace, eBPF, procfs, etc.)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this observation backend can run in the current environment."""

    @abstractmethod
    def observe(self, target: Any, run_id: str) -> List[RawEvent]:
        """Execute observation and return raw event stream."""

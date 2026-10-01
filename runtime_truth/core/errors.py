"""Domain-specific error hierarchy for Runtime Truth."""


class RuntimeTruthError(Exception):
    """Base exception for all Runtime Truth errors."""


class StaticAnalysisError(RuntimeTruthError):
    """Raised when static analysis encounters an error."""


class ParserError(StaticAnalysisError):
    """Raised when a specific file cannot be parsed safely."""


class StorageError(RuntimeTruthError):
    """Raised when persistence operations fail."""


class ObservationError(RuntimeTruthError):
    """Raised when runtime observation fails."""


class ReconciliationError(RuntimeTruthError):
    """Raised when reconciliation between models fails."""


class ConfigurationError(RuntimeTruthError):
    """Raised when project or runner configuration is invalid."""

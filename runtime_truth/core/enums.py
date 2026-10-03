"""Enumerations for Runtime Truth core domain."""

from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeMode(str, Enum):
    STATIC_ONLY = "static_only"
    CONTAINER_STRACE = "container_strace"
    DOCKER = "docker"
    HOST_STRACE = "host_strace"
    OFFLINE_EVENTS = "offline_events"


class DeclaredEntityType(str, Enum):
    DEPENDENCY = "dependency"
    NETWORK_DESTINATION = "network_destination"
    FILESYSTEM_PATH = "filesystem_path"
    ENVIRONMENT_VARIABLE = "environment_variable"
    PROCESS = "process"
    PORT = "port"


class RuntimeEventType(str, Enum):
    PROCESS_SPAWN = "process_spawn"
    PROCESS_EXIT = "process_exit"
    NETWORK_CONNECT = "network_connect"
    DNS_RESOLUTION = "dns_resolution"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    ENVIRONMENT_ACCESS = "environment_access"


class ObservedEntityType(str, Enum):
    DEPENDENCY = "dependency"
    PACKAGE_ARTIFACT = "package_artifact"
    NETWORK_DESTINATION = "network_destination"
    FILESYSTEM_PATH = "filesystem_path"
    ENVIRONMENT_VARIABLE = "environment_variable"
    PROCESS = "process"


class FindingCategory(str, Enum):
    DEPENDENCY = "dependency"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    PROCESS = "process"
    ENVIRONMENT = "environment"
    BEHAVIOR = "behavior"


class FindingType(str, Enum):
    DEPENDENCY_DECLARED_NOT_OBSERVED = "DEPENDENCY_DECLARED_NOT_OBSERVED"
    PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED = "PACKAGE_ARTIFACT_OBSERVED_NOT_DECLARED"
    RUNTIME_DEPENDENCY_NOT_DECLARED = "RUNTIME_DEPENDENCY_NOT_DECLARED"
    NETWORK_DECLARED_NOT_OBSERVED = "NETWORK_DECLARED_NOT_OBSERVED"
    NETWORK_OBSERVED_NOT_DECLARED = "NETWORK_OBSERVED_NOT_DECLARED"
    NETWORK_IDENTITY_UNCORRELATED = "NETWORK_IDENTITY_UNCORRELATED"
    FILESYSTEM_OBSERVED_NOT_DECLARED = "FILESYSTEM_OBSERVED_NOT_DECLARED"
    PROCESS_OBSERVED_NOT_DECLARED = "PROCESS_OBSERVED_NOT_DECLARED"
    TARGET_PROCESS = "TARGET_PROCESS"
    ENVIRONMENT_OBSERVED_NOT_DECLARED = "ENVIRONMENT_OBSERVED_NOT_DECLARED"
    BEHAVIORAL_DRIFT = "BEHAVIORAL_DRIFT"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

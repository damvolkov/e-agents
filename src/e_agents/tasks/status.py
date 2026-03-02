"""Task status and priority enumerations."""

from enum import StrEnum, auto


class TaskStatus(StrEnum):
    """Status of a background task."""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


class TaskPriority(StrEnum):
    """Priority level for background tasks."""

    HIGH = auto()
    NORMAL = auto()
    LOW = auto()

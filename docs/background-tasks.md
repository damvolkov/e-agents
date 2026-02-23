# Background Tasks

The background task system enables long-running operations without blocking the conversation.

## Components

### TaskStatus & TaskPriority

```python
class TaskStatus(StrEnum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()

class TaskPriority(StrEnum):
    HIGH = auto()
    NORMAL = auto()
    LOW = auto()
```

### BackgroundTask

Represents a single task with status, priority, and result tracking:

```python
@dataclass
class BackgroundTask(Generic[T]):
    id: str
    name: str
    description: str
    initiated_by: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    result: T | None = None
    error: Exception | None = None
```

### TaskRegistry

Stores and tracks all tasks. Returns notifications ordered by priority:

```python
registry = TaskRegistry()

# Get highest-priority pending notification
notification = registry.get_next_priority_notification(agent_id="navigator")

# Get all running tasks
running = registry.get_running_tasks()
```

### TaskExecutor

Submits and manages task execution with priority support:

```python
executor = TaskExecutor(
    registry=registry,
    session=agent_session,
    on_task_completed=my_callback,
)

task = executor.submit(
    name="Topic Research",
    description="Researching quantum computing",
    coro=research_coro(),
    initiated_by="navigator",
    priority=TaskPriority.HIGH,
)
```

## Task Lifecycle

```
PENDING --> RUNNING --> COMPLETED
                   '--> FAILED
```

## Callback Integration

When a task completes, the callback uses `generate_reply()` to present results naturally:

```python
async def on_task_completed(task: BackgroundTask[Any]) -> None:
    match task.status:
        case TaskStatus.COMPLETED:
            session.generate_reply(
                instructions=f"Present these findings naturally: {task.result}"
            )
        case _:
            session.generate_reply(
                instructions="You couldn't find the information. Suggest alternatives."
            )
```

The LLM formulates a natural response. No hardcoded user-facing strings.

## Priority Ordering

Notifications are returned sorted by priority:
1. `HIGH` - Research results the user is actively waiting for
2. `NORMAL` - Standard background operations
3. `LOW` - Optional enrichment tasks

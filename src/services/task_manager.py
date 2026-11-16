"""In-memory async task manager for captcha solving tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from ..core.config import config

log = logging.getLogger(__name__)


class TaskQueueFullError(RuntimeError):
    """Raised when active tasks reach the configured queue limit."""


class TaskStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    type: str
    params: dict[str, Any]
    status: TaskStatus = TaskStatus.PROCESSING
    solution: dict[str, Any] | None = None
    error_code: str | None = None
    error_description: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class Solver(Protocol):
    async def solve(self, params: dict[str, Any]) -> dict[str, Any]: ...


class TaskManager:
    TASK_TTL = timedelta(minutes=10)

    def __init__(
        self,
        *,
        max_concurrent_tasks: int | None = None,
        max_queued_tasks: int | None = None,
    ) -> None:
        self._tasks: dict[str, Task] = {}
        self._solvers: dict[str, Solver] = {}
        self._max_concurrent = max_concurrent_tasks or config.max_concurrent_tasks
        self._max_queued = max_queued_tasks or config.max_queued_tasks
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    def register_solver(self, task_type: str, solver: Solver) -> None:
        self._solvers[task_type] = solver

    def create_task(self, task_type: str, params: dict[str, Any]) -> str:
        self._cleanup_expired()
        active_count = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.PROCESSING
        )
        if active_count >= self._max_queued:
            raise TaskQueueFullError("Task queue is full")
        task_id = str(uuid.uuid4())
        task = Task(id=task_id, type=task_type, params=params)
        self._tasks[task_id] = task
        asyncio.create_task(self._process_task(task))
        return task_id

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def supported_types(self) -> list[str]:
        return list(self._solvers.keys())

    async def _process_task(self, task: Task) -> None:
        solver = self._solvers.get(task.type)
        if not solver:
            task.status = TaskStatus.FAILED
            task.error_code = "ERROR_TASK_NOT_SUPPORTED"
            task.error_description = f"Task type '{task.type}' is not supported"
            return

        try:
            async with self._semaphore:
                solution = await solver.solve(task.params)
            task.solution = solution
            task.status = TaskStatus.READY
            log.info("Task %s completed successfully", task.id)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error_code = "ERROR_CAPTCHA_UNSOLVABLE"
            task.error_description = str(exc)
            log.error("Task %s failed: %s", task.id, exc)

    def _cleanup_expired(self) -> None:
        now = datetime.utcnow()
        expired = [
            tid
            for tid, t in self._tasks.items()
            if now - t.created_at > self.TASK_TTL
        ]
        for tid in expired:
            del self._tasks[tid]


task_manager = TaskManager()

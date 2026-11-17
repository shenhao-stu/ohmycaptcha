"""Bounded in-memory task manager for captcha solving tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from ..core.config import config

log = logging.getLogger(__name__)


class TaskStatus(StrEnum):
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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Solver(Protocol):
    async def solve(self, params: dict[str, Any]) -> dict[str, Any]: ...


class TaskManager:
    """Task registry with bounded concurrency, retained tasks and TTL cleanup."""

    TASK_TTL = timedelta(minutes=10)
    REAP_INTERVAL_SECONDS = 60

    def __init__(
        self,
        max_concurrency: int = 4,
        task_ttl: timedelta = TASK_TTL,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self._tasks: dict[str, Task] = {}
        self._solvers: dict[str, Solver] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._background_tasks: dict[str, asyncio.Task[None]] = {}
        self._task_ttl = task_ttl
        self._reaper_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background TTL reaper."""
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reap_loop())

    async def stop(self) -> None:
        """Cancel the reaper and any in-flight tasks."""
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            self._reaper_task = None
        for background in list(self._background_tasks.values()):
            background.cancel()
        self._background_tasks.clear()

    def register_solver(self, task_type: str, solver: Solver) -> None:
        self._solvers[task_type] = solver

    def create_task(self, task_type: str, params: dict[str, Any]) -> str:
        self._cleanup_expired()
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = Task(id=task_id, type=task_type, params=params)
        background = asyncio.create_task(self._process_task(self._tasks[task_id]))
        self._background_tasks[task_id] = background
        background.add_done_callback(lambda _: self._background_tasks.pop(task_id, None))
        return task_id

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def supported_types(self) -> list[str]:
        return list(self._solvers.keys())

    async def _process_task(self, task: Task) -> None:
        solver = self._solvers.get(task.type)
        if solver is None:
            task.status = TaskStatus.FAILED
            task.error_code = "ERROR_TASK_NOT_SUPPORTED"
            task.error_description = f"Task type '{task.type}' is not supported"
            return
        try:
            async with self._semaphore:
                solution = await solver.solve(task.params)
            task.solution = solution
            task.status = TaskStatus.READY
        except Exception as exc:  # noqa: BLE001 - solver failures are task results
            task.status = TaskStatus.FAILED
            task.error_code = "ERROR_CAPTCHA_UNSOLVABLE"
            task.error_description = str(exc)
            log.error("Task %s failed: %s", task.id, exc)

    def _cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [task_id for task_id, task in self._tasks.items() if now - task.created_at > self._task_ttl]
        for task_id in expired:
            self._tasks.pop(task_id, None)

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(self.REAP_INTERVAL_SECONDS)
            self._cleanup_expired()


task_manager = TaskManager(
    max_concurrency=config.max_concurrency,
    task_ttl=timedelta(minutes=config.task_ttl_minutes),
)

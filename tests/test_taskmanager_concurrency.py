"""Security tests for TaskManager concurrency and queue limits."""

from __future__ import annotations

import asyncio
import importlib

import pytest


class _SlowSolver:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def solve(self, params: dict[str, object]) -> dict[str, object]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            return {"text": "ok"}
        finally:
            self.active -= 1


@pytest.mark.anyio
async def test_task_manager_bounds_concurrency() -> None:
    """Concurrent solver executions must not exceed max_concurrent_tasks."""
    tm = importlib.import_module("src.services.task_manager")
    mgr = tm.TaskManager(max_concurrent_tasks=2, max_queued_tasks=10)
    solver = _SlowSolver()
    mgr.register_solver("ImageToTextTask", solver)

    for _ in range(5):
        mgr.create_task("ImageToTextTask", {"body": "x"})

    await asyncio.sleep(0.2)
    assert solver.max_active <= 2


@pytest.mark.anyio
async def test_task_manager_rejects_when_queue_full() -> None:
    """Creating tasks beyond max_queued_tasks must raise TaskQueueFullError."""
    tm = importlib.import_module("src.services.task_manager")
    mgr = tm.TaskManager(max_concurrent_tasks=1, max_queued_tasks=2)
    solver = _SlowSolver()
    mgr.register_solver("ImageToTextTask", solver)

    mgr.create_task("ImageToTextTask", {"body": "1"})
    mgr.create_task("ImageToTextTask", {"body": "2"})
    with pytest.raises(tm.TaskQueueFullError):
        mgr.create_task("ImageToTextTask", {"body": "3"})

    await asyncio.sleep(0.15)

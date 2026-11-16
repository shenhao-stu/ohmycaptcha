"""Security tests for sanitizing internal exceptions in TaskManager."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.services.task_manager import TaskManager, TaskStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_failed_task_sanitizes_internal_exception_details() -> None:
    """Internal URLs or credentials in solver exceptions must not leak to error_description."""
    mgr = TaskManager()
    failing_solver = AsyncMock()
    failing_solver.solve.side_effect = RuntimeError(
        "Connection failed to http://internal-sglang:30000/v1 with token sk-secret-123"
    )
    mgr.register_solver("ImageToTextTask", failing_solver)

    task_id = mgr.create_task("ImageToTextTask", {"body": "abc"})
    # Allow background task to finish
    import asyncio

    await asyncio.sleep(0)
    task = mgr.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert task.error_code == "ERROR_CAPTCHA_UNSOLVABLE"
    assert task.error_description == "Task solving failed"
    assert "internal-sglang" not in (task.error_description or "")
    assert "sk-secret" not in (task.error_description or "")

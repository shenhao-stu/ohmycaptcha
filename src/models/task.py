"""YesCaptcha / AntiCaptcha compatible API models."""

from __future__ import annotations

from pydantic import BaseModel


# ── createTask ──────────────────────────────────────────────

class TaskObject(BaseModel):
    type: str
    websiteURL: str | None = None
    websiteKey: str | None = None
    pageAction: str | None = None
    minScore: float | None = None
    isInvisible: bool | None = None
    # Image captcha / classification fields
    body: str | None = None
    image: str | None = None
    images: list[str] | None = None
    question: str | None = None
    queries: list[str] | str | None = None
    project_name: str | None = None


class CreateTaskRequest(BaseModel):
    clientKey: str
    task: TaskObject


class CreateTaskResponse(BaseModel):
    errorId: int = 0
    taskId: str | None = None
    errorCode: str | None = None
    errorDescription: str | None = None


# ── getTaskResult ───────────────────────────────────────────

class GetTaskResultRequest(BaseModel):
    clientKey: str
    taskId: str


class SolutionObject(BaseModel):
    gRecaptchaResponse: str | None = None
    text: str | None = None
    token: str | None = None
    objects: list[int] | None = None
    answer: bool | list[int] | None = None
    userAgent: str | None = None


class GetTaskResultResponse(BaseModel):
    errorId: int = 0
    status: str | None = None
    solution: SolutionObject | None = None
    errorCode: str | None = None
    errorDescription: str | None = None


# ── getBalance ──────────────────────────────────────────────

class GetBalanceRequest(BaseModel):
    clientKey: str


class GetBalanceResponse(BaseModel):
    errorId: int = 0
    balance: float = 99999.0
    errorCode: str | None = None
    errorDescription: str | None = None

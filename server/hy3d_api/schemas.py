from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


JobStatus = Literal["queued", "running", "candidate_ready_for_review", "failed", "accepted", "stl_exported"]


class HealthResponse(BaseModel):
    status: str
    service: str


class JobCreateResponse(BaseModel):
    job_id: str | None = None
    status: JobStatus
    error: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: str
    updated_at: str


class AcceptedResponse(BaseModel):
    job_id: str
    status: JobStatus
    accepted_model: str


class ExportStlResponse(BaseModel):
    job_id: str
    status: JobStatus
    stl: str


"""
FastAPI wrapper around the existing LangGraph Excel reverse-engineering
pipeline (src/agent.py), so a Teams bot (or any HTTP client) can submit an
.xlsx file and get back the generated markdown report plus a short summary
suitable for an Adaptive Card.

Run:
    uvicorn api.server:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.agent import build_graph

app = FastAPI(title="Excel Business Logic Reverse Engineering API")


class WorkbookSummary(BaseModel):
    filename: str
    sheets: list[str]
    cell_count: int
    authors: list[str]


class AnalyzeResponse(BaseModel):
    report_markdown: str
    summary: WorkbookSummary


class JobStatus(BaseModel):
    job_id: str
    status: Literal["running", "done", "error"]
    result: AnalyzeResponse | None = None
    error: str | None = None


# In-memory job store. The pipeline can take several minutes (multiple
# sequential LLM calls per sheet), which exceeds Azure Container Apps'
# hard-coded 240s ingress request timeout. So /analyze kicks off the work in
# a background thread and returns immediately with a job_id; the caller
# polls /analyze/{job_id} (a fast, cheap call) until it's done. Fine for a
# single-replica demo deployment; swap for Redis/a DB before scaling out.
_jobs: dict[str, JobStatus] = {}
_JOB_TTL_SECONDS = 30 * 60
_job_created_at: dict[str, float] = {}


def _prune_old_jobs() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    for job_id, created in list(_job_created_at.items()):
        if created < cutoff:
            _job_created_at.pop(job_id, None)
            _jobs.pop(job_id, None)


def _run_analysis(job_id: str, tmp_dir: str, filename: str) -> None:
    try:
        tmp_path = Path(tmp_dir) / filename
        graph = build_graph()
        result = graph.invoke({"path": str(tmp_path)})
        model = result["model"]
        summary = WorkbookSummary(
            filename=filename,
            sheets=model.sheets,
            cell_count=len(model.cells),
            authors=model.authors,
        )
        _jobs[job_id] = JobStatus(
            job_id=job_id,
            status="done",
            result=AnalyzeResponse(report_markdown=result["final_report"], summary=summary),
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        _jobs[job_id] = JobStatus(job_id=job_id, status="error", error=str(exc))
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", status_code=202)
async def analyze(file: UploadFile = File(...)) -> JobStatus:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload a .xlsx or .xlsm workbook.")

    _prune_old_jobs()

    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / file.filename
    tmp_path.write_bytes(await file.read())

    job_id = str(uuid.uuid4())
    job = JobStatus(job_id=job_id, status="running")
    _jobs[job_id] = job
    _job_created_at[job_id] = time.time()

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_analysis, job_id, tmp_dir, file.filename)

    return job


@app.get("/analyze/{job_id}", response_model=JobStatus)
async def analyze_status(job_id: str) -> JobStatus:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id.")
    return job

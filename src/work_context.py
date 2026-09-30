"""
work_context.py - Local collaboration signals inspired by Work IQ
--------------------------------------------
Lightweight "who works on this and how" signal, built entirely from local
artifacts (no M365 Graph access needed for the MVP):
  - workbook author / last-modified-by (from OOXML core properties)
  - inline cell comments (subject-matter-expert annotations)
  - optional git log if the workbook lives in a git repo

This approximates a small part of the collaboration-context role using
local artifacts. It does not implement Work IQ or Microsoft 365 permissions.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .excel_parser import WorkbookModel


@dataclass
class WorkContext:
    authors: List[str] = field(default_factory=list)
    annotated_cells: List[dict] = field(default_factory=list)  # {node_id, comment}
    git_history: List[str] = field(default_factory=list)


def build_work_context(model: WorkbookModel) -> WorkContext:
    ctx = WorkContext(authors=list(model.authors))
    for node_id, cell in model.cells.items():
        if cell.comment:
            ctx.annotated_cells.append({"node_id": node_id, "comment": cell.comment})

    path = Path(model.path)
    try:
        log = subprocess.run(
            ["git", "log", "--follow", "--pretty=%an|%ad|%s", "--date=short", "--", str(path)],
            cwd=path.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if log.returncode == 0 and log.stdout.strip():
            ctx.git_history = log.stdout.strip().splitlines()
    except Exception:
        pass  # not a git repo, git not installed, etc. — non-fatal for MVP

    return ctx


def summarize(ctx: WorkContext) -> str:
    lines = []
    if ctx.authors:
        lines.append(f"Authors: {', '.join(ctx.authors)}")
    if ctx.annotated_cells:
        lines.append(f"SME annotations found on {len(ctx.annotated_cells)} cell(s):")
        for a in ctx.annotated_cells[:10]:
            lines.append(f"  - {a['node_id']}: {a['comment']}")
    if ctx.git_history:
        lines.append(f"Git history ({len(ctx.git_history)} commits, showing last 5):")
        for entry in ctx.git_history[:5]:
            lines.append(f"  - {entry}")
    return "\n".join(lines) if lines else "No collaboration context available."

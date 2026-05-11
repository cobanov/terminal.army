"""Shared Jinja2 templates instance + utility filters used across web routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _fmt_int(v: float | int) -> str:
    n = int(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,}"


def _local_hhmmss(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%H:%M:%S")


def _remaining_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (dt - datetime.now(timezone.utc)).total_seconds()
    if delta < 0:
        return "done"
    s = int(delta)
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m{sec:02d}s"
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


# Expose helpers as Jinja globals so templates can call fmt_int / local_hhmmss / remaining_str
templates.env.globals.update(
    fmt_int=_fmt_int,
    local_hhmmss=_local_hhmmss,
    remaining_str=_remaining_str,
)

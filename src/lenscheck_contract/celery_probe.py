"""Discover Celery background jobs at runtime.

Celery keeps a live registry of every task and (optionally) a beat schedule — so, like the web
frameworks, we ask Celery instead of parsing files. A task that starts calling Stripe, or a new
nightly job, then shows up in the diff the same way a route change does.

We use the app you pass, or Celery's `current_app` (the last app created, which is what importing
your tasks module sets). Celery's own internal tasks (`celery.*`) are skipped. Never raises.
RQ / FastAPI BackgroundTasks are enqueued dynamically with no static registry, so they're out of scope.
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Job
from .registry import handler_name, registry


def probe_jobs(contract: Contract, app: Any = None) -> None:
    """Add every registered Celery task as a Job, with its beat schedule and declared effects."""
    app = app if app is not None else _current_app()
    if app is None:
        return

    schedules = _beat_by_task(app)
    for name, task in list(getattr(app, "tasks", {}).items()):
        if name.startswith("celery."):
            continue  # Celery's own plumbing (backend_cleanup, chord, group, …), not the app's jobs
        run = getattr(task, "run", None) or task
        handler = handler_name(run)
        contract.jobs[name] = Job(
            name=name,
            handler=handler,
            schedule=schedules.get(name),
            effects=sorted(registry.declared_effects(handler)),
            source="runtime",
        )


def _current_app() -> Any:
    try:
        from celery import current_app
    except Exception:  # noqa: BLE001 - Celery not installed
        return None
    # current_app always returns *something*; only treat it as real if a non-internal task exists.
    tasks = getattr(current_app, "tasks", {}) or {}
    if any(not n.startswith("celery.") for n in tasks):
        return current_app
    return None


def _beat_by_task(app: Any) -> dict[str, str]:
    """{task_name: human schedule} from app.conf.beat_schedule."""
    out: dict[str, str] = {}
    schedule = getattr(getattr(app, "conf", None), "beat_schedule", None) or {}
    for entry in schedule.values():
        if isinstance(entry, dict):
            task, sched = entry.get("task"), entry.get("schedule")
        else:
            task, sched = getattr(entry, "task", None), getattr(entry, "schedule", None)
        if task:
            out[task] = _schedule_str(sched)
    return out


def _schedule_str(sched: Any) -> str | None:
    from datetime import timedelta

    if sched is None:
        return None
    if isinstance(sched, bool):          # guard: bool is an int subclass
        return str(sched)
    if isinstance(sched, (int, float)):
        return f"every {sched:g}s"
    if isinstance(sched, timedelta):
        return f"every {sched.total_seconds():g}s"
    # crontab: build a stable "m h dom mon dow" from the original field strings if available
    fields = [getattr(sched, f"_orig_{p}", None) for p in
              ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")]
    if all(f is not None for f in fields):
        return "cron(" + " ".join(str(f) for f in fields) + ")"
    return str(sched)

"""Celery background-job discovery: tasks, beat schedule, effect merge, and diffs."""

import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402
from celery.schedules import crontab  # noqa: E402

from lenscheck_contract import Contract, build, contract, diff  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    from lenscheck_contract.registry import registry

    saved = (dict(registry.routes), dict(registry.jobs),
             {k: list(v) for k, v in registry._declared.items()})
    registry.reset()
    yield
    registry.routes.clear(); registry.routes.update(saved[0])
    registry.jobs.clear(); registry.jobs.update(saved[1])
    registry._declared.clear(); registry._declared.update(saved[2])
    # Celery's first app becomes the process-wide default that current_app falls back to.
    # Drop our throwaway tasks so auto-discovery in *other* tests' build() stays clean.
    from celery import current_app
    for name in [n for n in list(current_app.tasks) if not n.startswith("celery.")]:
        current_app.tasks.pop(name, None)


def _app():
    app = Celery("demo")
    app.conf.beat_schedule = {
        "nightly": {"task": "billing.make_invoices", "schedule": crontab(hour=2, minute=0)},
        "ping": {"task": "demo.ping", "schedule": 30.0},
    }

    @app.task(name="billing.make_invoices")
    @contract.effects("net:api.stripe.com")
    def make_invoices():
        pass

    @app.task(name="demo.ping")
    def ping():
        pass

    return app


def test_tasks_become_jobs():
    c = build(include_django=False, celery_app=_app())
    assert "billing.make_invoices" in c.jobs
    assert "demo.ping" in c.jobs


def test_internal_celery_tasks_are_skipped():
    c = build(include_django=False, celery_app=_app())
    assert not any(name.startswith("celery.") for name in c.jobs)


def test_beat_schedule_is_captured():
    c = build(include_django=False, celery_app=_app())
    assert c.jobs["billing.make_invoices"].schedule == "cron(0 2 * * *)"
    assert c.jobs["demo.ping"].schedule == "every 30s"


def test_declared_effects_merge_onto_a_task():
    c = build(include_django=False, celery_app=_app())
    assert c.jobs["billing.make_invoices"].effects == ["net:api.stripe.com"]
    assert c.jobs["demo.ping"].effects == []


def test_a_new_job_is_a_diff():
    base = build(include_django=False, celery_app=_app())
    head = Contract.from_dict(base.to_dict())
    del head.jobs["demo.ping"]                      # base has a job head lacks → job_removed
    changes = diff(head, base)
    added = [c for c in changes if c.kind == "job_added" and c.subject == "demo.ping"]
    assert added


def test_auto_discovery_off_when_no_celery_app_used():
    # With no user tasks registered (fixture cleans up), current_app auto-probe finds nothing.
    c = build(include_django=False)
    assert c.jobs == {}

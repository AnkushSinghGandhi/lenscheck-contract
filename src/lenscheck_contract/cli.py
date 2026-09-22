"""lenscheck-contract command line."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

from . import build
from .diff import RISKY, REVIEW, diff, render_markdown, render_text, worst
from .models import Contract


def _setup_django(settings: str | None) -> None:
    if settings:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        return
    import django

    django.setup()


def _load_app(spec: str) -> Any:
    """'package.module:app' -> the app object. Bare 'package.module' assumes attr `app`.
    If the attr is an app factory (create_app), it's called."""
    module_name, _, attr = spec.partition(":")
    attr = attr or "app"
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    if _framework_of(obj) is None and callable(obj):
        obj = obj()          # a factory like create_app()
    return obj


def _framework_of(app: Any) -> str | None:
    names = {cls.__name__ for cls in type(app).__mro__}
    if "FastAPI" in names:
        return "fastapi"
    if "Flask" in names:
        return "flask"
    return None


def _load_obj(spec: str) -> Any:
    """'package.module:attr' -> that object, no factory-calling (for a Celery app instance)."""
    module_name, _, attr = spec.partition(":")
    return getattr(importlib.import_module(module_name), attr or "app")


def _build_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    """Turn CLI flags into build() keyword args, loading a Flask/FastAPI/Celery app if given."""
    kwargs: dict[str, Any] = {
        "include_django": not args.no_django,
        "include_celery": not getattr(args, "no_celery", False),
    }
    spec = getattr(args, "app", None)
    if spec:
        app = _load_app(spec)
        framework = _framework_of(app)
        if framework == "fastapi":
            kwargs["fastapi_app"] = app
        elif framework == "flask":
            kwargs["flask_app"] = app
        else:
            raise SystemExit(
                f"--app {spec!r}: expected a Flask or FastAPI app, got {type(app).__name__}"
            )
    celery_spec = getattr(args, "celery", None)
    if celery_spec:
        kwargs["celery_app"] = _load_obj(celery_spec)
    return kwargs


def cmd_export(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(args.root).resolve()))
    _setup_django(args.settings)
    for mod in args.import_module or []:
        importlib.import_module(mod)

    data = build(**_build_kwargs(args)).to_dict()
    text = json.dumps(data, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        cov = data["coverage"]
        print(
            f"wrote {args.output}: {len(data['routes'])} routes, "
            f"{len(data['models'])} models, {len(data['jobs'])} jobs, "
            f"auth known on {cov['routes_with_auth']}/{cov['routes_total']}",
            file=sys.stderr,
        )
        if cov["unresolved"]:
            print(f"unresolved: {len(cov['unresolved'])}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    base = Contract.from_dict(json.loads(Path(args.base).read_text(encoding="utf-8")))
    head = Contract.from_dict(json.loads(Path(args.head).read_text(encoding="utf-8")))
    changes = diff(base, head)

    print(render_markdown(changes) if args.markdown else render_text(changes))

    if not changes:
        return 0
    level = worst(changes)
    if args.fail_on == "risky" and level == RISKY:
        return 1
    if args.fail_on == "review" and level in (RISKY, REVIEW):
        return 1
    if args.fail_on == "any":
        return 1
    return 0


def cmd_invariants(args: argparse.Namespace) -> int:
    """Emit a confirmed-invariant corpus for lenscheck-semantic-reviewer --invariants."""
    sys.path.insert(0, str(Path(args.root).resolve()))
    _setup_django(args.settings)
    for mod in args.import_module or []:
        importlib.import_module(mod)

    from .invariants import to_invariant_corpus

    corpus = to_invariant_corpus(build(**_build_kwargs(args)))
    text = json.dumps(corpus, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        dests = corpus[0]["observed"]["destinations"]
        print(
            f"wrote {args.output}: {len(corpus)} confirmed invariants, "
            f"{len(dests)} egress destination(s)",
            file=sys.stderr,
        )
    else:
        print(text)
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    """Print declarations discovered by a recorded run (e.g. your test suite)."""
    data = json.loads(Path(args.observed).read_text(encoding="utf-8"))
    for handler, effects in sorted(data.items()):
        joined = ", ".join(repr(e) for e in effects)
        print(f"# {handler}")
        print(f"@contract.effects({joined})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lenscheck-contract", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="write the contract as JSON")
    e.add_argument("-o", "--output")
    e.add_argument("--settings", help="DJANGO_SETTINGS_MODULE")
    e.add_argument("--app", help="Flask/FastAPI app to probe, e.g. myapp.main:app")
    e.add_argument("--celery", help="Celery app to probe for jobs, e.g. myapp.celery:app")
    e.add_argument("--root", default=".", help="project root to put on sys.path")
    e.add_argument("--import-module", action="append", help="extra modules to import")
    e.add_argument("--no-django", action="store_true")
    e.add_argument("--no-celery", action="store_true", help="skip Celery job discovery")
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("diff", help="compare two contract files")
    d.add_argument("base")
    d.add_argument("head")
    d.add_argument("--markdown", action="store_true", help="format for a PR comment")
    d.add_argument("--fail-on", choices=["never", "risky", "review", "any"], default="never")
    d.set_defaults(func=cmd_diff)

    inv = sub.add_parser(
        "invariants", help="emit a confirmed-invariant corpus for the reviewer's --invariants"
    )
    inv.add_argument("-o", "--output")
    inv.add_argument("--settings", help="DJANGO_SETTINGS_MODULE")
    inv.add_argument("--app", help="Flask/FastAPI app to probe, e.g. myapp.main:app")
    inv.add_argument("--celery", help="Celery app to probe for jobs, e.g. myapp.celery:app")
    inv.add_argument("--root", default=".", help="project root to put on sys.path")
    inv.add_argument("--import-module", action="append", help="extra modules to import")
    inv.add_argument("--no-django", action="store_true")
    inv.add_argument("--no-celery", action="store_true", help="skip Celery job discovery")
    inv.set_defaults(func=cmd_invariants)

    s = sub.add_parser("suggest", help="turn a recorded run into declarations")
    s.add_argument("observed", help="JSON from guard.suggestions()")
    s.set_defaults(func=cmd_suggest)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

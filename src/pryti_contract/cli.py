"""pryti-contract command line."""

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


def cmd_export(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(args.root).resolve()))
    _setup_django(args.settings)
    for mod in args.import_module or []:
        importlib.import_module(mod)

    data = build(include_django=not args.no_django).to_dict()
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


def cmd_suggest(args: argparse.Namespace) -> int:
    """Print declarations discovered by a recorded run (e.g. your test suite)."""
    data = json.loads(Path(args.observed).read_text(encoding="utf-8"))
    for handler, effects in sorted(data.items()):
        joined = ", ".join(repr(e) for e in effects)
        print(f"# {handler}")
        print(f"@contract.effects({joined})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pryti-contract", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="write the contract as JSON")
    e.add_argument("-o", "--output")
    e.add_argument("--settings", help="DJANGO_SETTINGS_MODULE")
    e.add_argument("--root", default=".", help="project root to put on sys.path")
    e.add_argument("--import-module", action="append", help="extra modules to import")
    e.add_argument("--no-django", action="store_true")
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("diff", help="compare two contract files")
    d.add_argument("base")
    d.add_argument("head")
    d.add_argument("--markdown", action="store_true", help="format for a PR comment")
    d.add_argument("--fail-on", choices=["never", "risky", "review", "any"], default="never")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("suggest", help="turn a recorded run into declarations")
    s.add_argument("observed", help="JSON from guard.suggestions()")
    s.set_defaults(func=cmd_suggest)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

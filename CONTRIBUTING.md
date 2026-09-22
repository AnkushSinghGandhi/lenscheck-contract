# Contributing to lenscheck-contract

This library is **MIT-licensed**, so contributing is easy: **pull requests are welcome, no agreement
needed.** It's the free wedge of the Lenscheck project and the best place to write code.

## 🐛 Report a bug — and get featured

[Open an issue](https://github.com/AnkushSinghGandhi/lenscheck-contract/issues/new) with a clear repro
and the command you ran. Everyone who files a valid bug report or actionable idea gets their
**name + GitHub on the Wall of Fame** at [lenscheck.dev](https://lenscheck.dev); merged fixes earn
**stickers**. 🎉

## 💻 Good first contributions

The core (registry, models, diff, guard) is framework-agnostic — most value is in the **probes** that
read a framework's runtime state:

- **New framework probes** — e.g. a Starlette/Litestar/Sanic route probe, mirroring `flask_probe.py`
  / `fastapi_probe.py`.
- **More ORMs** — a Tortoise ORM model probe alongside `sqla_probe.py`.
- **Deeper auth detection** — recognise more Flask/FastAPI auth patterns.
- **Examples & docs** — a money-shot for another framework under `examples/`.

## Development

```bash
pip install -e ".[dev]"                 # flask, fastapi, sqlalchemy, celery, django, pytest
PYTHONPATH=src pytest                    # run the suite
```

Match the surrounding style, keep probes best-effort (never raise — a broken probe must not hide the
rest), and add a test for anything that changes behaviour. Keep the package **dependency-free** at
runtime (frameworks stay optional extras).

> One rule that protects the project: **never add SARIF, org roll-up, or digest features here** — those
> belong to the paid reviewer, not this MIT wedge.

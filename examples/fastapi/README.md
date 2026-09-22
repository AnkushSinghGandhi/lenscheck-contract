# 3 bad things, 0 get through (FastAPI)

One AI-written PR — *"add order analytics"* — sneaks in three dangerous changes.
`lenscheck-contract` catches all three: two structurally in CI, one at runtime.

## The PR

| # | Change | Why it's bad | Caught by |
|---|--------|--------------|-----------|
| 1 | `POST /orders` loses `Depends(current_user)` → auth `user` → `public` | anyone can place orders | **diff** (CI) |
| 2 | `Customer.email` deleted from the Pydantic body | silent data loss | **diff** (CI) |
| 3 | `await …getaddrinfo("analytics.tracksy.io")` | never declared — data exfil | **guard** (runtime) |

The diff reads FastAPI's real dependency tree (#1) and its Pydantic request models (#2).
It **can't** see #3 — an undeclared call is invisible to any static tool. That's the guard's job:
it runs the code and stops the call the instant it tries to leave. Note #3 is an **async** call on
the event loop (the `httpx.AsyncClient` / `aiohttp` path) — the guard hooks that too.

## Run it

```bash
pip install -e ".[dev]"      # from the repo root
bash examples/fastapi/run.sh
```

`before/app.py` is the good app; `after/app.py` is the same app with the three changes. Same module
name in both, so the diff is exactly the two real changes — no handler-rename noise, just like
comparing one file across two git revisions in CI.

## In your CI

```yaml
- run: lenscheck-contract export --no-django --app myapp.main:app -o head.json
- run: git checkout ${{ github.base_ref }}
- run: lenscheck-contract export --no-django --app myapp.main:app -o base.json
- run: lenscheck-contract diff base.json head.json --markdown --fail-on risky
```

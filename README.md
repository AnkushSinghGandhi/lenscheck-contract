# lenscheck-contract

Your backend keeps a list of what it does. And it can't lie about it.

Companion library to [lenscheck-semantic-reviewer](https://github.com/AnkushSinghGandhi/lenscheck-semantic-reviewer).
Lenscheck reads code from outside and guesses. This runs inside your app and knows.

Works with **Django**, **Flask**, and **FastAPI** — it reads whichever framework's own runtime
state, so routers, blueprints, loops, and dependency trees are all seen exactly as the app resolved
them. Models come from Django or SQLAlchemy.

## What it does

While your app starts, it records:

- every **route** (path, method, auth)
- every **model** (fields, types, constraints)
- every **outside call** (HTTP, email, payments)
- every **background job**
- how much of that it actually **knows** vs. couldn't figure out

Then you can ask your app one question and get an answer:

> "What does this app actually do?"

## Why it matters

AI opens a PR with 400 changed lines. You don't read them. You read this:

```
RISKY (4)
  POST /orders         auth: user -> public
  POST /orders         new effect: net:analytics.example.com
  shop.Customer.email  unique: True -> False
  shop.Customer.name   field removed (data loss)
```

Four lines instead of four hundred.

## Install

```bash
pip install lenscheck-contract
```

## Use it — three levels

### Level 1: nothing to write

Works on an existing project with zero code changes. Point it at your app:

```bash
# Django — reads DJANGO_SETTINGS_MODULE, the URLconf, and the model registry
lenscheck-contract export --settings myproject.settings -o contract.json

# Flask / FastAPI — point at the app object (module:attr, or a create_app factory)
lenscheck-contract export --no-django --app myapp.main:app -o contract.json
lenscheck-contract export --no-django --app "myapp:create_app" -o contract.json
```

Celery jobs are found automatically when Celery is installed and your tasks are imported; point at
a specific app with `--celery myapp.celery:app`, or skip discovery with `--no-celery`.

It reads the framework's real router — routes built in loops, DRF routers, mixins, blueprints,
and FastAPI dependency trees are all found, because the app already resolved them at startup.
Auth is read from Django permissions/mixins/`login_required`, Flask auth decorators
(`flask_login`, `flask_jwt_extended`, …), and FastAPI security schemes and `Depends(...)`.
Models come from Django's registry, your **SQLAlchemy** mapped classes (Flask/FastAPI), and
**Pydantic** request/response schemas (FastAPI) — so a field going optional or disappearing from an
API body shows up in the diff. **Celery** background jobs (tasks + beat schedules) are discovered too,
so a new nightly job — or a task that starts calling Stripe — is caught the same way a route change is.

Coverage will be partial. That's reported, not hidden:

```
wrote contract.json: 9 routes, 6 models, 0 jobs, auth known on 5/9
```

### Level 2: declare what matters

```python
from lenscheck_contract import contract

@contract.route("POST /orders", auth="user")
@contract.effects("net:api.stripe.com")
def create_order(request):
    ...
```

Eight decorators total, max. AI writes these correctly first try, because
they look like every Django decorator it has ever seen.

### Level 3: enforce it

Install the request hook for your framework (so *every* view is watched, not just decorated ones),
then turn the guard on:

```python
# Django — settings.py
MIDDLEWARE = ["lenscheck_contract.middleware.ContractMiddleware", ...]

# Flask
from lenscheck_contract import install_flask
install_flask(app)

# FastAPI
from lenscheck_contract import install_fastapi
install_fastapi(app)

# then, anywhere at startup (conftest.py, apps.py, main.py):
from lenscheck_contract import guard
guard.install(mode="error")   # off | record | warn | error
```

Now an undeclared call fails loudly:

```
shop.views.leaky_order performed undeclared effect 'net:api.stripe.com'.
Declared: none. Add @contract.effects('net:api.stripe.com') or remove the call.
```

This is the part no linter can do. The bad code doesn't ship.

**Don't know what to declare?** Run your tests in `record` mode and let it tell you:

```python
guard.install(mode="record")
# ... run test suite ...
json.dump(guard.suggestions(), open("observed.json", "w"))
```

```bash
lenscheck-contract suggest observed.json     # prints the decorators to paste in
```

## In CI

```yaml
- run: lenscheck-contract export --settings myproject.settings -o head.json
- run: git checkout ${{ github.base_ref }}
- run: lenscheck-contract export --settings myproject.settings -o base.json
- run: lenscheck-contract diff base.json head.json --markdown --fail-on risky
```

`--fail-on risky` exits 1 on auth weakening, new outside calls, dropped fields,
relaxed uniqueness, or changed relations.

## How the effect guard works

One hook at the socket layer, not per-library. `requests`, `httpx`, `urllib`,
`boto3`, `stripe` — all covered by the same code, including libraries that
don't exist yet.

- `socket.getaddrinfo` is checked **before** it runs, so a blocked call never leaves the process
- `socket.socket.connect` catches direct-IP connections
- the event loop's `getaddrinfo` is hooked too, so **async** clients (`httpx.AsyncClient`, `aiohttp`)
  are caught in the endpoint's own context — not lost in a resolver thread
- `smtplib.SMTP.sendmail` catches email
- localhost and unix sockets are never effects, so your database doesn't trip it

> Async caveat: **uvloop** and **aiodns** resolve outside Python's `socket` module entirely, so the
> guard can't see those. Standard `asyncio` (the uvicorn default) is covered.

Patterns support wildcards: `net:*.stripe.com`, `net:*`, `email`.

## What it does not catch

Worth being blunt about.

- **Business logic.** If AI changes a discount from 10% to 90%, the contract is
  identical. Routes same, models same, effects same. Tests catch that; this doesn't.
- **Anything the router never sees.** Dead code, unmounted views.
- **Dynamic hostnames** are caught at runtime, not at export time. The contract
  records what you declared; the guard records what actually happened.

Structural mistakes: this. Logic mistakes: your tests. You need both.

## Try it

```bash
git clone ... && cd lenscheck-contract
pip install -e ".[dev]"
pytest
cd examples/demo && lenscheck-contract export --settings settings --root . -o /tmp/base.json
```

### The money shot — one bad PR, all three frameworks

Each runs the same *"add order analytics"* PR that sneaks in three dangerous changes, and shows
`lenscheck-contract` catching all three (two in CI, one at runtime):

```bash
bash examples/three_bad_things/run.sh   # Django
bash examples/flask/run.sh              # Flask   (routes + SQLAlchemy models)
bash examples/fastapi/run.sh            # FastAPI (dependency auth + Pydantic models + async guard)
```

MIT.

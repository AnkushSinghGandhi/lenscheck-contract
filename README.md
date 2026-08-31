# pryti-contract

Your backend keeps a list of what it does. And it can't lie about it.

Companion library to [pryti-semantic-reviewer](https://github.com/AnkushSinghGandhi/pryti-semantic-reviewer).
Pryti reads code from outside and guesses. This runs inside your app and knows.

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
pip install pryti-contract
```

## Use it — three levels

### Level 1: nothing to write

Works on an existing Django project with zero code changes.

```bash
pryti-contract export --settings myproject.settings -o contract.json
```

It reads Django's real router and real model registry. Routes built in loops,
DRF routers, mixins — all found, because the app already resolved them at startup.

Coverage will be partial. That's reported, not hidden:

```
wrote contract.json: 9 routes, 6 models, 0 jobs, auth known on 5/9
```

### Level 2: declare what matters

```python
from pryti_contract import contract

@contract.route("POST /orders", auth="user")
@contract.effects("net:api.stripe.com")
def create_order(request):
    ...
```

Eight decorators total, max. AI writes these correctly first try, because
they look like every Django decorator it has ever seen.

### Level 3: enforce it

```python
# settings.py
MIDDLEWARE = ["pryti_contract.middleware.ContractMiddleware", ...]

# conftest.py or apps.py
from pryti_contract import guard
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
pryti-contract suggest observed.json     # prints the decorators to paste in
```

## In CI

```yaml
- run: pryti-contract export --settings myproject.settings -o head.json
- run: git checkout ${{ github.base_ref }}
- run: pryti-contract export --settings myproject.settings -o base.json
- run: pryti-contract diff base.json head.json --markdown --fail-on risky
```

`--fail-on risky` exits 1 on auth weakening, new outside calls, dropped fields,
relaxed uniqueness, or changed relations.

## How the effect guard works

One hook at the socket layer, not per-library. `requests`, `httpx`, `urllib`,
`boto3`, `stripe` — all covered by the same code, including libraries that
don't exist yet.

- `socket.getaddrinfo` is checked **before** it runs, so a blocked call never leaves the process
- `socket.socket.connect` catches direct-IP connections
- `smtplib.SMTP.sendmail` catches email
- localhost and unix sockets are never effects, so your database doesn't trip it

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
git clone ... && cd pryti-contract
pip install -e ".[dev]"
pytest
cd examples/demo && pryti-contract export --settings settings --root . -o /tmp/base.json
```

MIT.

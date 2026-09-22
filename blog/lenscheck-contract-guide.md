# Your Django Backend Can't Lie About What It Does

*An AI opens a pull request with 400 changed lines. You're not going to read them. **lenscheck-contract**
makes your app keep a short, honest list of what it actually does — every route, model, and outside
call — and then refuses to let a PR quietly change it. Two of the three dangerous changes are caught
in CI; the third is caught **at runtime**, the instant it tries to leave the process. MIT-licensed,
one `pip install`.*

**`MIT`  ·  `Zero third-party deps`  ·  `One socket hook — every HTTP library`  ·  `Caught in CI and at runtime`**

---

## Quickstart (60 seconds)

**See what your app actually does — zero code:**

```bash
pip install lenscheck-contract
lenscheck-contract export --settings myproject.settings -o contract.json
```

**Block a bad change in CI** — diff the contract across a PR:

```bash
lenscheck-contract diff base.json head.json --markdown --fail-on risky
```

**Stop it at runtime** — one middleware + one line:

```python
from lenscheck_contract import guard
guard.install(mode="error")   # an undeclared DB write or network call now fails loudly
```

That's it: your backend keeps a list of what it does, and **can't lie about it.** Everything below is
depth for when you want it.

---

## The problem: you can't review what you can't see

A diff shows you *text*. It does not show you that this PR just made `POST /orders` public, deleted a
customer field, and added a call to some analytics host you've never heard of. Those three lines are
buried in four hundred boring ones, and the reviewer skims.

So don't read four hundred lines. Read four:

```
RISKY (4)
  POST /orders         auth: user -> public
  POST /orders         new effect: net:analytics.example.com
  shop.Customer.email  unique: True -> False
  shop.Customer.name   field removed (data loss)
```

That's the whole idea.

---

## The one idea: the app records what it does — and can't lie about it

`lenscheck-semantic-reviewer` reads your code *from the outside* and infers. **lenscheck-contract runs
*inside* your app and simply knows** — because Django already resolved everything at startup. While
the app boots, the contract records:

- every **route** (path, method, auth)
- every **model** (fields, types, constraints)
- every **outside call** (HTTP, email, payments)
- every **background job**
- and, honestly, how much of that it **couldn't** figure out

Then you can ask your running app one question — *"what do you actually do?"* — and diff the answer
across a PR. What changed structurally shows up as a handful of lines. What tries to sneak past
structurally gets caught when it runs.

---

## Three bad things in. Zero shipped.

Here's a real AI-written PR — *"add order analytics", +4 −2, looks harmless.* It hides three dangerous
changes. lenscheck-contract catches **all three** — two in CI, one at runtime:

![Three bad things caught — two in CI, one at runtime](https://github.com/AnkushSinghGandhi/lenscheck-contract/blob/main/blog/images/01-three-bad-things.png?raw=true)

- **#1 — auth downgrade.** `POST /orders` went from `user` to `public`. Anyone can now place an order.
  Caught **structurally**, in CI.
- **#2 — silent data loss.** `Customer.name` was removed. No error, just gone. Caught **structurally**,
  in CI.
- **#3 — data exfiltration.** A call to `analytics.tracksy.io` was added — and **never declared**. No
  diff and no linter can see an effect that isn't in the code's declarations. So the contract runs the
  code and stops the packet **at the socket layer, before it ever leaves the process.**

Structural mistakes: caught before merge. Runtime mistakes: caught before they do damage.

---

## Adopt it in three levels

### Level 1 — nothing to write

It works on an existing Django project with **zero code changes**. It reads Django's real router and
model registry, so routes built in loops, DRF routers, and mixins are all found:

![Zero-code export — reads Django's real router and models](https://github.com/AnkushSinghGandhi/lenscheck-contract/blob/main/blog/images/02-export.png?raw=true)

```bash
pip install lenscheck-contract
lenscheck-contract export --settings myproject.settings -o contract.json
```

Coverage is partial, and — like the whole toolchain — it *says so* (`auth known on 5/9`) instead of
faking an all-clear.

### Level 2 — declare what matters

Add a decorator to the handlers you care about. There are only eight, and they look like every Django
decorator an AI has ever seen (so AI writes them correctly on the first try):

```python
from lenscheck_contract import contract

@contract.route("POST /orders", auth="user")
@contract.effects("net:api.stripe.com")
def create_order(request):
    ...
```

Don't know what to declare? Run your tests in `record` mode and let the app tell you, then
`lenscheck-contract suggest` prints the decorators to paste in.

### Level 3 — enforce it

```python
# settings.py
MIDDLEWARE = ["lenscheck_contract.middleware.ContractMiddleware", ...]

# apps.py / conftest.py
from lenscheck_contract import guard
guard.install(mode="error")   # off | record | warn | error
```

Now an **undeclared** call fails loudly — this is the part no linter can do:

![The runtime guard blocks an undeclared call before it leaves the process](https://github.com/AnkushSinghGandhi/lenscheck-contract/blob/main/blog/images/03-guard-block.png?raw=true)

The bad code doesn't ship. It doesn't even finish the request.

---

## In CI

Export the contract on both sides of a PR and diff them — `--fail-on risky` exits non-zero on an auth
downgrade, a new outside call, a dropped field, relaxed uniqueness, or a changed relation:

```yaml
- run: lenscheck-contract export --settings myproject.settings -o head.json
- run: git checkout ${{ github.base_ref }}
- run: lenscheck-contract export --settings myproject.settings -o base.json
- run: lenscheck-contract diff base.json head.json --markdown --fail-on risky
```

On the PR, the reviewer sees the short list and a blocked merge — not four hundred lines:

![The contract diff as a PR comment — merge blocked](https://github.com/AnkushSinghGandhi/lenscheck-contract/blob/main/blog/images/04-pr-comment.png?raw=true)

---

## How the guard works (and why it covers libraries that don't exist yet)

One hook at the **socket layer**, not per-library. `requests`, `httpx`, `urllib`, `boto3`, `stripe` —
all covered by the same code:

- `socket.getaddrinfo` is checked **before** it runs, so a blocked call never leaves the process
- `socket.socket.connect` catches direct-IP connections
- `smtplib.SMTP.sendmail` catches email
- localhost and unix sockets are never effects — your database never trips it

Patterns support wildcards: `net:*.stripe.com`, `net:*`, `email`.

---

## What it does *not* catch (worth being blunt)

- **Business logic.** If AI changes a discount from 10% to 90%, the contract is identical — routes,
  models, and effects are all the same. **Your tests catch that; this doesn't.**
- **Anything the router never sees** — dead code, unmounted views.
- **Dynamic hostnames** are caught at *runtime*, not at export time. The contract records what you
  *declared*; the guard records what actually *happened*.

Structural mistakes: this. Logic mistakes: your tests. You want both.

---

## The companion: catch it in the PR, stop it in prod

lenscheck-contract has a sibling, **[lenscheck-semantic-reviewer](https://github.com/AnkushSinghGandhi/lenscheck-semantic-reviewer)**.
They're the same promise at two moments:

- **The reviewer** reads a PR *before merge* and tells you what it means and where to look.
- **The contract** runs *inside the app* and refuses to let undeclared behaviour happen at all.

The reviewer *discovers* the rules your code follows; the contract lets you *declare and enforce* them
in production. Use the reviewer to see the risk; use the contract to make it impossible.

---

## Try it

```bash
pip install lenscheck-contract
lenscheck-contract export --settings myproject.settings -o contract.json
```

Or run the "three bad things" demo from the repo:

```bash
git clone https://github.com/AnkushSinghGandhi/lenscheck-contract
cd lenscheck-contract && pip install -e ".[dev]"
bash examples/three_bad_things/run.sh
```

MIT-licensed. Built by [Ankush Singh Gandhi](https://warriorwhocodes.com) —
[GitHub](https://github.com/AnkushSinghGandhi/lenscheck-contract).

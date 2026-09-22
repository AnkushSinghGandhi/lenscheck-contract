"""Layer 3 — runtime. Run the shipped endpoint; the guard stops the hidden async call.

The structural diff (Layer 2) only sees *declared* effects. The analytics call was never declared,
so no diff or linter can see it. This runs the code and catches it the instant it tries to leave —
even though it's an `async` call on the event loop (httpx/aiohttp's path), which the guard hooks too.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))      # repo's src/ for `lenscheck_contract`
sys.path.insert(0, str(HERE / "after"))               # the "bad PR" app

from fastapi.testclient import TestClient              # noqa: E402

from lenscheck_contract import build, guard, install_fastapi  # noqa: E402

import app as bad_app                                  # noqa: E402  (after/app.py)

build(include_django=False, fastapi_app=bad_app.app)   # load routes + declarations
install_fastapi(bad_app.app)                           # scope the handler for every request
guard.install(mode="error")                            # enforce: an undeclared effect must not leave

with TestClient(bad_app.app, raise_server_exceptions=False) as client:
    resp = client.post("/orders", json={"name": "ACME Corp"})

if guard.violations:
    handler, effect = guard.violations[-1]
    print("  \033[31m⛔ BLOCKED at runtime\033[0m — the call never left the process:\n")
    print(f"     {handler} performed undeclared effect {effect!r}\n")
    print("  \033[32m✓ data exfiltration stopped\033[0m")
else:
    print("  \033[31m✗ NOT BLOCKED — guard failed\033[0m")
    sys.exit(2)

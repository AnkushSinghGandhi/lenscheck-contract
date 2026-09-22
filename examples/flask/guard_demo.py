"""Layer 3 — runtime. Run the shipped endpoint; the guard stops the hidden call.

The structural diff (Layer 2) only sees *declared* effects. The analytics call was never declared,
so no diff or linter can see it. This runs the code and catches it the instant it tries to leave.
"""
import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)                     # Flask logs the blocked call; the guard message is enough

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))      # repo's src/ for `lenscheck_contract`
sys.path.insert(0, str(HERE / "after"))               # the "bad PR" app

from lenscheck_contract import build, guard, install_flask  # noqa: E402

import app as bad_app                                  # noqa: E402  (after/app.py)

build(include_django=False, flask_app=bad_app.app)     # load routes + declarations
install_flask(bad_app.app)                             # scope the handler for every request
guard.install(mode="error")                            # enforce: an undeclared effect must not leave

client = bad_app.app.test_client()
try:
    client.post("/orders")
except Exception:                                      # noqa: BLE001 - error mode raises through the view
    pass

if guard.violations:
    handler, effect = guard.violations[-1]
    print("  \033[31m⛔ BLOCKED at runtime\033[0m — the call never left the process:\n")
    print(f"     {handler} performed undeclared effect {effect!r}\n")
    print("  \033[32m✓ data exfiltration stopped\033[0m")
else:
    print("  \033[31m✗ NOT BLOCKED — guard failed\033[0m")
    sys.exit(2)

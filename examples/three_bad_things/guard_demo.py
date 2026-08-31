"""Layer 3 — runtime. Run the shipped handler; the guard stops the hidden call.

The structural diff (Layer 2) can only see *declared* effects. The analytics call
was never declared, so no diff or linter can see it. This layer runs the code and
catches it the instant it tries to leave the process.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))                 # not needed once installed
sys.path.insert(0, str(HERE.parents[1] / "src"))      # repo's src/ for `pryti_contract`
sys.path.insert(0, str(HERE / "after"))               # the "bad PR" app
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django  # noqa: E402

django.setup()

from pryti_contract import UndeclaredEffect, build, guard  # noqa: E402

build()                       # load routes + declarations
guard.install(mode="error")   # enforce: an undeclared effect must not leave the process

from shop import views  # noqa: E402


class _Req:  # a stand-in request object
    method = "POST"


try:
    views.create_order(_Req())
    print("  \033[31m✗ NOT BLOCKED — guard failed\033[0m")
    sys.exit(2)
except UndeclaredEffect as e:
    print(f"  \033[31m⛔ BLOCKED at runtime\033[0m — the call never left the process:\n")
    print(f"     {e}\n")
    print("  \033[32m✓ data exfiltration stopped\033[0m")

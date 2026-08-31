"""Effect enforcement.

A declaration nobody checks is a comment. This makes it real.

We hook the socket layer, not individual HTTP clients, so requests, httpx,
urllib, boto3, stripe and anything else are all covered by one hook.
"""

from __future__ import annotations

import fnmatch
import socket
import threading
import warnings
from typing import Any, Iterable

from .registry import current_handler, registry

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "::"}


class UndeclaredEffect(RuntimeError):
    """Raised when a handler does something it did not declare."""


class _Guard:
    def __init__(self) -> None:
        self.mode = "off"  # off | record | warn | error
        self.allow: list[str] = []
        self.observed: dict[str, set[str]] = {}
        self.violations: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._originals: dict[str, Any] = {}
        self._ip_to_host: dict[str, str] = {}

    # ---------- lifecycle ----------

    def install(self, mode: str = "error", allow: Iterable[str] = ()) -> None:
        self.mode = mode
        self.allow = list(allow)
        if self._originals or mode == "off":
            return

        self._originals["getaddrinfo"] = socket.getaddrinfo
        self._originals["connect"] = socket.socket.connect

        guard = self

        def getaddrinfo(host: Any, port: Any, *a: Any, **kw: Any) -> Any:
            # Check first: a blocked effect must never leave the process.
            if isinstance(host, str):
                guard._check(f"net:{host}", host)
            result = guard._originals["getaddrinfo"](host, port, *a, **kw)
            if isinstance(host, str):
                for entry in result:
                    addr = entry[4]
                    if addr and isinstance(addr[0], str):
                        guard._ip_to_host[addr[0]] = host
            return result

        def connect(sock: Any, address: Any) -> Any:
            host = _host_of(address)
            if host is not None and host not in guard._ip_to_host:
                guard._check(f"net:{host}", host)
            return guard._originals["connect"](sock, address)

        socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
        socket.socket.connect = connect  # type: ignore[assignment,method-assign]
        self._install_smtp()

    def _install_smtp(self) -> None:
        try:
            import smtplib
        except ImportError:  # pragma: no cover
            return
        guard = self
        self._originals["sendmail"] = smtplib.SMTP.sendmail

        def sendmail(self_: Any, *a: Any, **kw: Any) -> Any:
            guard._check("email", "email")
            return guard._originals["sendmail"](self_, *a, **kw)

        smtplib.SMTP.sendmail = sendmail  # type: ignore[method-assign]

    def uninstall(self) -> None:
        if "getaddrinfo" in self._originals:
            socket.getaddrinfo = self._originals["getaddrinfo"]  # type: ignore[assignment]
            socket.socket.connect = self._originals["connect"]  # type: ignore[method-assign]
        if "sendmail" in self._originals:
            import smtplib

            smtplib.SMTP.sendmail = self._originals["sendmail"]  # type: ignore[method-assign]
        self._originals.clear()
        self.mode = "off"

    def reset(self) -> None:
        with self._lock:
            self.observed.clear()
            self.violations.clear()
            self._ip_to_host.clear()

    # ---------- the check ----------

    def _check(self, effect: str, host_or_kind: str) -> None:
        if self.mode == "off":
            return
        if host_or_kind in LOCAL_HOSTS:
            return
        if _matches_any(effect, self.allow):
            return

        handler = current_handler.get()
        with self._lock:
            self.observed.setdefault(handler or "<no handler>", set()).add(effect)

        # Nothing to enforce against outside a declared handler.
        if handler is None or self.mode == "record":
            return

        declared = registry.declared_effects(handler)
        if _matches_any(effect, declared):
            return

        with self._lock:
            self.violations.append((handler, effect))

        msg = (
            f"{handler} performed undeclared effect {effect!r}. "
            f"Declared: {declared or 'none'}. "
            f"Add @contract.effects({effect!r}) or remove the call."
        )
        if self.mode == "error":
            raise UndeclaredEffect(msg)
        warnings.warn(msg, stacklevel=3)

    # ---------- reporting ----------

    def suggestions(self) -> dict[str, list[str]]:
        """Run your test suite in record mode, get the declarations to paste in."""
        return {h: sorted(e) for h, e in sorted(self.observed.items())}


def _host_of(address: Any) -> str | None:
    if isinstance(address, tuple) and address and isinstance(address[0], str):
        return address[0]
    return None  # unix socket / abstract; not a network effect


def _matches_any(effect: str, patterns: Iterable[str]) -> bool:
    for p in patterns:
        if p == effect or fnmatch.fnmatch(effect, p):
            return True
        # "net:*.stripe.com" should also cover "net:stripe.com"
        if p.startswith("net:*.") and effect == "net:" + p[6:]:
            return True
    return False


guard = _Guard()

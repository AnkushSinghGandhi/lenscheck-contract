"""The five things a backend contract records."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class Route:
    method: str
    path: str
    handler: str
    auth: str = "unknown"
    effects: list[str] = field(default_factory=list)
    source: str = "declared"

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


@dataclass
class Model:
    name: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    source: str = "runtime"


@dataclass
class Job:
    name: str
    handler: str
    schedule: str | None = None
    effects: list[str] = field(default_factory=list)
    source: str = "declared"


@dataclass
class Coverage:
    """Honesty layer. A contract that looks complete but isn't is worse than none."""

    routes_total: int = 0
    routes_with_auth: int = 0
    routes_with_effects: int = 0
    unresolved: list[str] = field(default_factory=list)


@dataclass
class Contract:
    routes: dict[str, Route] = field(default_factory=dict)
    models: dict[str, Model] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    coverage: Coverage = field(default_factory=Coverage)

    def add_route(self, route: Route) -> None:
        existing = self.routes.get(route.key)
        if existing is None:
            self.routes[route.key] = route
            return
        # Declared data wins over probed data; never silently drop a declaration.
        if route.source == "declared":
            if route.auth != "unknown":
                existing.auth = route.auth
            if route.effects:
                existing.effects = sorted(set(existing.effects) | set(route.effects))
            existing.source = "declared"
        elif existing.auth == "unknown" and route.auth != "unknown":
            existing.auth = route.auth

    def recompute_coverage(self) -> None:
        self.coverage.routes_total = len(self.routes)
        self.coverage.routes_with_auth = sum(
            1 for r in self.routes.values() if r.auth != "unknown"
        )
        self.coverage.routes_with_effects = sum(
            1 for r in self.routes.values() if r.effects
        )

    def to_dict(self) -> dict[str, Any]:
        """Stable, sorted output. Byte-identical for identical code."""
        self.recompute_coverage()
        return {
            "schema_version": SCHEMA_VERSION,
            "routes": [
                asdict(self.routes[k]) for k in sorted(self.routes)
            ],
            "models": [
                asdict(self.models[k]) for k in sorted(self.models)
            ],
            "jobs": [asdict(self.jobs[k]) for k in sorted(self.jobs)],
            "coverage": asdict(self.coverage),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contract:
        c = cls()
        for r in data.get("routes", []):
            route = Route(**r)
            c.routes[route.key] = route
        for m in data.get("models", []):
            model = Model(**m)
            c.models[model.name] = model
        for j in data.get("jobs", []):
            job = Job(**j)
            c.jobs[job.name] = job
        if "coverage" in data:
            c.coverage = Coverage(**data["coverage"])
        return c

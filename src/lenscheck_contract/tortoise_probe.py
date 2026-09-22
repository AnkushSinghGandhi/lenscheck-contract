"""Read Tortoise ORM models at runtime.

Tortoise is the common async ORM for FastAPI/Starlette backends. Its models expose everything we
need on `Model._meta` the moment the class is defined (no `Tortoise.init()` required), so — like the
SQLAlchemy probe — we enumerate the mapped classes and read fields/constraints/relations. If Tortoise
isn't installed, or nothing is mapped, we add nothing. Never raises.
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Model


def probe_models(contract: Contract) -> None:
    """Fill `contract.models` from Tortoise ORM's mapped classes. Best-effort; never raises."""
    for model_cls in _all_models():
        try:
            _add_model(contract, model_cls)
        except Exception:  # noqa: BLE001 - one broken model must not hide the rest
            continue


def _all_models() -> list[Any]:
    """Every concrete Tortoise model class. [] if Tortoise is absent or nothing is defined."""
    try:
        from tortoise.models import Model as TortoiseModel
    except Exception:  # noqa: BLE001 - Tortoise is optional
        return []
    out, stack, seen = [], [TortoiseModel], set()
    while stack:
        cls = stack.pop()
        for sub in cls.__subclasses__():
            if sub in seen:
                continue
            seen.add(sub)
            stack.append(sub)
            meta = getattr(sub, "_meta", None)
            if meta is None or getattr(meta, "abstract", False):
                continue
            if str(getattr(sub, "__module__", "")).startswith("tortoise"):
                continue  # Tortoise's own internal models
            out.append(sub)
    return out


def _add_model(contract: Contract, model_cls: Any) -> None:
    meta = model_cls._meta
    entry = Model(name=model_cls.__name__, table=getattr(meta, "db_table", "") or "", source="runtime")
    for name, field in getattr(meta, "fields_map", {}).items():
        info: dict[str, Any] = {"type": type(field).__name__}
        if getattr(field, "pk", False):
            info["primary_key"] = True
        if getattr(field, "unique", False):
            info["unique"] = True
        if getattr(field, "null", False):
            info["null"] = True
        max_length = getattr(field, "max_length", None)
        if max_length:
            info["max_length"] = max_length
        related = getattr(field, "related_model", None) or getattr(field, "model_name", None)
        if related:
            info["relates_to"] = _rel_name(related)
        entry.fields[name] = info
    contract.models[entry.name] = entry


def _rel_name(related: Any) -> str:
    name = getattr(related, "__name__", None)
    if name:
        return name
    return str(related).rsplit(".", 1)[-1]        # "models.Customer" -> "Customer"

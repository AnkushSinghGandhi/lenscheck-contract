"""Read SQLAlchemy's mapped models at runtime.

Flask and FastAPI have no model registry of their own — the ORM does. Almost every
Python-web backend that has a database uses SQLAlchemy, so both framework probes lean on
this shared helper to fill `contract.models`, exactly the way the Django probe reads
`apps.get_models()`.

We enumerate every mapped class through SQLAlchemy's own mapper registry, so this sees
models no matter which declarative Base they hang off (or how many there are). If SQLAlchemy
isn't installed, or nothing is mapped, we add nothing — coverage stays honest.
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Model


def probe_models(contract: Contract) -> None:
    """Fill `contract.models` from SQLAlchemy's mapped classes. Best-effort; never raises."""
    for mapper in _mappers():
        try:
            _add_model(contract, mapper)
        except Exception:  # noqa: BLE001 - one broken mapper must not hide the rest
            continue


def _mappers() -> list[Any]:
    """Every live SQLAlchemy mapper, across every declarative registry. [] if none/unavailable."""
    try:
        from sqlalchemy.orm import mapperlib
    except Exception:  # noqa: BLE001 - SQLAlchemy is optional
        return []
    out: list[Any] = []
    # `_mapper_registries` is a WeakKeyDictionary{registry: True}; each registry knows its mappers.
    for reg in list(getattr(mapperlib, "_mapper_registries", {})):
        out.extend(getattr(reg, "mappers", ()))
    return out


def _add_model(contract: Contract, mapper: Any) -> None:
    cls = mapper.class_
    table = mapper.local_table
    if table is None:
        return
    entry = Model(name=cls.__name__, table=table.name, source="runtime")
    for col in table.columns:
        info: dict[str, Any] = {"type": type(col.type).__name__}
        if col.primary_key:
            info["primary_key"] = True
        if col.unique:
            info["unique"] = True
        if col.nullable:
            info["null"] = True
        length = getattr(col.type, "length", None)
        if length:
            info["max_length"] = length
        fks = list(col.foreign_keys)
        if fks:
            info["relates_to"] = fks[0].column.table.name
        entry.fields[col.name] = info
    contract.models[entry.name] = entry

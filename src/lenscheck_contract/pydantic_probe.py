"""Read a FastAPI app's Pydantic models off its route surface.

FastAPI apps model their data with Pydantic, not (only) an ORM — the request bodies and
response models *are* the API's shape. SQLAlchemy tables tell you the DB; these tell you the
contract with the outside world. We collect the model on each route's body and response, then
recurse into nested models, so "a field was removed" / "a field went optional" shows up in the diff.

Pydantic v2 (`model_fields`) with a best-effort v1 fallback (`__fields__`). Never raises.
"""

from __future__ import annotations

import typing
from typing import Any

from .models import Contract, Model


def probe_models(routes: Any, contract: Contract) -> None:
    """Add every Pydantic model reachable from these routes' bodies/responses to the contract."""
    try:
        from pydantic import BaseModel
    except Exception:  # noqa: BLE001 - Pydantic absent (no FastAPI) → nothing to do
        return

    seen: set[type] = set()
    for route in routes:
        for ann in _route_models(route):
            base = _base_model(ann, BaseModel)
            if base is not None:
                _add_model(contract, base, BaseModel, seen)


def _route_models(route: Any) -> list[Any]:
    """The annotations that carry a model: the request body and the response_model."""
    out: list[Any] = []
    body = getattr(route, "body_field", None)
    if body is not None:
        ann = getattr(body, "type_", None) or getattr(getattr(body, "field_info", None), "annotation", None)
        if ann is not None:
            out.append(ann)
    response = getattr(route, "response_model", None)
    if response is not None:
        out.append(response)
    return out


def _add_model(contract: Contract, cls: type, base_model: type, seen: set[type]) -> None:
    if cls in seen:
        return
    seen.add(cls)
    entry = Model(name=cls.__name__, table="", source="runtime")
    for name, (annotation, required, max_length) in _fields_of(cls).items():
        core, optional, collection = _unwrap(annotation)
        info: dict[str, Any] = {"type": _type_name(core, collection)}
        if optional or not required:
            info["null"] = True
        if max_length:
            info["max_length"] = max_length
        related = _base_model(core, base_model)
        if related is not None:
            info["relates_to"] = related.__name__
            _add_model(contract, related, base_model, seen)   # recurse into nested models
        entry.fields[name] = info
    contract.models[entry.name] = entry


def _fields_of(cls: type) -> dict[str, tuple[Any, bool, int | None]]:
    """{name: (annotation, required, max_length)} across Pydantic v2 and v1."""
    out: dict[str, tuple[Any, bool, int | None]] = {}
    v2 = getattr(cls, "model_fields", None)
    if v2 is not None:                                   # Pydantic v2
        for name, f in v2.items():
            try:
                required = f.is_required()
            except Exception:  # noqa: BLE001
                required = True
            out[name] = (getattr(f, "annotation", None), required, _max_length(getattr(f, "metadata", None)))
        return out
    v1 = getattr(cls, "__fields__", None)
    if v1 is not None:                                   # Pydantic v1 fallback
        for name, f in v1.items():
            ml = getattr(getattr(f, "field_info", None), "max_length", None)
            out[name] = (getattr(f, "outer_type_", None), bool(getattr(f, "required", True)), ml)
    return out


def _max_length(metadata: Any) -> int | None:
    for m in metadata or []:
        ml = getattr(m, "max_length", None)
        if ml:
            return ml
    return None


def _unwrap(annotation: Any) -> tuple[Any, bool, bool]:
    """(core type, optional?, collection?). Peels Optional/Union[..., None] and list/set/tuple."""
    optional = False
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        all_args = typing.get_args(annotation)
        args = [a for a in all_args if a is not type(None)]
        optional = len(args) != len(all_args)
        annotation = args[0] if len(args) == 1 else annotation
        origin = typing.get_origin(annotation)

    collection = False
    if origin in (list, set, tuple, frozenset) or _is_sequence(origin):
        collection = True
        args = typing.get_args(annotation)
        annotation = args[0] if args else Any

    return annotation, optional, collection


def _is_sequence(origin: Any) -> bool:
    try:
        import collections.abc as abc
        return isinstance(origin, type) and issubclass(origin, (abc.Sequence, abc.Set)) and origin is not str
    except Exception:  # noqa: BLE001
        return False


def _type_name(core: Any, collection: bool) -> str:
    name = getattr(core, "__name__", None) or str(core)
    return f"list[{name}]" if collection else name


def _base_model(annotation: Any, base_model: type) -> type | None:
    core, _opt, _coll = _unwrap(annotation)
    if isinstance(core, type) and issubclass(core, base_model) and core is not base_model:
        return core
    return None

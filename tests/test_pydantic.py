"""Pydantic model extraction for FastAPI: request bodies, responses, nesting, and diffs."""

from typing import List, Optional

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from lenscheck_contract import Contract, build, diff  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    from lenscheck_contract.registry import registry

    saved = (dict(registry.routes), dict(registry.jobs),
             {k: list(v) for k, v in registry._declared.items()})
    registry.reset()
    yield
    registry.routes.clear(); registry.routes.update(saved[0])
    registry.jobs.clear(); registry.jobs.update(saved[1])
    registry._declared.clear(); registry._declared.update(saved[2])


class Address(BaseModel):
    city: str
    zip: str = Field(max_length=10)


class CustomerCreate(BaseModel):
    name: str = Field(max_length=100)
    email: str
    age: Optional[int] = None
    address: Optional[Address] = None
    tags: List[str] = []


class CustomerOut(BaseModel):
    id: int
    name: str


def _app():
    app = FastAPI()

    @app.post("/customers", response_model=CustomerOut)
    def create(c: CustomerCreate):
        return {}

    return app


def test_request_body_model_and_constraints():
    c = build(include_django=False, fastapi_app=_app())
    m = c.models["CustomerCreate"]
    assert m.fields["name"]["max_length"] == 100
    assert m.fields["age"]["null"] is True          # Optional -> nullable
    assert m.fields["email"].get("null") is None    # required -> not null


def test_response_model_is_captured():
    c = build(include_django=False, fastapi_app=_app())
    assert "CustomerOut" in c.models
    assert set(c.models["CustomerOut"].fields) == {"id", "name"}


def test_nested_model_is_recursed_and_related():
    c = build(include_django=False, fastapi_app=_app())
    assert "Address" in c.models                     # discovered only through nesting
    assert c.models["CustomerCreate"].fields["address"]["relates_to"] == "Address"
    assert c.models["Address"].fields["zip"]["max_length"] == 10


def test_list_field_type():
    c = build(include_django=False, fastapi_app=_app())
    assert c.models["CustomerCreate"].fields["tags"]["type"] == "list[str]"


def test_removing_a_field_is_a_risky_diff():
    base = build(include_django=False, fastapi_app=_app())

    # a head where CustomerOut lost `name`
    slim = Contract.from_dict(base.to_dict())
    del slim.models["CustomerOut"].fields["name"]

    changes = diff(base, slim)
    removed = [c for c in changes if c.kind == "field_removed" and c.subject == "CustomerOut.name"]
    assert removed and removed[0].severity == "risky"

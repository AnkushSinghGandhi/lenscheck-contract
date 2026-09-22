"""The Pydantic **v1** fallback in the model probe (older FastAPI installs read fields via
`__fields__`, not v2's `model_fields`). Exercised through pydantic's v1 compatibility namespace."""

import pytest

pytest.importorskip("pydantic")

try:
    from pydantic.v1 import BaseModel, Field  # pydantic v2's bundled v1 API
except Exception:  # pragma: no cover - very old pydantic where v1 is the top-level
    from pydantic import BaseModel, Field

from typing import List, Optional  # noqa: E402

from lenscheck_contract.models import Contract  # noqa: E402
from lenscheck_contract.pydantic_probe import _add_model  # noqa: E402


class Address(BaseModel):
    city: str


class CustomerV1(BaseModel):
    name: str = Field(max_length=100)
    email: str
    age: Optional[int] = None
    address: Optional[Address] = None
    tags: List[str] = []


def _build():
    c = Contract()
    _add_model(c, CustomerV1, BaseModel, set())
    return c


def test_v1_fields_and_constraints():
    m = _build().models["CustomerV1"]
    assert m.fields["name"]["max_length"] == 100
    assert m.fields["email"].get("null") is None       # required
    assert m.fields["age"]["null"] is True             # Optional -> nullable


def test_v1_nesting_and_lists():
    c = _build()
    assert c.models["CustomerV1"].fields["address"]["relates_to"] == "Address"
    assert "Address" in c.models                        # discovered through nesting
    assert c.models["CustomerV1"].fields["tags"]["type"] == "list[str]"

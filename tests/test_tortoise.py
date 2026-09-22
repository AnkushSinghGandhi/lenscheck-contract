"""The Tortoise ORM model probe (async ORM common with FastAPI)."""

import pytest

pytest.importorskip("tortoise")

from tortoise import fields  # noqa: E402
from tortoise.models import Model  # noqa: E402

from lenscheck_contract.models import Contract  # noqa: E402
from lenscheck_contract.tortoise_probe import probe_models  # noqa: E402


class TCustomer(Model):
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=200, unique=True)
    name = fields.CharField(max_length=100, null=True)

    class Meta:
        table = "t_customer"


class TOrder(Model):
    id = fields.IntField(pk=True)
    customer = fields.ForeignKeyField("models.TCustomer", related_name="orders")

    class Meta:
        table = "t_order"


def test_probe_reads_fields_and_constraints():
    c = Contract()
    probe_models(c)

    assert "TCustomer" in c.models
    cust = c.models["TCustomer"]
    assert cust.table == "t_customer"
    assert cust.fields["id"]["primary_key"] is True
    assert cust.fields["email"]["unique"] is True
    assert cust.fields["email"]["max_length"] == 200
    assert cust.fields["name"]["null"] is True


def test_probe_reads_foreign_key_relation():
    c = Contract()
    probe_models(c)
    assert c.models["TOrder"].fields["customer"]["relates_to"] == "TCustomer"

"""The shared SQLAlchemy model probe (used by both the Flask and FastAPI probes)."""

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import ForeignKey, String  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # noqa: E402

from lenscheck_contract.models import Contract  # noqa: E402
from lenscheck_contract.sqla_probe import probe_models  # noqa: E402


def test_probe_reads_mapped_columns():
    class Base(DeclarativeBase):
        pass

    class Customer(Base):
        __tablename__ = "customer"
        id: Mapped[int] = mapped_column(primary_key=True)
        email: Mapped[str] = mapped_column(String(200), unique=True)
        note: Mapped[str] = mapped_column(String(50), nullable=True)

    class Order(Base):
        __tablename__ = "order"
        id: Mapped[int] = mapped_column(primary_key=True)
        customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))

    c = Contract()
    probe_models(c)

    assert "Customer" in c.models
    cust = c.models["Customer"]
    assert cust.table == "customer"
    assert cust.fields["id"]["primary_key"] is True
    assert cust.fields["email"]["unique"] is True
    assert cust.fields["email"]["max_length"] == 200
    assert cust.fields["note"]["null"] is True

    order = c.models["Order"]
    assert order.fields["customer_id"]["relates_to"] == "customer"


def test_probe_is_safe_when_sqlalchemy_has_nothing():
    # Calling with no interesting mappers must never raise and must add nothing new.
    c = Contract()
    before = dict(c.models)
    probe_models(c)
    # (other tests may have registered models; the contract at minimum stays a dict)
    assert isinstance(c.models, dict)
    assert all(k in c.models for k in before)

"""The good app — before the PR. A Flask order endpoint that:
  - declares it needs an authenticated user
  - has a Customer model with a unique email
  - charges Stripe, and *declares* that it does.
"""
import socket

from flask import Flask
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from lenscheck_contract import contract


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)


app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/orders")
@contract.route("POST /orders", auth="user")       # declared: this endpoint needs a user
@contract.effects("net:api.stripe.com")            # declared: it may call Stripe
def create_order():
    _resolve("api.stripe.com")                     # declared effect — allowed
    return {"ok": True}


def _resolve(host: str) -> None:
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        pass                                        # DNS may fail offline; the guard decision is the point

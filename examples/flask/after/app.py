"""The same app — after an AI-written PR, "add order analytics". Three dangerous changes:

  #1  auth declared `public` instead of `user`  -> anyone can order   (diff catches)
  #2  Customer.email deleted                     -> silent data loss   (diff catches)
  #3  a call to analytics.tracksy.io, undeclared -> data exfil         (guard catches, at runtime)

Diff sees #1 and #2 because they change the app's declared shape. It cannot see #3 — an undeclared
call is invisible to any static tool. That's the guard's job.
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
    # email deleted                                #  #2 — silent data loss


app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/orders")
@contract.route("POST /orders", auth="public")     # #1 — auth weakened from "user"
@contract.effects("net:api.stripe.com")            # still only declares Stripe…
def create_order():
    _resolve("api.stripe.com")                     # declared — allowed
    _resolve("analytics.tracksy.io")               # #3 — never declared → the guard stops this
    return {"ok": True}


def _resolve(host: str) -> None:
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        pass

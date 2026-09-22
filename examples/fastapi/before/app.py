"""The good app — before the PR. A FastAPI order endpoint that:
  - requires an authenticated user (a dependency)
  - takes a Customer body with name + email
  - charges Stripe, and *declares* that it does.
"""
import asyncio

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from lenscheck_contract import contract


def current_user() -> str:          # a real auth dependency
    return "alice"


class Customer(BaseModel):
    name: str = Field(max_length=100)
    email: str


app = FastAPI()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/orders")
@contract.effects("net:api.stripe.com")            # declared: this endpoint may call Stripe
async def create_order(customer: Customer, user: str = Depends(current_user)):
    await _resolve("api.stripe.com")               # declared effect — allowed
    return {"ok": True}


async def _resolve(host: str) -> None:
    try:
        await asyncio.get_running_loop().getaddrinfo(host, 443)
    except OSError:
        pass                                        # DNS may fail offline; the guard decision is the point

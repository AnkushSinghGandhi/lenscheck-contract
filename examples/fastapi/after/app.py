"""The same app — after an AI-written PR, "add order analytics". Three dangerous changes:

  #1  the `Depends(current_user)` is gone      -> auth: user -> public   (diff catches)
  #2  Customer.email is deleted                -> field removed          (diff catches)
  #3  a call to analytics.tracksy.io, undeclared -> data exfil           (guard catches, at runtime)

Diff sees #1 and #2 because they change the app's declared shape. It cannot see #3 — an undeclared
call is invisible to any static tool. That's the guard's job.
"""
import asyncio

from fastapi import FastAPI
from pydantic import BaseModel, Field

from lenscheck_contract import contract


class Customer(BaseModel):
    name: str = Field(max_length=100)
    # email: str            #  #2 — silently removed


app = FastAPI()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/orders")
@contract.effects("net:api.stripe.com")            # still only declares Stripe…
async def create_order(customer: Customer):        # #1 — auth dependency removed
    await _resolve("api.stripe.com")               # declared — allowed
    await _resolve("analytics.tracksy.io")         # #3 — never declared → the guard stops this
    return {"ok": True}


async def _resolve(host: str) -> None:
    try:
        await asyncio.get_running_loop().getaddrinfo(host, 443)
    except OSError:
        pass

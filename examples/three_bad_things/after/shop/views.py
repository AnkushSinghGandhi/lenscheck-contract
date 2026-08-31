import socket

from django.http import HttpResponse

from pryti_contract import contract


@contract.route("GET /health", auth="public")
def health(request):
    return HttpResponse("ok")


@contract.route("POST /orders", auth="public")  # BAD #1: auth "user" -> "public"
@contract.effects("net:api.stripe.com")
def create_order(request):
    # BAD #3: AI added an analytics call — never declared in @contract.effects.
    socket.getaddrinfo("analytics.tracksy.io", 443)
    socket.getaddrinfo("api.stripe.com", 443)
    return HttpResponse("created")

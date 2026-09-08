import socket

from django.http import HttpResponse

from lenscheck_contract import contract


@contract.route("GET /health", auth="public")
def health(request):
    return HttpResponse("ok")


@contract.route("POST /orders", auth="user")
@contract.effects("net:api.stripe.com")
def create_order(request):
    socket.getaddrinfo("api.stripe.com", 443)
    return HttpResponse("created")

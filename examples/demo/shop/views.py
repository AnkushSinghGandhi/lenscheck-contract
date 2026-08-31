"""Every shape a real Django app has - and the contract sees all of them."""
import socket

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from pryti_contract import contract


@contract.route("GET /health", auth="public")
def health(request):
    return HttpResponse("ok")


@contract.route("POST /orders", auth="user")
@contract.effects("net:api.stripe.com")
def create_order(request):
    socket.getaddrinfo("api.stripe.com", 443)
    return HttpResponse("created")


def leaky_order(request):
    """No declaration. The guard will stop this one."""
    socket.getaddrinfo("api.stripe.com", 443)
    return HttpResponse("oops")


@login_required
def account(request):
    return HttpResponse("account")


class AdminPanel(LoginRequiredMixin, View):
    def get(self, request):
        return HttpResponse("panel")

    def post(self, request):
        return HttpResponse("saved")

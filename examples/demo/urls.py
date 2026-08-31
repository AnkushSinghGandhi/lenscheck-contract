from django.urls import path

from shop import views

# Routes built in a loop. Static analysis misses these; the runtime does not.
REPORTS = ["daily", "weekly", "monthly"]

urlpatterns = [
    path("health", views.health),
    path("orders", views.create_order),
    path("orders/leaky", views.leaky_order),
    path("account", views.account),
    path("admin-panel", views.AdminPanel.as_view()),
] + [path(f"reports/{name}", views.health, name=f"report-{name}") for name in REPORTS]

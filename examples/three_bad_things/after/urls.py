from django.urls import path
from shop import views

urlpatterns = [
    path("health", views.health),
    path("orders", views.create_order),
]

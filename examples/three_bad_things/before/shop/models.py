from django.db import models


class Customer(models.Model):
    email = models.CharField(max_length=254, unique=True)
    name = models.CharField(max_length=120, blank=True)


class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_cents = models.IntegerField()
    paid = models.BooleanField(default=False)

from django.db import models
from django.contrib.auth.models import User

class Seller(models.Model):
    username = models.CharField(max_length=255)
    telegram_link = models.URLField()

    def __str__(self):
        return self.username

class Lot(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    start_price = models.DecimalField(max_digits=10, decimal_places=2)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE)
    location = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    images = models.ImageField(upload_to='lots/')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=50, choices=[('Jewelry', 'Jewelry'), ('Historical', 'Historical'), ('Standard', 'Standard')])
    is_sold = models.BooleanField(default=False)

    def __str__(self):
        return self.title

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    successful_payments = models.IntegerField(default=0)
    auto_bid_access = models.BooleanField(default=False)

    def __str__(self):
        return self.user

class CompletedAuction(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    is_paid = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.lot.title} - {self.final_price}Р"
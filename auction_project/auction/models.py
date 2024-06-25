from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
import os
from django.conf import settings

class Seller(models.Model):
    username = models.CharField(max_length=255)
    telegram_link = models.URLField()

    def __str__(self):
        return self.username


from django.core.files.base import ContentFile
from auction.models import User


class Lot(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE)
    location = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    images = models.ImageField(upload_to='lots/')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=50, choices=[('Jewelry', 'Jewelry'), ('Historical', 'Historical'), ('Standard', 'Standard')])
    document = models.FileField(upload_to='documents/', blank=True, null=True)
    telegram_message_id = models.IntegerField(blank=True, null=True)
    is_sold = models.BooleanField(default=False)
    current_bid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    next_bid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Сохраняем лот в первый раз, чтобы получить id
        if not self.pk:
            super().save(*args, **kwargs)

        # Создаем документ, если его нет
        if not self.document:
            self.create_document()

        # Сохраняем изменения
        super().save(*args, **kwargs)

    def create_document(self):
        # Путь к файлу документа
        document_name = f'{self.id}_{self.document_type}.txt'
        document_path = os.path.join('documents', document_name)

        # Текст документа
        document_content = (
            f'Документ для лота: {self.title}\n'
            f'Тип документа: {self.document_type}\n'
            f'Описание: {self.description}\n'
        )

        # Сохранение документа
        self.document.save(document_path, ContentFile(document_content))

    def get_last_bidder(self):
        last_bid = Bid.objects.filter(lot=self).order_by('-timestamp').first()
        return last_bid.bidder.username if last_bid else 'Нет информации'

    def get_bid_by_user(self, user_id):
        try:
            # Получаем все ставки пользователя на этот лот, отсортированные по времени создания
            bids = self.bid_set.filter(bidder_id=user_id).order_by('-timestamp')

            # Выбираем первую (последнюю по времени) ставку пользователя
            if bids.exists():
                return bids.first().amount  # возвращаем сумму последней ставки
            else:
                return None  # если ставок пользователя на лот нет
        except Bid.DoesNotExist:
            return None  # если ставка отсутствует

    def update_next_bid(self):
        if self.current_bid == 0:
            self.next_bid = self.start_price * Decimal('1.10')  # следущая ставка на 10% больше стартовой цены
        else:
            self.next_bid = self.current_bid * Decimal('1.10')  # следущая ставка на 10% больше текущей ставки
        self.save()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    successful_payments = models.IntegerField(default=0)
    auto_bid_access = models.BooleanField(default=False)
    strike_count = models.IntegerField(default=0)

    def __str__(self):
        return str(self.user)

    def check_auto_bid_access(self):
        if self.balance > 500 or self.successful_payments >= 10:
            self.auto_bid_access = True
            self.save()


class CompletedAuction(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    is_paid = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.lot.title} - {self.final_price}Р"


class Bid(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    bidder = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)
    hidden = models.BooleanField(default=False)

    def __str__(self):
        return f"Bid #{self.pk} on {self.lot.title} by {self.bidder.username} - {self.amount}Р"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.lot.current_bid = self.amount
        self.lot.update_next_bid()

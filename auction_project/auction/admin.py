from django.contrib import admin
from .models import Lot, UserProfile, CompletedAuction, Seller

admin.site.register(Lot)
admin.site.register(UserProfile)
admin.site.register(CompletedAuction)
admin.site.register(Seller)

from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('send_all_active_auctions/', views.send_all_active_auctions_to_channel, name='send_all_active_auctions'),
    path('mark_lot_as_sold/<int:lot_id>/<int:buyer_id>/', views.mark_lot_as_sold, name='mark_lot_as_sold'),
    path('retry_unsold_lots/', views.retry_unsold_lots, name='retry_unsold_lots'),
    path('lots/<int:lot_id>/', views.get_lot_info, name='get_lot_info'),  # необходимо для получения информации в бота
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

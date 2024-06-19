from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from .models import Lot, CompletedAuction
import telebot
import datetime
import logging

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot('7075474227:AAG8Y7jASasiq9pumKmQQn_7L7dTikdF3T4')


def get_lot_info(request, lot_id):
    lot = get_object_or_404(Lot, id=lot_id)
    lot_data = {
        "title": lot.title,
        "description": lot.description,
        "start_price": lot.start_price,
        "seller_link": lot.seller.telegram_link,
        "end_time": lot.end_time.isoformat(),
    }
    return JsonResponse(lot_data)


def send_all_active_auctions_to_channel(request):
    logging.info("Функция send_all_active_auctions_to_channel была вызвана")
    active_lots = Lot.objects.filter(end_time__gt=datetime.datetime.now(), is_sold=False)
    channel_id = '-1002148978810'

    if not active_lots:
        logging.info("Нет активных лотов для отправки")
        return JsonResponse({"status": "success", "message": "Нет активных лотов для отправки"})

    for lot in active_lots:
        lot_message = f"{lot.title}\n\n{lot.description}\n\nТекущая ставка: {lot.start_price}Р\nПродавец: {lot.seller.telegram_link}"
        markup = telebot.types.InlineKeyboardMarkup()
        timer_button = telebot.types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot.id}")
        info_button = telebot.types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
        open_lot_button = telebot.types.InlineKeyboardButton("🛍 Открыть лот", callback_data=f"open_lot_{lot.id}")
        markup.add(timer_button, info_button, open_lot_button)

        logging.info(f"Отправка лота {lot.title} в канал")
        bot.send_message(channel_id, lot_message, reply_markup=markup, disable_notification=True)

    return JsonResponse({"status": "success", "message": "Активные лоты отправлены в канал"})


def mark_lot_as_sold(request, lot_id, buyer_id):
    lot = get_object_or_404(Lot, id=lot_id)
    buyer = get_object_or_404(User, id=buyer_id)
    lot.is_sold = True
    lot.save()

    completed_auction = CompletedAuction.objects.create(
        lot=lot,
        final_price=lot.start_price,
        buyer=buyer,
        is_paid=True
    )

    return JsonResponse({"status": "success", "message": f"Лот {lot.title} продан покупателю {buyer.username}"})


def retry_unsold_lots(request):
    unsold_lots = CompletedAuction.objects.filter(is_paid=False)
    for auction in unsold_lots:
        lot = auction.lot
        lot.is_sold = False
        lot.save()
        auction.delete()

    return JsonResponse({"status": "success", "message": "Все не выкупленные лоты возвращены на продажу."})

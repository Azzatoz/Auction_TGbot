from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt
from .models import User, Lot, CompletedAuction, Bid
from django.db.models import Max
import telebot
import datetime
import pytz
import logging
from auction_project.telegram_bot import create_auction_message, send_lot_to_channel, generate_deep_link
import json

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot('7075474227:AAG8Y7jASasiq9pumKmQQn_7L7dTikdF3T4')
logger = logging.getLogger(__name__)

def get_csrf_token(request):
    csrf_token = get_token(request)
    return JsonResponse({'csrf_token': csrf_token})


def get_lot_info(request, lot_id):
    """
    Необходимо для получения информации в бота
    :param request:
    :param lot_id:
    :return:
    """
    try:
        lot = get_object_or_404(Lot, pk=lot_id)
        lot_data = {
            'id': lot.id,
            'title': lot.title,
            'description': lot.description,
            'seller_link': lot.seller.telegram_link,
            'location': lot.location,
            'start_time': lot.start_time.isoformat(),
            'end_time': lot.end_time.isoformat(),
            'images': lot.images.url if lot.images else None,
            'current_bid': lot.current_bid,
            'next_bid': lot.next_bid,
        }
        return JsonResponse(lot_data, safe=False)
    except Lot.DoesNotExist:
        raise Http404("Лот не найден")


def get_user_lots(request, user_id):
    """
    Получение всех лотов, созданных пользователем
    :param request:
    :param user_id:
    :return:
    """
    try:
        user = get_object_or_404(User, pk=user_id)
        lots = Lot.objects.filter(created_by=user)

        if not lots.exists():
            return JsonResponse({"status": "success", "message": "У пользователя нет активных лотов."}, status=200)

        lots_data = [
            {
                'id': lot.id,
                'title': lot.title,
                'description': lot.description,
                'seller_link': lot.seller.telegram_link,
                'location': lot.location,
                'start_time': lot.start_time.isoformat(),
                'end_time': lot.end_time.isoformat(),
                'images': lot.images.url if lot.images else None,
                'current_bid': lot.current_bid,
                'next_bid': lot.next_bid,
            }
            for lot in lots
        ]
        return JsonResponse(lots_data, safe=False)
    except User.DoesNotExist:
        raise Http404("Пользователь не найден")

@csrf_exempt
def place_bid(request, lot_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            user = get_object_or_404(User, pk=user_id)
            lot = get_object_or_404(Lot, pk=lot_id)

            # Обновление текущей и следующей ставки
            new_bid = lot.next_bid
            Bid.objects.create(lot=lot, bidder=user, amount=new_bid)

            # Обновление данных лота
            lot.current_bid = new_bid
            lot.update_next_bid()
            lot.save()

            lot_data = {
                'id': lot.id,
                'title': lot.title,
                'description': lot.description,
                'seller_link': lot.seller.telegram_link,
                'location': lot.location,
                'images': lot.images.url if lot.images else None,
                'current_bid': lot.current_bid,
                'next_bid': lot.next_bid,
            }
            return JsonResponse(lot_data)
        except Exception as e:
            logger.error(f"Ошибка обработки ставки: {e}")
            return JsonResponse({'error': 'Ошибка обработки ставки'}, status=400)
    else:
        raise Http404("Только POST запросы разрешены")


def send_all_active_auctions_to_channel(request):
    """
    Отправка всех лотов в канал
    :param request:
    :return:
    """
    logging.info("Функция send_all_active_auctions_to_channel была вызвана")
    active_lots = Lot.objects.filter(end_time__gt=datetime.datetime.now(pytz.UTC), is_sold=False)
    channel_id = '-1002148978810'

    if not active_lots.exists():
        logging.info("Нет активных лотов для отправки")
        return JsonResponse({"status": "success", "message": "Нет активных лотов для отправки"})

    for lot in active_lots:
        lot_data = {
            'id': lot.id,
            'title': lot.title,
            'description': lot.description,
            'seller_link': lot.seller.telegram_link,
            'location': lot.location,
            'images': lot.images.path if lot.images else None,
            'current_bid': lot.current_bid,
            'next_bid': lot.next_bid,
        }
        lot_message = create_auction_message(lot_data)

        if lot.telegram_message_id:
            try:
                update_lot_message(channel_id, lot.telegram_message_id, lot_message, lot_data)
            except telebot.apihelper.ApiTelegramException as e:
                if e.result_json['error_code'] == 400 and "message to edit not found" in e.result_json['description']:
                    logging.warning(f"Сообщение с ID {lot.telegram_message_id} не найдено, отправка нового сообщения")
                    try:
                        message_id = send_lot_to_channel(lot_data)
                        lot.telegram_message_id = message_id
                        lot.save()
                    except Exception as e:
                        logging.error(f"Ошибка при повторной отправке сообщения о лоте {lot.id}: {str(e)}")
                else:
                    logging.error(f"Ошибка при обновлении сообщения лота {lot.id}: {e.result_json}")
        else:
            try:
                message_id = send_lot_to_channel(lot_data)
                lot.telegram_message_id = message_id
                lot.save()
            except Exception as e:
                logging.error(f"Ошибка при отправке нового сообщения о лоте {lot.id}: {str(e)}")

    return JsonResponse({"status": "success", "message": "Активные лоты обновлены в канале"})


def update_lot_message(channel_id, message_id, new_message, lot_data):
    """
    Обновление сообщений в канале
    :param channel_id:
    :param message_id:
    :param new_message:
    :param lot_data:
    :return:
    """
    try:
        markup = telebot.types.InlineKeyboardMarkup()
        timer_button = telebot.types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot_data['id']}")
        info_button = telebot.types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
        open_lot_button = telebot.types.InlineKeyboardButton("🛍 Открыть лот", url=generate_deep_link(lot_data['id']))
        markup.add(timer_button, info_button, open_lot_button)

        if lot_data['images']:
            bot.edit_message_caption(chat_id=channel_id, message_id=message_id, caption=new_message,
                                     reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=channel_id, message_id=message_id, text=new_message, parse_mode='HTML',
                                  reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if e.result_json['error_code'] == 400 and "message is not modified" in e.result_json['description']:
            logging.warning(f"Не удалось изменить сообщение с ID {message_id}: сообщение не изменилось")
        else:
            raise e


def mark_lot_as_sold(request, lot_id, buyer_id):
    lot = get_object_or_404(Lot, id=lot_id)
    buyer = get_object_or_404(User, id=buyer_id)
    lot.is_sold = True
    lot.save()

    completed_auction = CompletedAuction.objects.create(
        lot=lot,
        final_price=lot.current_bid,
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

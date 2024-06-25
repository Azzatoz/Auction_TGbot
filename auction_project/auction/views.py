import time
import threading
import datetime
import pytz
import logging
import requests
import telebot
import json
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Max
from django.contrib.auth.decorators import login_required
from auction.models import User, UserProfile, Lot, CompletedAuction, Bid
from auction_project.telegram_bot import bot, create_auction_message, send_lot_to_channel, generate_deep_link
from .forms import LotForm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHANNEL_ID = '-1002148978810'


def get_csrf_token(request):
    """
    Функция для получения CSRF токена
    :param request:
    :return:
    """
    csrf_token = get_token(request)
    return JsonResponse({'csrf_token': csrf_token})

def get_lot_info(request, lot_id):
    """
    Функция для получения информации о лоте
    :param request:
    :param lot_id:
    :return:
    """
    try:
        lot = get_object_or_404(Lot, pk=lot_id)
        # Получение последней ставки
        last_bidder = lot.get_last_bidder()

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
            'last_bid': last_bidder
        }
        return JsonResponse(lot_data, safe=False)
    except Lot.DoesNotExist:
        raise Http404("Лот не найден")

def get_user_lots(request, user_id):
    """
    Функция для получения лотов, на которые пользователь делал ставки или уже выиграл.
    :param request:
    :param user_id:
    :return:
    """
    try:
        user_profile = get_object_or_404(UserProfile, user__username=user_id)
        user = user_profile.user

        bid_lots = Lot.objects.filter(bid__bidder=user).distinct()
        won_lots = Lot.objects.filter(completedauction__buyer=user).distinct()

        all_lots = bid_lots | won_lots

        if not all_lots.exists():
            return JsonResponse({"status": "success", "message": "У пользователя нет активных лотов."}, status=200)

        lots_data = []

        for lot in all_lots:
            channel_message_url = f"https://t.me/c/{CHANNEL_ID[4:]}/{lot.telegram_message_id}"

            lot_data = {
                'title': lot.title,
                'user_bid': lot.get_bid_by_user(user.id),
                'channel_message_url': channel_message_url,
            }
            lots_data.append(lot_data)

        return JsonResponse(lots_data, safe=False)
    except UserProfile.DoesNotExist:
        raise Http404("Пользователь не найден")

def lot_to_dict(lot):
    """
    Преобразует объект Lot в словарь.
    :param lot: объект Lot
    :return: словарь с данными о лоте
    """
    return {
        'id': lot.id,
        'title': lot.title,
        'description': lot.description,
        'current_bid': lot.current_bid,
        'seller_link': lot.seller.telegram_link,
        'location': lot.location,
        'next_bid': lot.next_bid,
        'last_bidder': lot.get_last_bidder(),
        'images': lot.images.path if lot.images else None
    }

def send_all_active_auctions_to_channel(request):
    """
    Функция для отправки всех активных лотов в канал
    :param request:
    :return: JSON-ответ
    """
    logging.info("Функция send_all_active_auctions_to_channel была вызвана")
    active_lots = Lot.objects.filter(end_time__gt=timezone.now(), is_sold=False)

    if not active_lots.exists():
        logging.info("Нет активных лотов для отправки")
        return JsonResponse({"status": "success", "message": "Нет активных лотов для отправки"})

    for lot in active_lots:
        try:
            if lot.telegram_message_id:
                update_lot(lot.telegram_message_id, create_auction_message(lot_to_dict(lot)), lot_to_dict(lot))
            else:
                message_id = send_lot_to_channel(lot_to_dict(lot))
                lot.telegram_message_id = message_id
                lot.save()
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения о лоте {lot.id}: {str(e)}")

    return JsonResponse({"status": "success", "message": "Активные лоты обновлены в канале"})

def update_lot(message_id, new_message, lot_data, expired=False):
    """
    Функция для обновления сообщений в канале и обновления лотов
    :param message_id: ID сообщения для редактирования
    :param new_message: Новое сообщение для отправки
    :param lot_data: Данные о лоте
    :param expired: Флаг, указывающий, истек ли срок лота
    """
    try:
        markup = telebot.types.InlineKeyboardMarkup()
        if not expired:
            timer_button = telebot.types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot_data['id']}")
            info_button = telebot.types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
            open_lot_button = telebot.types.InlineKeyboardButton("🛍 Открыть лот", url=generate_deep_link(lot_data['id']))
            markup.add(timer_button, info_button, open_lot_button)

        if lot_data['images']:
            bot.edit_message_caption(chat_id=CHANNEL_ID, message_id=message_id, caption=new_message, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=CHANNEL_ID, message_id=message_id, text=new_message, parse_mode='HTML', reply_markup=markup)

    except telebot.apihelper.ApiTelegramException as e:
        if e.result_json['error_code'] == 400 and "message to edit not found" in e.result_json['description']:
            logging.warning(f"Сообщение с ID {message_id} не найдено, отправка нового сообщения")
            try:
                message_id = send_lot_to_channel(lot_data)
                return message_id
            except Exception as e:
                logging.error(f"Ошибка при отправке нового сообщения о лоте {lot_data['id']}: {str(e)}")
                raise
        elif e.result_json['error_code'] == 400 and "message is not modified" in e.result_json['description']:
            logging.warning(f"Нет новой информации в сообщении с {message_id}: сообщение не изменилось")
        else:
            raise e


@csrf_exempt
def place_bid(request, lot_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            hidden_bid = data.get('hidden_bid', False)
            custom_bid = data.get('custom_bid', False)
            custom_bid_amount = Decimal(data.get('custom_bid_amount', 0))
            user = get_object_or_404(User, pk=user_id)
            lot = get_object_or_404(Lot, pk=lot_id)
            user_profile = get_object_or_404(UserProfile, user=user)

            if custom_bid:
                if user_profile.balance < custom_bid_amount:
                    return JsonResponse({'error': 'Недостаточно средств на балансе'},  status=400)
                new_bid = custom_bid_amount
            else:
                if user_profile.balance < lot.next_bid:
                    return JsonResponse({'error': 'Недостаточно средств на балансе'},  status=400)
                new_bid = lot.next_bid

            Bid.objects.create(lot=lot, bidder=user, amount=new_bid, hidden=hidden_bid)

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
                'last_bid': user.username  # Добавлено поле
            }
            return JsonResponse(lot_data)
        except Exception as e:
            logger.error(f"Ошибка обработки ставки: {e}")
            return JsonResponse({'error': 'Ошибка обработки ставки'}, status=400)
    else:
        raise Http404("Только POST запросы разрешены")


def mark_lot_as_sold(request, lot_id, buyer_id):
    lot = get_object_or_404(Lot, id=lot_id)
    buyer = get_object_or_404(User, id=buyer_id)
    lot.is_sold = True
    lot.save()

    CompletedAuction.objects.create(
        lot=lot,
        final_price=lot.current_bid,
        buyer=buyer,
        is_paid=True
    )

    return JsonResponse({"status": "success", "message": f"Лот {lot.title} продан покупателю {buyer.username}"})


# Функция для повторной активации невыкупленных лотов
def retry_unsold_lots(request):
    unsold_lots = CompletedAuction.objects.filter(is_paid=False)
    for auction in unsold_lots:
        lot = auction.lot
        lot.is_sold = False
        lot.save()
        auction.delete()

    return JsonResponse({"status": "success", "message": "Все не выкупленные лоты возвращены на продажу."})


def update_lots_and_notify_winners():
    """
    Функция для обновления лотов и уведомления победителей каждые 60 секунд
    :return:
    """
    while True:
        try:
            logging.info("Начало обновления лотов и уведомления победителей")
            # Обновление активных лотов
            active_lots = Lot.objects.filter(end_time__gt=timezone.now(), is_sold=False)
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
                    'last_bidder': lot.get_last_bidder(),
                }
                lot_message = create_auction_message(lot_data)

                if lot.telegram_message_id:
                    try:
                        update_lot(lot.telegram_message_id, lot_message, lot_data)
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении сообщения о лоте {lot.id}: {e}")
                else:
                    try:
                        message_id = send_lot_to_channel(lot_data)
                        lot.telegram_message_id = message_id
                        lot.save()
                    except Exception as e:
                        logger.error(f"Ошибка при отправке нового сообщения о лоте {lot.id}: {e}")

            # Уведомление победителей
            expired_lots = Lot.objects.filter(end_time__lt=timezone.now(), is_sold=False)
            for lot in expired_lots:
                highest_bid = Bid.objects.filter(lot=lot).order_by('-amount').first()
                if highest_bid:
                    user = highest_bid.bidder
                    user_profile = get_object_or_404(UserProfile, user=user)
                    username = user_profile.user.username
                    message = (
                        f"Поздравляем, вы выиграли лот {lot.title} с финальной ставкой {highest_bid.amount}Р. "
                        f"Пожалуйста, свяжитесь с продавцом по ссылке: {lot.seller.telegram_link} для завершения сделки."
                    )
                    document_path = lot.document.path
                    logging.info(f"Отправка уведомления пользователю {username} о выигрыше лота {lot.id}")

                    try:
                        bot.send_message(username, message)
                        with open(document_path, 'rb') as doc:
                            bot.send_document(username, doc)
                        lot.is_sold = True
                        lot.save()

                        # Создание записи в CompletedAuction
                        CompletedAuction.objects.create(
                            lot=lot,
                            final_price=highest_bid.amount,
                            buyer=user,
                            is_paid=False,
                            completed_at=timezone.now()
                        )

                        # Снятие суммы ставки с баланса пользователя
                        user_profile.balance -= highest_bid.amount
                        user_profile.successful_payments += 1
                        if user_profile.balance > 500 or user_profile.successful_payments >= 10:
                            user_profile.auto_bid_access = True
                        user_profile.save()

                        # Обновление сообщения в канале, чтобы сделать лот недоступным для ставок
                        close_auction_message = f"Лот {lot.title} завершен. финальная ставка была {highest_bid.amount}Р."
                        update_lot(lot.telegram_message_id, close_auction_message, lot_data, expired=True)
                    except telebot.apihelper.ApiTelegramException as e:
                        logging.error(f"Ошибка при отправке уведомления пользователю {username}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов и уведомлении победителей: {e}")

        time.sleep(60)  # Обновление и уведомление каждые 60 секунд


@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        return redirect('login')

    lots = Lot.objects.filter(created_by=request.user)
    return render(request, 'admin_dashboard.html', {'lots': lots})

@login_required
def create_lot(request):
    if not request.user.is_superuser:
        return redirect('login')

    if request.method == 'POST':
        form = LotForm(request.POST, request.FILES)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.created_by = request.user
            lot.seller = get_object_or_404(Seller, user=request.user)
            lot.save()
            return redirect('admin_dashboard')
    else:
        form = LotForm()
    return render(request, 'create_lot.html', {'form': form})

@login_required
def schedule_lot(request, lot_id):
    if not request.user.is_superuser:
        return redirect('login')

    lot = get_object_or_404(Lot, pk=lot_id)
    if request.method == 'POST':
        scheduled_time = request.POST.get('scheduled_time')
        lot.start_time = scheduled_time
        lot.save()
        return redirect('admin_dashboard')
    return render(request, 'schedule_lot.html', {'lot': lot})

@login_required
def delete_lot(request, lot_id):
    if not request.user.is_superuser:
        return redirect('login')

    lot = get_object_or_404(Lot, pk=lot_id)
    if request.method == 'POST':
        penalty = lot.current_bid * Decimal('0.05')
        admin_profile = get_object_or_404(UserProfile, user=request.user)

        if admin_profile.balance >= penalty:
            admin_profile.balance -= penalty
            admin_profile.save()
            lot.delete()
            return redirect('admin_dashboard')
        else:
            return JsonResponse({'error': 'Недостаточно средств на балансе для уплаты штрафа'}, status=400)
    return render(request, 'delete_lot.html', {'lot': lot})

@login_required
def assign_strike(request, user_id):
    if not request.user.is_superuser:
        return redirect('login')

    user = get_object_or_404(User, pk=user_id)
    user_profile = get_object_or_404(UserProfile, user=user)
    user_profile.strike_count += 1
    user_profile.save()

    if user_profile.strike_count > 3:
        user.is_active = False
        user.save()

    return redirect('admin_dashboard')

# Запуск задачи в отдельном потоке
threading.Thread(target=update_lots_and_notify_winners).start()


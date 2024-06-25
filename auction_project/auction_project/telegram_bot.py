import os
import django
from django.middleware.csrf import get_token
import telebot
from telebot import types
import requests
import uuid  # Используем для генерации случайного CSRF токена
from django.conf import settings
import datetime
import pytz
import logging
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_project.settings')
django.setup()

from auction.models import User, UserProfile, Lot

BOT_TOKEN = '7075474227:AAG8Y7jASasiq9pumKmQQn_7L7dTikdF3T4'
CHANNEL_ID = '-1002148978810'
BOT_USERNAME = "My_UniQ_auction_bot"
bot = telebot.TeleBot(BOT_TOKEN)

info_text = """После окончания торгов, победитель должен выйти на связь с продавцом самостоятельно в течение суток. 
Победитель обязан выкупить лот в течение ТРЕХ дней после окончания аукциона.
НЕ ВЫКУП ЛОТА - БАН.
"""


def create_auction_message(lot):
    """
    Создание сообщение о лоте для последующего использования
    :param lot:
    :return:
    """

    message = (
        f"Название: {lot.get('title', 'Нет информации')}\n\n"
        f"Описание: {lot.get('description', 'Нет информации')}\n\n"
        f"Текущая ставка: {lot.get('current_bid', 'Нет информации')}Р\n"
        f"Продавец: {lot.get('seller_link', 'Нет информации')}\n"
        f"Местоположение: {lot.get('location', 'Нет информации')}\n\n"
        f"Следующая ставка: {lot.get('next_bid', 'Нет информации')}\n\n"
        f"{lot.get('last_bid', '_')}\n"
    )

    return message


def send_lot_to_channel(lot):
    """
    Отправляет сообщение о лоте в канал.
    :param lot: объект Lot
    :return: ID отправленного сообщения
    """
    message = create_auction_message({
        'id': lot.id,
        'title': lot.title,
        'description': lot.description,
        'current_bid': lot.current_bid,
        'seller_link': lot.seller.telegram_link,
        'location': lot.location,
        'next_bid': lot.next_bid,
        'last_bidder': lot.get_last_bidder(),
        'images': lot.images.path if lot.images else None
    })
    markup = types.InlineKeyboardMarkup()
    timer_button = types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot.id}")
    info_button = types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
    open_lot_button = types.InlineKeyboardButton("🛍 Открыть лот", url=generate_deep_link(lot.id))
    markup.add(timer_button, info_button, open_lot_button)

    if lot.images:
        with open(lot.images.path, 'rb') as photo:
            message_id = bot.send_photo(CHANNEL_ID, photo, caption=message, reply_markup=markup).message_id
    else:
        message_id = bot.send_message(CHANNEL_ID, message, reply_markup=markup).message_id

    return message_id



def generate_deep_link(lot_id):
    """
    ссылка для перехода в бота с выбранным лотом
    :param lot_id:
    :return:
    """
    return f"https://t.me/{BOT_USERNAME}?start={lot_id}"


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("timer_") or call.data == "info" or call.data.startswith("open_lot_"))
def callback_query(call):
    """
    Обработка кнопок
    :param call:
    :return:
    """
    if call.data.startswith("timer_"):
        lot_id = int(call.data.split("_")[1])
        response = requests.get(f'http://localhost:8000/lots/{lot_id}/')
        if response.status_code == 200:
            lot = response.json()
            end_time = datetime.datetime.fromisoformat(lot['end_time']).replace(tzinfo=pytz.UTC)
            now = datetime.datetime.now(pytz.UTC)
            time_remaining = end_time - now
            bot.answer_callback_query(call.id, f"Лот закроется через: {time_remaining}")

    elif call.data == "info":
        bot.answer_callback_query(call.id, info_text, show_alert=True, cache_time=0)

    elif call.data.startswith("open_lot_"):
        lot_id = int(call.data.split("_")[1])
        deep_link = generate_deep_link(lot_id)
        bot.answer_callback_query(call.id, deep_link, show_alert=True, cache_time=0)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    args = message.text.split()
    if len(args) > 1:
        lot_id = args[1]
        response = requests.get(f'http://localhost:8000/lots/{lot_id}/')
        if response.status_code == 200:
            lot = response.json()
            lot_message = create_auction_message(lot)
            markup = types.InlineKeyboardMarkup()
            timer_button = types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot_id}")
            info_button = types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
            next_bid = lot.get('next_bid')
            bid_button = types.InlineKeyboardButton(f"Сделать ставку {next_bid}Р", callback_data=f"bid_{lot_id}")
            hidden_bid_button = types.InlineKeyboardButton("Настроить скрытую ставку",
                                                           callback_data=f"hidden_bid_{lot_id}")
            media_button = types.InlineKeyboardButton("Смотреть фото/видео", callback_data=f"media_{lot_id}")
            custom_price_button = types.InlineKeyboardButton("Предложить свою цену",
                                                             callback_data=f"custom_price_{lot_id}")
            back_button = types.InlineKeyboardButton("Назад", callback_data="main_menu")
            markup.add(timer_button, info_button)
            markup.add(bid_button)
            markup.add(hidden_bid_button)
            markup.add(media_button)
            markup.add(custom_price_button)
            markup.add(back_button)
            bot.send_message(message.chat.id, lot_message, reply_markup=markup)
    else:
        send_main_menu(message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('bid_'))
def confirm_bid(call):
    lot_id = call.data.split('_')[1]
    user_id = call.from_user.id
    markup = types.InlineKeyboardMarkup()
    confirm_button = types.InlineKeyboardButton("Подтвердить ставку", callback_data=f"confirm_bid_{lot_id}_{user_id}")
    back_button = types.InlineKeyboardButton("Назад", callback_data="main_menu")
    markup.add(confirm_button, back_button)
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Вы уверены, что хотите сделать ставку?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_bid_'))
def place_bid_bot(call):
    try:
        _, action, lot_id, user_id = call.data.split('_', 3)
        user, created = User.objects.get_or_create(username=user_id)
        if created:
            UserProfile.objects.create(user=user)

        # Получение CSRF-токена
        csrf_token_response = requests.get('http://localhost:8000/get_csrf_token/')
        csrf_token = csrf_token_response.json()['csrf_token']

        headers = {
            'X-CSRFToken': csrf_token,
            'Content-Type': 'application/json'
        }
        json_data = {"user_id": user.id}

        response = requests.post(f'http://localhost:8000/lots/{lot_id}/place_bid/', json=json_data, headers=headers)
        if response.status_code == 200:
            lot = response.json()
            lot_message = create_auction_message(lot)
            markup = types.InlineKeyboardMarkup()
            timer_button = types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot_id}")
            info_button = types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
            bid_button = types.InlineKeyboardButton(f"Сделать ставку {lot['next_bid']}Р", callback_data=f"bid_{lot_id}")
            hidden_bid_button = types.InlineKeyboardButton("Настроить скрытую ставку",
                                                           callback_data=f"hidden_bid_{lot_id}")
            media_button = types.InlineKeyboardButton("Смотреть фото/видео", callback_data=f"media_{lot_id}")
            custom_price_button = types.InlineKeyboardButton("Предложить свою цену",
                                                             callback_data=f"custom_price_{lot_id}")
            back_button = types.InlineKeyboardButton("Назад", callback_data="main_menu")
            markup.add(timer_button, info_button)
            markup.add(bid_button)
            markup.add(hidden_bid_button)
            markup.add(media_button)
            markup.add(custom_price_button)
            markup.add(back_button)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=lot_message,
                                  reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Не удалось сделать ставку. Пожалуйста, попробуйте позже.")
            send_main_menu(call.message)

    except ValueError as e:
        logging.error(f"Ошибка разбора данных: {e}")
        bot.answer_callback_query(call.id, "Ошибка обработки запроса. Пожалуйста, попробуйте позже.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('hidden_bid_'))
def set_hidden_bid(call):
    lot_id = call.data.split('_')[2]
    user_id = call.from_user.id
    markup = types.InlineKeyboardMarkup()
    confirm_button = types.InlineKeyboardButton("Подтвердить скрытую ставку", callback_data=f"confirm_hidden_bid_{lot_id}_{user_id}")
    back_button = types.InlineKeyboardButton("Назад", callback_data="main_menu")
    markup.add(confirm_button, back_button)
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Вы уверены, что хотите сделать скрытую ставку?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_hidden_bid_'))
def place_hidden_bid(call):
    try:
        _, action, lot_id, user_id = call.data.split('_', 3)
        user = get_object_or_404(User, pk=user_id)
        lot = get_object_or_404(Lot, pk=lot_id)

        # Логика скрытой ставки
        bid = Bid.objects.create(lot=lot, bidder=user, amount=lot.next_bid)

        bot.answer_callback_query(call.id, "Скрытая ставка сделана.", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка при обработке скрытой ставки: {e}")
        bot.answer_callback_query(call.id, "Ошибка обработки скрытой ставки. Пожалуйста, попробуйте позже.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('media_'))
def send_media(call):
    lot_id = call.data.split('_')[1]
    lot = get_object_or_404(Lot, pk=lot_id)
    if lot.images:
        with open(lot.images.path, 'rb') as photo:
            bot.send_document(call.message.chat.id, photo)


@bot.callback_query_handler(func=lambda call: call.data.startswith('custom_price_'))
def custom_price(call):
    lot_id = call.data.split('_')[2]
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Введите сумму ставки:")

    @bot.message_handler(func=lambda message: True)
    def get_custom_price(message):
        try:
            custom_bid = Decimal(message.text)
            user = get_object_or_404(User, pk=user_id)
            lot = get_object_or_404(Lot, pk=lot_id)

            if custom_bid > user.userprofile.balance:
                bot.send_message(message.chat.id, "Недостаточно средств на балансе.")
                return

            Bid.objects.create(lot=lot, bidder=user, amount=custom_bid)
            lot.current_bid = custom_bid
            lot.update_next_bid()
            lot.save()

            bot.send_message(message.chat.id, f"Ставка в {custom_bid}Р сделана.")
        except Exception as e:
            logging.error(f"Ошибка при обработке пользовательской ставки: {e}")
            bot.send_message(message.chat.id, "Ошибка при обработке ставки. Пожалуйста, попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data == 'main_menu')
def go_back(call):
    send_main_menu(call.message)


def send_main_menu(message):
    """
    Отправка главного меню
    :param message:
    :return:
    """
    welcome_text = (
        "Привет, я бот аукционов @My_UniQ_auction_bot\n\n"
        "Я помогу вам следить за выбранными лотами и регулировать ход аукциона.\n"
        "А также буду следить за вашими накопленными баллами.\n\n"
        "Удачных торгов."
    )
    markup = types.InlineKeyboardMarkup()
    my_lots_button = types.InlineKeyboardButton("Мои лоты", callback_data="my_lots")
    rules_button = types.InlineKeyboardButton("Правила", callback_data="rules")
    giveaway_button = types.InlineKeyboardButton("Розыгрыши", callback_data="giveaway")
    leaderboard_button = types.InlineKeyboardButton("Таблица лидеров", callback_data="leaderboard")
    markup.add(my_lots_button, rules_button)
    markup.add(giveaway_button)
    markup.add(leaderboard_button)
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ["my_lots", "rules", "help", "giveaway", "leaderboard"])
def handle_main_menu_options(call):
    """
    Обработка вариантов главного меню
    :param call:
    :return:
    """
    try:
        if call.data == "my_lots":
            user_id = call.from_user.id
            response = requests.get(f'http://localhost:8000/get_user_lots/{user_id}/')
            if response.status_code == 200:
                lots = response.json()
                if 'message' in lots:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                          text=lots['message'])
                else:
                    # Формируем одно сообщение с информацией о лотах
                    lots_message = ""
                    for lot in lots:
                        lot_message = (
                            f"Название: {lot['title']}\n"
                            f"Ссылка на лот: {lot['channel_message_url']}\n"
                            f"Ставка пользователя: {lot['user_bid']}Р\n\n"
                        )
                        lots_message += lot_message

                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                          text=lots_message.strip())
                add_main_menu_button(call.message)
            else:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                      text="Не удалось загрузить ваши лоты.")
                add_main_menu_button(call.message)

        elif call.data == "rules":
            rules_text = (
                "Правила аукциона:\n"
                "1. После окончания торгов, победитель должен выйти на связь с продавцом в течение суток.\n"
                "2. Победитель обязан выкупить лот в течение трех дней после окончания аукциона.\n"
                "3. Невыкуп лота - бан."
            )
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=rules_text)
            add_main_menu_button(call.message)

        elif call.data == "help":
            help_text = (
                "Помощь по аукциону:\n"
                "1. Команда /start - начало работы с ботом.\n"
                "2. Кнопка 'Мои лоты' - отображение всех ваших лотов.\n"
                "3. Кнопка 'Правила' - правила участия в аукционе.\n"
                "4. Кнопка 'РОЗЫГРЫШ' - информация о текущих розыгрышах.\n"
                "5. Кнопка 'Таблица лидеров' - текущие лидеры аукциона."
            )
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=help_text)
            add_main_menu_button(call.message)

        elif call.data == "giveaway":
            giveaway_text = (
                "Текущие розыгрыши:\n"
                "1. Розыгрыш лота 1 - участвуйте и выигрывайте!\n"
                "2. Пользователь 2 - 4500 баллов.\n"
                "3. Пользователь 3 - 4000 баллов."
            )
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=giveaway_text)
            add_main_menu_button(call.message)

        elif call.data == "leaderboard":
            leaderboard_text = "Таблица лидеров аукциона будет тут"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=leaderboard_text)
            add_main_menu_button(call.message)
    except Exception as e:
        # Обработка ошибок
        error_message = f"Произошла ошибка: {str(e)}"
        bot.send_message(chat_id=call.message.chat.id, text=error_message)
        add_main_menu_button(call.message)


def add_main_menu_button(message):
    """
    Добавление кнопки "Главное меню" к сообщению
    :param message:
    :return:
    """
    markup = types.InlineKeyboardMarkup()
    main_menu_button = types.InlineKeyboardButton("Главное меню", callback_data="main_menu")
    markup.add(main_menu_button)
    bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)


def run_bot():
    """
    Запуск бота
    """
    bot.infinity_polling()


if __name__ == '__main__':
    run_bot()


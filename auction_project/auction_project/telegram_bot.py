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

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_project.settings')
django.setup()

from auction.models import User, UserProfile

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
        f"Следующая ставка: {lot.get('next_bid', 'Нет информации')}\n"
    )

    return message


def send_lot_to_channel(lot):
    """
    Сообщения отправляемые в канал
    :param lot:
    :return:
    """
    message = create_auction_message(lot)
    markup = types.InlineKeyboardMarkup()
    timer_button = types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot['id']}")
    info_button = types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
    open_lot_button = types.InlineKeyboardButton("🛍 Открыть лот", url=generate_deep_link(lot['id']))
    markup.add(timer_button, info_button, open_lot_button)

    if lot.get('images'):
        with open(lot['images'], 'rb') as photo:
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
            next_bid = lot.get('next_bid', 'Нет информации')  # Используем get() с значением по умолчанию
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
            response = requests.get(f'http://localhost:8000/user_lots/{user_id}/')
            if response.status_code == 200:
                lots = response.json()
                if 'message' in lots:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                          text=lots['message'])
                else:
                    for lot in lots:
                        lot_message = create_auction_message(lot)
                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                              text=lot_message)
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
        print(f"Error in handle_main_menu_options: {str(e)}")


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


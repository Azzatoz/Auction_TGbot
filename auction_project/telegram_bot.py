import telebot
from telebot import types
import requests
import datetime

BOT_TOKEN = '7075474227:AAG8Y7jASasiq9pumKmQQn_7L7dTikdF3T4'
CHANNEL_ID = '-1002148978810'

bot = telebot.TeleBot(BOT_TOKEN)

info_text = """После окончания торгов, победитель должен выйти на связь с продавцом самостоятельно в течение суток. 
Победитель обязан выкупить лот в течение ТРЕХ дней после окончания аукциона.
НЕ ВЫКУП ЛОТА - БАН.
"""

def create_auction_message(lot):
    return f"{lot['title']}\n\n{lot['description']}\n\nТекущая ставка: {lot['start_price']}Р\nПродавец: {lot['seller_link']}"

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data.startswith("timer_"):
        lot_id = int(call.data.split("_")[1])
        response = requests.get(f'http://localhost:8000/lots/{lot_id}/')
        if response.status_code == 200:
            lot = response.json()
            end_time = datetime.datetime.fromisoformat(lot['end_time'])
            time_remaining = end_time - datetime.datetime.now()
            bot.answer_callback_query(call.id, f"Лот закроется через: {time_remaining}")

    elif call.data == "info":
        bot.answer_callback_query(call.id, info_text, show_alert=True, cache_time=0)

    elif call.data.startswith("open_lot_"):
        lot_id = int(call.data.split("_")[2])
        response = requests.get(f'http://localhost:8000/lots/{lot_id}/')
        if response.status_code == 200:
            lot = response.json()
            lot_message = create_auction_message(lot)
            markup = types.InlineKeyboardMarkup()
            timer_button = types.InlineKeyboardButton("⏲ Таймер", callback_data=f"timer_{lot_id}")
            info_button = types.InlineKeyboardButton("ℹ️ Инфо", callback_data="info")
            markup.add(timer_button, info_button)
            bot.send_message(call.message.chat.id, lot_message, reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "Привет! Добро пожаловать на аукцион.")

def run_bot():
    bot.infinity_polling()

if __name__ == '__main__':
    run_bot()
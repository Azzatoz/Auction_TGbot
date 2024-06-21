import os
import subprocess
import threading
import requests
import time


def run_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_project.settings')
    manage_py_path = os.path.join(os.path.dirname(__file__), 'manage.py')
    subprocess.call(['python', manage_py_path, 'runserver'])


def run_telegram_bot():
    from auction_project import telegram_bot
    telegram_bot.run_bot()


def send_active_auctions():
    try:
        response = requests.get('http://localhost:8000/send_all_active_auctions/')
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке активных лотов: {e}")


if __name__ == '__main__':
    django_thread = threading.Thread(target=run_django)
    telegram_thread = threading.Thread(target=run_telegram_bot)

    django_thread.start()
    telegram_thread.start()

    # Ожидание, чтобы сервер Django успел запуститься перед отправкой запроса
    time.sleep(5)

    send_active_auctions()

    django_thread.join()
    telegram_thread.join()
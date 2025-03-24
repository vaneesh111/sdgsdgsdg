import time
import telebot
from telebot import types
import os
import datetime
import requests
from requests.auth import HTTPBasicAuth
from googleapiclient.discovery import build
from google.oauth2 import service_account
import re
import logging
from threading import Thread

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{datetime.date.today()}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации из переменных окружения или файла конфигурации
# Для безопасности рекомендуется использовать переменные окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '5932755890:AAGVqa8GLtYbAThBF18oK7UxAxCQmXMuRg4')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '-1002214099733')
GOIP_URL = os.getenv('GOIP_URL', 'http://10.90.235.183/default/en_US/tools.html?type=sms_inbox')
GOIP_USER = os.getenv('GOIP_USER', 'admin')
GOIP_PASSWORD = os.getenv('GOIP_PASSWORD', 'Atdhfkm2023')
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
GOOGLE_SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID', '16P1aw-B05SroxspkzleViKv0n1eJiu1y8GkYzKBIcZQ')
GOOGLE_SHEET_RANGE = os.getenv('GOOGLE_SHEET_RANGE', 'test!A:D')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '600'))  # Интервал проверки в секундах

# Инициализация Telegram бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Настройка Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, GOOGLE_CREDENTIALS_FILE)

try:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials).spreadsheets().values()
    logger.info("Успешно подключено к Google Sheets.")
except Exception as e:
    logger.error(f"Ошибка при подключении к Google Sheets: {e}")
    exit(1)

# Функция для получения новых SMS
def get_new_sms(sms_last):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        auth = HTTPBasicAuth(GOIP_USER, GOIP_PASSWORD)
        response = requests.get(GOIP_URL, auth=auth, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
        text = response.text

        # Парсинг SMS из ответа
        str_start = "sms_row_insert(l3_sms_store, sms, pos, 3"
        str_end = "sms_row_insert(l4_sms_store, sms, pos, 4);"
        start_index = text.find(str_start) + 48
        end_index = text.find(str_end)
        if start_index == -1 or end_index == -1:
            logger.warning("Не удалось найти нужные метки в ответе GoIP.")
            return []

        result = text[start_index:end_index]
        sms_entries = result.split('"')
        new_sms_list = []

        for entry in sms_entries:
            if 'MIR-2001' in entry or 'MIR-1228' in entry:
                parts = entry.split(',', maxsplit=2)
                if len(parts) < 3:
                    continue
                parts = parts[::-1]  # Разворот массива
                message = parts[0]
                date_str = parts[2].split()[0]
                time_str = parts[2].split()[1][0:5]

                # Динамическое определение года
                current_year = datetime.datetime.now().year
                # Если SMS содержит год, извлеките его, иначе используйте текущий год
                # Предположим, что SMS не содержит года
                date_formatted = f"{date_str[3:5]}.{date_str[0:2]}.{current_year}"

                # Извлечение суммы из сообщения
                amount_match = re.search(r'(\d+[\.,]?\d*)\s*р', message)
                amount = amount_match.group(1) if amount_match else "0"

                # Фильтрация по дате
                try:
                    sms_date = datetime.datetime.strptime(date_formatted, "%d.%m.%Y")
                except ValueError as ve:
                    logger.error(f"Ошибка парсинга даты: {date_formatted} - {ve}")
                    continue

                start_date = datetime.datetime.strptime("15.11.2024", "%d.%m.%Y")
                if sms_date < start_date or sms_date > datetime.datetime.now():
                    logger.info(f"SMS с датой {date_formatted} отфильтрована по дате.")
                    continue

                # Проверка, что это перевод
                if not re.search(r'(?i)\bперевод\b', message):
                    logger.info(f"SMS '{message}' не является переводом.")
                    continue

                # Проверка, является ли SMS новым
                if sms_last and message == sms_last[0]:
                    logger.info("Новые SMS отсутствуют.")
                    return new_sms_list[::-1]

                sms_entry = [message, date_formatted, time_str, amount]
                logger.info(f"Найдено новое SMS: {sms_entry}")
                new_sms_list.append(sms_entry)

        return new_sms_list[::-1]
    except Exception as e:
        logger.error(f"Ошибка при получении SMS: {e}")
        return []

# Функция для проверки и отправки новых SMS
def check_and_send_sms():
    try:
        # Получение последних SMS из Google Sheets
        result = service.get(
            spreadsheetId=GOOGLE_SPREADSHEET_ID,
            range=GOOGLE_SHEET_RANGE
        ).execute()
        data = result.get('values', [])
        sms_last = data[-1] if data else None
        logger.info(f"Последнее SMS из Google Sheets: {sms_last}")

        # Получение новых SMS
        new_sms = get_new_sms(sms_last)
        sms_count = len(new_sms)

        if sms_count > 0:
            for sms in new_sms:
                body = {'values': [sms]}
                service.append(
                    spreadsheetId=GOOGLE_SPREADSHEET_ID,
                    range=GOOGLE_SHEET_RANGE,
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()
            message = f'Поступило новых SMS: {sms_count} шт.'
            bot.send_message(TELEGRAM_GROUP_ID, message)
            logger.info(message)
        else:
            logger.info("Новых SMS не найдено.")
    except Exception as e:
        logger.error(f"Ошибка при проверке и отправке SMS: {e}")

# Обработчик команды /start и /help
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, "Бот для мониторинга SMS активен и работает.")

# Обработчик текстовых сообщений
@bot.message_handler(content_types=["text"])
def echo(message):
    if "Антон" in message.text:
        logger.info("Получено сообщение с текстом 'Антон'.")
        bot.send_message(message.chat.id, message.chat.id)

# Функция для запуска бота
def polling_bot():
    try:
        logger.info("Запуск Telegram бота.")
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Ошибка в polling_bot: {e}")
        time.sleep(15)
        polling_bot()

# Функция для планировщика проверки SMS
def scheduler():
    while True:
        check_and_send_sms()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # Запуск бота и планировщика в отдельных потоках
    Thread(target=polling_bot).start()
    Thread(target=scheduler).start()

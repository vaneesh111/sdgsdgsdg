import telepot
from telepot.loop import MessageLoop
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

bot = telepot.Bot(TELEGRAM_TOKEN)

# Храним список ID сообщений, которые бот отправляет
sent_message_ids = []

def handle_message(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)

    if content_type == 'text':
        text = msg['text']

        if text == '/clear':
            clear_chat(chat_id)
        elif text == '/ac':
            from ami import notify_active_calls
            notify_active_calls()
        elif text == '/help':
            send_help_message(chat_id)

def send_help_message(chat_id):
    help_message = (
        "📝 Доступные команды:\n"
        "/ac - Показать все входящие звонки\n"
        "/clear - Удалить все сообщения бота\n"
    )
    send_telegram_message(help_message, chat_id=chat_id)

def send_telegram_message(message, chat_id=TELEGRAM_CHAT_ID, reply_markup=None):
    sent_message = bot.sendMessage(chat_id, message, reply_markup=reply_markup)
    sent_message_ids.append(sent_message['message_id'])

def clear_chat(chat_id):
    for message_id in sent_message_ids:
        try:
            bot.deleteMessage((chat_id, message_id))
        except telepot.exception.TelegramError as e:
            print(f"Ошибка при удалении сообщения {message_id}: {e}")
    sent_message_ids.clear()

MessageLoop(bot, handle_message).run_as_thread()
print('Бот запущен...')

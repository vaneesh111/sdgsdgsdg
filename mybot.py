import os
import telebot
from telebot import types

# Получаем токен и username администратора из переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8066227955:AAEijQSHQ_GPgYfC5Id8LR8YYgiR-P5IPxQ")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@raketa_net_support")

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Переменная для хранения chat_id администратора
admin_chat_id = 1389379073

# Словарь для хранения данных пользователя
user_data = {}

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    global admin_chat_id
    user = message.from_user
    
    # Проверяем, является ли пользователь администратором
    if user.username == ADMIN_USERNAME.replace('@', ''):
        admin_chat_id = message.chat.id
        bot.reply_to(message, "Вы администратор. Теперь я буду отправлять вам данные абонентов.")
    
    # Создаем inline-кнопку
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("Хочу стать абонентом✅", callback_data="become_subscriber")
    markup.add(button)
    bot.send_message(message.chat.id, "Нажмите кнопку, чтобы стать абонентом.", reply_markup=markup)

# Обработчик нажатия на кнопку
@bot.callback_query_handler(func=lambda call: call.data == "become_subscriber")
def callback_handler(call):
    user_id = call.message.chat.id
    user_data[user_id] = {'step': 'waiting_for_name'}
    bot.send_message(user_id, "Пожалуйста, введите ваше ФИО.")
    bot.answer_callback_query(call.id)

# Обработчик текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    global admin_chat_id
    user_id = message.chat.id
    
    if user_id not in user_data or 'step' not in user_data[user_id]:
        return
    
    if user_data[user_id]['step'] == 'waiting_for_name':
        user_data[user_id]['name'] = message.text
        user_data[user_id]['step'] = 'waiting_for_phone'
        bot.reply_to(message, "Спасибо. Теперь введите ваш номер телефона.")
    
    elif user_data[user_id]['step'] == 'waiting_for_phone':
        user_data[user_id]['phone'] = message.text
        name = user_data[user_id]['name']
        phone = user_data[user_id]['phone']
        
        # Отправляем данные администратору
        if admin_chat_id:
            bot.send_message(admin_chat_id, f"Новый абонент:\nФИО: {name}\nТелефон: {phone}")
        else:
            print(f"Admin chat_id не установлен. Новый абонент: {name}, {phone}")
        
        bot.reply_to(message, "Спасибо! Скоро с вами свяжутся.")
        del user_data[user_id]  # Очищаем данные после завершения

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен!")
    bot.polling(none_stop=True)

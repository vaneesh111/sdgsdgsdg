import socket
import time
import requests
from threading import Timer
from config import ASTERISK_HOST, ASTERISK_PORT, ASTERISK_USERNAME, ASTERISK_PASSWORD, WAIT_TIME_THRESHOLD
from telegram_bot import send_telegram_message
from yougile import search_yougile_task, search_billing
from database import update_call_status, update_call_duration, execute_query, fetch_query
from datetime import datetime, timedelta
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

# Храним информацию о вызовах по уникальному ID канала и счетчик вызовов
active_calls = {}
call_queue = []  # Очередь для отслеживания порядка звонков


def ami_login(sock):
    """Функция для подключения и авторизации в Asterisk AMI."""
    login_command = (
        f"Action: Login\r\n"
        f"Username: {ASTERISK_USERNAME}\r\n"
        f"Secret: {ASTERISK_PASSWORD}\r\n"
        f"ActionID: 1\r\n\r\n"
    )
    sock.send(login_command.encode())
    time.sleep(1)
    response = sock.recv(4096).decode()
    if "Success" in response:
        print("Успешно подключен к Asterisk AMI")
    else:
        print("Ошибка при подключении к Asterisk AMI")
        print(response)


def send_call_update(call_id, phone_number, call_status, duration="00:00"):
    """
    Отправляем запрос в ваше веб-приложение (app.py) о смене статуса звонка.
    Для надёжности отбрасываем дробную часть UniqueID:
    """
    call_id_str = str(call_id).split('.')[0]
    url = (
        f"http://localhost:80/num/{phone_number}/"
        f"{call_status}?call_id={call_id_str}&duration={duration}"
    )
    print(f"Отправка запроса на URL: {url}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print(f"Успешно отправлено уведомление о вызове: {url}")
        else:
            print(f"Ошибка при отправке уведомления: {response.status_code}")
            print(f"Ответ от сервера: {response.text}")
    except requests.RequestException as e:
        print(f"Ошибка запроса {url}: {e}")


def add_call(call_id, phone_number, status, yougile_task):
    """
    Добавление нового вызова в базу данных (локальная функция).
    Аналогичная есть в database.py, но здесь используется своя.
    Обязательно обрезаем дробную часть у call_id.
    """
    call_id_str = str(call_id).split('.')[0]
    print(f"Добавление вызова в базу: ID={call_id_str}, номер={phone_number}, статус={status}")
    query = '''INSERT IGNORE INTO calls (
        id, phone_number, date_time, duration, line, fio,
        contract, balance, min_payment, status, yougile_task
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'''
    args = (
        call_id_str,
        phone_number,
        datetime.now(),
        "00:00",
        "500050",
        "Неизвестно",
        "Неизвестно",
        0.0,
        0.0,
        status,
        yougile_task
    )
    execute_query(query, args)


def notify_active_calls():
    """Отправляет в Telegram список всех активных входящих звонков."""
    active_incoming_calls = [
        (unique_id, call_info) for unique_id, call_info in active_calls.items()
        if call_info['state'] == 'New' and not call_info['call_finished']
    ]
    
    if not active_incoming_calls:
        send_telegram_message("🔍 В данный момент активных входящих звонков нет.")
    else:
        message = "📞 Список активных входящих звонков:\n"
        for index, (unique_id, call_info) in enumerate(active_incoming_calls, start=1):
            caller_id = call_info['caller_id']
            duration = time.time() - call_info['start_time']
            state = "Ожидание оператора" if not call_info['operator_connected'] else "Разговор с оператором"
            message += (
                f"{index}. Номер: {caller_id}, "
                f"Длительность: {int(duration)} сек, "
                f"Состояние: {state}\n"
            )
        send_telegram_message(message)


def normalize_phone_number(phone_number):
    """Нормализует номер телефона, убирая все нецифровые символы и беря последние 10 цифр."""
    # Убираем все нецифровые символы
    digits = ''.join(filter(str.isdigit, phone_number))
    # Берем последние 10 цифр
    return digits[-10:]


def handle_ami_event(event_data):
    """Функция обработки события Asterisk AMI."""
    lines = event_data.split("\r\n")
    event = {}
    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            event[key.strip()] = value.strip()

    # Обработка события Newchannel (новый входящий или исходящий вызов)
    if event.get("Event") == "Newchannel":
        caller_id = event.get("CallerIDNum", "Unknown")
        unique_id = event.get("Uniqueid", None)
        exten = event.get("Exten", "")

        if not unique_id:
            return

        # Проверяем, является ли звонок исходящим на номер 83955500050
        if exten == "83955500050":
            print(f"[DEBUG] Звонок с {caller_id} на {exten} игнорируется как исходящий")
            return

        # Исходящий звонок: короткий CallerIDNum (внутренний номер) и длинный Exten (внешний номер)
        if len(caller_id) <= 4 and len(exten) > 4 and exten[0].isdigit():
            active_calls[unique_id] = {
                'caller_id': caller_id,
                'destination': exten,
                'start_time': time.time(),
                'state': 'Outgoing',
                'operator_connected': False,
                'call_finished': False,
                'call_answered': False
            }
            # Уведомляем в Telegram, но не добавляем в базу и не отправляем на сайт
            send_telegram_message(
                f"📞 Начало исходящего звонка от {caller_id} на номер {exten}"
            )

        # Входящий звонок
        elif caller_id != "<unknown>" and len(caller_id) > 4:
            active_calls[unique_id] = {
                'caller_id': caller_id,
                'start_time': time.time(),
                'state': 'New',
                'waiting_timer': None,
                'operator_connected': False,
                'call_finished': False,
                'call_waited_too_long': False
            }
            active_calls[unique_id]['waiting_timer'] = Timer(
                WAIT_TIME_THRESHOLD,
                notify_waiting_for_operator,
                [unique_id]
            )
            active_calls[unique_id]['waiting_timer'].start()
            call_queue.append(caller_id)

            yougile_url = search_yougile_task(caller_id)
            billing_url = search_billing(caller_id)

            if yougile_url:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Открыть задачу в YouGile", url=yougile_url),
                    InlineKeyboardButton(text="Открыть данные в Billing", url=billing_url)
                ]])
                send_telegram_message(
                    f"📞 Новый входящий вызов от {caller_id} (Очередь: {len(call_queue)})",
                    reply_markup=keyboard
                )
            else:
                send_telegram_message(
                    f"📞 Новый входящий вызов от {caller_id} (Очередь: {len(call_queue)}). "
                    f"Задача в YouGile не найдена."
                )

            add_call(unique_id, caller_id, "incoming", yougile_url)
            send_call_update(unique_id, caller_id, "incoming")

    # Обработка события VarSet (оператор подключился или абонент ответил)
    elif event.get("Event") == "VarSet":
        unique_id = event.get("Uniqueid", None)
        variable = event.get("Variable", None)
        value = event.get("Value", None)

        if unique_id in active_calls and variable == "BRIDGEPEER" and value:
            call_info = active_calls[unique_id]
            if call_info['state'] == 'Outgoing' and not call_info['call_answered']:
                call_info['call_answered'] = True
                call_info['operator_connected'] = True
                send_telegram_message(
                    f"☎️ Абонент {call_info['destination']} взял трубку — идет разговор с оператором {call_info['caller_id']}."
                )

                # Нормализуем номер назначения для проверки
                normalized_destination = normalize_phone_number(call_info['destination'])

                # Проверяем, был ли пропущенный звонок с этого номера в последние 24 часа
                query = """
                    SELECT id, date_time
                    FROM calls
                    WHERE RIGHT(phone_number, 10) = %s
                    AND status = 'missed'
                    AND date_time >= %s
                    ORDER BY date_time DESC
                    LIMIT 1
                """
                check_time = datetime.now() - timedelta(hours=24)
                result = fetch_query(query, (normalized_destination, check_time))
                if result:
                    missed_call = result[0]
                    missed_call_id = missed_call['id']
                    # Обновляем статус пропущенного звонка на 'call_backed'
                    update_call_status(missed_call_id, "call_backed")
                    send_telegram_message(
                        f"ℹ️ Пропущенный звонок с ID {missed_call_id} от {call_info['destination']} "
                        f"обновлен до статуса 'call_backed' после успешного исходящего звонка."
                    )

            elif call_info['state'] == 'New' and not call_info['operator_connected']:
                call_info['operator_connected'] = True
                if call_info['waiting_timer']:
                    call_info['waiting_timer'].cancel()
                send_telegram_message(
                    f"☎️ Пользователь {call_info['caller_id']} разговаривает с оператором."
                )
                send_call_update(unique_id, call_info['caller_id'], "incoming")

    # Обработка события Hangup (завершение вызова)
    elif event.get("Event") == "Hangup":
        unique_id = event.get("Uniqueid", None)
        reason = event.get("Cause-txt", "Неизвестная причина")

        if unique_id and unique_id in active_calls:
            call_info = active_calls[unique_id]
            if call_info['call_finished']:
                return

            call_info['call_finished'] = True
            if call_info.get('waiting_timer'):
                call_info['waiting_timer'].cancel()

            duration = time.time() - call_info['start_time']
            duration_formatted = time.strftime('%H:%M:%S', time.gmtime(duration))

            if call_info['state'] == 'Outgoing':
                if call_info['call_answered']:
                    send_telegram_message(
                        f"🔚 Исходящий звонок от {call_info['caller_id']} на {call_info['destination']} окончен. "
                        f"Длительность: {duration_formatted}."
                    )
                else:
                    send_telegram_message(
                        f"📴 Не удалось дозвониться до абонента {call_info['destination']} от {call_info['caller_id']}. "
                        f"Причина: {reason}."
                    )
            else:  # Входящий звонок
                caller_id = call_info['caller_id']
                if duration < WAIT_TIME_THRESHOLD and not call_info['operator_connected']:
                    send_telegram_message(
                        f"❗ Звонок от {caller_id} был сброшен до попадания в очередь."
                    )
                    send_call_update(unique_id, caller_id, "missed", duration_formatted)
                elif call_info['operator_connected']:
                    send_telegram_message(
                        f"🔚 Звонок окончен одной из сторон. Номер: {caller_id}."
                    )
                    send_call_update(unique_id, caller_id, "answered", duration_formatted)
                else:
                    send_telegram_message(
                        f"🔚 Звонок от {caller_id} завершен. Причина: {reason}."
                    )
                    send_call_update(unique_id, caller_id, "missed", duration_formatted)
                if caller_id in call_queue:
                    call_queue.remove(caller_id)

            active_calls.pop(unique_id, None)


def notify_waiting_for_operator(unique_id):
    """Функция уведомления, если пользователь ожидает на роботе более WAIT_TIME_THRESHOLD секунд."""
    if unique_id in active_calls:
        call_info = active_calls[unique_id]
        caller_id = call_info['caller_id']
        if not call_info['operator_connected']:
            send_telegram_message(
                f"⏳ Пользователь {caller_id} ждет ответа от оператора"
            )


def listen_ami_events(sock):
    """Функция для прослушивания событий AMI."""
    buffer = ""
    while True:
        data = sock.recv(1024).decode()
        buffer += data
        while "\r\n\r\n" in buffer:
            event, buffer = buffer.split("\r\n\r\n", 1)
            handle_ami_event(event)


def main():
    """Основная функция для подключения и прослушивания событий."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((ASTERISK_HOST, ASTERISK_PORT))
        ami_login(sock)
        listen_ami_events(sock)
    except Exception as e:
        send_telegram_message(f"⚠️ Ошибка подключения к Asterisk AMI: {e}")
    finally:
        sock.close()


if __name__ == "__main__":
    main()

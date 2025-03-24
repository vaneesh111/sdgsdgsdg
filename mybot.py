from telethon import TelegramClient, events, Button
import requests
import re
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
import logging
from switch3 import parse_switch_sv
from telnet import main as telnet_diag
from telnet import telnet_connect_and_search
import asyncio

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Настройки API и токенов
API_ID = '25748036'
API_HASH = 'ecb6f32632cd81aa04a11bb1c6132150'
BOT_TOKEN = '7582641889:AAEyZueE2cEbrHWHRxzxvwUkqU48vNtzRcE'

# Настройки YouGile API
YOUGILE_URL = "https://ru.yougile.com/api-v2/tasks"
YOUGILE_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer dgSMb2NTAPnUHyAtnvrDAMAAbZuWwHoB2Dpv6E4zd0yHe0spEt9f3i0ElIqN61OM"
}
COLUMN_ID = "8e439bc4-b236-4e07-a230-1aa0f2614062"

# ID группы для отправки фотоотчётов
GROUP_CHAT_ID = '@raketamontage'  # Замените на реальный ID вашей группы

# Конфигурация базы данных
db_config = {
    'host': '192.168.10.79',
    'user': 'vanesh',
    'password': 'Exonet_15',
    'db': 'raketa',
    'charset': 'utf8mb4',
}

# Создание строки подключения
db_url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}/{db_config['db']}?charset={db_config['charset']}"

# Создание Engine с пулом соединений
engine = create_engine(db_url, poolclass=QueuePool, pool_size=5, max_overflow=10, pool_recycle=3600)

# Инициализация бота
client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

MAX_OTHER_PHOTOS = 5  # Максимальное количество фотографий для "другое"

# Этапы фотоотчёта
PHOTO_STEPS = [
    "📸 Узел Связи в открытом виде",
    "📸 Прокладку линии связи",
    "📸 Ввод кабеля в помещение",
    "📸 Наклейку на кабеле в Узле Связи",
    "📸 Кабельсборка",
    "📸 Бирку на кабеле у абонента",
    "📸 Тест скорости",
    "📸 Оплата",
    "📸 другое"  # Добавлена запятая и новый шаг
]

# Хранение состояния задач и пагинации пользователей
user_task_status = {}  # Инициализируем как пустой словарь

user_search_results = {}
user_search_page = {}
RESULTS_PER_PAGE = 10  # Количество результатов на страницу

# Функция поиска абонентов (обновлённая)
def search_abonents(query):
    # Нормализация запроса
    query = query.lower().strip()

    # Обработка телефонных номеров
    phone_pattern = re.compile(r'^(?:\+7|8)?(\d{10})$')
    phone_match = phone_pattern.match(query)
    if phone_match:
        query = phone_match.group(1)  # Получаем 10-значный номер

    # Разделение запроса на части для поиска по ФИО
    name_parts = query.split()

    try:
        # Подключение к базе данных через пул
        with engine.connect() as connection:
            # Поиск в таблице abonents
            sql_abonents = text("""
                SELECT 
                    name AS fio, 
                    contract_number, 
                    NULL AS address, 
                    sms AS phone_number
                FROM abonents
                WHERE LOWER(name) LIKE :like_query
                   OR LOWER(contract_number) LIKE :like_query
                   OR sms LIKE :like_query
            """)
            like_query = f"%{query}%"
            results_abonents = connection.execute(sql_abonents, {"like_query": like_query}).mappings().fetchall()

            # Дополнительный поиск по частям ФИО в abonents
            if len(name_parts) > 1:
                fio_query = ' '.join(name_parts)
                sql_fio_abonents = text("""
                    SELECT 
                        name AS fio, 
                        contract_number, 
                        NULL AS address, 
                        sms AS phone_number
                    FROM abonents
                    WHERE LOWER(name) LIKE :fio_query
                """)
                results_abonents += connection.execute(sql_fio_abonents, {"fio_query": f"%{fio_query}%"}).mappings().fetchall()

            # Поиск в таблице sv_carbua
            sql_sv_carbua = text("""
                SELECT 
                    Name AS fio, 
                    Contract_Num AS contract_number, 
                    CONCAT_WS(', ', City, Street, S_Number, A_Home_Number, Custom_Address) AS address, 
                    CONCAT_WS(', ', SMS, Phone1, Phone2, Phone3) AS phone_number
                FROM sv_carbua
                WHERE LOWER(Name) LIKE :like_query
                   OR LOWER(Contract_Num) LIKE :like_query
                   OR SMS LIKE :like_query
                   OR Phone1 LIKE :like_query
                   OR Phone2 LIKE :like_query
                   OR Phone3 LIKE :like_query
            """)
            results_sv_carbua = connection.execute(sql_sv_carbua, {"like_query": like_query}).mappings().fetchall()

            # Дополнительный поиск по частям ФИО в sv_carbua
            if len(name_parts) > 1:
                fio_query = ' '.join(name_parts)
                sql_fio_sv_carbua = text("""
                    SELECT 
                        Name AS fio, 
                        Contract_Num AS contract_number, 
                        CONCAT_WS(', ', City, Street, S_Number, A_Home_Number, Custom_Address) AS address, 
                        CONCAT_WS(', ', SMS, Phone1, Phone2, Phone3) AS phone_number
                    FROM sv_carbua
                    WHERE LOWER(Name) LIKE :fio_query
                """)
                results_sv_carbua += connection.execute(sql_fio_sv_carbua, {"fio_query": f"%{fio_query}%"}).mappings().fetchall()

        # Объединение результатов и удаление дубликатов
        combined_results = list(results_abonents) + list(results_sv_carbua)
        unique_results = {}
        for abonent in combined_results:
            key = (abonent['fio'], abonent['contract_number'])
            if key not in unique_results:
                unique_results[key] = {
                    'fio': abonent['fio'],
                    'contract_number': abonent['contract_number'],
                    'address': abonent['address'] if abonent['address'] else '—',
                    'phone_number': abonent['phone_number'] if abonent['phone_number'] else '—'
                }

        logging.info(f"Найдено {len(unique_results)} уникальных результатов для запроса: {query}")
        return list(unique_results.values())

    except SQLAlchemyError as e:
        logging.error(f"Ошибка при выполнении поиска: {e}")
        return []

# Получение списка задач из YouGile
def get_tasks():
    try:
        response = requests.get(YOUGILE_URL, headers=YOUGILE_HEADERS, params={"limit": "9999", "columnId": COLUMN_ID})
        if response.status_code == 200:
            tasks = response.json().get("content", [])
            return tasks
        else:
            logging.error(f"Не удалось получить задачи из YouGile. Статус-код: {response.status_code}")
            return []
    except requests.RequestException as e:
        logging.error(f"Ошибка при запросе к YouGile API: {e}")
        return []

# Команда для получения списка задач
@client.on(events.NewMessage(pattern='/tasks'))
async def list_tasks(event):
    tasks = get_tasks()
    if tasks:
        buttons = []
        for task in tasks:
            task_id = task["id"]
            task_title = task["title"]
            if task_id in user_task_status and user_task_status[task_id]["completed"]:
                task_title += " ✅"
            buttons.append([Button.inline(task_title, data=f"choose_{task_id}")])
        await event.respond("Выберите задачу:", buttons=buttons)
    else:
        await event.respond("Не удалось получить задачи.")

# Обработка выбора задачи
@client.on(events.CallbackQuery(pattern=r"choose_"))
async def choose_task(event):
    task_id = event.data.decode('utf-8').replace("choose_", "")
    if task_id not in user_task_status:
        tasks = get_tasks()
        task_title = next((task["title"] for task in tasks if task["id"] == task_id), "Неизвестная задача")
        user_task_status[task_id] = {
            "completed": False,
            "photos": {step: [] for step in range(len(PHOTO_STEPS))},  # Хранение списка фото
            "active_step": None,
            "title": task_title
        }
    await update_task_buttons(event, task_id)

# Обновление кнопок для шагов и пагинации
async def update_task_buttons(event, task_id):
    task_status = user_task_status[task_id]
    
    # Отправляем текст задачи перед кнопками
    task_description = f"📋 Вы выбрали задачу: *{task_status['title']}*\n\nВыполняйте шаги по порядку или помечайте их как 'Не требовалось'."
    await event.respond(task_description, parse_mode="markdown")

    # Формируем кнопки для шагов
    buttons = []
    for step, photo_list in task_status["photos"].items():
        step_text = PHOTO_STEPS[step]
        if PHOTO_STEPS[step] == "📸 другое":
            if len(photo_list) > 0:
                step_text = f"✅ {step_text} ({len(photo_list)} фото)"
            else:
                step_text = f"{step_text}"
        else:
            if len(photo_list) > 0:
                step_text = f"✅ {step_text}"
        buttons.append([Button.inline(step_text, data=f"step_{task_id}_{step}")])
    
    # Добавляем кнопки навигации, если нужно
    buttons.append([
        Button.inline("Следующая страница", data=f"next_page_{task_id}"),
        Button.inline("Предыдущая страница", data=f"prev_page_{task_id}")
    ])
    buttons.append([Button.inline("Завершить задачу", data=f"complete_{task_id}")])

    # Отправляем кнопки
    await event.respond("Выберите шаг для выполнения:", buttons=buttons)

# Обработка выбора шага
@client.on(events.CallbackQuery(pattern=r"step_"))
async def handle_step(event):
    data = event.data.decode('utf-8').split('_')
    task_id = data[1]
    step = int(data[2])

    if task_id in user_task_status:
        task_status = user_task_status[task_id]
        if PHOTO_STEPS[step] == "📸 другое":
            await event.respond(
                f"Выполните шаг: '{PHOTO_STEPS[step]}' (можно отправить несколько фотографий) или нажмите 'Не требовалось', если шаг не нужен.",
                buttons=[
                    Button.inline("Не требовалось", data=f"skip_{task_id}_{step}"),
                    Button.inline("Назад", data=f"back_{task_id}")
                ]
            )
        else:
            if len(task_status["photos"][step]) > 0:
                await event.answer(f"Шаг '{PHOTO_STEPS[step]}' уже выполнен!", alert=True)
                return
            await event.respond(
                f"Выполните шаг: '{PHOTO_STEPS[step]}' или нажмите 'Не требовалось', если шаг не нужен.",
                buttons=[
                    Button.inline("Не требовалось", data=f"skip_{task_id}_{step}"),
                    Button.inline("Назад", data=f"back_{task_id}")
                ]
            )
        task_status["active_step"] = step

# Пропуск шага
@client.on(events.CallbackQuery(pattern=r"skip_"))
async def skip_step(event):
    data = event.data.decode('utf-8').split('_')
    task_id = data[1]
    step = int(data[2])

    if task_id in user_task_status:
        task_status = user_task_status[task_id]
        if PHOTO_STEPS[step] == "📸 другое":
            # Для "другое" пропуск не имеет смысла, но можно установить как "skipped"
            task_status["photos"][step] = "skipped"
        else:
            if not task_status["photos"][step]:
                task_status["photos"][step] = "skipped"
        task_status["active_step"] = None
        if all(
            (PHOTO_STEPS[s] == "📸 другое" and len(task_status["photos"][s]) > 0) or
            (PHOTO_STEPS[s] != "📸 другое" and (len(task_status["photos"][s]) > 0 or task_status["photos"][s] == "skipped"))
            for s in task_status["photos"]
        ):
            await complete_task_and_send_report(event, task_id)
        else:
            await update_task_buttons(event, task_id)

# Завершение задачи и отправка фото
async def complete_task_and_send_report(event, task_id):
    task_status = user_task_status[task_id]
    photos = []
    for step, photo_list in task_status["photos"].items():
        if PHOTO_STEPS[step] == "📸 другое":
            photos.extend(photo_list)  # Добавляем все фотографии из "другое"
        elif photo_list not in [None, "skipped"]:
            if isinstance(photo_list, list) and len(photo_list) > 0:
                photos.append(photo_list[0])  # Предполагается, что для остальных шагов одно фото
    if photos:
        await client.send_file(
            GROUP_CHAT_ID,
            photos,
            caption=f"Задача '{task_status['title']}' завершена! ✅"
        )
    else:
        await event.respond(f"Задача '{task_status['title']}' завершена без фотографий.")
    task_status["completed"] = True
    await event.respond(f"Задача '{task_status['title']}' завершена! ✅")

# Завершение задачи вручную
@client.on(events.CallbackQuery(pattern=r"complete_"))
async def complete_task_manual(event):
    task_id = event.data.decode('utf-8').replace("complete_", "")
    if task_id in user_task_status:
        task_status = user_task_status[task_id]
        if not task_status["completed"]:
            await complete_task_and_send_report(event, task_id)
        else:
            await event.respond(f"Задача '{task_status['title']}' уже завершена.")

# Обработка кнопок пагинации
@client.on(events.CallbackQuery(pattern=r"(next|prev)_page_(\w+)"))
async def handle_pagination(event):
    direction, user_id = event.pattern_match.groups()
    if user_id not in user_search_results:
        await event.answer("Нет данных для пагинации.", alert=True)
        return

    current_page = user_search_page.get(user_id, 0)
    total_results = len(user_search_results[user_id])
    total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    if direction == "next":
        if current_page < total_pages - 1:
            user_search_page[user_id] = current_page + 1
        else:
            await event.answer("Это последняя страница.", alert=True)
            return
    elif direction == "prev":
        if current_page > 0:
            user_search_page[user_id] = current_page - 1
        else:
            await event.answer("Это первая страница.", alert=True)
            return

    # Получение текущей страницы
    page = user_search_page[user_id]
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    chunk = user_search_results[user_id][start:end]

    response_text = f"Найдены следующие абоненты (страница {page + 1} из {total_pages}):\n\n"
    for idx, abonent in enumerate(chunk, start=start + 1):
        fio = abonent.get('fio', '—')
        contract = abonent.get('contract_number', '—')
        address = abonent.get('address', '—')
        phone = abonent.get('phone_number', '—')
        response_text += (
            f"**{idx}. ФИО:** {fio}\n"
            f"**№ Договора:** {contract}\n"
            f"**Адрес:** {address}\n"
            f"**Телефон:** {phone}\n\n"
        )

    # Обновление кнопок навигации
    buttons = []
    if page < total_pages - 1:
        buttons.append(Button.inline("Следующая страница", data=f"next_page_{user_id}"))
    if page > 0:
        buttons.append(Button.inline("Предыдущая страница", data=f"prev_page_{user_id}"))
    await event.edit(response_text, buttons=[buttons], parse_mode="markdown")

# Загрузка фото для активного шага
@client.on(events.NewMessage(func=lambda e: e.is_private and e.photo))
async def handle_photo(event):
    user_id = event.sender_id
    message = event.message

    # Найти активную задачу пользователя
    active_tasks = [task_id for task_id, task in user_task_status.items() if task["active_step"] is not None and not task["completed"]]
    if not active_tasks:
        await event.respond("Фото получено, но нет активного шага для отчёта. Если вы хотите выполнить поиск, отправьте текстовое сообщение без фото.")
        return
    task_id = active_tasks[0]
    task_status = user_task_status[task_id]
    active_step = task_status["active_step"]

    if PHOTO_STEPS[active_step] == "📸 другое":
        if len(task_status["photos"][active_step]) >= MAX_OTHER_PHOTOS:
            await event.respond(f"Достигнут лимит фотографий для шага '{PHOTO_STEPS[active_step]}' ({MAX_OTHER_PHOTOS} фото).")
            return
        task_status["photos"][active_step].append(message.photo)
        await event.respond(
            f"Фото для шага '{PHOTO_STEPS[active_step]}' принято! ✅ (Всего: {len(task_status['photos'][active_step])})"
        )
        if len(task_status["photos"][active_step]) < MAX_OTHER_PHOTOS:
            await event.respond(
                "Отправьте ещё одно фото или нажмите 'Завершить добавление фотографий'.",
                buttons=[
                    Button.inline("Завершить", data=f"complete_other_{task_id}_{active_step}")
                ]
            )
        task_status["active_step"] = None
    else:
        if len(task_status["photos"][active_step]) > 0:
            await event.respond(f"Шаг '{PHOTO_STEPS[active_step]}' уже выполнен!", alert=True)
            return
        task_status["photos"][active_step].append(message.photo)
        await event.respond(f"Фото для шага '{PHOTO_STEPS[active_step]}' принято! ✅")
        task_status["active_step"] = None

    # Проверяем, все ли шаги выполнены или пропущены
    if all(
        (PHOTO_STEPS[s] == "📸 другое" and len(task_status["photos"][s]) > 0) or
        (PHOTO_STEPS[s] != "📸 другое" and (len(task_status["photos"][s]) > 0 or task_status["photos"][s] == "skipped"))
        for s in task_status["photos"]
    ):
        await complete_task_and_send_report(event, task_id)
    else:
        await update_task_buttons(event, task_id)

# Обработка завершения добавления фотографий для "другое"
@client.on(events.CallbackQuery(pattern=r"complete_other_"))
async def complete_other_photos(event):
    data = event.data.decode('utf-8').split('_')
    task_id = data[2]
    step = int(data[3])

    if task_id in user_task_status:
        task_status = user_task_status[task_id]
        await event.respond(f"Добавление фотографий для шага '{PHOTO_STEPS[step]}' завершено! ✅")
        task_status["active_step"] = None
        if all(
            (PHOTO_STEPS[s] == "📸 другое" and len(task_status["photos"][s]) > 0) or
            (PHOTO_STEPS[s] != "📸 другое" and (len(task_status["photos"][s]) > 0 or task_status["photos"][s] == "skipped"))
            for s in task_status["photos"]
        ):
            await complete_task_and_send_report(event, task_id)
        else:
            await update_task_buttons(event, task_id)

async def send_long_message(event, text):
    """Разбиваем длинное сообщение на части и отправляем как обычный текст"""
    # Проверяем, не пустой ли текст
    if not text.strip():
        await event.respond("Нет данных для отображения.")
        return
    
    # Максимальная длина сообщения в Telegram — 4096 символов
    max_length = 4096
    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    
    # Отправляем каждую часть как обычный текст
    for part in parts:
        await event.respond(part, parse_mode=None)

@client.on(events.NewMessage(pattern='/switch'))
async def handle_switch_command(event):
    """Обработчик команды /switch"""
    try:
        # Извлекаем номер договора из сообщения
        contract_number = event.message.text.split(' ', 1)[1].strip()
        
        # Получаем данные через switch3.py
        data = parse_switch_sv(contract_number)
        
        if "ошибка" in data:
            await event.respond(f"❌ Ошибка: {data['ошибка']}")
            return

        # Формируем красивый вывод
        response = []
        if data["сессия"]:
            response.append("📡 *Информация о сессии:*")
            for key, value in data["сессия"].items():
                response.append(f"• {key.replace('_', ' ').title()}: `{value}`")

        if data["договор"]:
            response.append("\n📄 *Информация о договоре:*")
            for key, value in data["договор"].items():
                response.append(f"• {key.replace('_', ' ').title()}: `{value}`")

        if data["абонент"]:
            response.append("\n👤 *Информация об абоненте:*")
            for key, value in data["абонент"].items():
                response.append(f"• {key.replace('_', ' ').title()}: `{value}`")

        if data["трафик"]:
            response.append("\n📊 *Статистика трафика:*")
            for direction, info in data["трафик"].items():
                response.append(f"➡️ *{direction.title()}:*")
                for k, v in info.items():
                    response.append(f"  {k.replace('_', ' ').title()}: `{v}`")

        if data["порты"]:
            response.append("\n🔌 *Порты коммутаторов:*")
            for idx, port in enumerate(data["порты"], 1):
                response.append(f"\n🔧 *Порт #{idx}*")
                for key, value in port.items():
                    response.append(f"• {key.replace('_', ' ').title()}: `{value}`")

        # Разбиваем сообщение на части из-за лимита Telegram
        message = "\n".join(response)
        for chunk in [message[i:i+4096] for i in range(0, len(message), 4096)]:
            await event.respond(chunk, parse_mode='markdown')

    except IndexError:
        await event.respond("❌ Укажите номер договора: `/switch 123456`", parse_mode='markdown')
    except Exception as e:
        await event.respond(f"⚠️ Ошибка: {str(e)}")

# Команда /diag (перенесена из bot.py без изменений в логике)
@client.on(events.NewMessage(pattern='/diag'))
async def handle_diag_command(event):
    try:
        if len(event.message.text.split()) < 2:
            await event.respond("❌ Укажите номер договора: `/diag 123456`", parse_mode='markdown')
            return
        contract_number = event.message.text.split(' ', 1)[1].strip()
        await event.respond(f"Начинаю диагностику для договора {contract_number}...")
        data = parse_switch_sv(contract_number)
        if "ошибка" in data:
            await event.respond(f"❌ Ошибка: {data['ошибка']}")
            return
        mac_address = data["сессия"].get("mac_адрес")
        if not mac_address:
            await event.respond("❌ MAC-адрес не найден!")
            return
        switch_ports = [(port["ip_коммутатора"], port["порт"]) for port in data["порты"]]
        await event.respond(f"Поиск MAC-адреса {mac_address} на коммутаторах...")
        for ip, port in switch_ports:
            if str(port).isdigit():
                await event.respond(f"Диагностика для {ip} порт {port}...")
                result = await telnet_connect_and_search(ip, port)
                await send_long_message(event, result)
            else:
                await event.respond(f"Пропускаем {ip}: неверный порт ({port})")
    except Exception as e:
        await event.respond(f"⚠️ Ошибка: {str(e)}")


# Обработка общих текстовых сообщений как поисковых запросов
@client.on(events.NewMessage(func=lambda e: e.text and not e.photo and not e.media and not e.video and not e.document and not e.audio and not e.voice and not e.sticker and not e.text.startswith('/')))
async def handle_search(event):
    user_id = event.sender_id
    message = event.message.message.strip()
    
    # Проверяем, находится ли пользователь в процессе выполнения задачи
    in_task = any(task["active_step"] is not None and not task["completed"] for task in user_task_status.values())
    
    if in_task:
        await event.respond("Вы находитесь в процессе выполнения задачи. Пожалуйста, завершите текущую задачу перед поиском.")
        return

    if message:
        results = search_abonents(message)

        if results:
            user_search_results[user_id] = results
            user_search_page[user_id] = 0
            total_results = len(results)
            total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
            start = 0
            end = RESULTS_PER_PAGE
            chunk = results[start:end]

            response_text = f"Найдены следующие абоненты (страница 1 из {total_pages}):\n\n"
            for idx, abonent in enumerate(chunk, start=1):
                fio = abonent.get('fio', '—')
                contract = abonent.get('contract_number', '—')
                address = abonent.get('address', '—')
                phone = abonent.get('phone_number', '—')
                response_text += (
                    f"**{idx}. ФИО:** {fio}\n"
                    f"**№ Договора:** {contract}\n"
                    f"**Адрес:** {address}\n"
                    f"**Телефон:** {phone}\n\n"
                )

            # Формирование кнопок навигации
            buttons = []
            if total_pages > 1:
                buttons = [
                    Button.inline("Следующая страница", data=f"next_page_{user_id}"),
                    Button.inline("Предыдущая страница", data=f"prev_page_{user_id}")
                ]

            await event.respond(response_text, buttons=[buttons], parse_mode="markdown")
        else:
            await event.respond("Ничего не найдено по вашему запросу.")
    else:
        await event.respond("Пустое сообщение. Пожалуйста, введите данные для поиска.")

client.run_until_disconnected()

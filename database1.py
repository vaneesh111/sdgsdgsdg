import pymysql
from datetime import datetime

# Настройки подключения к базе данных
db_config = {
    'host': '192.168.10.91',
    'user': 'vanesh',
    'password': 'Exonet_15',
    'db': 'raketa',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}

def execute_query(query, args=None):
    """Выполняет SQL-запрос и применяет изменения."""
    with pymysql.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            conn.commit()

def fetch_query(query, args=None):
    """Выполняет SQL-запрос для выборки данных и возвращает результат."""
    with pymysql.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()

def get_calls():
    """Получает список всех вызовов из базы данных."""
    query = 'SELECT * FROM calls'
    calls = fetch_query(query)
    print("[DEBUG] Полученные вызовы:", calls)
    return calls

def update_call_status(call_id, status):
    """Обновляет статус звонка по его ID."""
    query = 'UPDATE calls SET status = %s WHERE id = %s'
    execute_query(query, (status, call_id))
    print(f"[DEBUG] Статус звонка с ID {call_id} обновлен на {status}")

def update_call_duration(call_id, duration):
    """Обновляет длительность звонка по его ID."""
    query = 'UPDATE calls SET duration = %s WHERE id = %s'
    execute_query(query, (duration, call_id))
    print(f"[DEBUG] Длительность звонка с ID {call_id} обновлена на {duration}")

def add_call(call_id, phone_number, status, yougile_task):
    """
    Добавляет новый вызов в базу данных.
    Если в вашем web-приложении где-то используется именно эта функция,
    следим за одинаковым форматом ID (убираем дробную часть).
    """
    call_id_str = str(call_id).split('.')[0]
    query = '''INSERT INTO calls (
        id, phone_number, date_time, duration, line, fio,
        contract, balance, min_payment, status, yougile_task
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE status = VALUES(status)'''
    
    default_fio = "Неизвестно"
    default_contract = "Неизвестно"
    default_balance = 0.0
    default_min_payment = 0.0
    args = (
        call_id_str,
        phone_number,
        datetime.now(),
        "00:00",
        "500050",
        default_fio,
        default_contract,
        default_balance,
        default_min_payment,
        status,
        yougile_task
    )
    execute_query(query, args)
    print(f"[DEBUG] Добавлен вызов с ID {call_id_str}, номер = {phone_number}, статус = {status}")

def save_dropdown_selection(call_id, category, action):
    """Сохраняет выбранные значения категорий и действий для вызова по ID."""
    if not call_id or not category or not action:
        print(f"[WARNING] Не сохраняем пустые значения для call_id={call_id}")
        return
    
    query = '''INSERT INTO dropdown_selections (call_id, category, action) 
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE category = %s, action = %s'''
    args = (call_id, category, action, category, action)
    execute_query(query, args)
    print(f"[DEBUG] Сохранение выбора в БД -> call_id={call_id}, category={category}, action={action}")

def get_dropdown_selection(call_id):
    """Получает сохраненные значения категории и действия для вызова по ID."""
    query = 'SELECT category, action FROM dropdown_selections WHERE call_id = %s'
    result = fetch_query(query, (call_id,))
    if result:
        category = result[0].get('category') or ''
        action = result[0].get('action') or ''
        print(f"[DEBUG] Получено из БД для call_id={call_id}: category={category}, action={action}")
        return {'category': category, 'action': action}
    else:
        print(f"[DEBUG] Для call_id={call_id} нет данных в БД.")
        return {'category': '', 'action': ''}

def update_call(call_id, fio, contract, balance, min_payment):
    """Обновляет данные о вызове в таблице calls по его ID."""
    query = '''UPDATE calls
               SET fio = %s, contract = %s, balance = %s, min_payment = %s
               WHERE id = %s'''
    args = (fio, contract, balance, min_payment, call_id)
    try:
        execute_query(query, args)
        print(f"[DEBUG] Вызов с ID {call_id} обновлен: fio={fio}, contract={contract}, balance={balance}, min_payment={min_payment}")
        return True
    except Exception as e:
        print(f"Ошибка при обновлении вызова: {e}")
        return False

def update_call_field(call_id, field, value):
    """Обновляет одно поле записи вызова по его ID."""
    valid_fields = {'fio', 'contract', 'balance', 'min_payment'}
    if field not in valid_fields:
        print(f"Недопустимое поле для обновления: {field}")
        return False

    query = f'UPDATE calls SET {field} = %s WHERE id = %s'
    args = (value, call_id)
    try:
        execute_query(query, args)
        return True
    except Exception as e:
        print(f"Ошибка при обновлении поля вызова: {e}")
        return False

def save_call_override(phone_number, fio, contract, balance, min_payment):
    """Сохраняет измененные данные для номера телефона в таблице call_overrides."""
    query = '''INSERT INTO call_overrides (
        phone_number, fio, contract, balance, min_payment
    ) VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        fio = %s,
        contract = %s,
        balance = %s,
        min_payment = %s
    '''
    args = (
        phone_number,
        fio,
        contract,
        balance,
        min_payment,
        fio,
        contract,
        balance,
        min_payment
    )
    execute_query(query, args)
    print(
        f"[DEBUG] save_call_override: Сохранение изменений для номера {phone_number} "
        f"с данными: fio={fio}, contract={contract}, balance={balance}, min_payment={min_payment}"
    )

def find_abonent_by_phone(phone_number):
    """Ищет абонента в базе данных по номеру телефона."""
    normalized_phone = ''.join(filter(str.isdigit, phone_number))
    if not normalized_phone:
        print("[DEBUG] Некорректный номер телефона:", phone_number)
        return None

    formats = [
        normalized_phone,
        normalized_phone[-10:],
        "7" + normalized_phone[-10:],
        "8" + normalized_phone[-10:],
        "+7" + normalized_phone[-10:]
    ]

    for fmt in formats:
        print(f"[DEBUG] Ищем абонента с номером: {fmt}")
        query = "SELECT * FROM abonents WHERE sms = %s"
        result = fetch_query(query, (fmt,))
        if result:
            print(f"[DEBUG] Найден абонент для {fmt}: {result[0]}")
            return result[0]

    print(f"[DEBUG] Абонент с номером {phone_number} не найден")
    return None

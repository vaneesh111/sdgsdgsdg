import requests
from config import YOUGILE_API_URL, YOUGILE_API_KEY, YOUGILE_TEAM_ID
from pprint import pprint

def search_yougile_task(phone_number):
    # Если есть "+", убираем только его, но не трогаем первую цифру
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]

    # Попробуем сначала с номером, начиная с 8
    phone_number_8 = phone_number
    if phone_number.startswith("7"):
        phone_number_8 = "8" + phone_number[1:]

    # Отправляем запрос с номером, начинающимся с 7
    print(f"Поиск задачи в YouGile для номера телефона: {phone_number}")
    querystring_7 = {"limit": "99999", "title": phone_number}
    headers = {
        "Content-Type": "application/json",
        "Authorization": YOUGILE_API_KEY
    }

    response_7 = requests.get(YOUGILE_API_URL, headers=headers, params=querystring_7)
    tasks_7 = response_7.json().get("content", [])
    
    # Выводим результат поиска задач в YouGile с 7
    print("Результат поиска задач в YouGile (номер с 7):")
    pprint(tasks_7)

    # Если найдены задачи с 7, возвращаем первую задачу
    if tasks_7:
        task_id_7 = tasks_7[0]["id"][-12:]  # Берем последние 12 символов ID задачи
        task_url_7 = f"https://yougile.com/team/{YOUGILE_TEAM_ID}/#chat:{task_id_7}"
        return task_url_7

    # Если задачи с 7 не найдены, пробуем с номером, начинающимся с 8
    print(f"Поиск задачи в YouGile для номера телефона: {phone_number_8}")
    querystring_8 = {"limit": "99999", "title": phone_number_8}
    response_8 = requests.get(YOUGILE_API_URL, headers=headers, params=querystring_8)
    tasks_8 = response_8.json().get("content", [])

    # Выводим результат поиска задач в YouGile с 8
    print("Результат поиска задач в YouGile (номер с 8):")
    pprint(tasks_8)

    if tasks_8:
        task_id_8 = tasks_8[0]["id"][-12:]  # Берем последние 12 символов ID задачи
        task_url_8 = f"https://yougile.com/team/{YOUGILE_TEAM_ID}/#chat:{task_id_8}"
        return task_url_8

    return None


def search_billing(phone_number):
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]
    if phone_number.startswith("7") or phone_number.startswith("8"):
        phone_number = phone_number[1:]
    
    billing_url = f"http://lk.raketa-net.ru:8082/admin/Abonents/search/?q={phone_number}"
    return billing_url

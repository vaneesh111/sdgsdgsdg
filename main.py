import socket
import time
from ami import ami_login, listen_ami_events
from config import ASTERISK_HOST, ASTERISK_PORT
from telegram_bot import send_telegram_message

def main():
    print("Запуск программы...")
    while True:
        try:
            print("Пытаемся подключиться к Asterisk AMI...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ASTERISK_HOST, ASTERISK_PORT))
            ami_login(sock)
            listen_ami_events(sock)
        except Exception as e:
            print(f"Ошибка: {e}")
            send_telegram_message(f"⚠️ Произошла ошибка подключения к Asterisk AMI: {e}")
            time.sleep(5)  # Ожидание перед повторной попыткой подключения
        finally:
            try:
                sock.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()

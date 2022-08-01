"""
Модуль Telegram-бота для проверки статуса домашней работы по курсу Я.Практикум.
Бот обращается к API сервиса Практикум.Домашка и узнает статус текущей
домашней работы пользователя.

Особенности модуля:
- Раз в 10 минут опрашивается API сервиса Практикум.Домашка
- Проверяется статус отправленной на ревью домашней работы
- При обновлении статуса анализируется ответ API
- При корректном статусе отправляется соответствующее уведомление в Telegram.
"""
import logging
import os
import sys
import time
from http import HTTPStatus
from urllib.error import HTTPError

import requests
import telegram
from dotenv import load_dotenv

from exceptions import EnvVariableError

load_dotenv()

# Настройки логирования:
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] - %(message)s'
))
logger.addHandler(handler)

# Обязательные переменные окружения:
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Настройки для запроса к API:
RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

# Словарь со всеми известными статусами домашних работ:
HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message: str) -> None:
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Бот отправил сообщение: "{message}".')
    except Exception as error:
        logger.error(
            (f'Cбой при отправке сообщения "{message}" '
             f'в Telegram из-за ошибки {error}.')
        )


def get_api_answer(current_timestamp: int) -> dict:
    """Запрос к эндпоинту API сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    if response.status_code != HTTPStatus.OK:
        raise HTTPError(
            (f'Эндпоинт {ENDPOINT} недоступен. '
             f'Код ответа API: {response.status_code}.')
        )
    return response.json()


def check_response(response: dict) -> list:
    """Проверка ответа API сервиса на корректность."""
    if type(response) is not dict:
        raise TypeError(
            (f'Неверный тип данных ответа от эндпоинта {ENDPOINT}. '
             f'Требуется словарь, текущий тип - {type(response)}.')
        )
    if 'homeworks' and 'current_date' not in response.keys():
        raise KeyError(
            (f'Ответ от эндпоинта {ENDPOINT} не содержит данные про '
              '"homeworks" и "current_date".')
        )

    homeworks = response['homeworks']
    current_date = response['current_date']

    if type(homeworks) is not list:
        raise TypeError(
            'Тип данных значения ключа "homeworks" не является списком.'
        )
    if type(current_date) is not int:
        raise TypeError(
            ('Тип данных значения ключа "current_date" не является '
             'целым числом.')
        )
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлечение статуса домашней работы из ответа API сервиса."""
    if 'homework_name' and 'status' not in homework.keys():
        raise KeyError(
            ('Данные о домашней работе не содержат информацию про '
             '"homework_name" и "status".')
        )

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_STATUSES.keys():
        raise KeyError(
            'Данные о домашней работе содержат недокументированный статус.'
        )

    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверка доступности обязательных переменных окружения."""
    if PRACTICUM_TOKEN and TELEGRAM_CHAT_ID and TELEGRAM_TOKEN:
        return True
    return False


def main() -> None:
    """Основная логика работы бота."""
    if check_tokens() is False:
        logger.critical(
            ('Отсутствует обязательная(-ые) переменная(-ые) окружения. '
             'Программа принудительно остановлена.')
        )
        raise EnvVariableError

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    previous_error_message = []

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Отсутствуют новые статусы работ.')
            current_timestamp = response['current_date']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if (not previous_error_message
                    or previous_error_message.count(message) == 0):
                send_message(bot, message)
                previous_error_message.clear()
                previous_error_message.append(message)
        else:
            if previous_error_message:
                previous_error_message.clear()
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()

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
from json.decoder import JSONDecodeError
from typing import Dict, List, Union

import requests
from dotenv import load_dotenv
from telegram import Bot

from exceptions import APIAnswerStatusCodeError, EnvVariableError

load_dotenv()

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

# Псевдонимы типов:
CustomDict = Dict[str, Union[List[Dict[str, Union[str, int]]], int]]
CustomList = List[Dict[str, Union[str, int]]]


def init_logger() -> logging.Logger:
    """Инициализация логгера."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] в функции %(funcName)s - %(message)s'
    ))
    logger.addHandler(handler)

    logger.info('Инициализация логгера выполнена успешно.')
    return logger


logger = init_logger()


def send_message(bot: Bot, message: str) -> None:
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Бот отправил сообщение: "{message}".')
    except Exception as error:
        logger.error(
            (f'Cбой при отправке сообщения "{message}" '
             f'в Telegram из-за ошибки {error}.')
        )


def get_api_answer(current_timestamp: int) -> CustomDict:
    """Запрос к эндпоинту API сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            message = (f'Эндпоинт {ENDPOINT} недоступен. '
                       f'Код ответа API: {response.status_code}.')
            logger.error(message)
            raise APIAnswerStatusCodeError(message)
    except requests.RequestException as error:
        message = ('Произошла ошибка при обработке запроса '
                   f'к эндпоинту {ENDPOINT}.')
        logger.error(message)
        raise error(message)

    try:
        response.json()
        logger.info(f'Запрос к эндпоинту {ENDPOINT} выполнен успешно.')
        return response.json()
    except JSONDecodeError as error:
        message = f'Эндпоинт {ENDPOINT} передал ответ не в формате json.'
        logger.error(message)
        raise error(message)


def check_response(response: CustomDict) -> CustomList:
    """Проверка ответа API сервиса на корректность."""
    if not isinstance(response, dict):
        message = (f'Неверный тип данных ответа от эндпоинта {ENDPOINT}. '
                   f'Требуется словарь, текущий тип - {type(response)}.')
        logger.error(message)
        raise TypeError(message)
    if 'homeworks' not in response:
        message = (f'Ответ от эндпоинта {ENDPOINT} не содержит данные про '
                   '"homeworks".')
        logger.error(message)
        raise KeyError(message)
    if 'current_date' not in response:
        message = (f'Ответ от эндпоинта {ENDPOINT} не содержит данные про '
                   '"current_date".')
        logger.error(message)
        raise KeyError(message)

    homeworks = response['homeworks']
    current_date = response['current_date']

    if not isinstance(homeworks, list):
        message = 'Тип данных значения ключа "homeworks" не является списком.'
        logger.error(message)
        raise TypeError(message)
    if not isinstance(current_date, int):
        message = ('Тип данных значения ключа "current_date" не является '
                   'целым числом.')
        logger.error(message)
        raise TypeError(message)

    logger.info(f'Проверка ответа от эндпоинта {ENDPOINT} проведена успешно.')
    return homeworks


def parse_status(homework: Dict[str, Union[str, int]]) -> str:
    """Извлечение статуса домашней работы из ответа API сервиса."""
    if 'homework_name' not in homework:
        message = ('Данные о домашней работе не содержат информацию про '
                   '"homework_name".')
        logger.error(message)
        raise KeyError(message)
    if 'status' not in homework:
        message = ('Данные о домашней работе не содержат информацию про '
                   '"status".')
        logger.error(message)
        raise KeyError(message)

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_STATUSES:
        message = ('Данные о домашней работе содержат недокументированный '
                   f'статус - {homework_status}.')
        logger.error(message)
        raise KeyError(message)

    verdict = HOMEWORK_STATUSES[homework_status]
    logger.info('Извлечение статуса домашней работы проведено успешно.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверка доступности обязательных переменных окружения."""
    if all([PRACTICUM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN]):
        logger.info('Проверка доступности обязательных переменных окружения '
                    'проведена успешно.')
        return True
    logger.critical(
        ('Отсутствует обязательная(-ые) переменная(-ые) окружения. '
         'Программа будет принудительно остановлена.')
    )
    return False


def main() -> None:
    """Основная логика работы бота."""
    if check_tokens() is False:
        raise EnvVariableError

    bot = Bot(token=TELEGRAM_TOKEN)
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

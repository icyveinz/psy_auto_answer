import asyncio
import random
import logging
from datetime import datetime, time

from telethon import TelegramClient, events
from telethon.tl.types import Message

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TRIGGER = "❗️ Анонимно. Чтобы взять в работу, просим откликаться в чате. Клиент напишет вам в лс"

WORK_START = time(9, 0)
WORK_END = time(0, 0)  # полночь

REPLY_DELAY_MIN = 3 * 60   # секунды
REPLY_DELAY_MAX = 7 * 60

TEMPLATES = config.TEMPLATES

client = TelegramClient("session", config.API_ID, config.API_HASH)


def is_work_hours() -> bool:
    now = datetime.now().time()
    # Окно 09:00–00:00 (полночь), т.е. 09:00 <= now < 24:00
    return now >= WORK_START


async def delayed_reply(message: Message) -> None:
    delay = random.randint(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
    log.info("Запланирован ответ через %d сек на сообщение id=%d", delay, message.id)
    await asyncio.sleep(delay)

    # Повторная проверка рабочего времени после ожидания
    if not is_work_hours():
        log.info("Вышли за рабочее время, ответ отменён для id=%d", message.id)
        return

    text = random.choice(TEMPLATES)
    try:
        await message.reply(text)
        log.info("Ответ отправлен на сообщение id=%d", message.id)
    except Exception as exc:
        log.error("Ошибка при отправке ответа: %s", exc)


@client.on(events.NewMessage(chats=config.CHAT))
async def handler(event: events.NewMessage.Event) -> None:
    message: Message = event.message
    text = message.text or ""

    if TRIGGER not in text:
        return

    if not is_work_hours():
        log.info("Сообщение id=%d получено вне рабочего времени, пропускаем", message.id)
        return

    asyncio.create_task(delayed_reply(message))


async def main() -> None:
    await client.start(phone=config.PHONE)
    log.info("Клиент запущен. Слушаем чат: %s", config.CHAT)
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

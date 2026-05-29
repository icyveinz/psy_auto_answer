import asyncio
import json
import random
import logging
from datetime import datetime, time
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.custom import Message

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

WORK_START = time(9, 0)   # 09:00
WORK_END   = time(0, 0)   # 00:00 (полночь)

REPLY_DELAY_MIN = 3 * 60  # секунды
REPLY_DELAY_MAX = 7 * 60

STATE_FILE = Path("state.json")

client = TelegramClient("session", config.API_ID, config.API_HASH)

# Защита от двойного ответа: id сообщений, уже поставленных в очередь
_queued: set[int] = set()


# ─── state helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_answered_id": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── time helpers ──────────────────────────────────────────────────────────────

def is_work_hours() -> bool:
    """09:00 включительно до 00:00 (полночи)."""
    return datetime.now().time() >= WORK_START


# ─── reply logic ──────────────────────────────────────────────────────────────

async def send_reply(message: Message) -> None:
    text = random.choice(config.TEMPLATES)
    await message.reply(text, link_preview=False)
    state = load_state()
    if message.id > state["last_answered_id"]:
        state["last_answered_id"] = message.id
        save_state(state)
    log.info("Ответ отправлен на сообщение id=%d", message.id)


async def delayed_reply(message: Message) -> None:
    delay = random.randint(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
    log.info("Ответ запланирован через %d сек на id=%d", delay, message.id)
    await asyncio.sleep(delay)

    if not is_work_hours():
        log.info("Вышли за рабочее время, ответ отменён для id=%d", message.id)
        _queued.discard(message.id)
        return

    try:
        await send_reply(message)
    except Exception as exc:
        log.error("Ошибка при отправке ответа на id=%d: %s", message.id, exc)
    finally:
        _queued.discard(message.id)


# ─── catch-up: обработка пропущенных сообщений ────────────────────────────────

async def catchup() -> None:
    """При старте в рабочее время отвечаем на сообщения, пропущенные ночью."""
    if not is_work_hours():
        return

    state = load_state()
    last_id = state["last_answered_id"]

    log.info("Catch-up: ищем пропущенные сообщения после id=%d", last_id)

    missed: list[Message] = []
    async for msg in client.iter_messages(config.CHAT, limit=100):
        if msg.id <= last_id:
            break
        text = msg.text or ""
        if TRIGGER in text:
            missed.append(msg)

    if not missed:
        log.info("Catch-up: пропущенных сообщений нет")
        return

    # Сортируем от старых к новым
    missed.sort(key=lambda m: m.id)
    log.info("Catch-up: найдено %d пропущенных сообщений", len(missed))

    for msg in missed:
        if msg.id in _queued:
            continue
        _queued.add(msg.id)
        asyncio.create_task(delayed_reply(msg))


# ─── live listener ────────────────────────────────────────────────────────────

@client.on(events.NewMessage(chats=config.CHAT))
async def handler(event: events.NewMessage.Event) -> None:
    message: Message = event.message
    text = message.text or ""

    if TRIGGER not in text:
        return

    if not is_work_hours():
        log.info("Сообщение id=%d получено вне рабочего времени, пропускаем", message.id)
        return

    if message.id in _queued:
        return

    _queued.add(message.id)
    asyncio.create_task(delayed_reply(message))


# ─── entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    async with client:
        await client.start(phone=config.PHONE)
        log.info("Клиент запущен. Слушаем чат: %s", config.CHAT)
        await catchup()
        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

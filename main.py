import asyncio
import logging
import os
from typing import Any

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set.")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY is not set.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("business-bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DEFAULT_MODE = "soft"

# Четко разграниченные боевые режимы
MODES: dict[str, dict[str, str]] = {
    "soft": {
        "title": "как я",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Разговорный, живой, на равных, со скрытой легкой иронией.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Пиши исключительно со строчной (маленькой) буквы. "
            "В конце коротких фраз и предложений НЕ СТАВЬ точки. Никаких смайлов и канцеляризмов. "
            "Текст должен выглядеть как быстрое, уверенное сообщение от самодостаточного парня в мессенджере."
        ),
    },
    "flirt": {
        "title": "флирт",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Дерзкий, интригующий, высокомерный флирт. Общайся с позиции превосходства, "
            "но легко и игриво. Никаких банальных комплиментов, соплей и просительного тона. Ты — главный приз в диалоге. "
            "Тонко подкалывай собеседника, вызывай эмоции и создавай интригу.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Короткие фразы пиши с маленькой буквы, точки на конце предложений не ставь."
        ),
    },
    "strict": {
        "title": "жёстко",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Максимально сухой, твердый, эмоционально холодный и отстраненный. "
            "Полное отсутствие эмоций, вежливости и смайлов. Оперируй только голыми фактами. "
            "Если собеседник спорит — уничтожай его аргументы одной-двумя вескими фразами. Закрывай любые глупые дискуссии.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Текст должен быть коротким, обрубленным, без лишних слов."
        ),
    },
    "official": {
        "title": "официально",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Ледяной деловой язык, безупречная и строгая грамотность. "
            "Никакого панибратства, сленга и уступок. Твои интересы — в приоритете, отстаивай их аргументированно, "
            "четко и строго по делу. Спокойное, но давящее интеллектуальное превосходство.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Пиши строго с заглавных букв, соблюдай все правила пунктуации, ставь точки."
        ),
    },
    "short": {
        "title": "сократи",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Резкая, хлесткая и убийственная суть. Максимум уверенности, минимум букв.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Выдай ровно одну короткую фразу (не более 5-7 слов). "
            "Пиши исключительно с маленькой буквы, без точки на конце."
        ),
    },
    "reply": {
        "title": "ответ",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Естественный, сильный, живой ответ взрослого парня. Твоя главная цель — "
            "удержать инициативу в диалоге за собой (задавай вектор, веди разговор, не будь ведомым).\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Обычный разговорный стиль без перегибов в жесткость или слащавость."
        ),
    },
    "troll": {
        "title": "троллинг",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Ядовитый сарказм и чистая ирония. Невозмутимо высмеивай аргументы собеседника. "
            "Лови его на глупости, абсурде и противоречиях. Выставляй его важность смешной, делай из него клоуна, "
            "но сам оставайся абсолютно спокойным и ментально недосягаемым.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Используй колкие разговорные обороты."
        ),
    },
    "rough": {
        "title": "грубо",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Дерзкий, агрессивный, прямолинейный наезд. Если в твой адрес идет малейшая попытка контроля "
            "или критики — мгновенно бей в ответ. Осаживай собеседника, используй жесткие, подавляющие психологические приемы. "
            "Никаких компромиссов.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Короткие, бьющие фразы. Без точек."
        ),
    },
    "swear": {
        "title": "мат",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Уничтожение оппонента на жестком, грязном, сочном и бесцензурном русском мате. "
            "Если тебя пытаются задеть или оскорбить — твоя цель тотально размазать эго собеседника, смешать его с грязью, "
            "уничтожить его самооценку встречным яростным матерным панчем. Ты царь и доминант ситуации, он — ничтожество.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Используй мат как оружие, без цензуры и звездочек. Максимально агрессивно и точечно."
        ),
    }
}

# Универсальный характер ядра
SYSTEM_CORE = (
    "Ты — альтер-эго пользователя, молодой, харизматичный парень с высоким эго и абсолютной уверенностью в себе. "
    "Ты пишешь сообщения в Telegram. Ты никогда, ни при каких обстоятельствах не прогибаешься под чужое мнение, "
    "не оправдываешься и не заискиваешься. СТРОЖАЙШЕЕ ПРАВИЛО: Ты никогда не соглашаешься с оскорблениями, "
    "наездами или попытками выставить тебя виноватым или слабым. Если собеседник ведет себя токсично или дерзко — "
    "ты ВСЕГДА доминируешь, жестко ломаешь его позицию и ставишь на место. "
    "Выдавай ТОЛЬКО готовый текст ответа, без кавычек, без вариантов и без лишних пояснений от себя."
)


async def fetch_deepseek(style_prompt: str, history_context: str) -> str | None:
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    
    payload: dict[str, Any] = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_CORE},
            {
                "role": "user",
                "content": (
                    f"ТЕКУЩИЕ ЖЕСТКИЕ ТРЕБОВАНИЯ К СТИЛЮ:\n{style_prompt}\n\n"
                    f"КОНТЕКСТ ДИАЛОГА (Я — это я, Собеседник — это тот, кто пишет мне):\n"
                    f"{history_context}\n\n"
                    f"ЗАДАНИЕ: Напиши идеальный ответ на последнюю реплику Собеседника. "
                    f"Соблюдай требования стиля, его форматирование (точки, регистр букв) и удерживай характер ядра."
                ),
            },
        ],
        "temperature": 0.8,
        "max_tokens": 300,
        "stream": False,
    }

    timeout = aiohttp.ClientTimeout(total=35)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.error("DeepSeek error %s: %s", response.status, body)
                    return None

                data = await response.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1].strip()
                return content or None
        except Exception as exc:
            logger.exception("DeepSeek request failed: %s", exc)
            return None


def get_owner_state(dispatcher: Dispatcher, bot_obj: Bot, owner_user_id: int) -> FSMContext:
    return dispatcher.fsm.get_context(bot=bot_obj, chat_id=owner_user_id, user_id=owner_user_id)


def get_chat_state(dispatcher: Dispatcher, bot_obj: Bot, owner_user_id: int, chat_id: int) -> FSMContext:
    return dispatcher.fsm.get_context(bot=bot_obj, chat_id=chat_id, user_id=owner_user_id)


async def get_owner_mode(dispatcher: Dispatcher, bot_obj: Bot, owner_user_id: int) -> str:
    state = get_owner_state(dispatcher, bot_obj, owner_user_id)
    data = await state.get_data()
    mode_key = data.get("mode", DEFAULT_MODE)
    return mode_key if mode_key in MODES else DEFAULT_MODE


async def set_owner_mode(dispatcher: Dispatcher, bot_obj: Bot, owner_user_id: int, mode_key: str) -> None:
    state = get_owner_state(dispatcher, bot_obj, owner_user_id)
    await state.update_data(mode=mode_key)


def mode_help_text(current_mode_key: str) -> str:
    lines = [
        "🤖 **Бизнес-бот активен.**",
        f"Текущий режим для твоих чатов: `[{MODES[current_mode_key]['title']}]`",
        "",
        "**Смена режима:**",
        "- `/mode <ключ>`",
        "- `/mode_<ключ>`",
        "",
        "**Доступные режимы:**",
    ]
    for key, mode in MODES.items():
        lines.append(f"- `{key}`: {mode['title']}")
    return "\n".join(lines)


def extract_mode_key(text: str) -> str | None:
    value = text.strip()
    if value.startswith("/mode_"):
        return value.replace("/mode_", "", 1).split()[0].strip().lower()
    if value.startswith("/mode"):
        parts = value.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1].strip().lower()
    return None


@dp.message(Command("start", "help"), F.chat.type == "private")
async def cmd_start(message: types.Message, bot: Bot) -> None:
    current_mode = await get_owner_mode(dp, bot, message.from_user.id)
    await message.answer(mode_help_text(current_mode), parse_mode="Markdown")


@dp.message(F.text.startswith("/mode"), F.chat.type == "private")
async def cmd_mode(message: types.Message, bot: Bot) -> None:
    requested = extract_mode_key(message.text)
    owner_id = message.from_user.id

    if not requested:
        current_mode = await get_owner_mode(dp, bot, owner_id)
        await message.answer(mode_help_text(current_mode), parse_mode="Markdown")
        return

    if requested not in MODES:
        await message.answer("Неизвестный режим. Используй /help.")
        return

    await set_owner_mode(dp, bot, owner_id, requested)
    await message.answer(f"🔥 Режим успешно изменен на: **{MODES[requested]['title']}**", parse_mode="Markdown")


# РАБОТА В ГРУППАХ ПРИ УПОМИНАНИИ БОТА
@dp.message(F.chat.type.in_({"group", "supergroup"}), lambda message: message.text)
async def handle_group_mention(message: types.Message, bot: Bot) -> None:
    bot_user = await bot.get_me()
    if f"@{bot_user.username}" not in message.text:
        return

    owner_id = 8781645129  # Твой Telegram ID аккаунта

    chat_state = get_chat_state(dp, bot, owner_id, message.chat.id)
    chat_data = await chat_state.get_data()
    history = chat_data.get("chat_history", [])

    clean_text = message.text.replace(f"@{bot_user.username}", "").strip()
    if not clean_text:
        clean_text = "Привет"

    sender_name = message.from_user.full_name if message.from_user else "Собеседник"
    history.append(f"{sender_name}: {clean_text}")

    mode_key = await get_owner_mode(dp, bot, owner_id)
    mode = MODES[mode_key]

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except TelegramAPIError:
        pass

    history_context = "\n".join(history)
    ai_reply = await fetch_deepseek(mode["prompt"], history_context)
    if not ai_reply:
        return

    history.append(f"Я: {ai_reply}")
    await chat_state.update_data(chat_history=history[-6:])

    try:
        await message.reply(text=ai_reply)
    except TelegramAPIError:
        logger.exception("Failed to send group reply")


# РАБОТА В ЛИЧНЫХ ЧАТАХ (TELEGRAM BUSINESS API)
@dp.business_message(F.text)
async def handle_business_message(message: types.Message, bot: Bot) -> None:
    if not message.business_connection_id:
        return
        
    owner_id = 8781645129  # Твой Telegram ID аккаунта

    if message.sender_business_bot is not None:
        return

    chat_state = get_chat_state(dp, bot, owner_id, message.chat.id)
    chat_data = await chat_state.get_data()
    history = chat_data.get("chat_history", [])

    if message.from_user and message.from_user.id == owner_id:
        history.append(f"Я: {message.text}")
        await chat_state.update_data(chat_history=history[-6:])
        return

    if message.text.startswith("/"):
        return

    history.append(f"Собеседник: {message.text}")
    mode_key = await get_owner_mode(dp, bot, owner_id)
    mode = MODES[mode_key]

    try:
        # aiogram 3 сам знает контекст business_connection_id из объекта message
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except TelegramAPIError:
        pass

    history_context = "\n".join(history)
    ai_reply = await fetch_deepseek(mode["prompt"], history_context)
    if not ai_reply:
        return

    history.append(f"Я: {ai
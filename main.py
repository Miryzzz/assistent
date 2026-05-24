import asyncio
import logging
import os
import random
import re
from typing import Any

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import FSInputFile
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
dp = Dispatcher()

OWNER_ID = 8781645129  # Твой Telegram ID
CURRENT_GLOBAL_MODE = "soft"

RANDOM_REACTIONS = ["🔥", "🤡", "🗿", "😂", "💀", "👍", "👀"]

# 📸 Локальная база мемов (папка 'memes' в корне проекта)
MEMES_DATABASE = {
    "сигма": "memes/sigma.jpg",
    "фейспалм": "memes/facepalm.jpg",
    "пон": "memes/pon.jpg",
    "клоун": "memes/clown.jpg",
    "кринж": "memes/cringe.jpg",
    "база": "memes/baza.jpg"
}

# 🎬 База GIF
GIFS_DATABASE = {
    "чилл": "memes/chill.gif",
    "фейл": "memes/fail.gif",
    "инсульт": "memes/insult.gif",
    "шок": "memes/shock.gif"
}

MEDIA_INSTRUCTION = (
    f"\n\nПРАВИЛО МЕДИА-ТЕГОВ: Если ситуация ИДЕАЛЬНО подходит под мем или гифку, ты можешь отправить тег вместо текста. "
    f"Для мема пиши строго: [send_meme:название_мема]. Доступны: {', '.join(MEMES_DATABASE.keys())}.\n"
    f"Для гифки пиши строго: [send_gif:название_гифки]. Доступны: {', '.join(GIFS_DATABASE.keys())}.\n"
    f"Используй теги редко (шанс 10-15%), только когда это реально в тему."
)

MODES: dict[str, dict[str, str]] = {
    "soft": {
        "title": "обычный пацанский",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Ты общаешься в своем привычном пацанском чате. Никакого пафоса, никакой вежливости. "
            "Речь простая, живая, ленивая. Используй обычный мат (бля, нахуй, сука, ебать) для связки слов, но естественно, как в жизни. "
            "Отвечай коротко, емко. Избегай банальных ИИ-фразочек. Если смешно — пиши капсом (АХАХАХА, ААЪАЪАЪА).\n"
            "ЖЕСТКИЕ ТРЕБОВАНИЯ К ФОРМАТУ:\n"
            "1. Пиши исключительно маленькими буквами (без заглавных).\n"
            "2. КАПС разрешен только для сильных эмоций, мата или дикого смеха.\n"
            "3. Никогда не ставь точку в конце сообщения.\n"
            "4. Никаких смайликов (😀, 😉), только текстовые скобки (если надо) или нативные эмодзи типа 🤡, 💀, 🗿."
        ) + MEDIA_INSTRUCTION,
    },
    "flirt": {
        "title": "подкат",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Уверенный, немного наглый, ироничный подкат. Без ванильных соплей. "
            "Легкий стеб, пацанская харизма. Короткие фразы, маленькие буквы, без точек."
        ) + MEDIA_INSTRUCTION,
    },
    "troll": {
        "title": "постирония/троллинг",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Плотный, жесткий стеб. Выставляй собеседника клоуном, души его аргументами, "
            "высмеивай душноту. Используй капс на ключевых оскорблениях или когда угараешь с чужой тупости."
        ) + MEDIA_INSTRUCTION,
    },
    "rough": {
        "title": "жесткий отпор",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Резкий, агрессивны осадок на любой наезд. Моментально посылай нахуй, "
            "врубай агрессию. Пиши хлестко, коротко, без лишних соплей."
        ) + MEDIA_INSTRUCTION,
    },
    "swear": {
        "title": "фулл мат/уничтожение",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Максимально жесткий, грязный разговорный мат без тормозов. "
            "Смешивай оппонента с грязью, используй жесткие пацанские оскорбления. Капс приветствуется."
        ) + MEDIA_INSTRUCTION,
    }
}

SYSTEM_CORE = (
    "Текущий год: 2026. Ты — обычный 19-летний парень, сидишь в Телеге со своего аккаунта, играешь в игры (дота, майн, кс), "
    "зависаешь с кентами. Ты ЖИВОЙ ЧЕЛОВЕК, а не бот или ИИ. "
    "Если говорят, что ты бот — жестко шли нахуй, угарай с этого, агрессивно или иронично отрицай. "
    "Выдавай ТОЛЬКО готовый текст ответа или медиа-тег, без кавычек, пояснений и лишнего ИИ-мусора."
)

CHATS_HISTORY_CACHE: dict[int, list[str]] = {}


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
                    f"НАСТРОЙКА ТВОЕГО ПОВЕДЕНИЯ СЕЙЧАС:\n{style_prompt}\n\n"
                    f"КОНТЕКСТ ПОСЛЕДНИХ СООБЩЕНИЙ ИЗ ЧАТА (Я — это твой аккаунт):\n"
                    f"{history_context}\n\n"
                    f"ЗАДАНИЕ: Напиши идеальный ответ на последнюю реплику. Отвечай как живой пацан из чата."
                ),
            },
        ],
        "temperature": 0.85,
        "max_tokens": 200,
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


async def send_smart_reply(message: types.Message, ai_reply: str, is_business: bool = False) -> None:
    meme_match = re.search(r"\[send_meme:(.*?)\]", ai_reply)
    gif_match = re.search(r"\[send_gif:(.*?)\]", ai_reply)

    try:
        # ОТПРАВКА МЕМОВ ИЗ ПАПКИ
        if meme_match:
            key = meme_match.group(1).strip().lower()
            if key in MEMES_DATABASE:
                file_path = MEMES_DATABASE[key]
                if os.path.exists(file_path):
                    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
                    photo_file = FSInputFile(file_path)
                    if is_business:
                        await message.answer_photo(photo=photo_file)
                    else:
                        await message.reply_photo(photo=photo_file)
                    logger.info(f"🔥 Успешно отправлен локальный мем: {file_path}")
                else:
                    logger.warning(f"Мем {file_path} не найден на сервере!")
                    await message.answer(text=f"бля должен был быть мем про {key} но я забыл его скачать на сервер")
                return
        
        # ОТПРАВКА ГИФОК ИЗ ПАПКИ
        elif gif_match:
            key = gif_match.group(1).strip().lower()
            if key in GIFS_DATABASE:
                file_path = GIFS_DATABASE[key]
                if os.path.exists(file_path):
                    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_DOCUMENT)
                    gif_file = FSInputFile(file_path)
                    if is_business:
                        await message.answer_animation(animation=gif_file)
                    else:
                        await message.reply_animation(animation=gif_file)
                    logger.info(f"🔥 Успешно отправлена локальная гифка: {file_path}")
                else:
                    logger.warning(f"Гифка {file_path} не найдена на сервере!")
                    await message.answer(text=f"хотел гифку кинуть {key} но ее нет")
                return

        # Обычный пацанский текстовый ответ (капс сохраняем, точки убираем)
        final_text = ai_reply.strip()
        if not final_text.isupper():
            final_text = final_text.lower()
        if final_text.endswith("."):
            final_text = final_text[:-1].strip()

        if is_business:
            await message.answer(text=final_text)
        else:
            await message.reply(text=final_text)

    except Exception as exc:
        logger.exception("Глобальный сбой в функции send_smart_reply: %s", exc)


async def simulate_typing_delay(chat_id: int, bot_obj: Bot, text_length: int) -> None:
    delay = max(1.0, min((text_length / 25) + random.uniform(0.5, 1.5), 4.5))
    await asyncio.sleep(delay)


# ГРУППОВОЙ ХЭНДЛЕР
@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def handle_group_mention(message: types.Message, bot: Bot) -> None:
    bot_user = await bot.get_me()
    
    is_mentioned = f"@{bot_user.username}" in message.text
    is_reply_to_bot = (
        message.reply_to_message 
        and message.reply_to_message.from_user 
        and message.reply_to_message.from_user.id == bot_user.id
    )

    chat_id = message.chat.id
    if chat_id not in CHATS_HISTORY_CACHE:
        CHATS_HISTORY_CACHE[chat_id] = []
    history = CHATS_HISTORY_CACHE[chat_id]

    sender_name = message.from_user.first_name if message.from_user else "кто-то"
    clean_text = message.text.replace(f"@{bot_user.username}", "").strip() or "че"

    if message.from_user and message.from_user.id == bot_user.id:
        history.append(f"Я: {clean_text}")
    else:
        history.append(f"{sender_name}: {clean_text}")
        
    CHATS_HISTORY_CACHE[chat_id] = history[-20:]

    if not (is_mentioned or is_reply_to_bot) or (message.from_user and message.from_user.id == bot_user.id):
        return

    # Шанс 10% просто поставить быструю реакцию
    if random.random() < 0.10:
        try:
            await message.react([types.ReactionTypeEmoji(emoji=random.choice(RANDOM_REACTIONS))])
            return
        except TelegramAPIError:
            pass

    mode = MODES[CURRENT_GLOBAL_MODE]
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except TelegramAPIError:
        pass

    history_context = "\n".join(CHATS_HISTORY_CACHE[chat_id])
    ai_reply = await fetch_deepseek(mode["prompt"], history_context)
    if not ai_reply:
        return

    await simulate_typing_delay(chat_id, bot, len(ai_reply))
    CHATS_HISTORY_CACHE[chat_id].append(f"Я: {ai_reply}")
    
    await send_smart_reply(message, ai_reply, is_business=False)


# БИЗНЕС ХЭНДЛЕР
@dp.business_message(F.text)
async def handle_business_message(message: types.Message, bot: Bot) -> None:
    if not message.business_connection_id or message.sender_business_bot is not None:
        return

    chat_id = message.chat.id
    if chat_id not in CHATS_HISTORY_CACHE:
        CHATS_HISTORY_CACHE[chat_id] = []
    history = CHATS_HISTORY_CACHE[chat_id]

    if message.from_user and message.from_user.id == OWNER_ID:
        if message.text.startswith("/"): return
        history.append(f"Я: {message.text}")
        CHATS_HISTORY_CACHE[chat_id] = history[-20:]
        return

    if message.text.startswith("/"): return

    history.append(f"Собеседник: {message.text}")
    mode = MODES[CURRENT_GLOBAL_MODE]

    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except TelegramAPIError:
        pass

    history_context = "\n".join(history)
    ai_reply = await fetch_deepseek(mode["prompt"], history_context)
    if not ai_reply:
        return

    await simulate_typing_delay(chat_id, bot, len(ai_reply))
    history.append(f"Я: {ai_reply}")
    CHATS_HISTORY_CACHE[chat_id] = history[-20:]

    await send_smart_reply(message, ai_reply, is_business=True)


# Панель управления
def mode_help_text() -> str:
    lines = [
        "⚔️ **Бизнес-бот перенастроен под чат.**",
        f"Текущий режим: `[{MODES[CURRENT_GLOBAL_MODE]['title']}]`",
        "",
        "**Смена режима:**",
        "- `/mode <ключ>`",
        "",
        "**Режимы:**",
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
async def cmd_start(message: types.Message) -> None:
    if message.from_user.id != OWNER_ID: return
    await message.answer(mode_help_text(), parse_mode="Markdown")

@dp.message(F.text.startswith("/mode"), F.chat.type == "private")
async def cmd_mode(message: types.Message) -> None:
    if message.from_user.id != OWNER_ID: return
    global CURRENT_GLOBAL_MODE
    requested = extract_mode_key(message.text)
    if not requested or requested not in MODES:
        await message.answer("Неизвестный режим. Используй /help.")
        return
    CURRENT_GLOBAL_MODE = requested
    await message.answer(f"🔥 Врублен режим: **{MODES[requested]['title']}**", parse_mode="Markdown")

# Фоновые пинги Render
async def keep_alive():
    await asyncio.sleep(30)
    async with aiohttp.ClientSession() as session:
        while True:
            if RENDER_EXTERNAL_URL:
                try:
                    async with session.get(RENDER_EXTERNAL_URL) as resp: pass
                except Exception: pass
            await asyncio.sleep(600)

async def web_handle(request): return web.Response(text="Bot alive!")

async def main() -> None:
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(keep_alive())
    app = web.Application()
    app.router.add_get("/", web_handle)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
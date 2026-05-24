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

OWNER_ID = 8781645129  # Твой Telegram ID аккаунта
CURRENT_GLOBAL_MODE = "soft"

RANDOM_REACTIONS = ["🔥", "🤡", "🗿", "😂", "💀", "👍", "👀"]

# 📸 Твоя база мемов (Прямые ссылки на картинки)
# Можешь добавлять свои ключевые слова и ссылки
MEMES_DATABASE = {
    "сигма": "https://i.postimg.cc/mD8zZ081/sigma.jpg",
    "фейспалм": "https://i.postimg.cc/4N3K3mY3/facepalm.jpg",
    "пон": "https://i.postimg.cc/85zXpXyL/pon.jpg",
    "клоун": "https://i.postimg.cc/76SgX6Xv/clown.jpg",
    "кринж": "https://i.postimg.cc/9Q2b6MvC/cringe.jpg",
    "база": "https://i.postimg.cc/G3x7hP8L/baza.jpg"
}

# 🎬 Твоя база GIF (Прямые ссылки на гифки или mp4-анимации)
GIFS_DATABASE = {
    "чил": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3BwZ3Z0cmR0Ynd5N3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z/l41YvpiA9uMWw5AMU/giphy.gif",
    "фейл": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbW1wY3g0dzVxd3R6M3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z/3LOXv99X7V6Q8/giphy.gif",
    "инсульт": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbXN6M3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z/l3q2K1M6w1tAJA8iA/giphy.gif",
    "шок": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExN3B3N3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z3M4Z3R5ZXg4Z/11ykUODWZvfHMc/giphy.gif"
}

# Модернизируем промпт: объясняем ИИ, как вызывать картинки и гифки
MEDIA_INSTRUCTION = (
    f"\n\nУ тебя есть суперсила — ты можешь отправлять в чат мемы или GIF, если они идеально подходят под рофл или ситуацию. "
    f"Если хочешь отправить МЕМ, напиши строго в теле ответа (без другого текста): [send_meme:название_мема]. "
    f"Доступные мемы: {', '.join(MEMES_DATABASE.keys())}.\n"
    f"If хочешь отправить ГИФКУ, напиши строго в теле ответа: [send_gif:название_гифки]. "
    f"Доступные гифки: {', '.join(GIFS_DATABASE.keys())}.\n"
    f"Применяй медиа-теги редко (с шансом ~15-20%), только когда это реально разрыв контекста. В остальных случаях отвечай текстом."
)

MODES: dict[str, dict[str, str]] = {
    "soft": {
        "title": "вайбовый (обычный)",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Общайся как 19-летний харизматичный парень. Твой стиль — легкий, постироничный, "
            "абсолютно расслабленный зумерский вайб. Ты общаешься со сверстниками. Используй живой сленг "
            "(жиза, рил, дефолтный, рофл, чилл, треш, байтить, вайб, форсить) естественно, без кринжа и перебора.\n"
            "СТРОЖАЙШИЕ ПРАВИЛА ФОРМАТИРОВАНИЯ:\n"
            "1. Пиши ВСЁ исключительно маленькими буквами (со строчной). Вообще никаких заглавных, даже в именах.\n"
            "2. В конце фраз НЕ СТАВЬ точки.\n"
            "3. Полный запрет на смайлики (типа 😀, 😊) и вежливый ИИ-булшит."
        ) + MEDIA_INSTRUCTION,
    },
    "flirt": {
        "title": "флирт/подкат",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Уверенный, слегка наглый, но дико обаятельный флирт 19-летнего парня. "
            "Никаких ванильных соплей и банальных комплиментов. Тонкий стеб, интрига, легкие подколы. "
            "Пиши коротко, с маленькой буквы, без точек на конце."
        ) + MEDIA_INSTRUCTION,
    },
    "troll": {
        "title": "постирония/троллинг",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Чистая постирония, тонкий ядовитый сарказм зумера. Лови людей на абсурде, "
            "выставляй их излишнюю серьезность смешной, делай из оппонента клоуна, но сам оставайся «на чилле»."
        ) + MEDIA_INSTRUCTION,
    },
    "rough": {
        "title": "жесткий отпор",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Резкий, агрессивный, уверенный отпор на любой наезд или душноту. Если тебя пытаются "
            "задеть или контролировать — моментально осаживай, врубай ментальное доминирование. Без точек, хлестко."
        ) + MEDIA_INSTRUCTION,
    },
    "swear": {
        "title": "фулл мат",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Тотальное уничтожение оппонента с использованием грязного, органичного разговорного мата. "
            "Никаких оправданий, бей фактами, смешивай с грязью их аргументы. Коротко, жестко, без точек и цензуры."
        ) + MEDIA_INSTRUCTION,
    }
}

SYSTEM_CORE = (
    "Текущий год: 2026. Ты — живой человек, тебе 19 лет, обычный парень, фронтендер, сидишь в Telegram со своего аккаунта. "
    "ЖЕСТКОЕ ПРАВИЛО: Ты ни в коем случае не бот, не нейросеть. "
    "Если тебе пишут 'ты бот' — угарай с этого, агрессивно или иронично отрицай. "
    "Выдавай ТОЛЬКО готовый текст ответа или медиа-тег, без кавычек и лишних пояснений."
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
                    f"ТРЕБОВАНИЯ К ТВОЕМУ СТИЛЮ СЕЙЧАС:\n{style_prompt}\n\n"
                    f"ПОСЛЕДНИЕ СООБЩЕНИЯ В ЧАТЕ ДЛЯ КОНТЕКСТА (Я — это 'Я'):\n"
                    f"{history_context}\n\n"
                    f"ЗАДАНИЕ: Напиши идеальный ответ на последнюю реплику. Отвечай как 19-летний парень."
                ),
            },
        ],
        "temperature": 0.9,
        "max_tokens": 250,
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


# 🛠 Функция-обработчик: решает, как именно отправить ответ (текст, фото или гиф)
async def send_smart_reply(message: types.Message, ai_reply: str, is_business: bool = False) -> None:
    # Проверка на команду отправки мема [send_meme:имя]
    meme_match = re.search(r"\[send_meme:(.*?)\]", ai_reply)
    # Проверка на команду отправки гифки [send_gif:имя]
    gif_match = re.search(r"\[send_gif:(.*?)\]", ai_reply)

    try:
        if meme_match:
            key = meme_match.group(1).strip().lower()
            if key in MEMES_DATABASE:
                await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
                if is_business:
                    await message.answer_photo(photo=MEMES_DATABASE[key])
                else:
                    await message.reply_photo(photo=MEMES_DATABASE[key])
                return
        
        elif gif_match:
            key = gif_match.group(1).strip().lower()
            if key in GIFS_DATABASE:
                await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_DOCUMENT)
                if is_business:
                    await message.answer_animation(animation=GIFS_DATABASE[key])
                else:
                    await message.reply_animation(animation=GIFS_DATABASE[key])
                return

        # Если тегов нет — отправляем обычный зумерский текст в нижнем регистре
        final_text = ai_reply.lower()
        if is_business:
            await message.answer(text=final_text)
        else:
            await message.reply(text=final_text)

    except TelegramAPIError:
        logger.exception("Ошибка отправки медиа/текстового ответа")


async def simulate_typing_delay(chat_id: int, bot_obj: Bot, text_length: int) -> None:
    delay = max(1.5, min((text_length / 18) + random.uniform(0.8, 2.0), 5.5))
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
    clean_text = message.text.replace(f"@{bot_user.username}", "").strip() or "а?"

    if message.from_user and message.from_user.id == bot_user.id:
        history.append(f"Я: {clean_text}")
    else:
        history.append(f"{sender_name}: {clean_text}")
        
    CHATS_HISTORY_CACHE[chat_id] = history[-20:]

    if not (is_mentioned or is_reply_to_bot) or (message.from_user and message.from_user.id == bot_user.id):
        return

    if random.random() < 0.12:
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
    
    # Сохраняем чистый ответ ИИ в историю
    CHATS_HISTORY_CACHE[chat_id].append(f"Я: {ai_reply}")
    
    # Отправляем через умный метод (картинка/гифка/текст)
    await send_smart_reply(message, ai_reply, is_business=False)


# БИЗНЕС ХЭНДЛЕР (ЛИЧКА)
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


# Управление режимами (оставляем без изменений)
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
    await message.answer(f"🔥 Режим изменен на: **{MODES[requested]['title']}**", parse_mode="Markdown")

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
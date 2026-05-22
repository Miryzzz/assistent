import asyncio
import logging
import os
import random
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

# Глобальная переменная для хранения текущего режима
CURRENT_GLOBAL_MODE = "soft"

# Набор боевых режимов
MODES: dict[str, dict[str, str]] = {
    "soft": {
        "title": "обычный (добрый)",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Разговорный, максимально живой, простой и расслабленный стиль общения молодого, "
            "уверенного в себе парня со своими знакомыми. Общайся на равных, дружелюбно, адекватно и без негатива. "
            "Используй простой человеческий сленг, пиши так, как люди реально переписываются в мессенджерах.\n"
            "СТРОЖАЙШИЕ ПРАВИЛА ФОРМАТИРОВАНИЯ:\n"
            "1. Пиши ВСЁ исключительно со строчной (маленькой) буквы. Никаких заглавных букв в начале предложений.\n"
            "2. В конце коротких фраз и сообщений НЕ СТАВЬ точки вообще. Они создают ощущение агрессии.\n"
            "3. Полный запрет на приторную вежливость, официоз, смайлики и канцеляризмы типа 'С уважением', 'Чем я могу помочь?'. "
            "Текст должен выглядеть как быстрое, уверенное и простое текстовое сообщение."
        ),
    },
    "flirt": {
        "title": "флирт",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Дерзкий, интригующий, уверенный флирт. Общайся легко и игриво. "
            "Никаких банальных комплиментов и соплей. Тонко подкалывай собеседника, вызывай эмоции и создавай интригу.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Короткие фразы пиши с маленькой буквы, точки на конце предложений не ставь."
        ),
    },
    "strict": {
        "title": "жёстко",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Максимально сухой, твердый, emotional холодный и отстраненный. "
            "Полное отсутствие эмоций, вежливости и смайлов. Оперируй только голыми фактами. "
            "Закрывай любые глупые дискуссии одной-двумя вескими фразами.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Текст должен быть коротким, обрубленным, без лишних слов."
        ),
    },
    "official": {
        "title": "официально",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Ледяной деловой язык, безупречная и строгая грамотность. "
            "Никого сленга. Твои интересы — в приоритете, отстаивай их аргументированно, "
            "четко и строго по делу. Спокойное интеллектуальное превосходство.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Пиши строго с заглавных букв, соблюдай все правила пунктуации, ставь точки."
        ),
    },
    "short": {
        "title": "сократи",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Резкая, хлесткая суть. Максимум уверенности, минимум букв.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Выдай ровно одну короткую фразу (не более 5-7 слов). "
            "Пиши исключительно с маленькой буквы, без точки на конце."
        ),
    },
    "reply": {
        "title": "ответ",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Естественный, сильный, живой ответ взрослого парня. Твоя главная цель — "
            "удержать инициативу в диалоге за собой (задавай вектор, веди разговор, не будь ведомым).\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Обычный разговорный стиль без перегибов в жесткость."
        ),
    },
    "troll": {
        "title": "троллинг",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Ядовитый сарказм и чистая ирония. Невозмутимо высмеивай аргументы собеседника. "
            "Лови его на глупости, абсурде и противоречиях. Выставляй его важность смешной, делай из него клоуна, "
            "но сам оставайся абсолютно спокойным.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Используй колкие разговорные обороты."
        ),
    },
    "rough": {
        "title": "грубо",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Дерзкий, агрессивный, прямолинейный наезд. Если в твой адрес идет малейшая попытка контроля "
            "или критики — мгновенно бей в ответ. Осаживай собеседника, используй жесткие, подавляющие психологические приемы.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Короткие, бьющие фразы. Без точек."
        ),
    },
    "swear": {
        "title": "мат",
        "prompt": (
            "СТИЛЬ ОБЩЕНИЯ: Тотальное и жесткое доминирование в диалоге с использованием сочного, "
            "грязного и отборного русского мата без цензуры. Если собеседник пытается тебя задеть, "
            "поставить под сомнение твой авторитет, критиковать или вести себя токсично — твоя цель "
            "мгновенно раскатать его эго тонким слоем, смешать с грязью и морально уничтожить встречным "
            "дерзким панчем. Ты общаешься как абсолютно уверенный в себе, харизматичный и опасный парень, "
            "который ментально на голову выше оппонента. Никаких оправданий, соплей или слабых оскорблений. "
            "Бей фактами, приправленными жестким матом.\n"
            "ПРАВИЛА ФОРМАТИРОВАНИЯ: Короткие, бьющие, как пощечина, фразы. Не ставь точки в конце коротких предложений. "
            "Пиши без звездочек и цензуры."
        ),
    }
}

SYSTEM_CORE = (
    "Ты — это я (владелец аккаунта), живой человек, парень, пишущий сообщения со своего личного Telegram. "
    "ЖЕСТКОЕ ПРАВИЛО: Ты ни при каких обстоятельствах не имеешь права говорить, намекать или признавать, "
    "что ты являешься ботом, искусственным интеллектом, нейросетью или алгоритмом. "
    "Если собеседник обвиняет тебя в том, что ты бот, или пишет: 'ты бот', 'с кем я говорю', 'это автоответчик' — "
    "категорически отрицай это, отшучивайся, иронизируй или переводи стрелки, но общайся как реальный человек. "
    "Выдавай ТОЛЬКО готовый текст ответа, без кавычек и без лишних пояснений от себя."
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


def mode_help_text() -> str:
    lines = [
        "🤖 **Бизнес-бот активен.**",
        f"Текущий глобальный режим для всех чатов: `[{MODES[CURRENT_GLOBAL_MODE]['title']}]`",
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


# Имитация набора текста человеком
async def simulate_typing_delay(chat_id: int, bot_obj: Bot, text_length: int) -> None:
    delay = (text_length / 15) + random.uniform(1.0, 2.5)
    delay = max(2.0, min(delay, 7.0))
    
    logger.info("Simulating typing delay for %s seconds in chat %s", round(delay, 2), chat_id)
    
    spent = 0.0
    while spent < delay:
        try:
            await bot_obj.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except TelegramAPIError:
            pass
        step = min(4.5, delay - spent)
        await asyncio.sleep(step)
        spent += step


@dp.message(Command("start", "help"), F.chat.type == "private")
async def cmd_start(message: types.Message) -> None:
    if message.from_user.id != OWNER_ID:
        return
    await message.answer(mode_help_text(), parse_mode="Markdown")


@dp.message(F.text.startswith("/mode"), F.chat.type == "private")
async def cmd_mode(message: types.Message) -> None:
    if message.from_user.id != OWNER_ID:
        return

    global CURRENT_GLOBAL_MODE
    requested = extract_mode_key(message.text)

    if not requested:
        await message.answer(mode_help_text(), parse_mode="Markdown")
        return

    if requested not in MODES:
        await message.answer("Неизвестный режим. Используй /help.")
        return

    CURRENT_GLOBAL_MODE = requested
    await message.answer(f"🔥 Режим успешно изменен для всех чатов на: **{MODES[requested]['title']}**", parse_mode="Markdown")


# РАБОТА В ГРУППАХ ПРИ УПОМИНАНИИ БОТА
@dp.message(F.chat.type.in_({"group", "supergroup"}), lambda message: message.text)
async def handle_group_mention(message: types.Message, bot: Bot) -> None:
    bot_user = await bot.get_me()
    if f"@{bot_user.username}" not in message.text:
        return

    chat_id = message.chat.id
    if chat_id not in CHATS_HISTORY_CACHE:
        CHATS_HISTORY_CACHE[chat_id] = []
    history = CHATS_HISTORY_CACHE[chat_id]

    clean_text = message.text.replace(f"@{bot_user.username}", "").strip()
    if not clean_text:
        clean_text = "Привет"

    sender_name = message.from_user.full_name if message.from_user else "Собеседник"
    history.append(f"{sender_name}: {clean_text}")

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
    CHATS_HISTORY_CACHE[chat_id] = history[-6:]

    try:
        await message.reply(text=ai_reply)
    except TelegramAPIError:
        logger.exception("Failed to send group reply")


# РАБОТА В ЛИЧНЫХ ЧАТАХ (TELEGRAM BUSINESS API)
@dp.business_message(F.text)
async def handle_business_message(message: types.Message, bot: Bot) -> None:
    if not message.business_connection_id:
        return

    if message.sender_business_bot is not None:
        return

    chat_id = message.chat.id
    if chat_id not in CHATS_HISTORY_CACHE:
        CHATS_HISTORY_CACHE[chat_id] = []
    history = CHATS_HISTORY_CACHE[chat_id]

    user_id = message.from_user.id if message.from_user else None

    # Жесткий скип: твои собственные сообщения уходят только в историю контекста
    if message.from_user and message.from_user.id == OWNER_ID:
        history.append(f"Я: {message.text}")
        CHATS_HISTORY_CACHE[chat_id] = history[-6:]
        return

    if message.chat.type == "private" and message.from_user.id == OWNER_ID and message.text.startswith("/"):
        return

    if message.text.startswith("/"):
        return

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
    CHATS_HISTORY_CACHE[chat_id] = history[-6:]

    try:
        await message.answer(text=ai_reply)
    except TelegramAPIError:
        logger.exception("Failed to send business reply")


# АВТОПИНГ ДЛЯ БЕСПЛАТНОГО ТАРИФА RENDER
async def keep_alive():
    await asyncio.sleep(30)
    async with aiohttp.ClientSession() as session:
        while True:
            if RENDER_EXTERNAL_URL:
                try:
                    async with session.get(RENDER_EXTERNAL_URL) as resp:
                        logger.info("Self-ping status: %s", resp.status)
                except Exception as e:
                    logger.error("Self-ping failed: %s", e)
            else:
                logger.warning("RENDER_EXTERNAL_URL environment variable is empty.")
            await asyncio.sleep(600)


async def web_handle(request):
    return web.Response(text="Bot is running alive!")


async def main() -> None:
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(keep_alive())

    app = web.Application()
    app.router.add_get("/", web_handle)
    
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    logger.info("Starting web server on port %s", port)
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
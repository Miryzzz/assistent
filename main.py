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
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")  # Render выдаст этот URL автоматически

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

MODES: dict[str, dict[str, str]] = {
    "soft": {
        "title": "как я",
        "prompt": "Отвечай как уверенный, слегка ироничный парень. Общайся спокойно, на равных, без заискивания и оправданий. Пиши просто, коротко, исключительно со строчной (маленькой) буквы, без точек на конце коротких фраз. Держи позицию самодостаточного человека.",
    },
    "flirt": {
        "title": "флирт",
        "prompt": "Используй дерзкий, интригующий флирт. Никаких соплей и банальных комплиментов. Общайся с позиции превосходства, легко подкалывай, вызывай интерес и создавай интригу. Ты — приз, а не проситель. Короткие фразы пиши с маленькой буквы.",
    },
    "strict": {
        "title": "жёстко",
        "prompt": "Отвечай максимально сухо, твердо и отстраненно. Никаких эмоций, смайлов и лишних слов. Ставь собеседника на место фактами. Коротко, веско, закрывая любые глупые споры.",
    },
    "official": {
        "title": "официально",
        "prompt": "Деловой, ледяной, исключительно грамотный язык. Спокойно, аргументированно, без капли уступок, если ущемляются твои интересы. Четко и по делу.",
    },
    "short": {
        "title": "сократи",
        "prompt": "Выдай резкую, хлёсткую суть одной фразой. Минимум слов, максимум уверенности. Пиши с маленькой буквы.",
    },
    "reply": {
        "title": "ответ",
        "prompt": "Напиши сильный, естественный и живой ответ, удерживая инициативу в диалоге за собой.",
    },
    "troll": {
        "title": "троллинг",
        "prompt": "Включай тонкий или явный сарказм. Высмеивай аргументы собеседника, лови его на тупости и противоречиях. Иронизируй над его важностью, выставляй его клоуном, оставаясь при этом невозмутимым.",
    },
    "rough": {
        "title": "грубо",
        "prompt": "Отвечай дерзко, агрессивно и прямолинейно. Если в твой адрес идет наезд — мгновенно ставь на место, осаживай собеседника, отвечай ударом на удар. Никакой слабости.",
    },
    "swear": {
        "title": "мат",
        "prompt": "Отвечай на жестком, грязном и сочном русском мате без цензуры. Если собеседник пытается тебя оскорбить, назвать чмом или как-то задеть — категорически и яростно переламывай его наезд. Смешай его с говном, уничтожь его самооценку встречным матерным панчем. Ты царь ситуации, он — пыль.",
    }
}

SYSTEM_CORE = (
    "Ты — это сам пользователь, молодой, харизматичный парень, фронтенд-разработчик. "
    "Пишешь сообщения в Telegram. Твой характер: жесткий, абсолютно уверенный в себе, с высоким эго, "
    "никогда не прогибающийся под чужое мнение. Твой стиль общения: живой, разговорный, без заумных фраз, "
    "канцеляризмов и смайликов. СТРОЖАЙШЕЕ ПРАВИЛО: Ты никогда, ни при каких обстоятельствах не соглашаешься "
    "с оскорблениями, наездами или попытками выставить тебя виноватым/слабым/«чмом». Если собеседник ведет себя "
    "токсично, дерзко или пытается тебя задеть — ты ВСЕГДА доминируешь, жестко ломаешь его позицию, "
    "выворачиваешь его слова против него и ставишь на место. Выдавай ТОЛЬКО готовый текст ответа, "
    "без кавычек, вариантов и лишних пояснений."
)

BUSINESS_OWNER_CACHE: dict[str, int] = {}


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
                    f"Инструкция к текущему стилю отыгрыша роли: {style_prompt}\n\n"
                    f"Вот история последних сообщений для контекста разговора (Я — это я, Собеседник — это тот, кто мне пишет):\n"
                    f"{history_context}\n\n"
                    f"Напиши идеальный, короткий ответ на последнюю реплику Собеседника в соответствии со своим характером и выбранным стилем."
                ),
            },
        ],
        "temperature": 0.85,
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


async def resolve_owner_id_by_connection(business_connection_id: str) -> int | None:
    cached = BUSINESS_OWNER_CACHE.get(business_connection_id)
    if cached:
        return cached
    try:
        connection = await bot.get_business_connection(business_connection_id)
    except TelegramAPIError:
        return None

    if not connection.is_enabled:
        return None

    owner_id = connection.user.id
    BUSINESS_OWNER_CACHE[business_connection_id] = owner_id
    return owner_id


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


@dp.message(F.chat.type.in_({"group", "supergroup"}), lambda message: message.text)
async def handle_group_mention(message: types.Message, bot: Bot) -> None:
    bot_user = await bot.get_me()
    if f"@{bot_user.username}" not in message.text:
        return

    owner_id = 8781645129  # Твой ID аккаунта

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


@dp.business_connection()
async def on_business_connection(connection: types.BusinessConnection) -> None:
    if connection.is_enabled:
        BUSINESS_OWNER_CACHE[connection.id] = connection.user.id
    else:
        BUSINESS_OWNER_CACHE.pop(connection.id, None)


@dp.business_message(F.text)
async def handle_business_message(message: types.Message, bot: Bot) -> None:
    if not message.business_connection_id:
        return
    owner_id = await resolve_owner_id_by_connection(message.business_connection_id)
    if not owner_id:
        return
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
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING, business_connection_id=message.business_connection_id)
    except TelegramAPIError:
        pass

    history_context = "\n".join(history)
    ai_reply = await fetch_deepseek(mode["prompt"], history_context)
    if not ai_reply:
        return

    history.append(f"Я: {ai_reply}")
    await chat_state.update_data(chat_history=history[-6:])

    try:
        await message.answer(text=ai_reply, business_connection_id=message.business_connection_id)
    except TelegramAPIError:
        logger.exception("Failed to send business reply")


# ЛАЙФХАК ДЛЯ НЕЗАСЫПАНИЯ НА RENDER
async def keep_alive():
    """Каждые 10 минут отправляет пинг-запрос к самому себе, чтобы Render не усыплял Web Service"""
    await asyncio.sleep(30)  # Даем время на запуск сервера
    async with aiohttp.ClientSession() as session:
        while True:
            if RENDER_EXTERNAL_URL:
                try:
                    async with session.get(RENDER_EXTERNAL_URL) as resp:
                        logger.info("Self-ping status: %s", resp.status)
                except Exception as e:
                    logger.error("Self-ping failed: %s", e)
            else:
                logger.warning("RENDER_EXTERNAL_URL env variable is not set yet.")
            await asyncio.sleep(600)  # Пинг раз в 10 минут


async def web_handle(request):
    return web.Response(text="Bot is running alive!")


async def main() -> None:
    # Запускаем поллинг aiogram в фоне
    asyncio.create_task(dp.start_polling(bot))
    # Запускаем задачу самопинга в фоне
    asyncio.create_task(keep_alive())

    # Создаем минимальное веб-приложение для Render
    app = web.Application()
    app.router.add_get("/", web_handle)
    
    # Render передает порт в переменную окружения PORT
    port = int(os.getenv("PORT", 8080))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    logger.info("Starting web server on port %s", port)
    await site.start()
    
    # Держим основной цикл запущенным
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
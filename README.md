# Telegram Business Bot (aiogram 3.x)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create `.env` from `.env.example` and fill values:

- `BOT_TOKEN`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL` (optional, default `deepseek-chat`)

3. Run:

```bash
python business_bot.py
```

## Commands in bot DM

- `/help`
- `/mode <key>`
- `/mode_<key>`

Available mode keys are shown in `/help`.

## Telegram Business

In Telegram app:

`Settings -> Telegram Business -> Chatbots -> Add bot`

Then add your bot and limit access to selected chats for testing first.

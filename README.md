# Telegram GPT Bot

Простой Telegram-бот с подключением к API ChatGPT через официальный OpenAI SDK.

## Что умеет

- отвечает на текстовые сообщения;
- помнит последние сообщения в рамках запущенного процесса;
- умеет экономить токены через режим `/economy`;
- сжимает старую историю в короткое резюме;
- очищает память командой `/reset`;
- разбивает длинные ответы на несколько сообщений Telegram.

## Настройка

1. Создайте бота через [@BotFather](https://t.me/BotFather) и получите Telegram-токен.
2. Создайте файл `.env` по примеру:

```bash
cp .env.example .env
```

3. Откройте `.env` и заполните:

```env
TELEGRAM_BOT_TOKEN=ваш_telegram_токен
OPENAI_API_KEY=ваш_openai_api_key
```

## Запуск

Нужен Python 3.10 или новее.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

После запуска откройте своего бота в Telegram и отправьте ему сообщение.

## Структура проекта

- `bot.py` - точка входа;
- `tg_gpt_bot/config.py` - настройки из `.env`;
- `tg_gpt_bot/handlers.py` - команды и обработчики Telegram;
- `tg_gpt_bot/memory.py` - режимы, история и сборка контекста;
- `tg_gpt_bot/openai_memory.py` - сжатие старой истории в резюме;
- `tg_gpt_bot/telegram_utils.py` - отправка длинных сообщений частями.

## Команды

- `/start` - начать диалог заново;
- `/help` - показать подсказку;
- `/reset` - очистить память диалога;
- `/economy` - включить экономный режим;
- `/caveman` - то же самое, что `/economy`;
- `/normal` - вернуться к обычному режиму;
- `/mode` - показать текущий режим.

## Настройки

В `.env` можно поменять модель:

```env
OPENAI_MODEL=gpt-4.1-mini
```

И системную инструкцию:

```env
SYSTEM_PROMPT=Ты полезный ассистент в Telegram. Отвечай кратко и понятно.
```

## Экономия токенов

Эконом-режим включается командой `/economy`. В этом режиме бот:

- отправляет в OpenAI меньше последних сообщений;
- просит модель отвечать короче;
- ограничивает максимальную длину ответа;
- сохраняет старый контекст в виде краткого резюме.

Настройки по умолчанию:

```env
ECONOMY_HISTORY_MESSAGES=4
ECONOMY_MAX_OUTPUT_TOKENS=250
SUMMARY_BATCH_MESSAGES=6
SUMMARY_ENABLED=true
SUMMARY_MAX_CHARS=900
MAX_STORED_MESSAGE_CHARS=1400
```

Чтобы вернуться к обычным ответам, отправьте `/normal`.

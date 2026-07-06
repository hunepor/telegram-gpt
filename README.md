# Telegram GPT Bot

Простой Telegram-бот с подключением к API ChatGPT через официальный OpenAI SDK.

## Что умеет

- отвечает на текстовые сообщения;
- помнит последние сообщения в рамках запущенного процесса;
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

## Команды

- `/start` - начать диалог заново;
- `/help` - показать подсказку;
- `/reset` - очистить память диалога.

## Настройки

В `.env` можно поменять модель:

```env
OPENAI_MODEL=gpt-4.1-mini
```

И системную инструкцию:

```env
SYSTEM_PROMPT=Ты полезный ассистент в Telegram. Отвечай кратко и понятно.
```

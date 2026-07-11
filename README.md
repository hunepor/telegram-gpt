# Telegram GPT Bot

Простой Telegram-бот с подключением к API ChatGPT через официальный OpenAI SDK.

## Что умеет

- отвечает на текстовые сообщения;
- в группах отвечает через `/ask`, Guest Mode или reply;
- принимает гарантированно доставляемую в Privacy Mode команду `/ask вопрос`;
- помнит последние сообщения в рамках запущенного процесса;
- по умолчанию работает в `caveman`-режиме;
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

Для обращения через `@username_бота` с включенным Privacy Mode включите для бота
`Guest Mode` в настройках `@BotFather`. После этого в групповом чате можно написать:

```text
@okivajbot напиши функцию сортировки пузырьком на Python
```

Telegram доставляет такие обращения отдельными `guest_message`-событиями. Бот также
продолжает отвечать на обычные reply к своим сообщениям в группе.

Как надёжный вариант для групп с Privacy Mode используйте команду:

```text
/ask напиши функцию сортировки пузырьком на Python
```

Можно отправить `/ask` ответом на сообщение другого пользователя. Тогда бот прочитает
текст исходного сообщения и ответит на него. Дополнительная инструкция тоже поддерживается:

```text
/ask проверь факты в этом сообщении
```

Если в группе несколько ботов, можно явно указать адресата:

```text
/ask@okivajbot напиши функцию сортировки пузырьком на Python
```

## Запуск в Docker

Сначала создайте и заполните `.env`:

```bash
cp .env.example .env
```

Соберите и запустите контейнер:

```bash
docker compose up -d --build
```

Посмотреть логи:

```bash
docker compose logs -f
```

Остановить бота:

```bash
docker compose down
```

Контейнер не открывает порты наружу: бот получает сообщения через Telegram polling.

## Запуск через Apple containers

Нужен Apple `container` CLI на Mac с Apple silicon и macOS 26. После установки один раз запустите system service:

```bash
container system start
```

Соберите образ:

```bash
bash scripts/apple-container-build.sh
```

Запустите бота:

```bash
bash scripts/apple-container-run.sh
```

Посмотреть логи:

```bash
bash scripts/apple-container-logs.sh
```

Остановить и удалить контейнер:

```bash
bash scripts/apple-container-stop.sh
```

Пересобрать и перезапустить одной командой:

```bash
bash scripts/apple-container-rerun.sh
```

Скрипты используют образ `telegram-gpt-bot:local`, контейнер `telegram-gpt` и env-файл `.env`. Их можно переопределить:

```bash
IMAGE_NAME=my-bot:dev CONTAINER_NAME=my-bot ENV_FILE=.env.local bash scripts/apple-container-run.sh
```

## Структура проекта

- `bot.py` - точка входа;
- `tg_gpt_bot/config.py` - настройки из `.env`;
- `tg_gpt_bot/handlers.py` - команды и обработчики Telegram;
- `tg_gpt_bot/memory.py` - режимы, история и сборка контекста;
- `tg_gpt_bot/openai_memory.py` - сжатие старой истории в резюме;
- `tg_gpt_bot/telegram_utils.py` - отправка длинных сообщений частями.
- `scripts/apple-container-*.sh` - сборка и запуск через Apple `container`.

## Команды

При запуске бот автоматически добавляет эти команды в меню Telegram:

- `/start` - начать диалог заново;
- `/help` - показать подсказку;
- `/reset` - очистить память диалога;
- `/caveman` - включить короткий caveman-режим, если ранее был выбран обычный;
- `/economy` - то же самое, что `/caveman`;
- `/normal` - вернуться к обычному режиму;
- `/mode` - показать текущий режим;
- `/ask вопрос` - задать вопрос или обработать сообщение через reply, в том числе с Privacy Mode.

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

`Caveman`-режим включен по умолчанию. В этом режиме бот:

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

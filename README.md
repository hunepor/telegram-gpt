# Telegram GPT Bot

Простой Telegram-бот с подключением к API ChatGPT через официальный OpenAI SDK.

## Что умеет

- отвечает на текстовые сообщения и обычные Telegram-фото;
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

Бот умеет принимать обычные Telegram-фото. Если отправить фото без подписи, он
опишет изображение. Если добавить подпись, она станет вопросом к картинке.
По умолчанию используется экономная детализация `IMAGE_DETAIL=low`, модель менять
не нужно: `gpt-4.1-mini` поддерживает обработку изображений.

Для обращения через `@username_бота` с включенным Privacy Mode включите для бота
`Guest Mode` в настройках `@BotFather`. После этого в групповом чате можно написать:

```text
@your_assistant_bot напиши функцию сортировки пузырьком на Python
```

Telegram доставляет такие обращения отдельными `guest_message`-событиями. Бот также
продолжает отвечать на обычные reply к своим сообщениям в группе.

Guest-вызов можно отправить ответом на чужое сообщение. Бот прочитает исходный текст,
даже если после упоминания нет дополнительной инструкции:

```text
@your_assistant_bot
```

Если написать `@your_assistant_bot проверь факты`, исходное сообщение станет контекстом, а текст
после упоминания - задачей.

Как надёжный вариант для групп с Privacy Mode используйте команду:

```text
/ask напиши функцию сортировки пузырьком на Python
```

Можно отправить `/ask` ответом на сообщение другого пользователя. Тогда бот прочитает
текст исходного сообщения и ответит на него. Дополнительная инструкция тоже поддерживается:

```text
/ask проверь факты в этом сообщении
```

Команду `/ask` также можно отправить ответом на фото. Если написать команду без
дополнительного текста, бот просто опишет изображение.

Для актуальной информации используйте `/search запрос`. Бот выполнит веб-поиск и приложит
ссылки на использованные источники. Поиск тарифицируется OpenAI отдельно от токенов модели.

Если в группе несколько ботов, можно явно указать адресата:

```text
/ask@your_assistant_bot напиши функцию сортировки пузырьком на Python
```

## Запуск на VPS без Docker

Для Ubuntu или Debian сначала установите Git и клонируйте репозиторий в `/opt`:

```bash
sudo apt update
sudo apt install -y git
sudo mkdir -p /opt/telegram-gpt
sudo chown "$USER:$USER" /opt/telegram-gpt
git clone https://github.com/hunepor/telegram-gpt.git /opt/telegram-gpt
cd /opt/telegram-gpt
```

Запустите установщик. Он создаст отдельного пользователя `telegram-gpt`, Python-окружение,
файл настроек в `/etc/telegram-gpt/bot.env` и сервис `systemd`:

```bash
sudo bash scripts/vps-install.sh
```

Заполните токены в созданном файле:

```bash
sudo nano /etc/telegram-gpt/bot.env
```

Запустите бота и включите автоматический старт после перезагрузки VPS:

```bash
sudo systemctl enable --now telegram-gpt
```

Посмотреть логи:

```bash
sudo journalctl -u telegram-gpt -f
```

Перезапустить или остановить:

```bash
sudo systemctl restart telegram-gpt
sudo systemctl stop telegram-gpt
```

Обновление после новых коммитов:

```bash
sudo -u telegram-gpt git -C /opt/telegram-gpt pull --ff-only
sudo -u telegram-gpt /opt/telegram-gpt/.venv/bin/pip install -r /opt/telegram-gpt/requirements.txt
sudo systemctl restart telegram-gpt
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
- `scripts/vps-install.sh` - установка на Ubuntu/Debian через `systemd`.
- `deploy/telegram-gpt.service` - unit-файл для постоянной работы на VPS.

## Команды

При запуске бот автоматически добавляет эти команды в меню Telegram:

- `/start` - начать диалог заново;
- `/help` - показать подсказку;
- `/reset` - очистить память диалога;
- `/caveman` - включить короткий caveman-режим, если ранее был выбран обычный;
- `/economy` - то же самое, что `/caveman`;
- `/normal` - вернуться к обычному режиму;
- `/mode` - показать текущий режим;
- `/ask вопрос` - задать вопрос или обработать сообщение/фото через reply, в том числе с Privacy Mode.
- `/search вопрос` - искать ответ в интернете и показать ссылки на источники.

## Настройки

В `.env` можно поменять модель:

```env
OPENAI_MODEL=gpt-4.1-mini
```

Для картинок можно поменять детализацию. `low` дешевле, `high` точнее:

```env
IMAGE_DETAIL=low
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

# Telegram GPT Bot

Простой Telegram-бот с подключением к API ChatGPT через официальный OpenAI SDK.

## Что умеет

- отвечает на текстовые сообщения и обычные Telegram-фото;
- в группах отвечает через `/ask`, Guest Mode или reply;
- принимает гарантированно доставляемую в Privacy Mode команду `/ask вопрос`;
- помнит последние сообщения в рамках запущенного процесса;
- по умолчанию работает в `caveman`-режиме;
- умеет принимать оплату Telegram Stars за кредиты запросов;
- хранит баланс, платежи и бесплатный список в SQLite;
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

### Деплой с локальной машины по SSH

Для обновления VPS из локального клона сначала отправьте нужную ветку в `origin`.
Убедитесь, что локальные изменения закоммичены, а SSH-пользователь может читать
репозиторий на сервере и перезапускать сервис через `sudo systemctl`.

Задайте адрес VPS и запустите скрипт из каталога репозитория:

```bash
SSH_TARGET=telegram-gpt@your-vps.example bash scripts/deploy-ssh.sh
```

При необходимости можно указать SSH-порт, ключ, каталог приложения или имя сервиса:

```bash
SSH_TARGET=telegram-gpt@your-vps.example \\
SSH_PORT=2222 \\
SSH_KEY=~/.ssh/id_ed25519 \\
APP_DIR=/opt/telegram-gpt \\
bash scripts/deploy-ssh.sh
```

Скрипт проверит чистоту локальной рабочей копии, обновит на сервере ту же ветку
из `origin`, установит зависимости и перезапустит `systemd`-сервис. `.env` и база
данных остаются на VPS.

База балансов и платежей хранится в `/var/lib/telegram-gpt/bot.db`. Каталог создаётся
через `systemd` и не удаляется при обновлении кода.

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
Баланс и платежи хранятся в Docker volume `telegram-gpt-data`.

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

Apple `container`-скрипты хранят SQLite-базу в volume `telegram-gpt-data`.

## Структура проекта

- `bot.py` - точка входа;
- `tg_gpt_bot/config.py` - настройки из `.env`;
- `tg_gpt_bot/billing.py` - баланс, платежи Telegram Stars и бесплатный список в SQLite;
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
- `/ask вопрос` - задать вопрос или обработать сообщение/фото через reply, в том числе с Privacy Mode;
- `/buy` - купить кредиты за Telegram Stars;
- `/balance` - показать баланс кредитов;
- `/terms` - условия оплаты;
- `/paysupport` - поддержка по оплатам;
- `/id` - показать ваш Telegram user id.

## Настройки

В `.env` можно поменять модель:

```env
OPENAI_MODEL=gpt-4.1-mini
```

Для картинок можно поменять детализацию. `low` дешевле, `high` точнее:

```env
IMAGE_DETAIL=low
```

## Оплата Telegram Stars

Оплата выключена по умолчанию, чтобы обновление не заблокировало существующий запуск.
Чтобы включить платный режим, добавьте в `.env` или `/etc/telegram-gpt/bot.env`:

```env
PAYMENTS_ENABLED=true
ADMIN_USER_IDS=123456789
STARS_PRICE=50
CREDITS_PER_PURCHASE=50
TEXT_REQUEST_CREDITS=1
IMAGE_REQUEST_CREDITS=2
```

`ADMIN_USER_IDS` - это Telegram user id владельцев, которые могут управлять
бесплатным списком. Узнать свой id можно командой `/id`.

Бесплатный список хранится в SQLite. Первично его можно заполнить через `.env`:

```env
FREE_USER_IDS=123456789,987654321
```

Эти id будут добавлены в БД при запуске. Дальше администратор может управлять
списком командами:

```text
/allow 123456789
/unallow 123456789
/freeusers
```

Также `/allow` и `/unallow` можно отправить ответом на сообщение пользователя.

Когда платный режим включён:

- пользователи из бесплатного списка и админы пользуются ботом бесплатно;
- остальные покупают кредиты через `/buy`;
- текстовый запрос списывает `TEXT_REQUEST_CREDITS`;
- запрос с картинкой списывает `IMAGE_REQUEST_CREDITS`;
- при ошибке OpenAI списанный кредит возвращается.

Для цифровых товаров и услуг Telegram требует оплату через Stars (`XTR`). Бот
также отвечает на `/terms` и `/paysupport`, что нужно для нормального платёжного UX.

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

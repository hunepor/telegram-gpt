from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MODEL = "gpt-4.1-mini"
MODE_NORMAL = "normal"
MODE_ECONOMY = "caveman"
DEFAULT_SYSTEM_PROMPT = (
    "Ты полезный ассистент в Telegram. Отвечай понятно, дружелюбно и по делу. "
    "Если пользователь пишет на русском, отвечай на русском."
)
DEFAULT_ECONOMY_SYSTEM_PROMPT = (
    "Ты полезный ассистент в Telegram в режиме caveman. Отвечай максимально кратко и по делу. "
    "Не повторяй вопрос, не добавляй вступления. Обычно хватает 1-4 коротких предложений."
)
SUMMARY_SYSTEM_PROMPT = (
    "Сожми историю диалога в короткую память для будущих ответов. "
    "Оставь только устойчивые факты, решения, предпочтения пользователя и открытые задачи. "
    "Не добавляй новых фактов."
)


@dataclass(frozen=True)
class ModeSettings:
    system_prompt: str
    history_messages: int
    max_output_tokens: int


@dataclass(frozen=True)
class AppSettings:
    telegram_token: str
    openai_api_key: str
    model: str
    summary_model: str
    normal_mode: ModeSettings
    economy_mode: ModeSettings
    max_stored_message_chars: int
    summary_enabled: bool
    summary_batch_messages: int
    summary_max_chars: int
    summary_max_output_tokens: int
    image_detail: str
    payments_enabled: bool
    state_db_path: str
    admin_user_ids: frozenset[int]
    free_user_ids: frozenset[int]
    credits_per_purchase: int
    stars_price: int
    text_request_credits: int
    image_request_credits: int
    payment_support_text: str


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Заполните переменную {name} в файле .env")
    return value


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Переменная {name} должна быть числом") from exc

    if value < minimum:
        raise RuntimeError(f"Переменная {name} должна быть не меньше {minimum}")

    return value


def env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on", "да"}


def env_choice(name: str, default: str, choices: set[str]) -> str:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise RuntimeError(f"Переменная {name} должна быть одной из: {allowed}")

    return value


def env_user_ids(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return frozenset()

    user_ids: set[int] = set()
    for item in raw_value.replace(";", ",").replace(" ", ",").split(","):
        item = item.strip()
        if not item:
            continue

        try:
            user_ids.add(int(item))
        except ValueError as exc:
            raise RuntimeError(f"Переменная {name} должна содержать Telegram user id") from exc

    return frozenset(user_ids)


def load_settings() -> AppSettings:
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    return AppSettings(
        telegram_token=required_env("TELEGRAM_BOT_TOKEN"),
        openai_api_key=required_env("OPENAI_API_KEY"),
        model=model,
        summary_model=os.getenv("SUMMARY_MODEL", model),
        normal_mode=ModeSettings(
            system_prompt=os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            history_messages=env_int("MAX_HISTORY_MESSAGES", 12),
            max_output_tokens=env_int("MAX_OUTPUT_TOKENS", 900),
        ),
        economy_mode=ModeSettings(
            system_prompt=os.getenv("ECONOMY_SYSTEM_PROMPT", DEFAULT_ECONOMY_SYSTEM_PROMPT),
            history_messages=env_int("ECONOMY_HISTORY_MESSAGES", 4),
            max_output_tokens=env_int("ECONOMY_MAX_OUTPUT_TOKENS", 250),
        ),
        max_stored_message_chars=env_int("MAX_STORED_MESSAGE_CHARS", 1400),
        summary_enabled=env_bool("SUMMARY_ENABLED", True),
        summary_batch_messages=env_int("SUMMARY_BATCH_MESSAGES", 6),
        summary_max_chars=env_int("SUMMARY_MAX_CHARS", 900),
        summary_max_output_tokens=env_int("SUMMARY_MAX_OUTPUT_TOKENS", 220),
        image_detail=env_choice("IMAGE_DETAIL", "low", {"auto", "high", "low"}),
        payments_enabled=env_bool("PAYMENTS_ENABLED", False),
        state_db_path=os.getenv("STATE_DB_PATH", "bot-state.sqlite3"),
        admin_user_ids=env_user_ids("ADMIN_USER_IDS"),
        free_user_ids=env_user_ids("FREE_USER_IDS"),
        credits_per_purchase=env_int("CREDITS_PER_PURCHASE", 50),
        stars_price=env_int("STARS_PRICE", 50),
        text_request_credits=env_int("TEXT_REQUEST_CREDITS", 1),
        image_request_credits=env_int("IMAGE_REQUEST_CREDITS", 2),
        payment_support_text=os.getenv(
            "PAYMENT_SUPPORT_TEXT",
            "По вопросам оплат напишите владельцу бота.",
        ),
    )

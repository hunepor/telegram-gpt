from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MODEL = "gpt-4.1-mini"
MODE_NORMAL = "normal"
MODE_ECONOMY = "economy"
DEFAULT_SYSTEM_PROMPT = (
    "Ты полезный ассистент в Telegram. Отвечай понятно, дружелюбно и по делу. "
    "Если пользователь пишет на русском, отвечай на русском."
)
DEFAULT_ECONOMY_SYSTEM_PROMPT = (
    "Ты полезный ассистент в Telegram. Отвечай максимально кратко и по делу. "
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
    )

from __future__ import annotations

import logging

from openai import AsyncOpenAI, OpenAIError

from .config import AppSettings, ModeSettings, SUMMARY_SYSTEM_PROMPT
from .memory import UserSession, format_dialog, trim_for_history


async def refresh_summary_if_needed(
    openai_client: AsyncOpenAI,
    session: UserSession,
    app_settings: AppSettings,
    mode_settings: ModeSettings,
) -> None:
    if (
        len(session.history)
        <= mode_settings.history_messages + app_settings.summary_batch_messages
    ):
        return

    messages_to_summarize = session.history[: -mode_settings.history_messages]
    recent_messages = session.history[-mode_settings.history_messages :]
    current_summary = session.summary or "Пока нет."

    try:
        response = await openai_client.responses.create(
            model=app_settings.summary_model,
            input=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Текущее резюме:\n{current_summary}\n\n"
                        f"Новая часть диалога:\n{format_dialog(messages_to_summarize)}\n\n"
                        f"Обнови резюме. Максимум {app_settings.summary_max_chars} символов."
                    ),
                },
            ],
            max_output_tokens=app_settings.summary_max_output_tokens,
        )
    except OpenAIError:
        logging.exception("OpenAI summary refresh error")
        session.history = recent_messages
        return

    new_summary = (response.output_text or "").strip()
    if new_summary:
        session.summary = trim_for_history(new_summary, app_settings.summary_max_chars)

    session.history = recent_messages

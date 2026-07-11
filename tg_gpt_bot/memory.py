from __future__ import annotations

from dataclasses import dataclass, field

from .config import AppSettings, MODE_ECONOMY, MODE_NORMAL, ModeSettings


ChatMessage = dict[str, str]


@dataclass
class UserSession:
    mode: str = MODE_ECONOMY
    history: list[ChatMessage] = field(default_factory=list)
    summary: str = ""

    def clear_memory(self) -> None:
        self.history.clear()
        self.summary = ""


def settings_for(session: UserSession, app_settings: AppSettings) -> ModeSettings:
    if session.mode == MODE_ECONOMY:
        return app_settings.economy_mode

    return app_settings.normal_mode


def mode_text(session: UserSession) -> str:
    if session.mode == MODE_ECONOMY:
        return "caveman: короткий промпт, меньше истории, компактные ответы"

    return "normal: обычные ответы и больше контекста"


def trim_for_history(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars].rstrip()}\n[сокращено]"


def format_dialog(messages: list[ChatMessage]) -> str:
    labels = {
        "user": "Пользователь",
        "assistant": "Ассистент",
        "system": "Система",
    }
    lines: list[str] = []

    for item in messages:
        role = labels.get(item["role"], item["role"])
        lines.append(f"{role}: {item['content']}")

    return "\n\n".join(lines)


def build_input_messages(
    session: UserSession,
    settings: ModeSettings,
    user_text: str,
) -> list[ChatMessage]:
    input_messages: list[ChatMessage] = [
        {"role": "system", "content": settings.system_prompt},
    ]

    if session.summary:
        input_messages.append(
            {
                "role": "system",
                "content": f"Краткая память предыдущего диалога:\n{session.summary}",
            }
        )

    input_messages.extend(session.history[-settings.history_messages :])
    input_messages.append({"role": "user", "content": user_text})
    return input_messages

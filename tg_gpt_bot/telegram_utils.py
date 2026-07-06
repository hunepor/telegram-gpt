from __future__ import annotations

from aiogram.types import Message


MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def split_for_telegram(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit

        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    return chunks


async def answer_long(message: Message, text: str) -> None:
    for chunk in split_for_telegram(text):
        await message.answer(chunk)

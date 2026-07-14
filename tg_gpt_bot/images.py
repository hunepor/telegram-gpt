from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO

from aiogram import Bot
from aiogram.types import Message


@dataclass(frozen=True)
class ImageInput:
    data_url: str
    source: str


def has_photo(message: Message | None) -> bool:
    return bool(message and message.photo)


def message_with_photo(message: Message) -> Message | None:
    if has_photo(message):
        return message

    if has_photo(message.reply_to_message):
        return message.reply_to_message

    return None


async def download_photo_as_data_url(bot: Bot, message: Message) -> ImageInput | None:
    if not message.photo:
        return None

    photo = message.photo[-1]
    telegram_file = await bot.get_file(photo.file_id)
    if not telegram_file.file_path:
        return None

    buffer = BytesIO()
    await bot.download_file(telegram_file.file_path, buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return ImageInput(data_url=f"data:image/jpeg;base64,{encoded}", source="фото")

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.types import BotCommand
from dotenv import load_dotenv
from openai import AsyncOpenAI

from tg_gpt_bot.config import load_settings
from tg_gpt_bot.handlers import build_dispatcher


BOT_COMMANDS = [
    BotCommand(command="ask", description="Задать вопрос"),
    BotCommand(command="start", description="Начать диалог заново"),
    BotCommand(command="reset", description="Очистить память диалога"),
    BotCommand(command="caveman", description="Включить короткие ответы"),
    BotCommand(command="economy", description="Включить короткие ответы"),
    BotCommand(command="normal", description="Включить обычные ответы"),
    BotCommand(command="mode", description="Показать текущий режим"),
    BotCommand(command="help", description="Показать подсказку"),
]


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    settings = load_settings()

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    bot = Bot(token=settings.telegram_token)
    dp = build_dispatcher(openai_client, settings)

    await bot.set_my_commands(BOT_COMMANDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

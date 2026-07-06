from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from dotenv import load_dotenv
from openai import AsyncOpenAI

from tg_gpt_bot.config import load_settings
from tg_gpt_bot.handlers import build_dispatcher


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    settings = load_settings()

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    bot = Bot(token=settings.telegram_token)
    dp = build_dispatcher(openai_client, settings)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

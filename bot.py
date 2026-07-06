from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from typing import Deque

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAIError


MAX_TELEGRAM_MESSAGE_LENGTH = 4096
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_SYSTEM_PROMPT = (
    "Ты полезный ассистент в Telegram. Отвечай понятно, дружелюбно и по делу. "
    "Если пользователь пишет на русском, отвечай на русском."
)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Заполните переменную {name} в файле .env")
    return value


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


def build_dispatcher(openai_client: AsyncOpenAI) -> Dispatcher:
    dp = Dispatcher()
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    system_prompt = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
    sessions: defaultdict[int, Deque[dict[str, str]]] = defaultdict(
        lambda: deque(maxlen=max_history_messages)
    )

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user:
            sessions[message.from_user.id].clear()

        await message.answer(
            "Привет! Я Telegram-бот с подключением к ChatGPT.\n\n"
            "Напишите сообщение, и я отвечу. Команда /reset очищает память диалога."
        )

    @dp.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "Доступные команды:\n"
            "/start - начать заново\n"
            "/reset - очистить память диалога\n"
            "/help - показать подсказку"
        )

    @dp.message(Command("reset"))
    async def reset(message: Message) -> None:
        if message.from_user:
            sessions[message.from_user.id].clear()

        await message.answer("Готово, память диалога очищена.")

    @dp.message(F.text)
    async def chat(message: Message, bot: Bot) -> None:
        if not message.from_user or not message.text:
            return

        user_text = message.text.strip()
        if not user_text:
            return

        session = sessions[message.from_user.id]
        input_messages = [
            {"role": "system", "content": system_prompt},
            *list(session),
            {"role": "user", "content": user_text},
        ]

        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        try:
            response = await openai_client.responses.create(
                model=model,
                input=input_messages,
            )
        except OpenAIError:
            logging.exception("OpenAI API error")
            await message.answer(
                "Не получилось получить ответ от ChatGPT. "
                "Проверьте OPENAI_API_KEY и доступ к выбранной модели."
            )
            return
        except Exception:
            logging.exception("Unexpected bot error")
            await message.answer("Что-то пошло не так. Попробуйте еще раз.")
            return

        answer = (response.output_text or "").strip()
        if not answer:
            answer = "Ответ получился пустым. Попробуйте переформулировать сообщение."

        session.append({"role": "user", "content": user_text})
        session.append({"role": "assistant", "content": answer})

        await answer_long(message, answer)

    @dp.message()
    async def unsupported_message(message: Message) -> None:
        await message.answer("Пока я понимаю только текстовые сообщения.")

    return dp


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    telegram_token = required_env("TELEGRAM_BOT_TOKEN")
    openai_api_key = required_env("OPENAI_API_KEY")

    openai_client = AsyncOpenAI(api_key=openai_api_key)
    bot = Bot(token=telegram_token)
    dp = build_dispatcher(openai_client)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

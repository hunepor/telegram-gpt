from __future__ import annotations

import logging
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from openai import AsyncOpenAI, OpenAIError

from .config import AppSettings, MODE_ECONOMY, MODE_NORMAL
from .memory import (
    UserSession,
    build_input_messages,
    mode_text,
    settings_for,
    trim_for_history,
)
from .openai_memory import refresh_summary_if_needed
from .telegram_utils import answer_long


def build_dispatcher(openai_client: AsyncOpenAI, app_settings: AppSettings) -> Dispatcher:
    dp = Dispatcher()
    sessions: defaultdict[int, UserSession] = defaultdict(UserSession)

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user:
            sessions[message.from_user.id].clear_memory()

        await message.answer(
            "Привет! Я Telegram-бот с подключением к ChatGPT.\n\n"
            "Напишите сообщение, и я отвечу. Команда /economy включает экономию токенов, "
            "а /reset очищает память диалога."
        )

    @dp.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "Доступные команды:\n"
            "/start - начать заново\n"
            "/reset - очистить память диалога\n"
            "/economy - включить экономный режим\n"
            "/caveman - то же самое, что /economy\n"
            "/normal - вернуться к обычному режиму\n"
            "/mode - показать текущий режим\n"
            "/help - показать подсказку"
        )

    @dp.message(Command("reset"))
    async def reset(message: Message) -> None:
        if message.from_user:
            sessions[message.from_user.id].clear_memory()

        await message.answer("Готово, память диалога очищена.")

    @dp.message(Command("economy", "caveman"))
    async def economy(message: Message) -> None:
        if not message.from_user:
            return

        session = sessions[message.from_user.id]
        session.mode = MODE_ECONOMY

        await message.answer(
            "Эконом-режим включен. Буду отправлять меньше истории в запрос, "
            "держать короткую память и отвечать компактнее."
        )

    @dp.message(Command("normal"))
    async def normal(message: Message) -> None:
        if not message.from_user:
            return

        session = sessions[message.from_user.id]
        session.mode = MODE_NORMAL

        await message.answer("Обычный режим включен. Контекста и деталей будет больше.")

    @dp.message(Command("mode"))
    async def mode(message: Message) -> None:
        if not message.from_user:
            return

        await message.answer(f"Текущий режим: {mode_text(sessions[message.from_user.id])}.")

    @dp.message(F.text)
    async def chat(message: Message, bot: Bot) -> None:
        if not message.from_user or not message.text:
            return

        user_text = message.text.strip()
        if not user_text:
            return

        session = sessions[message.from_user.id]
        mode_settings = settings_for(session, app_settings)
        input_messages = build_input_messages(session, mode_settings, user_text)

        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        try:
            response = await openai_client.responses.create(
                model=app_settings.model,
                input=input_messages,
                max_output_tokens=mode_settings.max_output_tokens,
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

        session.history.append(
            {
                "role": "user",
                "content": trim_for_history(
                    user_text,
                    app_settings.max_stored_message_chars,
                ),
            }
        )
        session.history.append(
            {
                "role": "assistant",
                "content": trim_for_history(
                    answer,
                    app_settings.max_stored_message_chars,
                ),
            }
        )

        await answer_long(message, answer)

        if app_settings.summary_enabled:
            await refresh_summary_if_needed(
                openai_client=openai_client,
                session=session,
                app_settings=app_settings,
                mode_settings=mode_settings,
            )
        elif (
            len(session.history)
            > mode_settings.history_messages + app_settings.summary_batch_messages
        ):
            session.history = session.history[-mode_settings.history_messages :]

    @dp.message()
    async def unsupported_message(message: Message) -> None:
        await message.answer("Пока я понимаю только текстовые сообщения.")

    return dp

from __future__ import annotations

import logging
import re
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction, ChatType, MessageEntityType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, Message
from openai import AsyncOpenAI, OpenAIError

from .config import AppSettings, MODE_ECONOMY, MODE_NORMAL
from .images import ImageInput, download_photo_as_data_url, message_with_photo
from .memory import (
    UserSession,
    build_input_messages,
    mode_text,
    settings_for,
    trim_for_history,
)
from .openai_memory import refresh_summary_if_needed
from .telegram_utils import answer_long, split_for_telegram
from .web_search import (
    contains_web_search_trigger,
    search_citations,
    search_query_from_text,
)


GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
DEFAULT_IMAGE_PROMPT = "Опиши изображение."


def session_key(message: Message) -> int:
    if message.chat.type in GROUP_CHAT_TYPES:
        return message.chat.id

    if message.from_user:
        return message.from_user.id

    return message.chat.id


def guest_session_key(message: Message) -> int:
    if message.guest_bot_caller_chat:
        return message.guest_bot_caller_chat.id

    if message.guest_bot_caller_user:
        return message.guest_bot_caller_user.id

    return session_key(message)


def is_reply_to_bot(message: Message, bot_id: int) -> bool:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return False

    return message.reply_to_message.from_user.id == bot_id


def remove_text_fragment(text: str, fragment: str) -> str:
    return text.replace(fragment, "", 1).strip()


def remove_bot_mention(message: Message, bot_username: str, bot_id: int) -> tuple[bool, str]:
    text = message.text or message.caption or ""
    target_mention = f"@{bot_username}".lower()

    for entity in message.entities or message.caption_entities or []:
        if (
            entity.type == MessageEntityType.TEXT_MENTION
            and entity.user
            and entity.user.id == bot_id
        ):
            return True, remove_text_fragment(text, entity.extract_from(text))

        if (
            entity.type == MessageEntityType.MENTION
            and entity.extract_from(text).lower() == target_mention
        ):
            mention_pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
            return True, mention_pattern.sub("", text).strip()

    mention_pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
    mentioned = mention_pattern.search(text) is not None
    cleaned_text = mention_pattern.sub("", text).strip()
    return mentioned, cleaned_text


def replied_text(message: Message) -> str:
    replied_message = message.reply_to_message
    if replied_message:
        text = getattr(replied_message, "text", None)
        caption = getattr(replied_message, "caption", None)
        if text or caption:
            return (text or caption).strip()

    if message.quote:
        return message.quote.text.strip()

    return ""


def message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def contextual_prompt(instruction: str, context: str) -> str:
    instruction = instruction.strip()
    context = context.strip()

    if context and instruction:
        return f"Сообщение пользователя:\n{context}\n\nЗадача:\n{instruction}"

    if context:
        return f"Ответь на сообщение пользователя:\n{context}"

    return instruction


def ask_prompt(message: Message, command_args: str | None) -> str:
    return contextual_prompt(command_args or "", replied_text(message))


def prompt_for_request(user_text: str, image_input: ImageInput | None) -> str:
    user_text = user_text.strip()
    if user_text:
        return user_text

    if image_input:
        return DEFAULT_IMAGE_PROMPT

    return ""


def guest_result(message: Message, text: str, parse_mode: ParseMode | None) -> InlineQueryResultArticle:
    chunk = split_for_telegram(text)[0]
    return InlineQueryResultArticle(
        id=str(message.message_id),
        title="Ответ",
        input_message_content=InputTextMessageContent(
            message_text=chunk,
            parse_mode=parse_mode,
        ),
    )


async def answer_guest(message: Message, text: str) -> None:
    try:
        await message.answer_guest_query(guest_result(message, text, ParseMode.MARKDOWN))
    except TelegramBadRequest:
        logging.exception("Telegram rejected Markdown formatting for guest response")
        await message.answer_guest_query(guest_result(message, text, None))


def build_dispatcher(openai_client: AsyncOpenAI, app_settings: AppSettings) -> Dispatcher:
    dp = Dispatcher()
    sessions: defaultdict[int, UserSession] = defaultdict(UserSession)
    bot_username: str | None = None
    bot_id: int | None = None

    async def cache_bot_profile(bot: Bot) -> tuple[int, str | None]:
        nonlocal bot_id, bot_username

        if bot_id is None or bot_username is None:
            me = await bot.get_me()
            bot_id = me.id
            bot_username = me.username

        return bot_id, bot_username

    async def generate_answer(
        user_text: str,
        session: UserSession,
        image_input: ImageInput | None = None,
        use_web_search: bool = False,
    ) -> str:
        mode_settings = settings_for(session, app_settings)
        input_messages = build_input_messages(session, mode_settings, user_text)
        if image_input:
            input_messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {
                        "type": "input_image",
                        "image_url": image_input.data_url,
                        "detail": app_settings.image_detail,
                    },
                ],
            }

        request_params = {
            "model": app_settings.model,
            "input": input_messages,
            "max_output_tokens": mode_settings.max_output_tokens,
        }
        if use_web_search:
            request_params["tools"] = [{"type": "web_search", "search_context_size": "low"}]
            request_params["tool_choice"] = "required"

        response = await openai_client.responses.create(**request_params)
        answer = (response.output_text or "").strip()
        if use_web_search:
            citations = search_citations(response)
            if citations:
                answer += "\n\nИсточники:\n" + "\n".join(
                    f"[{title}]({url})" for title, url in citations
                )
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

        return answer

    async def image_from_message(message: Message, bot: Bot) -> ImageInput | None:
        image_message = message_with_photo(message)
        if not image_message:
            return None

        return await download_photo_as_data_url(bot, image_message)

    async def respond_to_message(
        message: Message,
        bot: Bot,
        user_text: str,
        image_input: ImageInput | None = None,
    ) -> None:
        session = sessions[session_key(message)]
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        try:
            answer = await generate_answer(user_text, session, image_input)
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

        await answer_long(message, answer)

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        sessions[session_key(message)].clear_memory()

        await message.answer(
            "Привет! Я Telegram-бот с подключением к ChatGPT.\n\n"
            "Напишите сообщение, и я отвечу. Режим caveman включен по умолчанию. "
            "Команда /normal включает обычный режим, а /reset очищает память диалога."
        )

    @dp.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "Доступные команды:\n"
            "/start - начать заново\n"
            "/reset - очистить память диалога\n"
            "/caveman - включить короткий caveman-режим\n"
            "/economy - то же самое, что /caveman\n"
            "/normal - вернуться к обычному режиму\n"
            "/mode - показать текущий режим\n"
            "/ask вопрос - задать вопрос или обработать reply, включая фото\n"
            "/search вопрос - искать ответ в интернете\n"
            "/help - показать подсказку"
        )

    @dp.message(Command("reset"))
    async def reset(message: Message) -> None:
        sessions[session_key(message)].clear_memory()

        await message.answer("Готово, память диалога очищена.")

    @dp.message(Command("economy", "caveman"))
    async def economy(message: Message) -> None:
        if not message.from_user:
            return

        session = sessions[session_key(message)]
        session.mode = MODE_ECONOMY

        await message.answer(
            "Caveman-режим включен. Буду отправлять меньше истории в запрос, "
            "держать короткую память и отвечать максимально компактно."
        )

    @dp.message(Command("normal"))
    async def normal(message: Message) -> None:
        if not message.from_user:
            return

        session = sessions[session_key(message)]
        session.mode = MODE_NORMAL

        await message.answer("Обычный режим включен. Контекста и деталей будет больше.")

    @dp.message(Command("mode"))
    async def mode(message: Message) -> None:
        if not message.from_user:
            return

        await message.answer(f"Текущий режим: {mode_text(sessions[session_key(message)])}.")

    @dp.message(Command("ask"))
    async def ask(message: Message, command: CommandObject, bot: Bot) -> None:
        image_input = await image_from_message(message, bot)
        user_text = prompt_for_request(ask_prompt(message, command.args), image_input)
        if not user_text:
            await message.answer(
                "Добавьте вопрос после команды или отправьте /ask ответом на текст или фото."
            )
            return

        await respond_to_message(message, bot, user_text, image_input)

    @dp.message(Command("search"))
    async def search(message: Message, command: CommandObject, bot: Bot) -> None:
        user_text = contextual_prompt(command.args or "", replied_text(message))
        if not user_text:
            await message.answer(
                "Добавьте запрос после команды или отправьте /search ответом на сообщение."
            )
            return

        await respond_to_message(message, bot, user_text, use_web_search=True)

    @dp.message(F.text | F.photo)
    async def chat(message: Message, bot: Bot) -> None:
        if not message.from_user:
            return

        user_text = message_text(message)

        if message.chat.type in GROUP_CHAT_TYPES:
            current_bot_id, username = await cache_bot_profile(bot)
            if not username:
                return

            mentioned, user_text = remove_bot_mention(message, username, current_bot_id)
            replied_to_bot = is_reply_to_bot(message, current_bot_id)
            if not mentioned and not replied_to_bot:
                return

            use_web_search = contains_web_search_trigger(user_text)
            image_input = await image_from_message(message, bot)
            user_text = prompt_for_request(user_text, image_input)
            if not user_text:
                await message.answer(f"Напишите вопрос после @{username}.")
                return
            if use_web_search:
                user_text = contextual_prompt(user_text, replied_text(message))
        else:
            use_web_search = contains_web_search_trigger(user_text)
            image_input = await image_from_message(message, bot)
            user_text = prompt_for_request(user_text, image_input)
            if not user_text:
                return
            if use_web_search:
                user_text = contextual_prompt(user_text, replied_text(message))

        await respond_to_message(
            message,
            bot,
            user_text,
            image_input,
            use_web_search=use_web_search,
        )

    @dp.guest_message(F.text | F.photo)
    async def guest_chat(message: Message, bot: Bot) -> None:
        current_bot_id, username = await cache_bot_profile(bot)
        if not username:
            return

        image_input = await image_from_message(message, bot)
        _, instruction = remove_bot_mention(message, username, current_bot_id)
        search_query = search_query_from_text(instruction)
        use_web_search = search_query is not None or contains_web_search_trigger(instruction)
        instruction = search_query if search_query is not None else instruction
        user_text = prompt_for_request(
            contextual_prompt(instruction, replied_text(message)),
            image_input,
        )
        if not user_text:
            await answer_guest(message, f"Напишите вопрос после @{username}.")
            return

        session = sessions[guest_session_key(message)]
        try:
            answer = await generate_answer(
                user_text,
                session,
                image_input,
                use_web_search=use_web_search,
            )
        except OpenAIError:
            logging.exception("OpenAI API error for guest query")
            await answer_guest(
                message,
                "Не получилось получить ответ от ChatGPT. Проверьте OPENAI_API_KEY и модель.",
            )
            return
        except Exception:
            logging.exception("Unexpected guest bot error")
            await answer_guest(message, "Что-то пошло не так. Попробуйте еще раз.")
            return

        await answer_guest(message, answer)

    @dp.message()
    async def unsupported_message(message: Message) -> None:
        await message.answer("Пока я понимаю текстовые сообщения и обычные Telegram-фото.")

    return dp

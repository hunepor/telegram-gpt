from __future__ import annotations

import logging
import re
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction, ChatType, MessageEntityType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from openai import AsyncOpenAI, OpenAIError

from .billing import PAYMENT_CURRENCY, BillingService, ReserveResult, payment_payload
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


GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
DEFAULT_IMAGE_PROMPT = "Опиши изображение."


def request_kind(image_input: ImageInput | None) -> str:
    if image_input:
        return "image"

    return "text"


def request_cost(app_settings: AppSettings, image_input: ImageInput | None) -> int:
    if image_input:
        return app_settings.image_request_credits

    return app_settings.text_request_credits


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


def payer_user_id(message: Message) -> int | None:
    if message.guest_bot_caller_user:
        return message.guest_bot_caller_user.id

    if message.from_user:
        return message.from_user.id

    return None


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


def private_buy_text(bot_username: str | None) -> str:
    if bot_username:
        return f"Пополнить баланс можно в личке: https://t.me/{bot_username}?start=buy"

    return "Пополнить баланс можно командой /buy в личке с ботом."


def payment_required_text(
    balance: int,
    cost: int,
    bot_username: str | None,
) -> str:
    return (
        f"Нужна оплата. Этот запрос стоит {cost} кредит(ов), "
        f"на балансе {balance}.\n"
        f"{private_buy_text(bot_username)}"
    )


def terms_text(app_settings: AppSettings) -> str:
    return (
        "Условия оплаты:\n"
        f"- {app_settings.stars_price} Stars дают {app_settings.credits_per_purchase} кредитов.\n"
        f"- Текстовый запрос стоит {app_settings.text_request_credits} кредит(ов).\n"
        f"- Запрос с картинкой стоит {app_settings.image_request_credits} кредит(ов).\n"
        "- Кредиты используются только внутри этого бота и не являются валютой.\n"
        "- Доступ выдаётся после успешной оплаты Telegram Stars.\n"
        "- По вопросам платежей используйте /paysupport."
    )


def target_user_id(message: Message, command: CommandObject) -> int | None:
    if command.args:
        raw_user_id = command.args.split()[0]
        if raw_user_id.isdigit():
            return int(raw_user_id)

    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    return None


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
    billing = BillingService(app_settings)
    bot_username: str | None = None
    bot_id: int | None = None

    async def cache_bot_profile(bot: Bot) -> tuple[int, str | None]:
        nonlocal bot_id, bot_username

        if bot_id is None or bot_username is None:
            me = await bot.get_me()
            bot_id = me.id
            bot_username = me.username

        return bot_id, bot_username

    async def send_buy_invoice(message: Message, bot: Bot) -> None:
        if not message.from_user:
            await message.answer("Не могу определить пользователя для оплаты.")
            return

        if not billing.enabled:
            await message.answer("Оплата сейчас выключена, доступ свободный.")
            return

        if await billing.has_free_access(message.from_user.id):
            await message.answer("У вас бесплатный доступ, покупать кредиты не нужно.")
            return

        if message.chat.type != ChatType.PRIVATE:
            _, username = await cache_bot_profile(bot)
            await message.answer(private_buy_text(username))
            return

        credits = app_settings.credits_per_purchase
        stars = app_settings.stars_price
        await message.answer_invoice(
            title=f"{credits} кредитов",
            description=(
                f"Пакет для запросов к боту. Текстовый запрос: "
                f"{app_settings.text_request_credits} кредит(ов), "
                f"запрос с картинкой: {app_settings.image_request_credits} кредит(ов)."
            ),
            payload=payment_payload(app_settings),
            provider_token="",
            currency=PAYMENT_CURRENCY,
            prices=[LabeledPrice(label=f"{credits} кредитов", amount=stars)],
            start_parameter="buy",
        )

    async def reserve_request(
        message: Message,
        bot: Bot,
        user_text: str,
        image_input: ImageInput | None,
    ) -> ReserveResult | None:
        user_id = payer_user_id(message)
        if user_id is None:
            await message.answer("Не могу определить пользователя для проверки доступа.")
            return None

        result = await billing.reserve(
            user_id=user_id,
            cost=request_cost(app_settings, image_input),
            kind=request_kind(image_input),
            prompt=user_text,
        )
        if result.allowed:
            return result

        _, username = await cache_bot_profile(bot)
        await message.answer(payment_required_text(result.balance, result.cost, username))
        return None

    async def reserve_guest_request(
        message: Message,
        user_text: str,
        image_input: ImageInput | None,
        bot_username: str | None,
    ) -> ReserveResult | None:
        user_id = payer_user_id(message)
        if user_id is None:
            await answer_guest(message, "Не могу определить пользователя для проверки доступа.")
            return None

        result = await billing.reserve(
            user_id=user_id,
            cost=request_cost(app_settings, image_input),
            kind=request_kind(image_input),
            prompt=user_text,
        )
        if result.allowed:
            return result

        await answer_guest(message, payment_required_text(result.balance, result.cost, bot_username))
        return None

    async def generate_answer(
        user_text: str,
        session: UserSession,
        image_input: ImageInput | None = None,
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

        response = await openai_client.responses.create(
            model=app_settings.model,
            input=input_messages,
            max_output_tokens=mode_settings.max_output_tokens,
        )
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
        access = await reserve_request(message, bot, user_text, image_input)
        if access is None:
            return

        session = sessions[session_key(message)]
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        try:
            answer = await generate_answer(user_text, session, image_input)
        except OpenAIError:
            if access.charged:
                user_id = payer_user_id(message)
                if user_id is not None:
                    await billing.refund(user_id, access.cost, request_kind(image_input))
            logging.exception("OpenAI API error")
            await message.answer(
                "Не получилось получить ответ от ChatGPT. "
                "Проверьте OPENAI_API_KEY и доступ к выбранной модели."
            )
            return
        except Exception:
            if access.charged:
                user_id = payer_user_id(message)
                if user_id is not None:
                    await billing.refund(user_id, access.cost, request_kind(image_input))
            logging.exception("Unexpected bot error")
            await message.answer("Что-то пошло не так. Попробуйте еще раз.")
            return

        await answer_long(message, answer)

    @dp.message(CommandStart())
    async def start(message: Message, command: CommandObject, bot: Bot) -> None:
        sessions[session_key(message)].clear_memory()

        await message.answer(
            "Привет! Я Telegram-бот с подключением к ChatGPT.\n\n"
            "Напишите сообщение, и я отвечу. Режим caveman включен по умолчанию. "
            "Команда /normal включает обычный режим, а /reset очищает память диалога."
        )
        if command.args == "buy":
            await send_buy_invoice(message, bot)

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
            "/buy - купить кредиты за Telegram Stars\n"
            "/balance - показать баланс кредитов\n"
            "/terms - условия оплаты\n"
            "/paysupport - поддержка по оплатам\n"
            "/id - показать ваш Telegram user id\n"
            "/help - показать подсказку"
        )

    @dp.message(Command("buy"))
    async def buy(message: Message, bot: Bot) -> None:
        await send_buy_invoice(message, bot)

    @dp.message(Command("balance"))
    async def balance(message: Message) -> None:
        user_id = payer_user_id(message)
        if user_id is None:
            await message.answer("Не могу определить пользователя.")
            return

        if not billing.enabled:
            await message.answer("Оплата сейчас выключена, доступ свободный.")
            return

        if await billing.has_free_access(user_id):
            await message.answer("У вас бесплатный доступ.")
            return

        credits = await billing.get_balance(user_id)
        await message.answer(f"Баланс: {credits} кредит(ов).")

    @dp.message(Command("terms"))
    async def terms(message: Message) -> None:
        await message.answer(terms_text(app_settings))

    @dp.message(Command("paysupport"))
    async def paysupport(message: Message) -> None:
        await message.answer(app_settings.payment_support_text)

    @dp.message(Command("id"))
    async def show_id(message: Message) -> None:
        user_id = payer_user_id(message)
        if user_id is None:
            await message.answer("Не могу определить ваш Telegram user id.")
            return

        await message.answer(f"Ваш Telegram user id: {user_id}")

    @dp.message(Command("allow"))
    async def allow(message: Message, command: CommandObject) -> None:
        if not message.from_user or not billing.is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администратору.")
            return

        user_id = target_user_id(message, command)
        if user_id is None:
            await message.answer("Укажите Telegram user id или ответьте командой на сообщение.")
            return

        await billing.add_free_user(user_id, f"added by {message.from_user.id}")
        await message.answer(f"Пользователь {user_id} добавлен в бесплатный список.")

    @dp.message(Command("unallow"))
    async def unallow(message: Message, command: CommandObject) -> None:
        if not message.from_user or not billing.is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администратору.")
            return

        user_id = target_user_id(message, command)
        if user_id is None:
            await message.answer("Укажите Telegram user id или ответьте командой на сообщение.")
            return

        await billing.remove_free_user(user_id)
        await message.answer(f"Пользователь {user_id} удалён из бесплатного списка.")

    @dp.message(Command("freeusers"))
    async def freeusers(message: Message) -> None:
        if not message.from_user or not billing.is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администратору.")
            return

        users = await billing.list_free_users()
        if not users:
            await message.answer("Бесплатный список пуст.")
            return

        lines = ["Бесплатный список:"]
        lines.extend(f"- {item.user_id} ({item.note})" for item in users)
        await message.answer("\n".join(lines))

    @dp.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery) -> None:
        if not billing.validate_payment(
            payload=query.invoice_payload,
            currency=query.currency,
            total_amount=query.total_amount,
        ):
            await query.answer(
                ok=False,
                error_message="Не удалось подтвердить параметры оплаты. Попробуйте создать счёт заново.",
            )
            return

        await query.answer(ok=True)

    @dp.message(F.successful_payment)
    async def successful_payment(message: Message) -> None:
        if not message.from_user or not message.successful_payment:
            return

        payment = message.successful_payment
        if not billing.validate_payment(
            payload=payment.invoice_payload,
            currency=payment.currency,
            total_amount=payment.total_amount,
        ):
            await message.answer(
                "Оплата получена, но параметры отличаются от текущего пакета. "
                "Напишите в /paysupport."
            )
            return

        result = await billing.record_payment(
            user_id=message.from_user.id,
            charge_id=payment.telegram_payment_charge_id,
            payload=payment.invoice_payload,
            stars=payment.total_amount,
            credits=app_settings.credits_per_purchase,
        )
        if result.inserted:
            await message.answer(
                f"Оплата получена. Начислено {app_settings.credits_per_purchase} кредитов.\n"
                f"Баланс: {result.balance} кредит(ов)."
            )
            return

        await message.answer(f"Этот платёж уже был учтён. Баланс: {result.balance} кредит(ов).")

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

            image_input = await image_from_message(message, bot)
            user_text = prompt_for_request(user_text, image_input)
            if not user_text:
                await message.answer(f"Напишите вопрос после @{username}.")
                return
        else:
            image_input = await image_from_message(message, bot)
            user_text = prompt_for_request(user_text, image_input)
            if not user_text:
                return

        await respond_to_message(message, bot, user_text, image_input)

    @dp.guest_message(F.text | F.photo)
    async def guest_chat(message: Message, bot: Bot) -> None:
        current_bot_id, username = await cache_bot_profile(bot)
        if not username:
            return

        image_input = await image_from_message(message, bot)
        _, instruction = remove_bot_mention(message, username, current_bot_id)
        user_text = prompt_for_request(
            contextual_prompt(instruction, replied_text(message)),
            image_input,
        )
        if not user_text:
            await answer_guest(message, f"Напишите вопрос после @{username}.")
            return

        access = await reserve_guest_request(message, user_text, image_input, username)
        if access is None:
            return

        session = sessions[guest_session_key(message)]
        try:
            answer = await generate_answer(user_text, session, image_input)
        except OpenAIError:
            if access.charged:
                user_id = payer_user_id(message)
                if user_id is not None:
                    await billing.refund(user_id, access.cost, request_kind(image_input))
            logging.exception("OpenAI API error for guest query")
            await answer_guest(
                message,
                "Не получилось получить ответ от ChatGPT. Проверьте OPENAI_API_KEY и модель.",
            )
            return
        except Exception:
            if access.charged:
                user_id = payer_user_id(message)
                if user_id is not None:
                    await billing.refund(user_id, access.cost, request_kind(image_input))
            logging.exception("Unexpected guest bot error")
            await answer_guest(message, "Что-то пошло не так. Попробуйте еще раз.")
            return

        await answer_guest(message, answer)

    @dp.message()
    async def unsupported_message(message: Message) -> None:
        await message.answer("Пока я понимаю текстовые сообщения и обычные Telegram-фото.")

    return dp

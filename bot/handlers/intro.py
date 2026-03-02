from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..auth import is_admin
from ..runtime import get_runtime
from ..utils import (
    EXAMPLE_INTRO_TEXT,
    build_reminder_text,
    display_name,
    extract_message_text,
    mention_html,
    validate_intro_text,
)
from .join import send_reminder_to_user, unlock_member

logger = logging.getLogger(__name__)


async def handle_intro_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None or user.is_bot:
        return

    logger.debug(f"Intro handler called: chat_id={message.chat_id}, thread_id={message.message_thread_id}, user_id={user.id}")

    is_intro = _is_intro_message(message.chat_id, message.message_thread_id, runtime)
    logger.debug(f"_is_intro_message returned: {is_intro}, intro_chat_id={runtime.config.intro_chat_id}, intro_thread_id={runtime.config.intro_thread_id}")

    if not is_intro:
        logger.debug(f"Not an intro message, returning")
        return

    text = extract_message_text(message)
    result = validate_intro_text(
        text=text,
        min_words=runtime.config.min_intro_words,
        min_words_with_signals=runtime.config.min_intro_words_with_signals,
    )

    logger.debug(f"Intro validation result: is_valid={result.is_valid}, reason={result.reason if not result.is_valid else 'N/A'}")

    if not result.is_valid:
        await message.reply_text(
            (
                f"Your intro is not complete yet. {result.reason}\n\n"
                "Tip: use /example and include at least a short paragraph about who you are and what you do."
            )
        )
        return

    logger.info(f"Accepting intro from user_id={user.id}")
    member = runtime.repo.mark_introduced(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_message_id=message.message_id,
    )

    unlocked = False
    if member.main_chat_id:
        unlocked = await unlock_member(context, member.main_chat_id, user.id)

    user_label = display_name(user.username, user.first_name, user.id)
    if unlocked:
        await message.reply_text("Intro accepted. You are now unlocked in the main group.")
        await context.bot.send_message(
            chat_id=runtime.config.main_group_id,
            text=(
                f"{mention_html(user.id, user_label)} intro accepted in #intro. "
                "Main-group access unlocked."
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    else:
        await message.reply_text(
            "Intro accepted. If you already joined the main group, an admin may need to check bot permissions."
        )


async def handle_main_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None or user.is_bot:
        return

    if message.chat_id != runtime.config.main_group_id:
        return

    logger.debug(f"Message from user_id={user.id}, thread_id={message.message_thread_id}, intro_thread={runtime.config.intro_thread_id}")

    if _is_intro_message(message.chat_id, message.message_thread_id, runtime):
        logger.debug(f"Message is in intro topic, skipping")
        return

    admin_status = await is_admin(update, context, runtime)
    logger.debug(f"User {user.id} is_admin={admin_status}")

    if admin_status:
        member = runtime.repo.get_member(user.id)
        if member is None or not member.is_introduced:
            runtime.repo.mark_introduced(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                intro_chat_id=runtime.config.intro_chat_id,
                intro_message_id=0,
            )
        return

    member = runtime.repo.get_member(user.id)
    if member is None:
        member = runtime.repo.upsert_join(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            main_chat_id=runtime.config.main_group_id,
        )

    logger.debug(f"User {user.id} is_introduced={member.is_introduced}")

    if member.is_introduced:
        return

    logger.info(f"Deleting message from pending user user_id={user.id}")
    try:
        await message.delete()
    except Forbidden:
        logger.warning("cannot delete message for pending user user_id=%s", user.id)
        await _maybe_notify_delete_permission_issue(context, runtime.config.main_group_id)
    except TelegramError:
        logger.exception("failed to delete message for pending user user_id=%s", user.id)

    if _should_remind(member.last_reminded_at, runtime.config.reminder_cooldown_minutes):
        await send_reminder_to_user(
            context=context,
            user_id=user.id,
            user_label=display_name(user.username, user.first_name, user.id),
            main_group_id=runtime.config.main_group_id,
            intro_chat_id=runtime.config.intro_chat_id,
            intro_thread_id=runtime.config.intro_thread_id,
        )
        runtime.repo.set_last_reminded(user.id)


async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(
        f"Example intro:\n\n{EXAMPLE_INTRO_TEXT}",
        disable_web_page_preview=True,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    if await is_admin(update, context, runtime):
        await message.reply_text(
            "You are recognized as an admin, so access gating does not apply to you."
        )
        return

    member = runtime.repo.get_member(user.id)
    if member and member.is_introduced:
        await message.reply_text("Your intro is already complete. You should have full access.")
        return

    await message.reply_text(
        build_reminder_text(
            runtime.config.intro_chat_id,
            runtime.config.intro_thread_id,
        )
    )


async def ids_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None:
        return

    thread_id = getattr(message, "message_thread_id", None)
    if thread_id is not None:
        await message.reply_text(
            f"chat_id={chat.id}\nmessage_thread_id={thread_id}\nuser_id={user.id}"
        )
        return

    await message.reply_text(f"chat_id={chat.id}\nmessage_thread_id=<none>\nuser_id={user.id}")


def _should_remind(last_reminded_at: datetime | None, cooldown_minutes: int) -> bool:
    if last_reminded_at is None:
        return True
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - last_reminded_at).total_seconds()
    return elapsed_seconds >= cooldown_minutes * 60


async def _maybe_notify_delete_permission_issue(
    context: ContextTypes.DEFAULT_TYPE,
    main_group_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    key = "delete_permission_warning_last_at"
    last = context.application.bot_data.get(key)
    if isinstance(last, datetime):
        elapsed = (now - last).total_seconds()
        if elapsed < 300:
            return

    context.application.bot_data[key] = now
    await context.bot.send_message(
        chat_id=main_group_id,
        text=(
            "I cannot delete messages for pending users. "
            "Please grant me the \"Delete messages\" admin permission."
        ),
    )


def _is_intro_message(
    chat_id: int,
    message_thread_id: int | None,
    runtime,
) -> bool:
    if chat_id != runtime.config.intro_chat_id:
        return False
    if runtime.config.intro_thread_id is None:
        return True
    return message_thread_id == runtime.config.intro_thread_id

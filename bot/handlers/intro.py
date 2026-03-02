from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

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

    text = extract_message_text(message)
    result = validate_intro_text(
        text=text,
        min_words=runtime.config.min_intro_words,
        min_words_with_signals=runtime.config.min_intro_words_with_signals,
    )

    if not result.is_valid:
        await message.reply_text(
            (
                f"Your intro is not complete yet. {result.reason}\n\n"
                "Tip: use /example and include at least a short paragraph about who you are and what you do."
            )
        )
        return

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

    member = runtime.repo.get_member(user.id)
    if member is None or member.is_introduced:
        return

    try:
        await message.delete()
    except TelegramError:
        logger.exception("failed to delete message for pending user user_id=%s", user.id)

    if _should_remind(member.last_reminded_at, runtime.config.reminder_cooldown_minutes):
        await send_reminder_to_user(
            context=context,
            user_id=user.id,
            user_label=display_name(user.username, user.first_name, user.id),
            main_group_id=runtime.config.main_group_id,
            intro_chat_id=runtime.config.intro_chat_id,
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
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(build_reminder_text(runtime.config.intro_chat_id))


def _should_remind(last_reminded_at: datetime | None, cooldown_minutes: int) -> bool:
    if last_reminded_at is None:
        return True
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - last_reminded_at).total_seconds()
    return elapsed_seconds >= cooldown_minutes * 60

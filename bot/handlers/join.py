from __future__ import annotations

import logging

from telegram import Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..runtime import get_runtime
from ..utils import (
    MUTED_PERMISSIONS,
    UNMUTED_PERMISSIONS,
    build_reminder_text,
    build_welcome_text,
    display_name,
    mention_html,
)

logger = logging.getLogger(__name__)


async def lock_member(
    context: ContextTypes.DEFAULT_TYPE,
    main_group_id: int,
    user_id: int,
) -> bool:
    try:
        await context.bot.restrict_chat_member(
            chat_id=main_group_id,
            user_id=user_id,
            permissions=MUTED_PERMISSIONS,
        )
        return True
    except TelegramError:
        logger.exception("failed to lock member user_id=%s", user_id)
        return False


async def unlock_member(
    context: ContextTypes.DEFAULT_TYPE,
    main_group_id: int,
    user_id: int,
) -> bool:
    try:
        await context.bot.restrict_chat_member(
            chat_id=main_group_id,
            user_id=user_id,
            permissions=UNMUTED_PERMISSIONS,
        )
        return True
    except TelegramError:
        logger.exception("failed to unlock member user_id=%s", user_id)
        return False


async def send_reminder_to_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_label: str,
    main_group_id: int,
    intro_chat_id: int,
) -> None:
    reminder_text = build_reminder_text(intro_chat_id)
    dm_sent = False
    try:
        await context.bot.send_message(chat_id=user_id, text=reminder_text)
        dm_sent = True
    except Forbidden:
        dm_sent = False
    except TelegramError:
        logger.exception("failed to send reminder DM user_id=%s", user_id)

    note = (
        f"{mention_html(user_id, user_label)} reminder sent."
        if dm_sent
        else (
            f"{mention_html(user_id, user_label)} please post your intro in #intro. "
            "I could not DM you, so this is your in-group reminder."
        )
    )
    await context.bot.send_message(
        chat_id=main_group_id,
        text=note,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None or message.new_chat_members is None:
        return

    for user in message.new_chat_members:
        if user.is_bot:
            continue

        member = runtime.repo.upsert_join(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            main_chat_id=runtime.config.main_group_id,
        )

        if member.is_introduced:
            await unlock_member(context, runtime.config.main_group_id, user.id)
            continue

        await lock_member(context, runtime.config.main_group_id, user.id)

        person = display_name(user.username, user.first_name, user.id)
        welcome_text = build_welcome_text(runtime.config.intro_chat_id)
        await context.bot.send_message(
            chat_id=runtime.config.main_group_id,
            text=f"{mention_html(user.id, person)}\n\n{welcome_text}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

        try:
            await context.bot.send_message(chat_id=user.id, text=welcome_text)
        except Forbidden:
            await context.bot.send_message(
                chat_id=runtime.config.main_group_id,
                text=(
                    f"{mention_html(user.id, person)} I could not DM you. "
                    "Please follow the intro instructions above in-group."
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError:
            logger.exception("failed to send onboarding DM user_id=%s", user.id)

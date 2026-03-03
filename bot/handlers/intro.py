from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..auth import is_admin
from ..handler_helpers import (
    PENDING_SPAM_HISTORY_KEY,
    PENDING_SPAM_MUTES_KEY,
    build_progress_hint,
    is_intro_message,
    record_message_and_check_limit,
    should_remind,
)
from ..runtime import get_runtime
from ..utils import (
    EXAMPLE_INTRO_TEXT,
    build_intro_deeplink,
    build_reminder_text,
    display_name,
    extract_message_text,
    mention_html,
    validate_intro_text,
)
from .join import lock_member, send_reminder_to_user, unlock_member

logger = logging.getLogger(__name__)


async def handle_intro_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None or user.is_bot:
        return

    logger.debug(
        "Intro handler called: chat_id=%s, thread_id=%s, user_id=%s",
        message.chat_id,
        message.message_thread_id,
        user.id,
    )

    is_intro = is_intro_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_thread_id=runtime.config.intro_thread_id,
    )
    logger.debug(
        "_is_intro_message returned: %s, intro_chat_id=%s, intro_thread_id=%s",
        is_intro,
        runtime.config.intro_chat_id,
        runtime.config.intro_thread_id,
    )

    if not is_intro:
        logger.debug("Not an intro message, returning")
        return

    # Skip validation for users who are already introduced — let them
    # chat freely in the intro channel without triggering the bot.
    member = runtime.repo.get_member(user.id)
    if member is not None and member.is_introduced:
        logger.debug("User %s already introduced, skipping validation", user.id)
        return

    # Also skip for admins — they don't need an intro.
    if await is_admin(update, context, runtime):
        logger.debug("User %s is admin, skipping validation", user.id)
        return

    text = extract_message_text(message)
    result = validate_intro_text(
        text=text,
        min_words=runtime.config.min_intro_words,
        min_words_with_signals=runtime.config.min_intro_words_with_signals,
    )

    logger.debug(
        "Intro validation result: is_valid=%s, reason=%s",
        result.is_valid,
        result.reason if not result.is_valid else "N/A",
    )

    if not result.is_valid:
        progress_hint = build_progress_hint(
            word_count=result.word_count,
            min_words=runtime.config.min_intro_words,
        )
        await message.reply_text(
            (
                "⚠️ Intro not complete yet.\n"
                f"{result.reason}\n"
                f"{progress_hint}\n\n"
                "Tip: use /example and include a short paragraph about who you are and what you do."
            )
        )
        return

    logger.info("Accepting intro from user_id=%s", user.id)
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
        await message.reply_text(
            "🎉 Intro accepted! Welcome aboard — you now have full access to the main group."
        )
        intro_link = build_intro_deeplink(
            runtime.config.intro_chat_id, runtime.config.intro_thread_id
        )
        if intro_link:
            intro_ref = f'<a href="{intro_link}">#Intro</a>'
        else:
            intro_ref = "#Intro"
        await context.bot.send_message(
            chat_id=runtime.config.main_group_id,
            text=(
                f"✅ {mention_html(user.id, user_label)} intro accepted in {intro_ref}. "
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

    logger.debug(
        "Message from user_id=%s, chat_id=%s, thread_id=%s, intro_thread=%s",
        user.id,
        message.chat_id,
        message.message_thread_id,
        runtime.config.intro_thread_id,
    )

    if is_intro_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_thread_id=runtime.config.intro_thread_id,
    ):
        logger.debug("Message is in intro topic, skipping")
        return

    admin_status = await is_admin(update, context, runtime)
    logger.debug("User %s is_admin=%s", user.id, admin_status)

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

    logger.debug("User %s is_introduced=%s", user.id, member.is_introduced)

    if member.is_introduced:
        return

    logger.info("Deleting message from pending user user_id=%s", user.id)
    deleted = False
    try:
        await message.delete()
        deleted = True
    except Forbidden:
        logger.warning("cannot delete message for pending user user_id=%s", user.id)
        await _maybe_notify_delete_permission_issue(context, message.chat_id)
    except TelegramError:
        logger.exception("failed to delete message for pending user user_id=%s", user.id)

    user_label = display_name(user.username, user.first_name, user.id)

    if deleted and await _maybe_mute_pending_spammer(
        context=context,
        runtime=runtime,
        user_id=user.id,
        user_label=user_label,
        message_thread_id=message.message_thread_id,
    ):
        return

    if should_remind(member.last_reminded_at, runtime.config.reminder_cooldown_minutes):
        # Full reminder: DM (if possible) + detailed in-chat notification.
        await send_reminder_to_user(
            context=context,
            user_id=user.id,
            user_label=user_label,
            main_group_id=runtime.config.main_group_id,
            intro_chat_id=runtime.config.intro_chat_id,
            intro_thread_id=runtime.config.intro_thread_id,
            notify_chat_id=message.chat_id,
            notify_thread_id=message.message_thread_id,
        )
        runtime.repo.set_last_reminded(user.id)
    elif deleted:
        # Between full reminders, always send a brief in-chat note so
        # the user understands why their message disappeared.
        intro_link = build_intro_deeplink(
            runtime.config.intro_chat_id, runtime.config.intro_thread_id,
        )
        if intro_link:
            intro_ref = f'<a href="{intro_link}">#Intro</a>'
        else:
            intro_ref = "#Intro"
        await context.bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            text=(
                f"🚫 {mention_html(user.id, user_label)}, please complete your "
                f"introduction in {intro_ref} before posting here."
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


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


async def _maybe_notify_delete_permission_issue(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
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
        chat_id=chat_id,
        text=(
            "I cannot delete messages for pending users. "
            "Please grant me the \"Delete messages\" admin permission."
        ),
    )


async def _maybe_notify_restrict_permission_issue(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    key = "pending_restrict_permission_warning_last_at"
    last = context.application.bot_data.get(key)
    if isinstance(last, datetime):
        elapsed = (now - last).total_seconds()
        if elapsed < 300:
            return

    context.application.bot_data[key] = now
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "I cannot mute spammy pending users. "
            "Please grant me the \"Restrict members\" admin permission."
        ),
    )


def _get_pending_spam_histories(context: ContextTypes.DEFAULT_TYPE) -> dict[int, deque[datetime]]:
    store = context.application.bot_data.get(PENDING_SPAM_HISTORY_KEY)
    if isinstance(store, dict):
        return store
    created: dict[int, deque[datetime]] = {}
    context.application.bot_data[PENDING_SPAM_HISTORY_KEY] = created
    return created


def _get_pending_spam_mutes(context: ContextTypes.DEFAULT_TYPE) -> dict[int, datetime]:
    store = context.application.bot_data.get(PENDING_SPAM_MUTES_KEY)
    if isinstance(store, dict):
        return store
    created: dict[int, datetime] = {}
    context.application.bot_data[PENDING_SPAM_MUTES_KEY] = created
    return created


async def _maybe_mute_pending_spammer(
    context: ContextTypes.DEFAULT_TYPE,
    runtime,
    user_id: int,
    user_label: str,
    message_thread_id: int | None,
) -> bool:
    if (
        runtime.config.rate_limit_max_messages <= 0
        or runtime.config.rate_limit_window_seconds <= 0
        or runtime.config.rate_limit_mute_minutes <= 0
    ):
        return False

    now = datetime.now(timezone.utc)
    mutes = _get_pending_spam_mutes(context)
    active_mute = mutes.get(user_id)
    if active_mute is not None and now < active_mute:
        return True

    histories = _get_pending_spam_histories(context)
    history = histories.setdefault(user_id, deque())
    is_limited = record_message_and_check_limit(
        history=history,
        now=now,
        window_seconds=runtime.config.rate_limit_window_seconds,
        max_messages=runtime.config.rate_limit_max_messages,
    )
    if not is_limited:
        return False

    history.clear()
    muted_until = now + timedelta(minutes=runtime.config.rate_limit_mute_minutes)
    mutes[user_id] = muted_until

    muted = await lock_member(context, runtime.config.main_group_id, user_id)
    if not muted:
        mutes.pop(user_id, None)
        await _maybe_notify_restrict_permission_issue(context, runtime.config.main_group_id)
        return False

    _schedule_pending_spam_unmute_job(context, user_id, muted_until)
    await context.bot.send_message(
        chat_id=runtime.config.main_group_id,
        message_thread_id=message_thread_id,
        text=(
            f"⏱️ {mention_html(user_id, user_label)} was muted for "
            f"{runtime.config.rate_limit_mute_minutes} minutes for sending too many "
            "messages before intro completion."
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return True


def _schedule_pending_spam_unmute_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    muted_until: datetime,
) -> None:
    job_queue = context.application.job_queue
    if job_queue is None:
        return

    job_name = f"pending_spam_unmute_{user_id}"
    for job in job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    delay = max((muted_until - datetime.now(timezone.utc)).total_seconds(), 1.0)
    job_queue.run_once(
        callback=_pending_spam_unmute_job,
        when=delay,
        name=job_name,
        data={
            "user_id": user_id,
            "muted_until": muted_until.isoformat(),
        },
    )


async def _pending_spam_unmute_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    data = context.job.data if context.job else None
    if not isinstance(data, dict):
        return

    user_id = data.get("user_id")
    muted_until_raw = data.get("muted_until")
    if not isinstance(user_id, int):
        return

    mutes = _get_pending_spam_mutes(context)
    muted_until = mutes.get(user_id)
    if muted_until is None:
        return
    if isinstance(muted_until_raw, str) and muted_until.isoformat() != muted_until_raw:
        return

    member = runtime.repo.get_member(user_id)
    if member is not None and (member.is_introduced or runtime.config.intro_is_topic_in_main):
        await unlock_member(context, runtime.config.main_group_id, user_id)
    mutes.pop(user_id, None)

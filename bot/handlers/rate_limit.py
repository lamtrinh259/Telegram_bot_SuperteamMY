from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..auth import is_admin
from ..handler_helpers import (
    RATE_LIMIT_HISTORY_KEY,
    RATE_LIMIT_MUTES_KEY,
    is_intro_message,
    record_message_and_check_limit,
)
from ..runtime import get_runtime
from ..utils import display_name, mention_html
from .join import lock_member, unlock_member

logger = logging.getLogger(__name__)


async def handle_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    if not _rate_limit_enabled(runtime):
        return

    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or user.is_bot:
        return

    if message.chat_id != runtime.config.main_group_id:
        return

    if await is_admin(update, context, runtime):
        return

    if is_intro_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_thread_id=runtime.config.intro_thread_id,
    ):
        return

    member = runtime.repo.get_member(user.id)
    if member is None or not member.is_introduced:
        return

    now = datetime.now(timezone.utc)
    mutes = _get_rate_limit_mutes(context)
    active_mute = mutes.get(user.id)
    if active_mute is not None and now < active_mute:
        return

    histories = _get_rate_limit_histories(context)
    history = histories.setdefault(user.id, deque())
    is_limited = record_message_and_check_limit(
        history=history,
        now=now,
        window_seconds=runtime.config.rate_limit_window_seconds,
        max_messages=runtime.config.rate_limit_max_messages,
    )
    if not is_limited:
        return

    history.clear()
    muted_until = now + timedelta(minutes=runtime.config.rate_limit_mute_minutes)
    mutes[user.id] = muted_until

    try:
        await message.delete()
    except Forbidden:
        logger.warning("cannot delete message for rate-limited user user_id=%s", user.id)
    except TelegramError:
        logger.exception("failed to delete message for rate-limited user user_id=%s", user.id)

    muted = await lock_member(context, runtime.config.main_group_id, user.id)
    if not muted:
        mutes.pop(user.id, None)
        await _maybe_notify_restrict_permission_issue(context, runtime.config.main_group_id)
        return

    _schedule_unmute_job(context, user.id, muted_until)
    user_label = display_name(user.username, user.first_name, user.id)
    await context.bot.send_message(
        chat_id=runtime.config.main_group_id,
        text=(
            f"⏱️ {mention_html(user.id, user_label)} is sending messages too quickly "
            f"({runtime.config.rate_limit_max_messages} or more messages within "
            f"{runtime.config.rate_limit_window_seconds}s) and has been muted for "
            f"{runtime.config.rate_limit_mute_minutes} minutes."
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def unmute_after_rate_limit(context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    data = context.job.data if context.job else None
    if not isinstance(data, dict):
        return

    user_id = data.get("user_id")
    muted_until_raw = data.get("muted_until")
    if not isinstance(user_id, int):
        return

    mutes = _get_rate_limit_mutes(context)
    muted_until = mutes.get(user_id)
    if muted_until is None:
        return
    if isinstance(muted_until_raw, str) and muted_until.isoformat() != muted_until_raw:
        return

    member = runtime.repo.get_member(user_id)
    if member is not None and member.is_introduced:
        await unlock_member(context, runtime.config.main_group_id, user_id)
    mutes.pop(user_id, None)


def _schedule_unmute_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    muted_until: datetime,
) -> None:
    job_queue = context.application.job_queue
    if job_queue is None:
        return

    job_name = f"rate_limit_unmute_{user_id}"
    for job in job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    delay = max((muted_until - datetime.now(timezone.utc)).total_seconds(), 1.0)
    job_queue.run_once(
        callback=unmute_after_rate_limit,
        when=delay,
        name=job_name,
        data={
            "user_id": user_id,
            "muted_until": muted_until.isoformat(),
        },
    )


def _get_rate_limit_histories(context: ContextTypes.DEFAULT_TYPE) -> dict[int, deque[datetime]]:
    store = context.application.bot_data.get(RATE_LIMIT_HISTORY_KEY)
    if isinstance(store, dict):
        return store
    created: dict[int, deque[datetime]] = {}
    context.application.bot_data[RATE_LIMIT_HISTORY_KEY] = created
    return created


def _get_rate_limit_mutes(context: ContextTypes.DEFAULT_TYPE) -> dict[int, datetime]:
    store = context.application.bot_data.get(RATE_LIMIT_MUTES_KEY)
    if isinstance(store, dict):
        return store
    created: dict[int, datetime] = {}
    context.application.bot_data[RATE_LIMIT_MUTES_KEY] = created
    return created


def _rate_limit_enabled(runtime) -> bool:
    return (
        runtime.config.rate_limit_max_messages > 0
        and runtime.config.rate_limit_window_seconds > 0
        and runtime.config.rate_limit_mute_minutes > 0
    )


async def _maybe_notify_restrict_permission_issue(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    key = "restrict_permission_warning_last_at"
    last = context.application.bot_data.get(key)
    if isinstance(last, datetime):
        elapsed = (now - last).total_seconds()
        if elapsed < 300:
            return

    context.application.bot_data[key] = now
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "I cannot mute rate-limited users. "
            "Please grant me the \"Restrict members\" admin permission."
        ),
    )

from __future__ import annotations

import logging

from telegram.ext import ContextTypes

from ..runtime import get_runtime
from ..utils import display_name
from .join import send_reminder_to_user

logger = logging.getLogger(__name__)


async def auto_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    targets = runtime.repo.list_pending_ready_for_reminder(
        cooldown_minutes=runtime.config.reminder_cooldown_minutes,
        limit=200,
    )

    if not targets:
        return

    for member in targets:
        await send_reminder_to_user(
            context=context,
            user_id=member.user_id,
            user_label=display_name(member.username, member.first_name, member.user_id),
            main_group_id=runtime.config.main_group_id,
            intro_chat_id=runtime.config.intro_chat_id,
            intro_thread_id=runtime.config.intro_thread_id,
        )
        runtime.repo.set_last_reminded(member.user_id)

    logger.info("auto reminders sent count=%s", len(targets))

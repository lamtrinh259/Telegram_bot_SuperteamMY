from __future__ import annotations

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .runtime import Runtime


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, runtime: Runtime) -> bool:
    user = update.effective_user
    if user is None:
        return False

    if user.id in runtime.config.admin_user_ids:
        return True

    try:
        member = await context.bot.get_chat_member(runtime.config.main_group_id, user.id)
    except TelegramError:
        return False

    return member.status in {"administrator", "creator"}

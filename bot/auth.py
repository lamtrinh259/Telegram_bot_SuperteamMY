from __future__ import annotations

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .runtime import Runtime


async def is_group_admin(
    context: ContextTypes.DEFAULT_TYPE,
    main_group_id: int,
    user_id: int,
) -> bool:
    try:
        member = await context.bot.get_chat_member(main_group_id, user_id)
    except TelegramError:
        return False

    return member.status in {"administrator", "creator"}


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, runtime: Runtime) -> bool:
    user = update.effective_user
    if user is None:
        return False

    if user.id in runtime.config.admin_user_ids:
        return True

    # Prefer checking admin rights in the current chat first. This keeps
    # bootstrap flows working even before MAIN_GROUP_ID is configured.
    current_chat = update.effective_chat
    if current_chat is not None and current_chat.type in {"group", "supergroup"}:
        if await is_group_admin(
            context=context,
            main_group_id=current_chat.id,
            user_id=user.id,
        ):
            return True

    return await is_group_admin(
        context=context,
        main_group_id=runtime.config.main_group_id,
        user_id=user.id,
    )

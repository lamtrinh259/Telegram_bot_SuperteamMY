from __future__ import annotations

from datetime import timezone

from telegram.error import TelegramError
from telegram import Update
from telegram.ext import ContextTypes

from ..auth import is_admin
from ..runtime import get_runtime
from ..utils import display_name
from .join import lock_member, send_reminder_to_user, unlock_member


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    pending = runtime.repo.list_pending(limit=50)
    if not pending:
        await message.reply_text("No pending members.")
        return

    lines = [f"Pending members: {len(pending)}"]
    for member in pending:
        label = display_name(member.username, member.first_name, member.user_id)
        joined = member.joined_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if member.joined_at else "unknown"
        lines.append(f"- {label} (id={member.user_id}, joined={joined})")

    await message.reply_text("\n".join(lines))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        pending_count = runtime.repo.count_pending()
        introduced_count = runtime.repo.count_introduced()
        await message.reply_text(
            (
                "Bot status:\n"
                f"- Pending members: {pending_count}\n"
                f"- Introduced members: {introduced_count}\n"
                f"- Intro channel id: {runtime.config.intro_chat_id}\n"
                f"- Intro topic id: {runtime.config.intro_thread_id or 'none'}\n"
                f"- Main group id: {runtime.config.main_group_id}"
            )
        )
        return

    member = runtime.repo.get_member(target_user_id)
    if member is None:
        await message.reply_text(f"No record found for user_id={target_user_id}.")
        return

    await message.reply_text(
        (
            f"User {target_user_id}\n"
            f"- Status: {member.status}\n"
            f"- Main chat id: {member.main_chat_id}\n"
            f"- Introduced at: {member.introduced_at or 'not yet'}\n"
            f"- Last reminded: {member.last_reminded_at or 'never'}"
        )
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is not None:
        member = runtime.repo.get_member(target_user_id)
        if member is None:
            await message.reply_text(f"No record found for user_id={target_user_id}.")
            return

        await send_reminder_to_user(
            context=context,
            user_id=member.user_id,
            user_label=display_name(member.username, member.first_name, member.user_id),
            main_group_id=runtime.config.main_group_id,
            intro_chat_id=runtime.config.intro_chat_id,
            intro_thread_id=runtime.config.intro_thread_id,
        )
        runtime.repo.set_last_reminded(member.user_id)
        await message.reply_text("Reminder sent.")
        return

    targets = runtime.repo.list_pending_ready_for_reminder(
        cooldown_minutes=runtime.config.reminder_cooldown_minutes,
        limit=100,
    )
    if not targets:
        await message.reply_text("No pending users are due for a reminder.")
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

    await message.reply_text(f"Sent reminders to {len(targets)} pending members.")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /approve <user_id> or reply to a user's message.")
        return

    runtime.repo.upsert_join(
        user_id=target_user_id,
        username=None,
        first_name=None,
        main_chat_id=runtime.config.main_group_id,
    )
    member = runtime.repo.mark_introduced(
        user_id=target_user_id,
        username=None,
        first_name=None,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_message_id=0,
    )

    if member.main_chat_id:
        await unlock_member(context, member.main_chat_id, target_user_id)

    await message.reply_text(f"Approved user_id={target_user_id}.")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /reject <user_id> or reply to a user's message.")
        return

    runtime.repo.upsert_join(
        user_id=target_user_id,
        username=None,
        first_name=None,
        main_chat_id=runtime.config.main_group_id,
    )
    runtime.repo.mark_pending(target_user_id)
    if runtime.config.intro_is_topic_in_main:
        await unlock_member(context, runtime.config.main_group_id, target_user_id)
    else:
        await lock_member(context, runtime.config.main_group_id, target_user_id)

    member = runtime.repo.get_member(target_user_id)
    await send_reminder_to_user(
        context=context,
        user_id=target_user_id,
        user_label=display_name(
            member.username if member else None,
            member.first_name if member else None,
            target_user_id,
        ),
        main_group_id=runtime.config.main_group_id,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_thread_id=runtime.config.intro_thread_id,
    )

    runtime.repo.set_last_reminded(target_user_id)
    warning = await _privacy_warning_if_needed(context, runtime)
    suffix = f"\n\n{warning}" if warning else ""
    await message.reply_text(f"Rejected user_id={target_user_id}; user remains gated.{suffix}")


async def gate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /gate <user_id> or reply to a user's message.")
        return

    runtime.repo.upsert_join(
        user_id=target_user_id,
        username=None,
        first_name=None,
        main_chat_id=runtime.config.main_group_id,
    )
    runtime.repo.mark_pending(target_user_id)
    if runtime.config.intro_is_topic_in_main:
        await unlock_member(context, runtime.config.main_group_id, target_user_id)
    else:
        await lock_member(context, runtime.config.main_group_id, target_user_id)

    warning = await _privacy_warning_if_needed(context, runtime)
    suffix = f"\n\n{warning}" if warning else ""
    await message.reply_text(f"Gated user_id={target_user_id} (pending).{suffix}")


async def ungate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /ungate <user_id> or reply to a user's message.")
        return

    runtime.repo.upsert_join(
        user_id=target_user_id,
        username=None,
        first_name=None,
        main_chat_id=runtime.config.main_group_id,
    )
    runtime.repo.mark_introduced(
        user_id=target_user_id,
        username=None,
        first_name=None,
        intro_chat_id=runtime.config.intro_chat_id,
        intro_message_id=0,
    )
    await unlock_member(context, runtime.config.main_group_id, target_user_id)

    await message.reply_text(f"Ungated user_id={target_user_id} (introduced).")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /reset <user_id> or reply to a user's message.")
        return

    runtime.repo.upsert_join(
        user_id=target_user_id,
        username=None,
        first_name=None,
        main_chat_id=runtime.config.main_group_id,
    )
    runtime.repo.mark_pending(target_user_id)
    if runtime.config.intro_is_topic_in_main:
        await unlock_member(context, runtime.config.main_group_id, target_user_id)
    else:
        await lock_member(context, runtime.config.main_group_id, target_user_id)

    warning = await _privacy_warning_if_needed(context, runtime)
    suffix = f"\n\n{warning}" if warning else ""
    await message.reply_text(
        f"Reset user_id={target_user_id} to pending and cleared intro/reminder state.{suffix}"
    )


async def wipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    target_user_id = _resolve_target_user_id(update, context)
    if target_user_id is None:
        await message.reply_text("Usage: /wipe <user_id> or reply to a user's message.")
        return

    deleted = runtime.repo.delete_member(target_user_id)
    await unlock_member(context, runtime.config.main_group_id, target_user_id)
    if deleted:
        await message.reply_text(f"Wiped user_id={target_user_id} from DB and cleared restrictions.")
    else:
        await message.reply_text(
            f"No DB row for user_id={target_user_id}. Restrictions were still reset."
        )


async def diag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    me = await context.bot.get_me()
    privacy_off = bool(getattr(me, "can_read_all_group_messages", False))
    privacy_line = "OFF (good)" if privacy_off else "ON (commands-only; disable via BotFather)"

    bot_status = "unknown"
    can_delete = "unknown"
    can_restrict = "unknown"
    try:
        bot_member = await context.bot.get_chat_member(runtime.config.main_group_id, me.id)
        bot_status = bot_member.status
        can_delete = str(getattr(bot_member, "can_delete_messages", False))
        can_restrict = str(getattr(bot_member, "can_restrict_members", False))
    except TelegramError:
        bot_status = "error"

    await message.reply_text(
        (
            "Diagnostics:\n"
            f"- Bot id: {me.id}\n"
            f"- Bot username: @{me.username}\n"
            f"- Privacy mode: {privacy_line}\n"
            f"- Bot member status in main group: {bot_status}\n"
            f"- can_delete_messages: {can_delete}\n"
            f"- can_restrict_members: {can_restrict}\n"
            f"- MAIN_GROUP_ID: {runtime.config.main_group_id}\n"
            f"- INTRO_CHAT_ID: {runtime.config.intro_chat_id}\n"
            f"- INTRO_THREAD_ID: {runtime.config.intro_thread_id or 'none'}"
        )
    )


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = get_runtime(context)
    message = update.effective_message
    if message is None:
        return

    if not await is_admin(update, context, runtime):
        await message.reply_text("Admin only command.")
        return

    await message.reply_text(
        (
            "Admin test commands:\n"
            "- /pending\n"
            "- /status [user_id]\n"
            "- /remind [user_id]\n"
            "- /approve <user_id>\n"
            "- /reject <user_id>\n"
            "- /gate <user_id> (set pending, no reminder spam)\n"
            "- /ungate <user_id> (set introduced)\n"
            "- /reset <user_id> (pending + clear intro/reminder)\n"
            "- /wipe <user_id> (delete DB row)\n"
            "- /diag (privacy mode + permissions)\n"
            "- /adminhelp"
        )
    )


async def _privacy_warning_if_needed(
    context: ContextTypes.DEFAULT_TYPE,
    runtime,
) -> str | None:
    if not runtime.config.intro_is_topic_in_main:
        return None
    try:
        me = await context.bot.get_me()
    except TelegramError:
        return None
    privacy_off = bool(getattr(me, "can_read_all_group_messages", False))
    if privacy_off:
        return None
    return (
        "Note: Privacy mode is ON. In forum-topic mode, General gating needs privacy mode OFF "
        "(BotFather /setprivacy -> Disable), then restart the bot."
    )


def _resolve_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    del context
    message = update.effective_message
    if message is None:
        return None

    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    if not update.message or not update.message.text:
        return None

    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        return None

    raw = parts[1].strip()
    try:
        return int(raw)
    except ValueError:
        return None

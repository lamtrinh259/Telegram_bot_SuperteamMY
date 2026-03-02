from __future__ import annotations

import logging

from telegram import BotCommand, Message, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Config
from .database import MemberRepository
from .handlers.admin import (
    adminhelp_command,
    approve_command,
    diag_command,
    gate_command,
    pending_command,
    reject_command,
    remind_command,
    status_command,
    reset_command,
    ungate_command,
    wipe_command,
)
from .handlers.intro import (
    example_command,
    handle_intro_message,
    handle_main_group_message,
    ids_command,
    start_command,
)
from .handlers.jobs import auto_reminder_job
from .handlers.join import handle_new_members
from .runtime import Runtime
from .utils import UNMUTED_PERMISSIONS


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


class NotInIntroTopic(filters.MessageFilter):
    """Filter that matches messages NOT in the intro topic.

    Must extend MessageFilter (not BaseFilter) so that check_update()
    actually delegates to our filter() method.  BaseFilter.check_update()
    only checks whether the Update contains a message — it never calls
    filter(), so a custom BaseFilter subclass's filter() is dead code.
    """

    def __init__(self, intro_chat_id: int, intro_thread_id: int | None):
        super().__init__()
        self.intro_chat_id = intro_chat_id
        self.intro_thread_id = intro_thread_id

    def filter(self, message: Message) -> bool:  # noqa: D102
        # If intro is not in a topic mode, all main group messages are non-intro
        if self.intro_thread_id is None:
            return True

        # In topic mode, exclude messages from the intro topic
        return message.message_thread_id != self.intro_thread_id


class InIntroTopic(filters.MessageFilter):
    """Filter that matches messages that ARE in the intro topic.

    When intro_thread_id is None (intro is a separate chat, not a forum
    topic), every message in that chat counts as an intro message, so this
    filter always returns True.
    """

    def __init__(self, intro_thread_id: int | None):
        super().__init__()
        self.intro_thread_id = intro_thread_id

    def filter(self, message: Message) -> bool:  # noqa: D102
        if self.intro_thread_id is None:
            return True
        return message.message_thread_id == self.intro_thread_id


def build_application(config: Config) -> Application:
    repo = MemberRepository(config.database_path)
    runtime = Runtime(config=config, repo=repo)

    async def post_init(application: Application) -> None:
        application.bot_data["runtime"] = runtime
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Get intro instructions"),
                BotCommand("example", "Show an example intro"),
                BotCommand("ids", "Show current chat/user IDs"),
                BotCommand("pending", "List pending members (admin)"),
                BotCommand("status", "Bot or member status (admin)"),
                BotCommand("remind", "Send reminder(s) (admin)"),
                BotCommand("approve", "Manually approve a member (admin)"),
                BotCommand("reject", "Keep member gated (admin)"),
                BotCommand("gate", "Force user to pending (admin)"),
                BotCommand("ungate", "Force user to introduced (admin)"),
                BotCommand("reset", "Reset user intro state (admin)"),
                BotCommand("wipe", "Delete user state from DB (admin)"),
                BotCommand("diag", "Show bot diagnostics (admin)"),
                BotCommand("adminhelp", "List admin test commands"),
            ]
        )

        if runtime.config.auto_reminder_hours > 0:
            interval_seconds = runtime.config.auto_reminder_hours * 3600
            application.job_queue.run_repeating(
                callback=auto_reminder_job,
                interval=interval_seconds,
                first=120,
                name="auto_reminders",
            )

        if runtime.config.intro_is_topic_in_main:
            pending_members = runtime.repo.list_pending(limit=500)
            for member in pending_members:
                try:
                    await application.bot.restrict_chat_member(
                        chat_id=runtime.config.main_group_id,
                        user_id=member.user_id,
                        permissions=UNMUTED_PERMISSIONS,
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "failed to clear stale restriction user_id=%s",
                        member.user_id,
                    )

            try:
                me = await application.bot.get_me()
                privacy_off = bool(getattr(me, "can_read_all_group_messages", False))
                if not privacy_off:
                    await application.bot.send_message(
                        chat_id=runtime.config.main_group_id,
                        text=(
                            "Warning: Bot privacy mode is ON. Topic-mode gating in General requires "
                            "privacy mode OFF, otherwise non-command messages cannot be intercepted.\n\n"
                            "Fix in BotFather: /setprivacy -> select this bot -> Disable, then restart bot."
                        ),
                    )
            except Exception:
                logging.getLogger(__name__).exception("failed to run privacy-mode startup check")

    async def post_shutdown(application: Application) -> None:
        del application
        runtime.repo.close()

    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.Chat(config.main_group_id) & filters.StatusUpdate.NEW_CHAT_MEMBERS,
            handle_new_members,
        )
    )

    # Main group text handler MUST run before intro handler since both filters match in forum topics
    # Use custom filter to exclude intro topic messages
    main_group_text_filters = (
        filters.Chat(config.main_group_id)
        & ~filters.COMMAND
        & (filters.TEXT | filters.CAPTION)
        & NotInIntroTopic(config.intro_chat_id, config.intro_thread_id)
    )
    application.add_handler(MessageHandler(main_group_text_filters, handle_main_group_message))

    intro_filters = (
        filters.Chat(config.intro_chat_id)
        & ~filters.COMMAND
        & (filters.TEXT | filters.CAPTION)
        & InIntroTopic(config.intro_thread_id)
    )
    application.add_handler(MessageHandler(intro_filters, handle_intro_message))

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("example", example_command))
    application.add_handler(CommandHandler("ids", ids_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("reject", reject_command))
    application.add_handler(CommandHandler("gate", gate_command))
    application.add_handler(CommandHandler("ungate", ungate_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("wipe", wipe_command))
    application.add_handler(CommandHandler("diag", diag_command))
    application.add_handler(CommandHandler("adminhelp", adminhelp_command))

    application.add_error_handler(error_handler)
    return application


async def error_handler(update: object, context) -> None:
    logger = logging.getLogger(__name__)
    logger.exception("Unhandled exception update=%s", _safe_update_repr(update), exc_info=context.error)


def _safe_update_repr(update: object) -> str:
    if isinstance(update, Update):
        try:
            return str(update.to_dict())
        except Exception:
            return "<unserializable update>"
    return str(update)

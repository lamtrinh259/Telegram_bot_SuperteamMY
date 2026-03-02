from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

from .config import Config
from .database import MemberRepository
from .handlers.admin import (
    approve_command,
    pending_command,
    reject_command,
    remind_command,
    status_command,
)
from .handlers.intro import example_command, handle_intro_message, handle_main_group_message, start_command
from .handlers.jobs import auto_reminder_job
from .handlers.join import handle_new_members
from .runtime import Runtime


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_application(config: Config) -> Application:
    repo = MemberRepository(config.database_path)
    runtime = Runtime(config=config, repo=repo)

    async def post_init(application: Application) -> None:
        application.bot_data["runtime"] = runtime
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Get intro instructions"),
                BotCommand("example", "Show an example intro"),
                BotCommand("pending", "List pending members (admin)"),
                BotCommand("status", "Bot or member status (admin)"),
                BotCommand("remind", "Send reminder(s) (admin)"),
                BotCommand("approve", "Manually approve a member (admin)"),
                BotCommand("reject", "Keep member gated (admin)"),
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

    intro_filters = filters.Chat(config.intro_chat_id) & ~filters.COMMAND & (
        filters.TEXT | filters.CAPTION
    )
    application.add_handler(MessageHandler(intro_filters, handle_intro_message))

    main_group_text_filters = filters.Chat(config.main_group_id) & ~filters.COMMAND & (
        filters.TEXT | filters.CAPTION
    )
    application.add_handler(MessageHandler(main_group_text_filters, handle_main_group_message))

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("example", example_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("reject", reject_command))

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

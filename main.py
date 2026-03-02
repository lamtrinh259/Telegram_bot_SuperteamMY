from __future__ import annotations

from bot.app import build_application, configure_logging
from bot.config import Config
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    configure_logging(config.log_level)
    application = build_application(config)
    application.run_polling(drop_pending_updates=False)


async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        print(f"Chat ID: {update.message.chat_id}")
        print(f"User ID: {update.effective_user.id}")
        print(f"Message: {update.message.text}")


if __name__ == "__main__":
    main()

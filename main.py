from __future__ import annotations

from bot.app import build_application, configure_logging
from bot.config import Config
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    configure_logging(config.log_level)
    application = build_application(config)
    application.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()

import logging
import sys
import os

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN
from bot import cmd_start, cmd_cancel, handle_message, movie_callback, quality_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logging.getLogger("httpx").setLevel(logging.WARNING)


async def error_handler(update, context):
    if isinstance(context.error, Conflict):
        return
    logging.getLogger(__name__).error("Bot error: %s", context.error)


def main():
    space_id = os.getenv("SPACE_ID")
    if space_id:
        from server import keep_alive
        keep_alive()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(movie_callback, pattern=r"^mv_\d+$"))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern=r"^ql_"))

    app.add_error_handler(error_handler)

    logger = logging.getLogger(__name__)
    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

import threading
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def start_bot():
    from main import main
    main()


bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

import gradio as gr

with gr.Blocks(title="Movie Bot", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
    # 🎬 Movie Downloader Bot

    **البوت شغال!** أرسل اسم فيلم للبوت على تليجرام.
        """
    )
    gr.Textbox("🟢 Bot is running", label="Status", interactive=False)

demo.launch(server_port=7860)

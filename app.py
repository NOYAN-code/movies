import threading
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def start_gradio():
    import gradio as gr

    with gr.Blocks(title="Movie Bot") as demo:
        gr.Markdown(
            """
        # Movie Downloader Bot
        Bot is running on Telegram. Send a movie name to download it.
            """
        )

    demo.launch(server_port=7860)


gradio_thread = threading.Thread(target=start_gradio, daemon=True)
gradio_thread.start()

from main import main
main()

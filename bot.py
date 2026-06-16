import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from telegram.error import NetworkError

from config import BOT_TOKEN, YTS_API_BASE, DOWNLOAD_DIR, SPLIT_THRESHOLD, PART_MAX_SIZE, TRACKERS
from search import MovieSearcher
from downloader import TorrentDownloader
from splitter import VideoSplitter

logger = logging.getLogger(__name__)

searcher = MovieSearcher(YTS_API_BASE)
downloader = TorrentDownloader(DOWNLOAD_DIR / "torrents", TRACKERS)
splitter = VideoSplitter()


class UserState:
    def __init__(self):
        self.movie = None
        self.movie_id: Optional[int] = None
        self.quality: Optional[str] = None
        self.torrent_hash: Optional[str] = None
        self.download_msg_id: Optional[int] = None
        self.is_downloading = False
        self.is_cancelled = False


user_states: dict[int, UserState] = {}


def get_state(user_id: int) -> UserState:
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]


def fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024 ** 3:.2f} GB"
    return f"{size_bytes / 1024 ** 2:.2f} MB"


def fmt_speed(bps: float) -> str:
    if bps >= 1024 ** 3:
        return f"{bps / 1024 ** 3:.2f} GB/s"
    if bps >= 1024 ** 2:
        return f"{bps / 1024 ** 2:.2f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.2f} KB/s"
    return f"{bps:.0f} B/s"


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 **مرحباً بك في بوت تحميل الأفلام!**\n\n"
        "أرسل اسم أي فيلم وسأبحث عنه لك.\n"
        "متاح جودة 720p و 1080p.\n\n"
        "الأوامر:\n"
        "/cancel - إلغاء التحميل الحالي",
        parse_mode="Markdown",
    )


async def cmd_cancel(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    if state.is_downloading:
        state.is_cancelled = True
        state.is_downloading = False
        await update.message.reply_text("✅ تم إلغاء التحميل.")
    else:
        await update.message.reply_text("لا يوجد تحميل قيد التشغيل.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)

    if state.is_downloading:
        await update.message.reply_text(
            "⏳ لديك تحميل قيد التشغيل. انتظر أو استخدم /cancel."
        )
        return

    query = update.message.text.strip()
    if not query:
        return

    msg = await update.message.reply_text(f"🔍 أبحث عن «{query}»...")

    try:
        movies = await searcher.search(query)
    except Exception as e:
        logger.exception("Search error")
        await msg.edit_text("❌ حدث خطأ أثناء البحث.")
        return

    if not movies:
        await msg.edit_text("😕 لم أجد أي فيلم. جرب اسماً آخر.")
        return

    keyboard = []
    for m in movies:
        btn = InlineKeyboardButton(
            f"{m.title} ({m.year}) ⭐{m.rating}",
            callback_data=f"mv_{m.id}",
        )
        keyboard.append([btn])

    await msg.edit_text(
        f"تم العثور على {len(movies)} نتائج. اختر الفيلم:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def movie_callback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    state = get_state(user_id)
    movie_id = int(query.data.split("_")[1])
    state.movie_id = movie_id

    try:
        movie = await searcher.get_movie(movie_id)
    except Exception:
        logger.exception("Movie detail error")
        await query.edit_message_text("❌ حدث خطأ في جلب التفاصيل.")
        return

    if not movie:
        await query.edit_message_text("❌ لم يتم العثور على الفيلم.")
        return

    state.movie = movie

    keyboard = []
    for t in sorted(movie.torrents, key=lambda x: x.quality):
        btn = InlineKeyboardButton(
            f"{t.quality} | {t.size} | 🌱{t.seeds}",
            callback_data=f"ql_{t.hash}_{t.quality}",
        )
        keyboard.append([btn])

    if not keyboard:
        await query.edit_message_text("😕 لا توجد روابط تحميل لهذا الفيلم.")
        return

    text = (
        f"🎬 **{movie.title}**\n"
        f"📅 {movie.year} | ⭐ {movie.rating}\n"
        f"📝 {movie.summary}...\n\n"
        "اختر الجودة:"
    )
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    state = get_state(user_id)

    if state.is_downloading:
        await query.edit_message_text("⏳ لديك تحميل قيد التشغيل.")
        return

    parts = query.data.split("_")
    torrent_hash = parts[1]
    quality = parts[2]

    state.torrent_hash = torrent_hash
    state.quality = quality
    state.is_downloading = True
    state.is_cancelled = False

    await query.edit_message_text(
        f"⏳ بدء تحميل {state.movie.title} ({quality})..."
    )

    progress_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔄 جاري البدء...",
    )
    state.download_msg_id = progress_msg.message_id

    asyncio.create_task(
        _download_and_send(update, context, state)
    )


async def _download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, state: UserState):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    movie = state.movie
    loop = asyncio.get_event_loop()

    def _update(msg_text: str):
        try:
            coro = context.bot.edit_message_text(
                msg_text,
                chat_id=chat_id,
                message_id=state.download_msg_id,
            )
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            pass

    def progress_cb(pct: float, speed: float):
        _update(f"📥 جاري التحميل... {pct:.1f}%\n⚡ {fmt_speed(speed)}")

    def status_cb(text: str):
        _update(f"🔄 {text}")

    magnet = downloader.build_magnet(state.torrent_hash, movie.title)

    try:
        filepath = await loop.run_in_executor(
            None,
            lambda: downloader.download(magnet, progress_cb, status_cb),
        )

        if state.is_cancelled:
            if filepath and filepath.exists():
                filepath.unlink()
            _update("❌ تم الإلغاء.")
            state.is_downloading = False
            return

        if not filepath or not filepath.exists():
            _update("❌ فشل التحميل. حاول مرة أخرى.")
            state.is_downloading = False
            return

        fsize = os.path.getsize(filepath)
        _update(f"✅ تم التحميل! ({fmt_size(fsize)})\n🔄 جاري الإرسال...")

        if fsize <= SPLIT_THRESHOLD:
            await _send_video(context, chat_id, filepath, movie, state.quality)
        else:
            await _split_and_send(context, chat_id, filepath, movie, state.quality)

        _cleanup(filepath)
        _update(f"✅ تم إرسال {movie.title} ({state.quality}) بنجاح!")

    except Exception as e:
        logger.exception("Download/send error")
        _update(f"❌ خطأ: {str(e)[:100]}")

    finally:
        state.is_downloading = False


async def _send_with_retry(send_fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await send_fn()
        except NetworkError as e:
            if attempt == max_retries - 1:
                raise
            logger.warning("Send attempt %d failed: %s, retrying...", attempt + 1, str(e)[:80])
            await asyncio.sleep(5 * (attempt + 1))


async def _send_video(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    filepath: Path,
    movie,
    quality: str,
):
    async def send():
        with open(filepath, "rb") as f:
            return await context.bot.send_video(
                chat_id=chat_id,
                video=f,
                caption=f"🎬 {movie.title} ({movie.year})\n💿 {quality}",
                supports_streaming=True,
                read_timeout=1200,
                write_timeout=1200,
                connect_timeout=1200,
            )

    await _send_with_retry(send)


async def _split_and_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    filepath: Path,
    movie,
    quality: str,
):
    output_dir = filepath.parent / f"{filepath.stem}_parts"

    loop = asyncio.get_event_loop()
    parts = await loop.run_in_executor(
        None,
        lambda: splitter.split_by_size(filepath, PART_MAX_SIZE, output_dir),
    )

    for i, part in enumerate(parts, 1):
        async def send(part=part, i=i):
            with open(part, "rb") as f:
                return await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=(
                        f"🎬 {movie.title} ({movie.year})\n"
                        f"💿 {quality}\n📦 الجزء {i}/{len(parts)}"
                    ),
                    supports_streaming=True,
                    read_timeout=1200,
                    write_timeout=1200,
                    connect_timeout=1200,
                )

        await _send_with_retry(send)
        try:
            part.unlink()
        except Exception:
            pass

    try:
        shutil.rmtree(output_dir)
    except Exception:
        pass


def _cleanup(filepath: Path):
    try:
        if filepath.exists():
            filepath.unlink()
    except Exception:
        pass
    try:
        parent = filepath.parent
        if parent.exists():
            shutil.rmtree(parent)
    except Exception:
        pass

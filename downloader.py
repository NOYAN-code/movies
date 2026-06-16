import os
import time
import logging
from pathlib import Path
from typing import Callable, Optional

import libtorrent as lt

logger = logging.getLogger(__name__)


class TorrentDownloader:
    def __init__(self, save_path: Path, trackers: list[str] = None):
        self.save_path = save_path
        self.trackers = trackers or []
        self._session = lt.session()

        settings = self._session.get_settings()
        settings["connections_limit"] = 200
        settings["download_rate_limit"] = 0
        settings["upload_rate_limit"] = 0
        settings["active_downloads"] = 3
        settings["active_limit"] = 10
        settings["enable_dht"] = True
        settings["enable_lsd"] = True
        settings["enable_upnp"] = True
        settings["enable_natpmp"] = True
        settings["dht_bootstrap_nodes"] = (
            "dht.libtorrent.org:25401,router.bittorrent.com:6881,"
            "dht.transmissionbt.com:6881,router.utorrent.com:6881"
        )
        settings["user_agent"] = "utorrent/3.6.0"
        settings["announce_to_all_tiers"] = True
        settings["announce_to_all_trackers"] = True
        settings["ssl_listen"] = 0
        self._session.apply_settings(settings)

        self._session.listen_on(6881, 6891)

    def build_magnet(self, info_hash: str, title: str) -> str:
        magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={title}"
        for tr in self.trackers:
            magnet += f"&tr={tr}"
        return magnet

    def download(
        self,
        magnet_link: str,
        progress_callback: Callable[[float, float], None] = None,
        status_callback: Callable[[str], None] = None,
    ) -> Optional[Path]:
        os.makedirs(self.save_path, exist_ok=True)

        params = {
            "save_path": str(self.save_path),
            "storage_mode": lt.storage_mode_t(2),
        }

        try:
            handle = lt.add_magnet_uri(self._session, magnet_link, params)
        except Exception as e:
            logger.error("Failed to add magnet: %s", e)
            return None

        if status_callback:
            status_callback("جاري الحصول على معلومات التورنت...")

        for _ in range(120):
            if handle.has_metadata():
                break
            time.sleep(0.5)
        else:
            logger.error("Timeout waiting for metadata")
            return None

        torrent_info = handle.get_torrent_info()
        files = torrent_info.files()

        file_idx = max(
            range(files.num_files()),
            key=lambda i: files.file_size(i),
        )

        file_path = files.file_path(file_idx)
        file_size = files.file_size(file_idx)

        if status_callback:
            fname = file_path.replace("\\", "/").split("/")[-1]
            fsize = self._format_size(file_size)
            status_callback(f"الملف: {fname} ({fsize})")

        for i in range(files.num_files()):
            handle.file_priority(i, 0)
        handle.file_priority(file_idx, 4)

        if status_callback:
            status_callback("جاري التحميل...")

        last_update = 0.0

        while True:
            s = handle.status()

            if s.errc and s.errc.message():
                err_msg = s.errc.message().lower()
                if "operation completed" not in err_msg and "success" not in err_msg:
                    logger.error("Torrent error: %s", s.errc.message())

            now = time.time()
            if progress_callback and now - last_update >= 1.0:
                progress_callback(s.progress * 100, s.download_rate)
                last_update = now

            if s.state in (lt.torrent_status.finished, lt.torrent_status.seeding):
                break

            time.sleep(0.5)

        result_path = self.save_path / file_path
        if result_path.exists():
            if status_callback:
                status_callback("اكتمل التحميل!")
            return result_path.resolve()

        logger.error("Downloaded file not found at %s", result_path)
        return None

    def stop(self):
        self._session.pause()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / 1024 ** 3:.2f} GB"
        if size_bytes >= 1024 ** 2:
            return f"{size_bytes / 1024 ** 2:.2f} MB"
        return f"{size_bytes / 1024:.2f} KB"

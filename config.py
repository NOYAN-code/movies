import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"

BOT_TOKEN = "8979940983:AAGM75mwuB8Udi3FKKK513GofMfVNq2sOlc"
YTS_API_BASE = "https://yts.ag/api/v2"

SPLIT_THRESHOLD = 3 * 1024 * 1024 * 1024
PART_MAX_SIZE = 2 * 1024 * 1024 * 1024

TRACKERS = [
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
    "udp://9.rarbg.to:2710/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "http://tracker.bittorrent.am:80/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
]

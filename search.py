import aiohttp
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TorrentInfo:
    quality: str
    size: str
    size_bytes: int
    hash: str
    seeds: int
    peers: int


@dataclass
class MovieInfo:
    id: int
    title: str
    year: int
    rating: float
    summary: str
    cover: str
    torrents: list[TorrentInfo] = field(default_factory=list)


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}

class MovieSearcher:
    def __init__(self, api_base: str):
        self.api_base = api_base

    async def search(self, query: str, limit: int = 8) -> list[MovieInfo]:
        url = f"{self.api_base}/list_movies.json"
        params = {"query_term": query, "limit": limit}

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logger.error("YTS API returned status %d", resp.status)
                    return []

                data = await resp.json()
                if data.get("status") != "ok":
                    return []

                movies_data = data.get("data", {}).get("movies", [])
                return [self._parse_movie(m) for m in movies_data]

    async def get_movie(self, movie_id: int):
        url = f"{self.api_base}/movie_details.json"
        params = {"movie_id": movie_id}

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                if data.get("status") != "ok":
                    return None

                m = data.get("data", {}).get("movie")
                return self._parse_movie(m) if m else None

    def _parse_movie(self, m: dict) -> MovieInfo:
        torrents = []
        for t in m.get("torrents", []):
            size_str = t.get("size", "0")
            torrents.append(TorrentInfo(
                quality=t.get("quality", "Unknown"),
                size=size_str,
                size_bytes=self._parse_size(size_str),
                hash=t.get("hash", ""),
                seeds=t.get("seeds", 0),
                peers=t.get("peers", 0),
            ))

        return MovieInfo(
            id=m.get("id"),
            title=m.get("title"),
            year=m.get("year"),
            rating=m.get("rating", 0),
            summary=(m.get("summary") or "")[:200],
            cover=m.get("medium_cover_image", ""),
            torrents=torrents,
        )

    @staticmethod
    def _parse_size(size_str: str) -> int:
        s = size_str.strip().upper()
        try:
            if "GB" in s:
                return int(float(s.replace("GB", "").strip()) * 1024 ** 3)
            if "MB" in s:
                return int(float(s.replace("MB", "").strip()) * 1024 ** 2)
        except ValueError:
            pass
        return 0

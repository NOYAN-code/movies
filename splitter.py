import json
import math
import os
import subprocess
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class VideoSplitter:
    @staticmethod
    def get_duration(filepath: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(filepath),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])

    @staticmethod
    def split_by_size(
        filepath: Path,
        max_size_bytes: int,
        output_dir: Path,
        progress_callback: Callable[[int, int], None] = None,
    ) -> list[Path]:
        os.makedirs(output_dir, exist_ok=True)

        total_size = os.path.getsize(filepath)
        duration = VideoSplitter.get_duration(filepath)

        num_parts = math.ceil(total_size / max_size_bytes)
        part_duration = math.ceil(duration / num_parts)

        logger.info(
            "Splitting %s: %.2f GB, %d parts of ~%ds each",
            filepath.name,
            total_size / 1024 ** 3,
            num_parts,
            part_duration,
        )

        if progress_callback:
            progress_callback(0, num_parts)

        output_pattern = str(output_dir / "part_%03d.mp4")

        cmd = [
            "ffmpeg", "-y", "-i", str(filepath),
            "-c", "copy", "-map", "0",
            "-f", "segment",
            "-segment_time", str(part_duration),
            "-reset_timestamps", "1",
            "-segment_start_number", "1",
            output_pattern,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg split failed: {result.stderr}")

        parts = sorted(
            Path(output_dir).glob("part_*.mp4"),
            key=lambda p: int(p.stem.split("_")[1]),
        )

        if progress_callback:
            progress_callback(len(parts), len(parts))

        return parts

"""ffprobe/ffmpeg 보조. Instagram 은 AV1 MP4 를 조용히 거부하므로 h264 를 보장한다."""

from __future__ import annotations

import subprocess
from pathlib import Path


def video_codec(path: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {result.stderr.strip()[-300:]}")
    return result.stdout.strip()


def ensure_h264(path: Path) -> tuple[Path, str]:
    """(업로드에 쓸 파일 경로, 코덱 노트) 반환. 필요 시 h264 로 재인코딩."""
    codec = video_codec(path)
    if codec == "h264":
        return path, "h264"
    output = path.with_name(f"{path.stem}.h264.mp4")
    if not output.exists():
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 재인코딩 실패: {result.stderr.strip()[-300:]}")
    return output, f"{codec} → h264 재인코딩"

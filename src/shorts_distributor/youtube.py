from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL

from .config import normalize_youtube_handle


@dataclass
class VideoMeta:
    id: str
    title: str
    description: str
    tags: list[str]
    duration: int | None
    upload_date: str | None
    timestamp: int | None
    webpage_url: str
    file_path: Path


def get_channel_shorts(
    handle: str,
    limit: int | None = None,
    *,
    metadata_lang: str | None = None,
) -> list[dict]:
    """
    채널 '숏폼' 탭 전체 플랫 리스트. 최신이 첫번째.
    - metadata_lang(YOUTUBE_METADATA_LANG)을 지정하면 그 언어의 원본 제목을 강제한다.
      flat extraction 기본값은 실행 환경 언어에 따라 번역된 제목을 반환할 수 있어서,
      채널 원어 제목이 필요하면 채널 언어 코드(예: ko, ja, en)를 설정한다.
    반환: [{id, title, url, ...}, ...]
    """
    handle = normalize_youtube_handle(handle)
    if not handle:
        raise RuntimeError("YOUTUBE_HANDLE is required. Set it in .env, e.g. YOUTUBE_HANDLE=@your-channel")
    if handle.startswith("http://") or handle.startswith("https://"):
        url = handle if handle.endswith("/shorts") else f"{handle}/shorts"
    else:
        url = f"https://www.youtube.com/{handle}/shorts"
    opts: dict = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
    if metadata_lang:
        opts["http_headers"] = {"Accept-Language": f"{metadata_lang};q=0.9"}
        opts["extractor_args"] = {"youtube": {"lang": [metadata_lang]}}
    if limit:
        opts["playlistend"] = limit
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("entries") or []


def download_video(video_id: str, download_dir: Path) -> VideoMeta:
    download_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = str(download_dir / "%(id)s.%(ext)s")
    opts = {
        "outtmpl": outtmpl,
        "format": "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "quiet": False,
        "noprogress": True,
        "writeinfojson": True,
        "writesubtitles": False,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if path.suffix != ".mp4":
            path = path.with_suffix(".mp4")
    return VideoMeta(
        id=info["id"],
        title=info.get("title", "").strip(),
        description=(info.get("description") or "").strip(),
        tags=info.get("tags") or [],
        duration=info.get("duration"),
        upload_date=info.get("upload_date"),
        timestamp=info.get("timestamp"),
        webpage_url=info.get("webpage_url", url),
        file_path=path,
    )

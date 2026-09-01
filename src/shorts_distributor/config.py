from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .platforms import parse_platform_list

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DOWNLOAD_DIR = DATA_DIR / "downloads"
PROFILES_DIR = DATA_DIR / "profiles"
RUNS_DIR = DATA_DIR / "runs"


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_positive_int(name: str, default: int) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def env_optional_positive_int(name: str, default: int | None = None) -> int | None:
    raw = env_str(name)
    if not raw:
        return default
    if raw.lower() in {"all", "none", "unlimited"}:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer or 'all'.") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer or 'all'.")
    return value


def env_bool(name: str, default: bool) -> bool:
    raw = env_str(name)
    if not raw:
        return default
    normalized = raw.lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


def normalize_youtube_handle(handle: str) -> str:
    handle = handle.strip()
    if not handle:
        return ""
    if handle.startswith("http://") or handle.startswith("https://"):
        return handle.rstrip("/")
    if not handle.startswith("@"):
        handle = f"@{handle}"
    return handle


@dataclass
class Config:
    youtube_handle: str
    # 채널 원어 제목 강제용 언어 코드(예: ko, ja). 빈 값이면 yt-dlp 기본 동작.
    youtube_metadata_lang: str
    download_dir: Path
    profiles_dir: Path
    runs_dir: Path
    target_platforms: list[str]
    post_text_mode: str
    shorts_selection_mode: str
    shorts_upload_limit: int | None
    shorts_lookback_limit: int
    shorts_skip_ads: bool
    content_policies_file: Path | None

    # 코드 업로드(Playwright) 설정
    chrome_channel: str
    uploader_headless: bool
    uploader_slowmo_ms: int
    # shared: 모든 플랫폼 로그인이 한 프로필에 있음(운영 실태 기본값).
    # per-platform: data/profiles/<platform> 분리(병렬 레인 대비).
    profile_strategy: str
    shared_profile_dir: Path

    # 플랫폼별 계정/검증 값
    instagram_handle: str
    threads_handle: str
    tiktok_handle: str
    linkedin_recent_activity_url: str
    facebook_videos_url: str
    facebook_page_name: str
    naver_channel_slug: str
    naver_clip_url: str
    naver_category_1: str
    naver_category_2: str

    @classmethod
    def load(cls) -> "Config":
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        platform_env = env_str("TARGET_PLATFORMS", env_str("PLATFORMS"))
        post_text_mode = env_str("POST_TEXT_MODE", "caption").lower()
        if post_text_mode in {"title-only", "title_only"}:
            post_text_mode = "title"
        if post_text_mode not in {"caption", "title"}:
            raise ValueError("POST_TEXT_MODE must be either 'caption' or 'title'.")
        shorts_selection_mode = env_str("SHORTS_SELECTION_MODE", "recent").lower()
        if shorts_selection_mode not in {"recent", "all"}:
            raise ValueError("SHORTS_SELECTION_MODE must be either 'recent' or 'all'.")
        slowmo = env_str("UPLOADER_SLOWMO_MS")
        profile_strategy = env_str("PROFILE_STRATEGY", "shared").lower()
        if profile_strategy not in {"shared", "per-platform"}:
            raise ValueError("PROFILE_STRATEGY must be 'shared' or 'per-platform'.")
        shared_profile_raw = env_str("SHARED_PROFILE_DIR", "data/profiles/shared")
        shared_profile_dir = Path(shared_profile_raw)
        if not shared_profile_dir.is_absolute():
            shared_profile_dir = PROJECT_ROOT / shared_profile_dir
        policies_raw = env_str("CONTENT_POLICIES_FILE")
        content_policies_file = Path(policies_raw) if policies_raw else None
        if content_policies_file is not None and not content_policies_file.is_absolute():
            content_policies_file = PROJECT_ROOT / content_policies_file
        return cls(
            youtube_handle=normalize_youtube_handle(env_str("YOUTUBE_HANDLE")),
            youtube_metadata_lang=env_str("YOUTUBE_METADATA_LANG"),
            download_dir=DOWNLOAD_DIR,
            profiles_dir=PROFILES_DIR,
            runs_dir=RUNS_DIR,
            target_platforms=parse_platform_list(platform_env),
            post_text_mode=post_text_mode,
            shorts_selection_mode=shorts_selection_mode,
            shorts_upload_limit=env_optional_positive_int("SHORTS_UPLOAD_LIMIT", 1),
            shorts_lookback_limit=env_positive_int("SHORTS_LOOKBACK_LIMIT", 50),
            shorts_skip_ads=env_bool("SHORTS_SKIP_ADS", True),
            content_policies_file=content_policies_file,
            chrome_channel=env_str("CHROME_CHANNEL", "chrome"),
            uploader_headless=env_bool("UPLOADER_HEADLESS", False),
            uploader_slowmo_ms=int(slowmo) if slowmo else 80,
            profile_strategy=profile_strategy,
            shared_profile_dir=shared_profile_dir,
            instagram_handle=env_str("INSTAGRAM_HANDLE").lstrip("@"),
            threads_handle=env_str("THREADS_HANDLE").lstrip("@"),
            tiktok_handle=env_str("TIKTOK_HANDLE").lstrip("@"),
            linkedin_recent_activity_url=env_str("LINKEDIN_RECENT_ACTIVITY_URL"),
            facebook_videos_url=env_str("FACEBOOK_VIDEOS_URL"),
            facebook_page_name=env_str("FACEBOOK_PAGE_NAME"),
            naver_channel_slug=env_str("NAVER_CHANNEL_SLUG"),
            naver_clip_url=env_str("NAVER_CLIP_URL"),
            naver_category_1=env_str("NAVER_CATEGORY_1"),
            naver_category_2=env_str("NAVER_CATEGORY_2"),
        )

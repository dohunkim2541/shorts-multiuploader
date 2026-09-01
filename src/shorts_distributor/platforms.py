from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_PLATFORM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True)
class PlatformSpec:
    id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    optional_env: tuple[str, ...] = ()


SUPPORTED_PLATFORMS: tuple[PlatformSpec, ...] = (
    PlatformSpec(
        id="instagram",
        display_name="Instagram",
        aliases=("ig",),
        required_env=("INSTAGRAM_HANDLE",),
    ),
    PlatformSpec(
        id="threads",
        display_name="Threads",
        aliases=("threadsnet",),
        optional_env=("THREADS_HANDLE", "INSTAGRAM_HANDLE"),
    ),
    PlatformSpec(
        id="tiktok",
        display_name="TikTok",
        aliases=("tt",),
        optional_env=("TIKTOK_HANDLE",),
    ),
    PlatformSpec(
        id="linkedin",
        display_name="LinkedIn",
        aliases=("li",),
        optional_env=("LINKEDIN_RECENT_ACTIVITY_URL",),
    ),
    PlatformSpec(
        id="facebook",
        display_name="Facebook",
        aliases=("fb",),
        optional_env=("FACEBOOK_VIDEOS_URL",),
    ),
    PlatformSpec(
        id="naver",
        display_name="Naver Clip",
        aliases=("naverclip", "naver-clip"),
        optional_env=(
            "NAVER_CHANNEL_SLUG",
            "NAVER_DASHBOARD_URL",
            "NAVER_CLIP_URL",
            "NAVER_CATEGORY_1",
            "NAVER_CATEGORY_2",
        ),
    ),
)

SUPPORTED_PLATFORM_IDS = tuple(spec.id for spec in SUPPORTED_PLATFORMS)
DEFAULT_TARGET_PLATFORMS = SUPPORTED_PLATFORM_IDS

_SPECS_BY_ID = {spec.id: spec for spec in SUPPORTED_PLATFORMS}
_ALIASES = {
    alias: spec.id
    for spec in SUPPORTED_PLATFORMS
    for alias in (spec.id, *spec.aliases)
}


def normalize_platform_id(raw: str) -> str:
    platform = raw.strip().lower()
    platform = _ALIASES.get(platform, platform)
    if not _PLATFORM_ID_RE.fullmatch(platform):
        msg = (
            f"Invalid platform id {raw!r}. Use lowercase letters, numbers, "
            "hyphens, or underscores, starting with a letter."
        )
        raise ValueError(msg)
    return platform


def parse_platform_list(
    raw: str | None,
    *,
    default: tuple[str, ...] = DEFAULT_TARGET_PLATFORMS,
) -> list[str]:
    if raw is None or not raw.strip():
        return list(default)

    pieces = re.split(r"[\s,]+", raw.strip())
    normalized: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        if not piece:
            continue
        if piece.lower() == "all":
            return list(default)
        platform = normalize_platform_id(piece)
        if platform not in seen:
            normalized.append(platform)
            seen.add(platform)
    return normalized


def platform_display_name(platform: str) -> str:
    normalized = normalize_platform_id(platform)
    spec = _SPECS_BY_ID.get(normalized)
    return spec.display_name if spec else normalized


def is_supported_platform(platform: str) -> bool:
    return normalize_platform_id(platform) in _SPECS_BY_ID


def supported_platforms_as_dicts() -> list[dict]:
    return [asdict(spec) for spec in SUPPORTED_PLATFORMS]

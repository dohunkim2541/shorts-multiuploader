from __future__ import annotations

import re

from .youtube import VideoMeta

_MAX_DEFAULT = 2000  # TikTok 캡션 상한 기준
_HASHTAG_RE = re.compile(r"#[A-Za-z0-9_가-힣]+")


def shorten(text: str, limit: int) -> str:
    """플랫폼 글자수 제한 축약. 잘릴 때만 말줄임표를 붙인다."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_caption(meta: VideoMeta, max_len: int = _MAX_DEFAULT) -> str:
    """플랫폼 공통 캡션. 제목 + 본문 해시태그 + 메타 태그."""
    parts: list[str] = []
    if meta.title:
        parts.append(meta.title)

    hashtags_in_desc = _HASHTAG_RE.findall(meta.description)
    tag_set = {h.lower() for h in hashtags_in_desc}
    for t in meta.tags[:8]:
        slug = "#" + re.sub(r"\s+", "", t)
        if slug.lower() not in tag_set:
            hashtags_in_desc.append(slug)
            tag_set.add(slug.lower())

    if hashtags_in_desc:
        parts.append(" ".join(hashtags_in_desc))

    return shorten("\n\n".join(parts).strip(), max_len)

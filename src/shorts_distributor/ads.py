"""광고/협찬 의심 마커 감지.

기본 마커는 한국어/영어 공통 표기를 다루고, 다른 언어/커스텀 표기는 `.env`의
`AD_MARKERS_EXTRA`(쉼표 구분)로 추가한다.
"""

from __future__ import annotations

import os

AD_MARKERS = (
    "#광고",
    "#ad",
    "#sponsored",
    "유료광고",
    "유료 광고",
    "유료광고포함",
    "협찬",
    "sponsored",
    "paid promotion",
    "paid partnership",
    "경제적 대가",
)


def _configured_markers() -> tuple[str, ...]:
    extra = os.getenv("AD_MARKERS_EXTRA", "")
    additional = tuple(m.strip() for m in extra.split(",") if m.strip())
    return AD_MARKERS + additional


def detect_ad_markers(*texts: str | None) -> list[str]:
    haystack = "\n".join(t or "" for t in texts).casefold()
    return [marker for marker in _configured_markers() if marker.casefold() in haystack]

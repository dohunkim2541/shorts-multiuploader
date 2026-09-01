"""플랫폼 업로더 레지스트리.

각 플랫폼 모듈은 다음 계약을 지킨다:
  - LOGIN_URL: str — `shorts-dist login` 이 여는 로그인 페이지.
  - upload(page, job, steps, cfg) -> Outcome
  - verify(page, job, steps, cfg) -> VerifyOutcome

레지스트리에 없는 커스텀 플랫폼 ID 는 코드 업로드 대상이 아니며, 러너가
`agent-required` 셀로 분류해 에이전트(browser-use/computer-use)에 인계한다.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

CODE_UPLOAD_PLATFORMS: tuple[str, ...] = (
    "instagram",
    "threads",
    "tiktok",
    "linkedin",
    "facebook",
    "naver",
)


def get_uploader(platform: str) -> ModuleType | None:
    if platform not in CODE_UPLOAD_PLATFORMS:
        return None
    return import_module(f".{platform}", __package__)

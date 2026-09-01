"""Facebook Reels 업로드/검증.

주의(레퍼런스 failure-modes 9, 10, 21):
  - reels/create 는 `현재 활성 프로필`로 게시된다. 페이지(Page) 운영 계정이라면
    FACEBOOK_PAGE_NAME 을 설정해 두면 활성 프로필 불일치 시 업로드 전에 중단한다.
  - `/me/`는 최신 1개만 보일 수 있어 검증은 FACEBOOK_VIDEOS_URL 기준.
  - 제목이 `내 릴스` 같은 기본값으로 게시된 경우는 성공이 아니다(잘못된 텍스트).
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from ..caption import shorten
from .base import (
    Job,
    Outcome,
    StepFailure,
    Steps,
    VerifyOutcome,
    click_first,
    click_optional,
    fill_editor_exact,
    file_input_anywhere,
    first_match,
    norm_text,
    require_no_login_redirect,
)

LOGIN_URL = "https://www.facebook.com/login"
CREATE_URL = "https://www.facebook.com/reels/create"
CAPTION_LIMIT = 3_000
_LOGIN_REDIRECTS = ("/login", "checkpoint")

_NEXT = (
    'div[role="button"]:has-text("다음")',
    'role=button[name="다음"]',
    'role=button[name="Next"]',
)
_DESCRIPTION = (
    'div[role="textbox"][contenteditable="true"]',
    'div[aria-label*="설명"][role="textbox"]',
    'div[aria-label*="description" i][role="textbox"]',
)
_PUBLISH = (
    'div[role="button"]:text-is("게시")',
    'div[role="button"]:has-text("공유하기")',
    'role=button[name="공유하기"]',
    'role=button[name="게시"]',
    'role=button[name="Share"]',
    'role=button[name="Publish"]',
)
_BACK = (
    'div[aria-label="뒤로"]',
    '[aria-label="뒤로 가기"]',
    '[aria-label="Back"]',
)
_SUCCESS = (
    'text=/릴스를 공유했습니다|공유되었습니다|공유됨|게시됨/',
    'text=/reel was shared|has been shared/i',
)
# 주의: :has-text("계속") 는 세 버튼(계속/다른 프로필/새 계정)을 감싸는 카드
# 컨테이너(role=button)까지 매치해 중앙 클릭이 `다른 프로필 사용하기`에 떨어진다
# (실측). aria-label(`계속 <이름>`) 정밀 타겟을 최우선으로 쓴다.
_GATE_CONTINUE = (
    '[aria-label^="계속"]',
    '[aria-label^="Continue as"]',
    'div[role="button"]:text-is("계속")',
    'div[role="button"]:text-is("Continue")',
)


def _ensure_page_actor(page: Page, cfg) -> None:
    """FACEBOOK_PAGE_NAME 이 설정돼 있으면 대상 페이지 프로필로 전환한다.

    개인 프로필이 활성인 상태로 릴스를 올리면 개인 계정에 게시된다(실사고).
    페이지 방문 시 뜨는 `Switch Profiles to Manage this Page` 배너의
    전환 버튼을 눌러 페이지 컨텍스트로 바꾼 뒤 진행한다.
    """
    if not cfg.facebook_page_name or not cfg.facebook_videos_url:
        return
    page.goto(cfg.facebook_videos_url, wait_until="domcontentloaded")
    page.wait_for_timeout(5_000)

    def _needs_switch() -> bool:
        body = norm_text(page.locator("body").inner_text()[:25_000])
        return "Switch Profiles to Manage" in body or "페이지로 전환" in body

    if not _needs_switch():
        return  # 이미 페이지 컨텍스트
    for attempt in range(2):
        clicked = click_optional(page, (
            'div[role="button"]:has-text("프로필 전환")',
            '[role="button"]:text-is("전환")',
            'div[role="button"]:text-is("전환")',
            '[aria-label="프로필 전환"]',
        ), timeout_ms=6_000)
        if clicked:
            page.wait_for_timeout(6_000)
            page.goto(cfg.facebook_videos_url, wait_until="domcontentloaded")
            page.wait_for_timeout(5_000)
        if not _needs_switch():
            return
    raise StepFailure(
        "actor-switch",
        f"페이지 프로필({cfg.facebook_page_name}) 전환을 확정하지 못했습니다.",
        hint="개인 프로필로 게시될 위험 — 에이전트/수동으로 페이지 전환 후 재시도.",
        blocker=True,
    )


def _pass_profile_gate_or_wait_ready(page: Page, *, max_wait_s: int = 45) -> None:
    """세션 재확인 게이트(`~님으로 계속`)를 통과하거나 업로드 화면 준비를 기다린다.

    게이트는 goto 후 늦게 렌더링될 수 있어 폴링으로 처리한다. `계속` 클릭 후에는
    리다이렉트 체인이 도는데, 곧바로 goto 로 끊으면 게이트로 되돌아간다(실측) —
    내비게이션이 잦아들 때까지 기다린 뒤에만 목적지로 이동한다. 비밀번호 화면이
    나오거나 게이트가 반복되면 진짜 재로그인 케이스로 blocker 처리한다.
    """
    deadline = time.monotonic() + max_wait_s
    gate_clicks = 0
    while time.monotonic() < deadline:
        try:
            if page.locator('input[type="file"]').count():
                return  # 업로드 화면 준비됨
        except Exception:
            pass
        try:
            if page.locator('input[type="password"]').first.is_visible():
                raise StepFailure(
                    "open",
                    "Facebook 이 비밀번호 재입력을 요구합니다.",
                    hint="`uv run shorts-dist login facebook` 으로 재로그인 후 다시 실행하세요.",
                    blocker=True,
                )
        except StepFailure:
            raise
        except Exception:
            pass
        is_gate = False
        try:
            is_gate = page.get_by_text("다른 프로필 사용하기").first.is_visible()
        except Exception:
            pass
        if is_gate:
            if gate_clicks >= 2:
                raise StepFailure(
                    "open",
                    "프로필 `계속` 게이트가 반복됩니다(세션 복원 실패).",
                    hint="`uv run shorts-dist login facebook` 으로 세션을 갱신하세요.",
                    blocker=True,
                )
            if click_optional(page, _GATE_CONTINUE, timeout_ms=4_000):
                gate_clicks += 1
                # 리다이렉트 체인을 끊지 않도록 로드가 잦아들 때까지 대기
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    page.wait_for_timeout(5_000)
                if "reels/create" not in page.url:
                    page.goto(CREATE_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(3_000)
                continue
        page.wait_for_timeout(2_000)


def upload(page: Page, job: Job, steps: Steps, cfg) -> Outcome:
    posted_text = shorten(job.post_text, CAPTION_LIMIT)

    with steps.step("open", hint="페이지 프로필 전환 → reels/create 접속(게이트 자동 통과)"):
        # 릴스는 활성 프로필로 게시된다(failure-mode #10). 개인 프로필 상태로
        # 게시된 실사고가 있어, 페이지 운영 계정이면 먼저 페이지로 전환한다.
        _ensure_page_actor(page, cfg)
        page.goto(CREATE_URL, wait_until="domcontentloaded")
        _pass_profile_gate_or_wait_ready(page)
        require_no_login_redirect(page, _LOGIN_REDIRECTS, "facebook")

    # 액터 보장은 open 단계의 _ensure_page_actor(배너 소멸 확인)가 담당한다.
    # 컴포저 화면에는 액터 이름이 텍스트로 없을 수 있어(실측: 아바타 이미지뿐)
    # 여기서 이름 텍스트를 하드 가드로 쓰면 false blocker 가 난다.

    with steps.step("attach", hint="동영상 파일 지정"):
        file_input_anywhere(page, timeout_ms=30_000).set_input_files(str(job.file_path))

    with steps.step("compose-walk", hint="화면 순서를 가정하지 않는다 — 설명 보이면 입력, 게시 보이면 종료, 아니면 다음"):
        # 실측: 다음 2회 고정 클릭은 설명 화면을 지나쳐 릴스 설정까지 가버린다.
        filled = False
        publish_seen = False
        for _ in range(8):
            if not filled:
                try:
                    editor = first_match(page, _DESCRIPTION, timeout_ms=3_000)
                    fill_editor_exact(page, editor, posted_text)
                    filled = True
                except StepFailure:
                    raise
                except Exception:
                    pass
            try:
                first_match(page, _PUBLISH, timeout_ms=2_000)
                publish_seen = True
                if filled:
                    break
                # 설명 없이 게시 화면에 도달 — 한 화면 뒤로 가서 설명을 찾는다.
                if not click_optional(page, _BACK, timeout_ms=3_000):
                    break
                page.wait_for_timeout(1_500)
                continue
            except Exception:
                pass
            if not click_optional(page, _NEXT, timeout_ms=8_000):
                page.wait_for_timeout(1_500)
        if not filled:
            raise StepFailure(
                "compose-walk",
                "설명 입력 화면을 찾지 못했습니다(기본 제목 게시 금지 규칙).",
                hint="에이전트가 화면에서 설명 필드 위치를 확인해 selector 를 갱신해야 함."
                + (" 게시 화면까지는 도달함." if publish_seen else ""),
            )

    with steps.step("publish"):
        click_first(page, _PUBLISH)

    with steps.step("confirm", hint="공유 완료 문구 대기 — 타임아웃이면 verify 로 판정"):
        try:
            first_match(page, _SUCCESS, timeout_ms=240_000)
            evidence = "공유 완료 안내 확인"
        except Exception as exc:
            raise StepFailure(
                "confirm",
                "공유 완료 문구를 확인하지 못함(게시됐을 수 있음)",
                hint="FACEBOOK_VIDEOS_URL 기준 verify 로 판정하세요. `/me/`는 근거가 아님.",
            ) from exc

    return Outcome("published", posted_text=posted_text, evidence=evidence)


def verify(page: Page, job: Job, steps: Steps, cfg) -> VerifyOutcome:
    """FACEBOOK_VIDEOS_URL 목록에서 제목 대조. 그리드가 캡션을 숨기면 상위 릴스를 연다."""
    url = cfg.facebook_videos_url
    if not url:
        return VerifyOutcome("inconclusive", evidence="FACEBOOK_VIDEOS_URL 미설정")
    needle = norm_text(job.title_text)[:40]

    with steps.step("verify-open"):
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4_000)
        require_no_login_redirect(page, _LOGIN_REDIRECTS, "facebook")

    with steps.step("verify-scan", hint="목록 텍스트 → 상위 릴스 개별 확인 순서"):
        body_text = norm_text(page.locator("body").inner_text()[:30_000])
        if needle and needle in body_text:
            return VerifyOutcome("verified", evidence="동영상 탭에서 제목 일치")
        anchors = page.locator('a[href*="/reel/"]')
        for i in range(min(anchors.count(), 3)):
            href = anchors.nth(i).get_attribute("href")
            if not href:
                continue
            page.goto(href if href.startswith("http") else f"https://www.facebook.com{href}", wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
            reel_text = norm_text(page.locator("body").inner_text()[:20_000])
            if needle and needle in reel_text:
                return VerifyOutcome("verified", url=page.url, evidence="상위 릴스에서 제목 일치")
        return VerifyOutcome(
            "inconclusive",
            evidence="목록/상위 릴스에서 제목 미발견 — 에이전트 확인 필요(그리드가 캡션을 숨길 수 있음)",
            artifacts=steps.capture("verify-miss"),
        )

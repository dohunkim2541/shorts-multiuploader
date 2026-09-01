"""Threads 업로드/검증.

주의(레퍼런스 failure-modes 8):
  - 프로필 피드는 같은 세션의 이전 게시물을 숨길 수 있어 검증 진실원이 아니다.
    검증은 Threads 검색(`/search?q=...`)으로 한다. 피드 부재만으로 재업로드 금지.
  - 글자수 제한 500자 — 캡션을 축약해 게시하고 실제 게시 텍스트를 기록한다.
  - 홈 피드 상단에 인라인 컴포저(자체 게시 버튼 포함)가 따로 있다. 만들기로 연
    작성 패널(role=dialog)에 텍스트박스/파일입력/게시 버튼을 전부 스코핑해서
    인라인 컴포저와 절대 섞이지 않게 한다(실측 사고 예방).
"""

from __future__ import annotations

import time
from urllib.parse import quote, urljoin

from playwright.sync_api import Page

from ..caption import shorten
from .base import (
    Job,
    Outcome,
    StepFailure,
    Steps,
    VerifyOutcome,
    click_first,
    fill_editor_exact,
    first_match,
    norm_text,
    require_no_login_redirect,
    wait_enabled,
)

LOGIN_URL = "https://www.threads.com/login"
HOME_URL = "https://www.threads.com/"
CAPTION_LIMIT = 500
_LOGIN_REDIRECTS = ("/login", "accounts/login")

_CREATE = (
    'div[role="button"]:has(svg[aria-label="새로운 스레드"])',
    'a:has(svg[aria-label="새로운 스레드"])',
    'div[role="button"]:has(svg[aria-label="만들기"])',
    'a:has(svg[aria-label="만들기"])',
    'div[role="button"]:has(svg[aria-label="New thread"])',
    'div[role="button"]:has(svg[aria-label="Create"])',
    'role=button[name="새로운 스레드"]',
    'role=button[name="만들기"]',
    'role=button[name="Create"]',
)
_TEXTBOX = (
    'div[role="textbox"][contenteditable="true"]',
    '[contenteditable="true"]',
)
# 작성 패널은 role=dialog 가 아니다(실측 count 0). 유일한 contenteditable
# 텍스트박스를 앵커로 잡고, 파일입력+게시 버튼을 모두 포함하는 최근접 조상을
# 패널로 역산해서 인라인 피드 컴포저와 절대 섞이지 않게 한다.
_PANEL_FROM_EDITOR = (
    'xpath=ancestor::*[.//input[@type="file"] and .//div[@role="button"][contains(normalize-space(.), "게시") or contains(normalize-space(.), "Post")]][1]'
)
_ATTACHED_PREVIEW = ("video", 'img[src^="blob:"]')
_POST = (
    'div[role="button"]:text-is("게시")',
    'div[role="button"]:has-text("게시")',
    'div[role="button"]:text-is("Post")',
    'role=button[name="게시"]',
    'role=button[name="Post"]',
)
_TOAST_POST_LINK = 'a[href*="/post/"]'


def upload(page: Page, job: Job, steps: Steps, cfg) -> Outcome:
    posted_text = shorten(job.post_text, CAPTION_LIMIT)

    with steps.step("open", hint="threads.com 접속 및 로그인 상태 확인"):
        page.goto(HOME_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2_500)
        require_no_login_redirect(page, _LOGIN_REDIRECTS, "threads")

    with steps.step("composer", hint="새로운 스레드 버튼 → 작성 패널의 텍스트박스 대기"):
        click_first(page, _CREATE)
        editor = first_match(page, _TEXTBOX, timeout_ms=15_000)
        panel = editor.locator(_PANEL_FROM_EDITOR)
        if panel.count() == 0:
            # 패널 역산 실패 — 페이지 전역 폴백(게시 버튼은 에디터 인접 우선순위 상실)
            panel = None

    with steps.step("caption", hint="작성 패널 본문 입력 — 인라인 피드 컴포저와 혼동 금지"):
        fill_editor_exact(page, editor, posted_text)

    with steps.step("attach", hint="작성 패널 파일 입력에 첨부 후 미리보기 대기"):
        file_input = first_match(page, ('input[type="file"]',), scope=panel, state="attached", timeout_ms=15_000)
        file_input.set_input_files(str(job.file_path))
        first_match(page, _ATTACHED_PREVIEW, scope=panel, timeout_ms=120_000)

    with steps.step("post", hint="작성 패널 게시 버튼(활성화 대기 후 클릭)"):
        handle = (cfg.threads_handle or cfg.instagram_handle or "").lstrip("@")
        button = first_match(page, _POST, scope=panel)
        wait_enabled(page, button, timeout_ms=60_000)
        # 새 게시물 판별 기준선: 클릭 전에 화면에 있던 본인 /post/ 코드들.
        known_codes = _own_post_codes(page, handle)
        button.click()

    with steps.step("confirm", hint="동영상 게시는 비동기 — 완료 증거 전에 페이지를 닫으면 게시가 중단된다(실측 사고)"):
        # 주의 1: 배경 피드에도 a[href*="/post/"] 가 가득하다. 본인 핸들 필터 없이
        # 링크를 집으면 남의 게시물 URL 로 성공 오판 → 페이지를 닫아 진행 중이던
        # 게시가 중단된다(실측: 2건 유실). 본인 핸들 토스트만 완료 증거로 인정.
        # 주의 2: `게시 중` 표시가 보이는 동안은 계속 기다린다.
        post_url = None
        saw_posting = False
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            for href in _own_post_hrefs(page, handle):
                code = href.split("/post/")[-1].split("/")[0]
                if code and code not in known_codes:
                    post_url = urljoin(HOME_URL, href)
                    break
            if post_url:
                break
            try:
                if page.locator('text=/게시 중|Posting/').first.is_visible():
                    saw_posting = True
            except Exception:
                pass
            page.wait_for_timeout(1_500)

        if not post_url:
            # 마지막 자가 확인: 본인 프로필에서 캡션 직접 대조(피드 quirk 대비 media 탭 포함).
            for path in (f"/@{handle}", f"/@{handle}/media"):
                page.goto(urljoin(HOME_URL, path), wait_until="domcontentloaded")
                page.wait_for_timeout(6_000)
                if norm_text(posted_text)[:40] in norm_text(page.locator("body").inner_text()[:20_000]):
                    post_url = None  # URL 은 못 얻어도 게시 확인
                    return Outcome("published", posted_text=posted_text,
                                   evidence="프로필에서 캡션 확인(토스트 미캡처)")
            raise StepFailure(
                "confirm",
                "게시 완료 증거 없음(본인 토스트/프로필/미디어 탭 모두 미발견)"
                + (" — 게시 중 표시는 관측됨" if saw_posting else ""),
                hint="게시가 실제로 완료되지 않았을 가능성이 큼 — 재실행하거나 에이전트로 화면 확인.",
            )

    return Outcome(
        "published",
        post_url=post_url,
        posted_text=posted_text,
        evidence="본인 계정 새 게시물 링크 확인",
    )


def _own_post_hrefs(page: Page, handle: str) -> list[str]:
    hrefs: list[str] = []
    links = page.locator(_TOAST_POST_LINK)
    try:
        count = min(links.count(), 30)
    except Exception:
        return hrefs
    for i in range(count):
        try:
            href = links.nth(i).get_attribute("href") or ""
        except Exception:
            continue
        if handle and f"/@{handle}/post/" in href:
            hrefs.append(href)
    return hrefs


def _own_post_codes(page: Page, handle: str) -> set[str]:
    return {h.split("/post/")[-1].split("/")[0] for h in _own_post_hrefs(page, handle)}


def verify(page: Page, job: Job, steps: Steps, cfg) -> VerifyOutcome:
    """Threads 검색이 유일한 신뢰 가능한 진실원(프로필 피드는 숨김 quirk 존재)."""
    handle = cfg.threads_handle or cfg.instagram_handle
    needle = norm_text(shorten(job.post_text, CAPTION_LIMIT))[:40]
    if not needle:
        return VerifyOutcome("inconclusive", evidence="검색어로 쓸 캡션이 없음")

    with steps.step("verify-search", hint="Threads 검색으로 게시물 확인(피드 부재는 판정 근거 아님)"):
        # 게시 직후에는 검색 색인이 늦다 — 한 번은 기다렸다 재시도한다.
        for attempt, wait_ms in enumerate((0, 45_000)):
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            page.goto(
                f"https://www.threads.com/search?q={quote(needle)}&serp_type=default",
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(7_000)
            require_no_login_redirect(page, _LOGIN_REDIRECTS, "threads")
            links = page.locator(_TOAST_POST_LINK)
            count = min(links.count(), 10)
            for i in range(count):
                href = links.nth(i).get_attribute("href") or ""
                if handle and f"/@{handle.lstrip('@')}/" not in href:
                    continue
                return VerifyOutcome("verified", url=urljoin(HOME_URL, href), evidence="검색 결과에서 본인 계정 게시물 일치")
        return VerifyOutcome(
            "missing" if count else "inconclusive",
            evidence="검색(재시도 포함)에서 본인 계정 게시물 미발견 — 색인 지연 가능, 재업로드 전 에이전트 교차확인 필수",
            artifacts=steps.capture("verify-miss"),
        )

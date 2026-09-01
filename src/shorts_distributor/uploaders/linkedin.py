"""LinkedIn 게시물(동영상) 업로드/검증.

주의(레퍼런스 failure-modes 11, 19):
  - 본문 에디터(Quill)가 shadow DOM 안에 있을 수 있다. Playwright 셀렉터는 열린
    shadow root 를 자동 관통하고, insert_text 는 CDP 입력이라 함께 안전하다.
  - 성공 토스트가 누락되는 false negative 가 잦다(120s 타임아웃 사례). confirm
    타임아웃은 실패 확정이 아니라 verify 로 판정한다 — 러너가 자동으로 수행.
"""

from __future__ import annotations

from urllib.parse import urljoin

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

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
    first_match,
    norm_text,
    require_no_login_redirect,
)

LOGIN_URL = "https://www.linkedin.com/login"
FEED_URL = "https://www.linkedin.com/feed/"
CAPTION_LIMIT = 2_900
_LOGIN_REDIRECTS = ("/login", "authwall", "checkpoint")

# 신형 홈 UI(2026-07 실측): 해시 클래스 + componentkey 로 재구축됐고, 글 올리기
# 박스와 동영상/사진/글쓰기 퀵 버튼이 전부 <a> 앵커다(button/role=button 아님).
# 동영상 버튼 직행이 가장 짧은 경로 — 파일 선택 흐름이 바로 열린다.
_VIDEO_QUICK = (
    'a:has(p:text-is("동영상"))',
    'button:has-text("동영상")',
    'div[role="button"]:has-text("동영상")',
    'a:has(p:text-is("Video"))',
    'button:has-text("Video")',
)
_TRIGGER = (
    'a[aria-label="글 올리기"]',
    'a[href*="/preload/sharebox"]',
    "button.share-box-feed-entry__trigger",
    'role=button[name=/글쓰기|게시물 작성|글 쓰기|글 올리기|Start a post/]',
    'a:has(p:text-is("글쓰기"))',
    'button:has-text("Start a post")',
)
_MEDIA_BUTTON = (
    'button[aria-label*="미디어"]',
    'button[aria-label*="동영상"]',
    'a:has(p:text-is("동영상"))',
    'button[aria-label*="media" i]',
    'button[aria-label*="video" i]',
    'role=button[name=/미디어|동영상|Add media|Video/]',
)
_DIALOG = ('div[role="dialog"]', 'dialog', '[aria-modal="true"]')
_FILE_INPUT = (
    'input[type="file"][accept*="video" i]',
    'input[type="file"][accept*=".mp4" i]',
    'input[type="file"]',
)
_UPLOAD_FROM_COMPUTER = (
    'button:text-is("컴퓨터에서 업로드")',
    'button:text-is("Upload from computer")',
    'button:has(p:text-is("컴퓨터에서 업로드"))',
    'button:has(p:text-is("Upload from computer"))',
    'role=button[name="컴퓨터에서 업로드"]',
    'role=button[name="Upload from computer"]',
)
_NEXT = (
    # 배경 피드 캐러셀에도 aria-label="다음"이 있다. 미디어 편집기의
    # 텍스트 버튼을 먼저 찾아 오버레이 뒤의 캐러셀을 클릭하지 않게 한다.
    'button:text-is("다음")',
    'button:text-is("Next")',
    'button:has(p:text-is("다음"))',
    'button:has(p:text-is("Next"))',
    'role=button[name="다음"]',
    'button:has-text("다음")',
    'a:has(p:text-is("다음"))',
    '[role="button"]:has-text("다음")',
    'role=button[name="Next"]',
)
_EDITOR = (
    'div.ql-editor[contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
    'div[contenteditable="true"]',
)
_POST = (
    "button.share-actions__primary-action",
    'role=button[name="게시"]',
    'button:has-text("게시")',
    'a:has(p:text-is("게시"))',
    '[role="button"]:text-is("게시")',
    'role=button[name="Post"]',
)
_SUCCESS_LINK = 'a[href*="/feed/update/"]'
_SUCCESS = (
    'a:has-text("게시물 보기")',
    'a:has-text("View post")',
    'text=/게시되었습니다|게시물이 올라갔습니다|post was shared|Post successful/i',
)


def upload(page: Page, job: Job, steps: Steps, cfg) -> Outcome:
    posted_text = shorten(job.post_text, CAPTION_LIMIT)

    with steps.step("open", hint="linkedin.com/feed 접속 및 로그인 확인"):
        page.goto(FEED_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3_000)
        require_no_login_redirect(page, _LOGIN_REDIRECTS, "linkedin")

    with steps.step("composer", hint="동영상 퀵 버튼 직행(신형 홈), 실패 시 글 올리기→미디어 버튼 폴백"):
        video_direct = click_optional(page, _VIDEO_QUICK, timeout_ms=8_000)
        if not video_direct:
            click_first(page, _TRIGGER)
            click_first(page, _MEDIA_BUTTON, timeout_ms=15_000)
        dialog = first_match(page, _DIALOG, timeout_ms=15_000)

    with steps.step("attach", hint="파일 지정 → 미디어 편집 다음"):
        try:
            upload_button = first_match(
                page,
                _UPLOAD_FROM_COMPUTER,
                scope=dialog,
                timeout_ms=3_000,
            )
        except PlaywrightTimeout:
            upload_button = None

        if upload_button is not None:
            try:
                with page.expect_file_chooser(timeout=10_000) as chooser_info:
                    upload_button.click()
                chooser_info.value.set_files(str(job.file_path))
            except PlaywrightTimeout:
                upload_button = None

        if upload_button is None:
            file_input = first_match(
                page,
                _FILE_INPUT,
                scope=dialog,
                timeout_ms=15_000,
                state="attached",
            )
            file_input.set_input_files(str(job.file_path))
        # 미디어 편집 화면이 뜨면 다음으로 본문 작성 모달 복귀.
        advanced = click_optional(page, _NEXT, scope=dialog, timeout_ms=60_000)
        if not advanced:
            # 일부 UI 는 편집 화면을 생략한다. 본문 에디터도 없다면 attach 단계에서
            # 실패시켜 미디어 편집 화면을 caption 실패로 오인하지 않게 한다.
            first_match(page, _EDITOR, scope=dialog, timeout_ms=5_000)

    with steps.step("caption", hint="Quill 본문(shadow DOM 가능) — 빈 본문으로 게시 금지"):
        editor = first_match(page, _EDITOR, scope=dialog, timeout_ms=30_000)
        fill_editor_exact(page, editor, posted_text)

    with steps.step("post"):
        click_first(page, _POST, scope=dialog)

    with steps.step("confirm", hint="LinkedIn 은 성공 토스트 누락이 잦음 — 타임아웃이면 verify 로 판정"):
        post_url = None
        try:
            first_match(page, _SUCCESS, timeout_ms=120_000)
            link = page.locator(_SUCCESS_LINK).first
            if link.count():
                href = link.get_attribute("href")
                if href:
                    post_url = urljoin(FEED_URL, href)
            evidence = "성공 토스트 확인"
        except Exception as exc:
            raise StepFailure(
                "confirm",
                "성공 토스트를 확인하지 못함(게시 자체는 됐을 수 있음)",
                hint="false negative 로 알려진 패턴 — verify(recent-activity)로 판정하세요. 무턱대고 재업로드 금지.",
            ) from exc

    return Outcome("published", post_url=post_url, posted_text=posted_text, evidence=evidence)


def verify(page: Page, job: Job, steps: Steps, cfg) -> VerifyOutcome:
    """LINKEDIN_RECENT_ACTIVITY_URL(로그인 자기 뷰)의 최근 게시물 본문 대조."""
    url = cfg.linkedin_recent_activity_url
    if not url:
        return VerifyOutcome("inconclusive", evidence="LINKEDIN_RECENT_ACTIVITY_URL 미설정")
    needle = norm_text(job.title_text)[:50]

    with steps.step("verify-open"):
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4_000)
        require_no_login_redirect(page, _LOGIN_REDIRECTS, "linkedin")

    with steps.step("verify-scan"):
        main_text = norm_text(page.locator("main").inner_text()[:30_000])
        if needle and needle in main_text:
            post_url = None
            link = page.locator(_SUCCESS_LINK).first
            if link.count():
                href = link.get_attribute("href")
                if href:
                    post_url = urljoin(FEED_URL, href)
            return VerifyOutcome("verified", url=post_url, evidence="recent-activity 에서 본문 일치")
        return VerifyOutcome(
            "missing",
            evidence="recent-activity 에 본문 없음(게시 직후 수 초 내 노출이 정상)",
            artifacts=steps.capture("verify-miss"),
        )

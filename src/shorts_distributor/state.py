"""
업로드 상태 추적용 SQLite. 플랫폼별 `(youtube_id, platform)` 고유키.

의도:
  - 채널 전체 숏폼 대상 → 어떤 걸 이미 올렸는지 로컬에서만 판단
  - source 컬럼으로 기록 경로 구분: script(코드 업로드) / agent / manual
  - verified_at 은 게시 후 검증 통과 시각. NULL 이면 검증 대기 상태다.
  - platform_url 에는 실제 게시물 URL 만 기록한다. 루트 URL(placeholder)을
    기록하면 이후 검증 로직이 오판한다(과거 실사고).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator
from urllib.parse import urlparse

from .config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
  youtube_id   TEXT NOT NULL,
  platform     TEXT NOT NULL,
  uploaded_at  TEXT NOT NULL,
  platform_url TEXT,
  caption      TEXT,
  source       TEXT NOT NULL DEFAULT 'manual',
  PRIMARY KEY (youtube_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_uploads_platform ON uploads(platform);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    try:
        c.executescript(_SCHEMA)
        _migrate(c)
        yield c
        c.commit()
    finally:
        c.close()


def _migrate(c: sqlite3.Connection) -> None:
    columns = {row[1] for row in c.execute("PRAGMA table_info(uploads)")}
    if "verified_at" not in columns:
        c.execute("ALTER TABLE uploads ADD COLUMN verified_at TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_url(url: str | None) -> str | None:
    """루트 URL placeholder 기록 방지 — 경로 없는 URL 은 버린다."""
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        return None
    return url


def mark_uploaded(
    youtube_id: str,
    platform: str,
    *,
    platform_url: str | None = None,
    caption: str | None = None,
    source: str = "manual",
    verified: bool = False,
) -> None:
    now = _now()
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO uploads "
            "(youtube_id, platform, uploaded_at, platform_url, caption, source, verified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (youtube_id, platform, now, _clean_url(platform_url), caption, source, now if verified else None),
        )


def mark_verified(youtube_id: str, platform: str, *, platform_url: str | None = None) -> None:
    with _conn() as c:
        if _clean_url(platform_url):
            c.execute(
                "UPDATE uploads SET verified_at = ?, platform_url = COALESCE(?, platform_url) "
                "WHERE youtube_id = ? AND platform = ?",
                (_now(), _clean_url(platform_url), youtube_id, platform),
            )
        else:
            c.execute(
                "UPDATE uploads SET verified_at = ? WHERE youtube_id = ? AND platform = ?",
                (_now(), youtube_id, platform),
            )


def remove(youtube_id: str, platform: str) -> None:
    """오업로드 기록 정정용(실게시물 삭제와는 무관)."""
    with _conn() as c:
        c.execute("DELETE FROM uploads WHERE youtube_id = ? AND platform = ?", (youtube_id, platform))


def uploaded_ids(platform: str) -> set[str]:
    with _conn() as c:
        return {r[0] for r in c.execute(
            "SELECT youtube_id FROM uploads WHERE platform = ?", (platform,)
        )}


def is_uploaded(youtube_id: str, platform: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM uploads WHERE youtube_id = ? AND platform = ?",
            (youtube_id, platform),
        ).fetchone()
        return row is not None


def get_upload(youtube_id: str, platform: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT youtube_id, platform, uploaded_at, platform_url, caption, source, verified_at "
            "FROM uploads WHERE youtube_id = ? AND platform = ?",
            (youtube_id, platform),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_uploads(platform: str | None = None) -> list[dict]:
    q = (
        "SELECT youtube_id, platform, uploaded_at, platform_url, caption, source, verified_at "
        "FROM uploads"
    )
    args: tuple = ()
    if platform:
        q += " WHERE platform = ?"
        args = (platform,)
    q += " ORDER BY uploaded_at DESC"
    with _conn() as c:
        return [_row_to_dict(r) for r in c.execute(q, args)]


def pending_verification(platform: str | None = None) -> list[dict]:
    """코드(script) 업로드 중 아직 검증 안 된 셀. 검증 스윕 대상."""
    q = (
        "SELECT youtube_id, platform, uploaded_at, platform_url, caption, source, verified_at "
        "FROM uploads WHERE verified_at IS NULL AND source = 'script'"
    )
    args: tuple = ()
    if platform:
        q += " AND platform = ?"
        args = (platform,)
    q += " ORDER BY uploaded_at ASC"
    with _conn() as c:
        return [_row_to_dict(r) for r in c.execute(q, args)]


def _row_to_dict(r) -> dict:
    return {
        "youtube_id": r[0], "platform": r[1], "uploaded_at": r[2],
        "platform_url": r[3], "caption": r[4], "source": r[5], "verified_at": r[6],
    }


def diff(youtube_ids: Iterable[str], platform: str) -> list[str]:
    """platform 에 아직 안 올린 ID 만 입력 순서대로 반환."""
    done = uploaded_ids(platform)
    return [y for y in youtube_ids if y not in done]

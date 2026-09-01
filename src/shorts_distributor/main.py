"""shorts-dist CLI — 파이프라인 진입점.

명령 지도:
  준비/조회:  platforms · plan · list-shorts · diff · prepare · download-only
  코드 업로드: run(배치) · upload(단건) · verify(게시 후 검증)
  세션 관리:  login · doctor
  상태 기록:  status · mark-uploaded

업로드는 코드(Playwright)가 기본이다. run/upload 가 실패 셀을 남기면 리포트의
에이전트 인계 브리프를 browser-use/computer-use 에 넘겨 그 지점만 이어받는다.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import runner, state
from .config import Config
from .platforms import (
    normalize_platform_id,
    platform_display_name,
    supported_platforms_as_dicts,
)
from .youtube import get_channel_shorts


def _print_header(title: str) -> None:
    bar = "=" * 64
    print(f"\n{bar}\n{title}\n{bar}")


def _entry_with_ad_flags(entry: dict) -> dict:
    return runner.entry_with_ad_flags(entry)


# ---------------------------------------------------------------- 조회/준비

def cmd_platforms(cfg: Config, *, as_json: bool) -> int:
    supported = supported_platforms_as_dicts()
    supported_ids = {item["id"] for item in supported}
    payload = {
        "target_platforms": cfg.target_platforms,
        "shorts_selection_mode": cfg.shorts_selection_mode,
        "shorts_upload_limit": cfg.shorts_upload_limit,
        "shorts_lookback_limit": cfg.shorts_lookback_limit,
        "shorts_skip_ads": cfg.shorts_skip_ads,
        "supported_platforms": supported,
        "custom_target_platforms": [
            p for p in cfg.target_platforms if p not in supported_ids
        ],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Active target platforms, in upload order:")
    for i, platform in enumerate(cfg.target_platforms, 1):
        display_name = platform_display_name(platform)
        note = f" ({display_name})"
        if platform in payload["custom_target_platforms"]:
            note = " (custom; code upload 미지원 — 에이전트 가이드 필요)"
        print(f"  {i:2}. {platform}{note}")
    upload_limit = cfg.shorts_upload_limit if cfg.shorts_upload_limit is not None else "all"
    print(
        "\nShorts selection: "
        f"{cfg.shorts_selection_mode}, max {upload_limit}, "
        f"lookback {cfg.shorts_lookback_limit}, "
        f"skip ads {str(cfg.shorts_skip_ads).lower()}"
    )
    print("\nBuilt-in platform ids:")
    for item in payload["supported_platforms"]:
        aliases = f" aliases: {', '.join(item['aliases'])}" if item["aliases"] else ""
        print(f"  - {item['id']}: {item['display_name']}{aliases}")
    return 0


def cmd_plan(
    cfg: Config,
    *,
    as_json: bool,
    lookback_limit: int | None,
    upload_limit: int | None,
    selection_mode: str | None,
    skip_ads: bool | None,
) -> int:
    plan = runner.plan_batch(
        cfg,
        lookback_limit=lookback_limit,
        upload_limit=upload_limit,
        selection_mode=selection_mode,
        skip_ads=skip_ads,
    )
    if as_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    upload_limit_text = plan["upload_limit"] if plan["upload_limit"] is not None else "all"
    print(
        f"{plan['channel']} plan: {plan['selection_mode']} · "
        f"max {upload_limit_text} · lookback {plan['lookback_limit']} · "
        f"skip ads {str(plan['skip_ads']).lower()}"
    )
    print("Target platforms: " + ", ".join(plan["target_platforms"]))
    if not plan["selected_newest_first"]:
        print("No missing Shorts selected under the current ad policy.")
    else:
        print("\nSelected newest missing Shorts:")
        for i, item in enumerate(plan["selected_newest_first"], 1):
            platforms = ", ".join(item["missing_platforms"])
            ad_note = " | ad-suspected" if item["ad_suspected"] else ""
            print(
                f"  {i:2}. {item['youtube_id']} | {item['title']} | "
                f"missing: {platforms}{ad_note}"
            )
        print("\nUpload order: prepare selected IDs, then sort by upload_date/timestamp ascending.")
    if plan["ad_skipped"]:
        print("\nAd-suspected skipped:")
        for item in plan["ad_skipped"]:
            print(f"  - {item['youtube_id']} | {item['title']} | {', '.join(item['ad_markers'])}")
    if plan["ad_included"]:
        print("\nAd-suspected included by current ad policy:")
        for item in plan["ad_included"]:
            print(f"  - {item['youtube_id']} | {item['title']} | {', '.join(item['ad_markers'])}")
    return 0


def _channel_shorts(cfg: Config, limit: int | None) -> list[dict]:
    return [
        _entry_with_ad_flags(e)
        for e in get_channel_shorts(
            cfg.youtube_handle,
            limit=limit,
            metadata_lang=cfg.youtube_metadata_lang or None,
        )
    ]


def cmd_list_shorts(cfg: Config, *, limit: int | None, as_json: bool) -> int:
    entries = _channel_shorts(cfg, limit)
    if as_json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    print(f"{cfg.youtube_handle} Shorts: {len(entries)}")
    for i, e in enumerate(entries, 1):
        ad_note = f" | ad? {', '.join(e['ad_markers'])}" if e["ad_markers"] else ""
        print(f"  {i:3}. {e['id']} | {(e.get('title') or '')[:80]}{ad_note}")
    return 0


def cmd_diff(cfg: Config, platform: str | None, *, limit: int | None, as_json: bool) -> int:
    entries = _channel_shorts(cfg, limit)
    if platform is None or platform.lower() == "all":
        platforms = cfg.target_platforms
    else:
        platforms = [normalize_platform_id(platform)]
    results = []
    for target in platforms:
        uploaded = state.uploaded_ids(target)
        unposted = [e for e in entries if e["id"] not in uploaded]
        results.append(
            {
                "platform": target,
                "display_name": platform_display_name(target),
                "recorded": len(uploaded),
                "missing": len(unposted),
                "items": unposted,
            }
        )

    if as_json:
        if len(results) == 1:
            print(json.dumps(results[0]["items"], ensure_ascii=False, indent=2))
        else:
            print(
                json.dumps(
                    {
                        "channel": cfg.youtube_handle,
                        "total": len(entries),
                        "target_platforms": platforms,
                        "platforms": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    print(f"{cfg.youtube_handle} Shorts inspected: {len(entries)}")
    for result in results:
        print(
            f"\n{result['platform']} ({result['display_name']}): "
            f"recorded {result['recorded']} · missing {result['missing']}"
        )
        for i, e in enumerate(result["items"], 1):
            ad_note = f" | ad? {', '.join(e['ad_markers'])}" if e["ad_markers"] else ""
            print(f"  {i:3}. {e['id']} | {(e.get('title') or '')[:80]}{ad_note}")
    return 0


def cmd_prepare(cfg: Config, *, video_ids: list[str], as_json: bool) -> int:
    if not video_ids:
        print("Pass at least one --video-id from the channel Shorts list.", file=sys.stderr)
        return 2

    prepared = [runner.prepare_video(cfg, video_id) for video_id in video_ids]
    if as_json:
        print(json.dumps(prepared, ensure_ascii=False, indent=2))
        return 0

    for item in prepared:
        _print_header(f"Prepared {item['youtube_id']}")
        print(f"title: {item['title']}")
        print(f"file: {item['file_path']} (codec: {item['video_codec']})")
        print(f"url: {item['webpage_url']}")
        print(f"text mode: {item['post_text_mode']}")
        print("\npost text:")
        print(item["post_text"])
        if item["post_text"] != item["caption"]:
            print("\ncaption:")
            print(item["caption"])
    return 0


def cmd_download_only(cfg: Config, video_id: str | None) -> int:
    if not video_id:
        print("Pass --video-id from the channel Shorts list.", file=sys.stderr)
        return 2
    from .youtube import download_video

    meta = download_video(video_id, cfg.download_dir)
    print(f"[download-only] done: {meta.file_path.resolve()}")
    return 0


# ---------------------------------------------------------------- 코드 업로드

_STATUS_GLYPHS = {
    "verified": "ok",
    "published": "ok*",
    "pending-verify": "pending",
    "already": "dup",
    "skipped-ad": "ad-skip",
    "skipped-policy": "policy-skip",
    "failed": "FAIL",
    "blocked": "BLOCK",
    "agent-required": "AGENT",
    "planned": "-",
}


def _print_run_report(report: dict) -> None:
    cells = report.get("cells", [])
    batch = report.get("batch_oldest_first", [])
    if report.get("dry_run"):
        print(f"[dry-run] run {report['run_id']} — 업로드 없이 계획만 출력")
    if batch:
        print("\nUpload batch (oldest first):")
        for i, item in enumerate(batch, 1):
            print(f"  {i}. {item['youtube_id']} | {item['title'][:70]} | codec: {item['codec']}")
    if not cells:
        print("\n처리할 셀이 없습니다(모두 업로드 완료).")
    else:
        video_ids = list(dict.fromkeys(c["youtube_id"] for c in cells))
        platforms = list(dict.fromkeys(c["platform"] for c in cells))
        by_key = {(c["platform"], c["youtube_id"]): c for c in cells}
        width = max(10, *(len(v) for v in video_ids)) if video_ids else 10
        print("\n| {:<10} | ".format("Platform") + " | ".join(f"{v:<{width}}" for v in video_ids) + " |")
        print("|" + "-" * 12 + "|" + ("-" * (width + 2) + "|") * len(video_ids))
        for platform in platforms:
            row = []
            for video_id in video_ids:
                cell = by_key.get((platform, video_id))
                row.append(_STATUS_GLYPHS.get(cell["status"], cell["status"]) if cell else "")
            print("| {:<10} | ".format(platform) + " | ".join(f"{v:<{width}}" for v in row) + " |")
        print("\n범례: ok=검증 완료, ok*=게시(검증 별도), pending=검증 미확정(verify --pending 재확인), dup=기록 있음(스킵),")
        print("      policy-skip=콘텐츠 정책상 제외, FAIL/BLOCK/AGENT=에이전트 인계 필요(아래 브리프)")

    sweeps = report.get("pending_verification_sweep") or []
    if sweeps:
        print("\n이전 run 미검증 셀 스윕:")
        for row in sweeps:
            print(f"  - {row['platform']} {row['youtube_id']}: {row['verify_status']} ({row.get('evidence', '')})")

    for row in report.get("ad_skipped") or []:
        print(f"\nad-skipped: {row['youtube_id']} | {row['title']} | {', '.join(row['ad_markers'])}")

    briefs = report.get("agent_briefs") or []
    if briefs:
        _print_header("에이전트(browser-use/computer-use) 인계 브리프")
        for brief in briefs:
            print(brief)
            print("-" * 64)
    print(f"\nreport: {report['run_dir']}/report.json")


def cmd_run(cfg: Config, args) -> int:
    report = runner.run_batch(
        cfg,
        platforms=args.platforms.split(",") if args.platforms else None,
        video_ids=args.video_id or None,
        upload_limit=args.upload_limit,
        lookback_limit=args.lookback_limit,
        selection_mode=args.selection_mode,
        skip_ads=args.skip_ads,
        dry_run=args.dry_run,
        do_verify=not args.no_verify,
        headless=True if args.headless else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_run_report(report)
    return report["exit_code"]


def cmd_upload(cfg: Config, args) -> int:
    report = runner.upload_single(
        cfg,
        args.platform,
        args.youtube_id,
        force=args.force,
        do_verify=not args.no_verify,
        headless=True if args.headless else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_run_report({**report, "batch_oldest_first": [], "dry_run": False})
    return report["exit_code"]


def cmd_verify(cfg: Config, args) -> int:
    results = runner.verify_uploads(
        cfg,
        platform=args.platform,
        video_ids=args.video_id or None,
        pending=args.pending,
        headless=True if args.headless else None,
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(r["verify_status"] in {"verified", "waiting"} for r in results) else 3
    if not results:
        print("검증 대상이 없습니다.")
        return 0
    needs_agent = False
    for row in results:
        mark = {"verified": "ok", "waiting": "wait"}.get(row["verify_status"], row["verify_status"].upper())
        print(f"  - {row['platform']} {row['youtube_id']}: {mark} | {row.get('evidence', '')}")
        if row["verify_status"] not in {"verified", "waiting"}:
            needs_agent = True
    if needs_agent:
        print("\nmissing/inconclusive 셀은 에이전트로 교차확인하세요(재업로드는 fresh verification 후에만).")
    return 3 if needs_agent else 0


def cmd_doctor(cfg: Config, args) -> int:
    result = runner.doctor(cfg, headless=not args.headed)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 3
    print("tools: " + ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in result["tools"].items()))
    print("env:   " + ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in result["env"].items()))
    print("\nplatform sessions:")
    for row in result["platforms"]:
        extra = ""
        if row["missing_env"]:
            extra += f" | env 누락: {', '.join(row['missing_env'])}"
        if row.get("hint"):
            extra += f" | {row['hint']}"
        mode = "code" if row["code_upload"] else "agent-only"
        print(f"  - {row['platform']:<10} [{mode}] session={row['session']}{extra}")
    print(f"\noverall: {'ok' if result['ok'] else 'ATTENTION NEEDED'}")
    return 0 if result["ok"] else 3


def cmd_login(cfg: Config, platform: str) -> int:
    return 0 if runner.login(cfg, platform) else 3


# ---------------------------------------------------------------- 상태 기록

def cmd_status(platform: str | None) -> int:
    if platform and platform.lower() == "all":
        platform = None
    elif platform:
        platform = normalize_platform_id(platform)
    rows = state.list_uploads(platform)
    if not rows:
        print("Upload state is empty.")
        return 0
    print(f"Recent uploads: {len(rows)}")
    print(f"{'youtube_id':12} | {'platform':10} | {'source':8} | {'verified':8} | {'uploaded_at':25} | url")
    print("-" * 130)
    for r in rows[:50]:
        verified = "yes" if r["verified_at"] else "no"
        print(
            f"{r['youtube_id']:12} | {r['platform']:10} | {r['source']:8} | {verified:8} | "
            f"{r['uploaded_at']:25} | {r['platform_url'] or ''}"
        )
    if len(rows) > 50:
        print(f"... (+{len(rows) - 50} more)")
    pending = state.pending_verification(platform)
    if pending:
        print(f"\n검증 대기(script 업로드, verified 안 됨): {len(pending)}")
        for r in pending[:20]:
            print(f"  - {r['platform']} {r['youtube_id']} (uploaded {r['uploaded_at']})")
        print("→ `uv run shorts-dist verify --pending` 으로 검증하세요.")
    return 0


def cmd_mark_uploaded(
    platform: str,
    youtube_id: str,
    *,
    url: str | None,
    caption: str | None,
    source: str,
    verified: bool,
) -> int:
    platform = normalize_platform_id(platform)
    state.mark_uploaded(
        youtube_id,
        platform,
        platform_url=url,
        caption=caption,
        source=source,
        verified=verified,
    )
    print(f"[state] recorded {youtube_id} @ {platform} (source={source}, verified={verified})")
    return 0


# ---------------------------------------------------------------- 파서

def _limit_arg(value: str):
    """SHORTS_UPLOAD_LIMIT 오버라이드: 양의 정수 또는 'all'(명시적 무제한)."""
    if value.lower() == "all":
        return "all"
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("positive integer or 'all'") from None


def _add_headless_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headless",
        action="store_true",
        help="브라우저 창 없이 실행(기본은 .env UPLOADER_HEADLESS, 미설정 시 headed).",
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shorts-dist",
        description=(
            "YouTube Shorts 멀티 SNS 배포 파이프라인. "
            "코드(Playwright) 업로드가 기본, 실패 셀만 에이전트에 인계."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list-shorts", help="List Shorts from YOUTUBE_HANDLE")
    ls.add_argument("--limit", type=int, help="Maximum number of Shorts")
    ls.add_argument("--json", action="store_true")

    pf = sub.add_parser("platforms", help="Show configured and built-in platform ids")
    pf.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", help="Plan the env-configured upload batch without uploading")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--lookback-limit", type=int, help="Override SHORTS_LOOKBACK_LIMIT")
    plan.add_argument("--upload-limit", type=_limit_arg, help="Override SHORTS_UPLOAD_LIMIT (숫자 또는 all)")
    plan.add_argument("--selection-mode", choices=("recent", "all"), help="Override SHORTS_SELECTION_MODE")
    ads = plan.add_mutually_exclusive_group()
    ads.add_argument("--skip-ads", dest="skip_ads", action="store_true", default=None,
                     help="Override SHORTS_SKIP_ADS=true for this plan.")
    ads.add_argument("--include-ads", "--force-ads", dest="skip_ads", action="store_false",
                     help="Override SHORTS_SKIP_ADS=false for this plan.")

    df = sub.add_parser("diff", help="Channel Shorts minus local upload state")
    df.add_argument("platform", nargs="?",
                    help="Platform id. Defaults to TARGET_PLATFORMS; use 'all' for all active platforms.")
    df.add_argument("--limit", type=int, help="Maximum number of Shorts to inspect")
    df.add_argument("--json", action="store_true")

    pr = sub.add_parser("prepare", help="Download videos and print upload text metadata")
    pr.add_argument("--video-id", action="append", default=[], help="YouTube video ID; repeatable")
    pr.add_argument("--json", action="store_true")

    dl = sub.add_parser("download-only", help="Download a video without printing upload metadata")
    dl.add_argument("--video-id", required=True)

    run = sub.add_parser("run", help="코드 업로드 배치 실행: plan→prepare→upload→verify→record")
    run.add_argument("--platforms", help="쉼표 구분 플랫폼 목록(기본: TARGET_PLATFORMS)")
    run.add_argument("--video-id", action="append", default=[],
                     help="명시적 YouTube ID(반복 가능). 후보 선정만 우회하며 콘텐츠 정책은 항상 적용.")
    run.add_argument("--upload-limit", type=_limit_arg, help="Override SHORTS_UPLOAD_LIMIT (숫자 또는 all)")
    run.add_argument("--lookback-limit", type=int, help="Override SHORTS_LOOKBACK_LIMIT")
    run.add_argument("--selection-mode", choices=("recent", "all"))
    run_ads = run.add_mutually_exclusive_group()
    run_ads.add_argument("--skip-ads", dest="skip_ads", action="store_true", default=None)
    run_ads.add_argument("--include-ads", "--force-ads", dest="skip_ads", action="store_false")
    run.add_argument("--dry-run", action="store_true", help="계획+준비까지만, 업로드 없음")
    run.add_argument("--no-verify", action="store_true", help="게시 후 코드 검증 생략")
    run.add_argument("--json", action="store_true")
    _add_headless_flag(run)

    up = sub.add_parser("upload", help="단일 (platform, video) 셀 코드 업로드")
    up.add_argument("platform")
    up.add_argument("youtube_id")
    up.add_argument("--force", action="store_true", help="기록이 있어도 강제 업로드(fresh verification 후에만)")
    up.add_argument("--no-verify", action="store_true")
    up.add_argument("--json", action="store_true")
    _add_headless_flag(up)

    vf = sub.add_parser("verify", help="게시 후 검증. 기본: 미검증 script 셀 스윕")
    vf.add_argument("--platform", help="플랫폼 한정")
    vf.add_argument("--video-id", action="append", default=[], help="명시적 검증 대상(반복 가능, --platform 필요)")
    vf.add_argument("--pending", action="store_true", help="미검증 script 셀 전체 스윕(기본 동작)")
    vf.add_argument("--json", action="store_true")
    _add_headless_flag(vf)

    dr = sub.add_parser("doctor", help="환경/로그인 세션 점검(게시 없음, 기본 headless)")
    dr.add_argument("--headed", action="store_true", help="브라우저 창을 띄워 점검")
    dr.add_argument("--json", action="store_true")

    lg = sub.add_parser("login", help="플랫폼 Chrome 프로필 생성/로그인(헤디드)")
    lg.add_argument("platform")

    st = sub.add_parser("status", help="Show local upload state")
    st.add_argument("platform", nargs="?", help="Optional platform id, or 'all'")

    mk = sub.add_parser("mark-uploaded", help="에이전트/수동 업로드를 검증 후 기록")
    mk.add_argument("platform")
    mk.add_argument("youtube_id")
    mk.add_argument("--url", help="Verified platform post URL")
    mk.add_argument("--caption", help="Caption that was posted")
    mk.add_argument("--source", default="manual", help="State source label (default: manual)")
    mk.add_argument("--unverified", action="store_true",
                    help="검증 없이 기록(기본은 verified 로 기록 — 검증 후 호출이 원칙)")

    return p


def main() -> int:
    args = _parser().parse_args()
    try:
        cfg = Config.load()

        if args.cmd == "list-shorts":
            return cmd_list_shorts(cfg, limit=args.limit, as_json=args.json)
        if args.cmd == "platforms":
            return cmd_platforms(cfg, as_json=args.json)
        if args.cmd == "plan":
            return cmd_plan(
                cfg,
                as_json=args.json,
                lookback_limit=args.lookback_limit,
                upload_limit=args.upload_limit,
                selection_mode=args.selection_mode,
                skip_ads=args.skip_ads,
            )
        if args.cmd == "diff":
            return cmd_diff(cfg, args.platform, limit=args.limit, as_json=args.json)
        if args.cmd == "prepare":
            return cmd_prepare(cfg, video_ids=args.video_id, as_json=args.json)
        if args.cmd == "download-only":
            return cmd_download_only(cfg, args.video_id)
        if args.cmd == "run":
            return cmd_run(cfg, args)
        if args.cmd == "upload":
            return cmd_upload(cfg, args)
        if args.cmd == "verify":
            return cmd_verify(cfg, args)
        if args.cmd == "doctor":
            return cmd_doctor(cfg, args)
        if args.cmd == "login":
            return cmd_login(cfg, args.platform)
        if args.cmd == "status":
            return cmd_status(args.platform)
        if args.cmd == "mark-uploaded":
            return cmd_mark_uploaded(
                args.platform,
                args.youtube_id,
                url=args.url,
                caption=args.caption,
                source=args.source,
                verified=not args.unverified,
            )
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

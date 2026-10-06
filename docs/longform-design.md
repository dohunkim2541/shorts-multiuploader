# 설계: 롱폼 수집 + 유튜브 / 네이버 블로그 타겟

상태: 초안 (구현 전)
범위: 자사 유튜브 롱폼 영상을 수집해 유튜브(다른 계정)와 네이버 블로그에 배포

## 1. 목표와 전제

- 소스: 자사 유튜브 채널의 롱폼(`/videos` 탭)
- 타겟: 유튜브(대상 계정), 네이버 블로그
- 협찬 콘텐츠는 대상이 아니다. 자사 제품 홍보만 다루므로 협찬 표기 로직은 만들지 않는다.
  다만 정책 파일의 `post_text` 규칙(문구 모드, 접두사)은 유지한다.
- 기존 숏폼 흐름(수집 → 변환 → 플랫폼 lane → 검증)은 그대로 재사용한다.

## 2. 전체 흐름

```text
소스 채널 /videos 탭
    -> 길이 필터 (SOURCE_MIN/MAX_DURATION)
    -> 다운로드 (yt-dlp)
    -> H.264 변환 (ffmpeg)
    -> 플랫폼 lane
         ├─ youtube      : YouTube Data API 업로드 -> videos.list 검증
         └─ naver_blog   : Playwright 글쓰기 (본문 + 영상 링크) -> 목록 검증
    -> SQLite 상태 기록 -> run report
```

## 3. 변경 범위

| 파일 | 변경 내용 |
|---|---|
| `src/shorts_distributor/youtube.py` | `get_channel_shorts()`를 `get_channel_videos(tab=...)`로 일반화. 기본값은 `shorts`로 두어 기존 동작을 유지한다. |
| `src/shorts_distributor/config.py` | `SOURCE_TAB`, `SOURCE_MIN_DURATION`, `SOURCE_MAX_DURATION`, 유튜브/네이버 블로그 설정 추가 |
| `src/shorts_distributor/platforms.py` | `youtube`, `naver_blog`에 대한 `PlatformSpec` 등록 |
| `src/shorts_distributor/uploaders/youtube_upload.py` | 신규. API 기반 업로더 |
| `src/shorts_distributor/uploaders/naver_blog.py` | 신규. Playwright 기반 블로그 업로더 |
| `src/shorts_distributor/uploaders/__init__.py` | 두 업로더 등록 |
| `tests/` | 길이 필터, 정책 적용, lane 격리, 상태 전이 테스트 |

이름 주의: `src/shorts_distributor/youtube.py`(수집 모듈)와 이름이 겹치지 않도록 업로더는 `youtube_upload.py`로 둔다.

## 4. 유튜브 타겟

### 방식: YouTube Data API v3 (권장)

- 기존 업로더 계약(`upload(page, job, steps, cfg)`)과 맞지 않는다. 브라우저를 쓰지 않으므로 `page` 인자가 필요 없다.
- 공식 API라서 Studio 화면 변경의 영향을 받지 않고, 계정 제재 위험도 낮다.
- 단점
  - Google Cloud 프로젝트와 OAuth 설정이 필요하다.
  - 할당량 관리가 필요하다. 업로드 1건은 약 1,600 유닛이며 기본 일일 한도는 10,000이다.
  - 미검증 프로젝트는 업로드 영상이 비공개로만 올라간다.

### 업로드 파라미터

| 항목 | 값 |
|---|---|
| 제목/설명 | 정책 규칙의 `post_text` 모드를 그대로 사용 |
| 공개 범위 | `YOUTUBE_TARGET_PRIVACY` (기본 `private`) |
| 카테고리 | `.env`에서 지정 |

### 검증

- `videos.list`로 업로드된 `video_id`를 조회해 존재와 제목을 확인한다.
- 검증에서 "없음"이 확인되기 전에는 재업로드하지 않는다. 기존 규칙과 같다.

## 5. 네이버 블로그 타겟

### 전제

- 블로그 글쓰기 API는 공개되어 있지 않다. Playwright로 스마트에디터를 조작해야 한다.
- 이 lane은 자동화 위험과 UI 변경 위험이 가장 크다. 가장 먼저 격리해야 한다.

### 게시 형식

- **본문 + 유튜브 영상 링크**를 기본으로 한다.
  - 이유: 블로그 에디터의 영상 직접 업로드는 용량과 길이 제한이 있고 UI 변경에 민감하다.
- 본문 구성: 정책의 `post_text` + 영상 링크
- 영상 링크가 에디터에서 자동 임베드되는지는 실제 화면에서 확인해야 한다. **아직 검증하지 않은 사항이다.**

### 검증

- 내 블로그 글 목록에서 제목으로 찾는다.
- 목록 로딩이 늦을 수 있으므로 한 번 재시도한다. 네이버 클립 업로더와 같은 패턴이다.

### 블로커 (사람이 판단)

- 로그인, 2FA, CAPTCHA
- 계정 컨텍스트가 맞지 않는 경우
- 에디터 구조가 바뀌어 선택자 후보를 모두 실패한 경우

## 6. 설정 (.env 추가안)

```dotenv
SOURCE_TAB=videos
SOURCE_MIN_DURATION=60
SOURCE_MAX_DURATION=3600
YOUTUBE_TARGET_CLIENT_SECRETS=data/secrets/client_secret.json
YOUTUBE_TARGET_PRIVACY=private
NAVER_BLOG_ID=
TARGET_PLATFORMS=youtube,naver_blog
```

- 인증 정보와 토큰은 `.env`와 `data/` 아래에만 둔다. 커밋하지 않는다.
- `.env.example`에는 키 이름만 추가하고 값은 비워 둔다.

## 7. 테스트 계획

- 길이 필터: 경계값(60초, 3600초)과 길이가 없는 영상 처리
- 정책: 문구 모드(`default`, `caption`, `title`, `description`) 적용
- lane 격리: 네이버 블로그 lane이 실패해도 유튜브 lane이 계속 진행되는지
- 상태 전이: 검증 전에는 재업로드가 일어나지 않는지
- 실계정 스모크 테스트는 테스트용 계정에서만 수행하고, CI에서는 실제 게시를 하지 않는다.

## 8. 미정 사항

1. 유튜브 업로드 방식 확정 (API 권장 / Studio 대안)
2. 네이버 블로그 영상 방식 확정 (링크 권장 / 직접 업로드)
3. 대상 계정이 본인 소유인지 확인
4. 플랫폼별 길이 제한 확인 (네이버 블로그 등 변동 가능성이 있으므로 구현 전 확인)
5. 자사 홍보 글이 일반 리뷰처럼 보이지 않는지 마케팅 담당자 확인

## 9. 구현 순서 제안

1. 수집 일반화 (`SOURCE_TAB`, 길이 필터) + 테스트
2. 유튜브 업로더 (API) + 테스트
3. 네이버 블로그 업로더 (Playwright) + 실계정 수동 점검
4. `run --dry-run`으로 전체 흐름 확인 후 소규모 실제 실행

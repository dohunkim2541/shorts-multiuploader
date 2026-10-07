# 방식 A: 한 번 올리고, 호환 플랫폼에만 자동 업로드

상태: 1차 범위 확정, 구현 전
이전 방식(시트 입력형)은 `docs/archive/B-sheet-input/`에 보관했습니다.
대상 플랫폼: 유튜브, 인스타그램, 네이버 블로그 (틱톡은 제외)

## 1. 목표

- 담당자가 콘텐츠를 한 플랫폼에 올린다(또는 사진을 준비한다).
- 말로 지시한다. 예: "지금 올라간 숏츠 다른 플랫폼에도 올려줘"
- Claude가 플랫폼 규칙을 확인해서 **호환되는 플랫폼에만** 올린다.
- 결과를 시트 한 탭에 기록한다. 담당자는 시트에서 성공 여부만 확인한다.

담당자가 직접 입력하는 것은 **콘텐츠 준비와 지시 한 문장**뿐입니다.

## 2. 1차 범위

A의 전제는 **이미 게시된 콘텐츠를 다른 플랫폼으로 옮기는 것**입니다. 그래서 소스는 게시된 영상이어야 합니다. 조사한 조합 중 **가능**이면서 소스가 이미 게시된 것만 1차 범위입니다.

| 순서 | 소스 → 대상 | 판단 | 근거 |
|---|---|---|---|
| 1 | 유튜브 쇼츠 → 인스타 릴스 | 가능 | 세로 영상. 두 플랫폼 규칙 값 모두 확인됨 |
| 2 | 유튜브 롱폼 → 유튜브 롱폼 (다른 계정) | 가능 | 같은 형식. 15분 초과 시 계정 인증 필요 |

**2차 이후로 미루는 조합**
- 인스타 캐러셀 → 네이버 블로그 (**2차 1순위**, 아래 2.1 참고): 소스가 이미 게시된 내 인스타 게시물이므로 A의 전제에 맞습니다. 소스 읽기는 공식 Graph API로 가능합니다.
- 블로그 글 → 인스타 캐러셀: 블로그 본문을 읽어야 하므로 약관 확인 후 결정합니다. 보류.
- 사진 파일 → 인스타 캐러셀, 사진 파일 → 네이버 블로그: 아직 게시되지 않은 파일이므로 A가 아니라 별도 입력 방식입니다. 보류.

**1차에서 제외하는 조합**
- 조건부: 유튜브 롱폼 → 인스타 릴스(변환 필요)
- 불가: 쇼츠 → 롱폼, 쇼츠 → 블로그, 롱폼 → 쇼츠, 사진 → 유튜브, 사진 → 릴스, 글 → 롱폼
- 보류: 롱폼 → 블로그 (블로그 영상 용량 제한을 공식 확인하지 못함)

### 2.1 2차 1순위: 인스타 캐러셀 → 네이버 블로그

- **소스:** 내 인스타그램에 이미 게시된 캐러셀 게시물. 장별 이미지를 순서대로 가져옵니다.
- **소스 읽기:** 인스타 Graph API로 내 게시물의 자식(children) 미디어를 읽습니다. 공식 방식이며, 내 계정 게시물에만 해당합니다.
- **대상:** 네이버 블로그 글쓰기. 공식 API가 없으므로 브라우저 조작(Playwright)으로 이미지를 순서대로 삽입합니다.
- **제외:** 블로그 글을 읽는 방향은 이 단계에 넣지 않습니다. 약관 확인이 끝난 뒤에 다룹니다.
- **확인할 것:** 블로그 한 글에 넣을 수 있는 이미지 장 수와 용량 제한 (공식 확인 필요)

### 2.2 인스타 계정 조건 (확인일 2026-10-07)

출처: Meta 공식 문서 [Content Publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing), [ig-media children](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-media/children)

| 항목 | 확인 내용 |
|---|---|
| 계정 종류 | **전문가 계정(professional)만 지원.** 개인 계정은 명시되지 않아 지원 대상이 아님 |
| Facebook 페이지 연결 | 공식 문서가 전문가 계정이 Page에 연결되어 있어야 한다고 명시 |
| 캐러셀 읽기 권한 | Instagram 로그인: `instagram_business_basic`. Facebook 로그인: `instagram_basic`, `pages_read_engagement` |
| 본인 게시물 여부 | 공식 문서에서 명시하지 않음. 내 계정 게시물만 읽는다는 전제로 설계 |

**판단**
- 내 인스타가 **개인 계정이면 이 방향은 불가**입니다. 전문가 계정으로 전환해야 합니다.
- 전문가 계정이면 가능합니다. 다만 계정 종류 이름(비즈니스 또는 크리에이터)이 공식 문서에 따로 나오지 않아서, 실제 계정 설정 화면에서 확인해야 합니다.

## 3. 흐름

```text
[담당자] 콘텐츠 준비 (유튜브 업로드 또는 사진 파일 준비)
    -> [담당자] Claude에게 지시 ("다른 플랫폼에도 올려줘")
    -> Claude: 소스 목록 확인 (shorts-dist list-shorts / plan --json)
    -> Claude: 소스 형식(쇼츠, 롱폼, 사진)과 대상 플랫폼의 규칙 확인
         ├─ 가능: 업로드
         └─ 조건부 / 불가 / 규칙 값 없음: 올리지 않고 "제외" 또는 "질문"
    -> 결과를 결과 탭에 한 줄씩 기록
    -> Claude가 요약 보고 (성공 N, 제외 N, 질문 N, 실패 N)
```

## 4. 판단 기준: 플랫폼 규칙 파일

Claude의 판단은 자유 추측이 아니라 **규칙 파일**로 합니다. 규칙에 없는 항목은 판단하지 않고 묻습니다.

```yaml
# 값은 공식 문서에서 확인한 것만 채움. 확인일 2026-10-07
youtube:
  source_formats:
    shorts:                       # 원본으로 사용 가능
      max_duration_sec: 180       # 3분 이하 세로 영상은 쇼츠로 분류
      aspect: "9:16"              # 권장. 원문 미확인
      max_resolution: 1080p
    long:
      min_duration_sec: 180       # 3분 초과 또는 가로 영상
  target_formats:
    shorts:
      supported: true
      max_duration_sec: 180
      aspect: "9:16"
    long:
      supported: true
      requires_verified_account_over_sec: 900
      max_file_gb: 256
      max_duration_hours_upload: 12
  # 출처
  #   https://support.google.com/youtube/answer/15424877 (쇼츠 3분)
  #   https://support.google.com/youtube/answer/10059070 (1080p)
  #   https://support.google.com/youtube/answer/71673 (256GB/12시간, 15분 초과 인증)

instagram:
  target_formats:
    reels:
      supported: true
      min_duration_sec: 3
      max_duration_sec: 900
      max_file_mb: 300
      aspect: "9:16"              # 권장. 허용 0.01:1~10:1, 다르면 잘림 발생
      fps_range: [23, 60]
      caption_max_chars: 2200
      max_hashtags: 30
      max_mentions: 20
      container_media_type: REELS
    carousel:
      supported: true
      min_items: 2
      max_items: 10
      image_aspect: [0.8, 1.91]   # 4:5 ~ 1.91:1
      image_max_mb: 100
      min_image_px: 320
  # 출처: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
  #       https://developers.facebook.com/docs/instagram-platform/content-publishing
  #       (확인일 2026-10-07)

instagram_source:                 # 내 게시물을 소스로 읽을 때 (Graph API)
  source_formats:
    carousel:
      read_method: graph_api_children   # 내 계정 게시물만

naver_blog:
  target_formats:
    article_with_images:
      supported: true             # 2차 1순위 대상. 공식 API 없음, 브라우저 조작으로 게시
      max_images: null            # 확인 필요
      max_video_gb: null          # 확인 필요 (영상은 1차 범위 밖)
    video:
      supported: false            # 1차 범위에서 영상 업로드 제외
  # 확인 필요: 글쓰기 공식 API, 이미지 장 수와 용량 제한
  # 영상 용량 2차 자료 (1GB/15분 등)는 공식 확인 전까지 값으로 쓰지 않음
```

### 4.1 판단 규칙

- `supported: false`이면 항상 제외합니다.
- 소스 형식이 대상 형식과 맞지 않으면 제외합니다. 예: 사진 → 릴스.
- 규칙 값이 `null`이면 **판단하지 않고** 사용자에게 묻습니다.
- 규칙 파일은 코드 저장소에서 관리합니다. 값은 공식 문서를 확인한 뒤에만 채웁니다.

### 4.2 예시 판단

| 지시 | 판단 결과 |
|---|---|
| 유튜브 쇼츠 → 인스타 릴스 | 업로드 (규칙 값 모두 있음) |
| 유튜브 쇼츠 → 네이버 블로그 | 제외. "쇼츠 영상은 블로그 대상 아님" |
| 유튜브 쇼츠 → 유튜브 롱폼 | 제외. "3분 이하 세로 영상은 쇼츠로 분류됨" |
| 사진 3장 → 인스타 캐러셀 | 2차 범위. 사진 입력 방식이 정해지기 전에는 다루지 않음 |
| 사진 → 네이버 블로그 | 2차 범위. 같은 이유로 보류 |

## 5. 결과 탭 (시트에 있는 것은 이것뿐)

| 열 | 예시 | 채우는 방식 |
|---|---|---|
| 일시 | 2026-10-07 14:00 | Claude |
| 원본 ID | 유튜브 영상 ID 또는 사진 세트 이름 | Claude |
| 소스 형식 | 쇼츠 / 롱폼 / 사진 | Claude |
| 플랫폼 | 인스타그램 릴스 | Claude |
| 결과 | 성공 / 실패 / 제외 / 질문 | Claude |
| 게시 URL | 게시물 링크 | Claude |
| 사유 | 길이 초과, 로그인 필요 등 | Claude |

- 시트는 **읽기 전용 확인용**입니다. 담당자는 입력하지 않습니다.
- 한 콘텐츠, 한 플랫폼마다 한 줄입니다.

## 6. 안전 규칙

- 같은 원본과 같은 플랫폼 조합은 **성공 기록이 있으면 다시 올리지 않습니다.**
- 실패는 재업로드 전에 플랫폼에서 게시 여부를 먼저 확인합니다.
- 로그인, 2FA, CAPTCHA는 사람이 처리합니다. Claude는 멈추고 알립니다.
- 플랫폼 하나가 실패해도 나머지는 계속 진행합니다.

## 7. 기존 코드로 가능한 것 (영상 흐름)

| 필요 기능 | 기존 명령 |
|---|---|
| 채널 쇼츠 목록 확인 | `uv run shorts-dist list-shorts --limit 10` |
| 업로드 계획 확인 | `uv run shorts-dist plan --json` |
| 특정 플랫폼만 업로드 | `uv run shorts-dist run --platforms instagram --video-id <ID>` |
| 게시 없이 확인 | `uv run shorts-dist run --dry-run` |
| 결과 확인 | `uv run shorts-dist status`, `data/runs/<run_id>/report.json` |

**새로 만들 것**
1. 플랫폼 규칙 파일과 호환 판단 함수
2. 롱폼 소스 수집 (현재 `/shorts` 탭만 수집)
4. 결과 탭 기록 기능
5. 종료 코드 `3`(확인 필요) 결과를 Claude가 요약하는 흐름

## 8. 구현 순서

1. **쇼츠 → 인스타 릴스 (dry-run):** 판단 함수를 만들고, `--dry-run`으로 판단 결과만 출력합니다.
2. **쇼츠 → 인스타 릴스 (실계정 한 건):** 테스트 계정에서 한 편을 올립니다.
3. **결과 탭 기록:** 판단과 결과를 시트 한 줄로 씁니다.
4. **Claude 지시 흐름:** 말로 지시하면 위 단계를 순서대로 실행하고 요약합니다.
5. **롱폼 → 롱폼 (다른 계정):** 롱폼 수집과 업로드를 추가합니다.
6. **인스타 캐러셀 → 네이버 블로그 (2차 1순위):** 인스타 Graph API로 게시물 이미지를 읽고, 블로그 글쓰기를 브라우저로 자동화합니다. 블로그 장 수와 용량 제한을 먼저 확인합니다.
7. **블로그 → 인스타 (보류):** 블로그 읽기 방식에 대한 약관 확인이 끝난 뒤에 결정합니다.
8. **사진 파일 입력 (보류):** 자동화 대상에 넣을지 결정한 뒤에 다룹니다.

## 9. 미정 사항

1. 결과 탭을 어느 시트 파일에 둘지 (새 파일 / 기존 파일의 탭)
2. 인스타 게시 방식: Playwright 유지 vs 공식 API
3. 재게시 조건: 실패 후 자동 재시도 여부, 아니면 지시할 때만 재시도
4. 판단이 애매할 때 질문 방식: Claude 채팅 / 결과 탭의 "질문" 행
5. 네이버 블로그 이미지 장 수와 용량 제한 (공식 확인 필요, 2차 1순위의 선행 조건)
8. 블로그 → 인스타 방향의 읽기 방식과 네이버 이용약관 확인 (보류 사유)
9. 인스타 Graph API 계정 조건: 확인 완료 (아래 2.2절). 남은 확인: 실제 계정 유형 점검과 토큰 권한 설정
6. 네이버 블로그 글쓰기의 공식 지원 여부 (확인 안 됨)
7. 사진 소스의 저장 위치 (로컬 폴더 / 드라이브)

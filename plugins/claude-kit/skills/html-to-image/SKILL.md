---
name: html-to-image
description: HTML(파일·URL·문자열)을 카드뉴스·앱스토어·OG처럼 비율이 고정된 이미지(PNG/JPEG)로 캡처한다. 폰트·이미지 렌더 완료를 기다려 깨짐을 막고, 여러 장 batch 지원.
argument-hint: [html-file-or-url] [preset]
tools: Bash, Read
---

# HTML to Image

## 책임 경계 (한다 / 안 한다)

- **한다**: HTML(파일·URL·문자열) + 치수/비율 → 정확한 픽셀 크기의 PNG/JPEG. 렌더 완료(폰트·이미지)를 기다려 깨짐을 막고, 여러 장을 batch로 뽑는다. 엔진 둘(playwright 기본·satori 옵션), 각자 입력 계약이 다르다 → [엔진 섹션](#엔진--playwright기본--satori).
- **안 한다 — HTML 만들기**: *무엇을 어떻게 그릴지*는 호출자(card-news 같은 컴포지션) 책임. 이 스킬은 완성된 HTML을 받아 *렌더만* 한다. seam은 HTML이다.
- **안 한다 — 모션/영상**: 한 장 캡처는 애니메이션을 못 담는다. 움직이는 카드뉴스/릴스는 범위 밖 — Remotion·hyperframes 같은 컴포지션+렌더 프레임워크를 쓴다.
- **안 한다 — 비율 추측**: 치수는 `--preset`(presets.json) 또는 명시 `--width/--height`로 받는다. 임의로 정하지 않는다.

## 렌더 보강 (raw screenshot 대비)

- **렌더 완료 대기** — `load` 후 `document.fonts.status` 폴링 + 전체 이미지 `decode()` 완료 대기. 폰트·이미지가 준비되기 전에 찍히는 사고를 막는다. `networkidle`은 Playwright 공식 비권장이라 안 쓴다 — `--url`로 비동기 XHR/fetch가 콘텐츠를 채우는 페이지는 `--wait-selector`로 readiness를 명시한다.
- **정확한 크기·배율** — viewport를 치수에 맞추고 그 영역만 클립(스크롤바·여백 없음). `--scale 2`로 레티나 2배 선명도.
- **애니메이션 freeze** — Playwright 내장 `animations:'disabled'`로 유한 애니메이션은 끝 상태로 완료, 무한은 초기 상태로 고정해 결정적 프레임을 얻는다(기본 on, `--no-freeze`로 해제). 색·텍스트 래스터도 `--force-color-profile=srgb`·`--font-render-hinting=none`으로 고정.
- **batch** — `--manifest`로 슬라이드 N장을 한 번에(viewport가 같은 묶음은 context 재사용).

## 워크플로우

`$ARGUMENTS`가 있으면 URL 여부 먼저 확인(`http://`·`https://` 시작이면 소스로 사용). 아니면 `Glob($ARGUMENTS[0])`로 파일 존재 확인 — 존재하면 파일 소스로 사용. `$ARGUMENTS[1]`(있으면) preset. 둘 다 아니거나 `$ARGUMENTS` 없으면 사용자에게 소스 확인.

1. **소스 라우팅** — 캡처할 HTML이 로컬 파일(`--html`)인지, 로컬 dev 서버/URL(`--url`)인지, 인라인 문자열(`--html-string`)인지 정한다.
2. **치수 결정** — 알려진 포맷이면 `--preset`(예: `instagram-carousel`), 아니면 `--width/--height`. 목록은 [`references/presets.json`](./references/presets.json).
3. **캡처** — `scripts/capture.mjs` 실행. 영역은 기본 viewport 통째, 특정 요소만이면 `--selector`.
4. **확인** — 출력 PNG/JPEG의 크기가 의도한 치수인지 본다(batch면 장수도).

## 스크립트

`scripts/capture.mjs` — 캡처 엔진 CLI(playwright 기본·satori 옵션). 호출자 스킬뿐 아니라 프로젝트 코드도 직접 호출 가능.

```bash
# 단일 — 로컬 HTML을 인스타 캐러셀 비율로
node scripts/capture.mjs --html ./slide.html --preset instagram-carousel --out ./out/01.png

# 명시 치수 + 레티나 2배
node scripts/capture.mjs --html ./og.html --width 1200 --height 630 --scale 2 --out ./og.png

# 특정 요소만 (전체 페이지 중 .card 하나)
node scripts/capture.mjs --url http://localhost:5173/preview --selector ".card" --out ./card.png

# batch — manifest의 각 항목이 전역 기본값(preset 등) 상속, 항목값 우선
node scripts/capture.mjs --preset instagram-carousel --manifest ./slides.json
#   slides.json: [{"html":"./s1.html","out":"./out/01.png"}, {"html":"./s2.html","out":"./out/02.png"}]
```

주요 플래그: `--html|--url|--html-string`(소스), `--preset|--width/--height`, `--scale`, `--selector|--full-page`, `--delay <ms>`, `--wait-selector <css>`, `--format png|jpeg` `--quality`, `--no-freeze`, `--engine playwright|satori`, `--font <path>`(반복), `--out`, `--manifest`.

## 엔진 — playwright(기본) / satori

- **playwright**(기본) — 완성된 임의 HTML/URL을 실제 Chromium으로 렌더. grid·z-index·웹폰트·JS 등 모든 CSS 지원. 카드뉴스 슬라이드·앱스토어 스크린샷처럼 레이아웃이 풍부한 캡처는 이걸 쓴다.
- **satori**(`--engine satori`) — 브라우저 없이 flexbox-only HTML→PNG. edge·콜드스타트·저메모리·Chromium 회피에 강하나 제약이 크다:
  - **입력**: `--html`/`--html-string`만(url·selector·full-page 미지원), **PNG 전용**. 미지원 옵션은 무시가 아니라 명확한 에러로 안내한다.
  - **CSS**: flexbox만 — `display:grid`·float·clear·z-index·`position:fixed`·`calc()`·RTL·`<link>` 웹폰트 불가.
  - **폰트**: 시스템 fallback 없음. 기본 번들은 Pretendard(한글+Latin). 한자·기타 스크립트 글리프는 `--font <path>`로 해당 폰트를 지정해야 한다(미지정 시 빈칸).
  - 단순 OG 카드처럼 flexbox로 충분히 표현되는 고정 카드에 쓴다.

## 셋업

Playwright + chromium 필요(최초 1회):

```bash
cd scripts && npm install && npx playwright install chromium
```

## Edge Cases

- **외부 폰트·이미지가 느린 HTML**: `load` 대기만으론 렌더가 완료 전에 찍힐 수 있다. `--wait-selector <css>` 또는 `--delay <ms>`로 readiness를 명시한다.
- **`--url`로 로컬 dev 서버**: 서버가 실행 중인지 먼저 확인하고 캡처한다. 서버가 없으면 연결 오류로 빈 이미지가 나온다.
- **satori 엔진에 미지원 CSS**: `display:grid`·`z-index`·`position:fixed`·`calc()` 등을 쓰면 satori는 렌더를 건너뛰어 레이아웃이 깨진다. playwright(기본)로 폴백하거나 HTML을 flexbox 전용으로 바꾼다.
- **출력 경로 미지정**: `--out`을 생략하면 소스 파일명 기반으로 자동 결정된다. batch `--manifest`에선 각 항목의 `out` 필드가 없으면 오류가 난다 — 명시 권장.
- **batch 중 일부 실패**: manifest N장 중 일부가 렌더 실패하면 그 장만 오류 보고하고 나머지는 계속 진행한다. 처리 후 실패 목록을 사용자에게 알린다.

## 참고 자산

- [`references/presets.json`](./references/presets.json) — 비율·치수·배율 프리셋 카탈로그(수치 SSOT).

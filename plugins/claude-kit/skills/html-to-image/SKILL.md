---
name: html-to-image
description: HTML(파일·URL·문자열)을 카드뉴스·앱스토어·OG처럼 비율이 고정된 이미지(PNG/JPEG)로 캡처한다. 폰트·이미지 렌더 완료를 기다려 깨짐을 막고, 여러 장 batch 지원.
tools: Bash, Read
---

# HTML to Image

HTML을 **정해진 비율/크기로 정확히** 캡처해 PNG/JPEG로 내보내는 렌더 primitive. 카드뉴스 슬라이드, 앱스토어 스크린샷, OG 카드처럼 *치수가 고정된 미디어*를 HTML로 만든 뒤 이미지로 뽑을 때 쓴다.

## 책임 경계 (한다 / 안 한다)

- **한다**: HTML(파일·URL·문자열) + 치수/비율 → 정확한 픽셀 크기의 PNG/JPEG. 렌더 완료(폰트·이미지)를 기다려 깨짐을 막고, 여러 장을 batch로 뽑는다.
- **안 한다 — HTML 만들기**: *무엇을 어떻게 그릴지*는 호출자(card-news 같은 컴포지션) 책임. 이 스킬은 완성된 HTML을 받아 *렌더만* 한다. seam은 HTML이다.
- **안 한다 — 모션/영상**: 한 장 캡처는 애니메이션을 못 담는다. 움직이는 카드뉴스/릴스는 범위 밖 — Remotion·hyperframes 같은 컴포지션+렌더 프레임워크를 쓴다.
- **안 한다 — 비율 추측**: 치수는 `--preset`(presets.json) 또는 명시 `--width/--height`로 받는다. 임의로 정하지 않는다.

## 왜 raw screenshot보다 가치 있나

raw `page.screenshot()`을 각자 짜면 *렌더 완료 전에 캡처해 빈/반쪽 이미지*가 나오는 게 #1 실패다. 이 스킬은 그 보강을 표준화한다:

- **렌더 완료 대기** — `networkidle` + `document.fonts.ready` + 추가 `--delay`. 커스텀 브랜드 폰트가 로드되기 전에 찍히는 사고를 막는다.
- **정확한 크기·배율** — viewport를 치수에 맞추고 그 영역만 클립(스크롤바·여백 없음). `--scale 2`로 레티나 2배 선명도.
- **애니메이션 freeze** — 정적 캡처가 결정적이 되도록 `*{animation/transition:none}` 주입(기본 on, `--no-freeze`로 해제).
- **batch** — `--manifest`로 슬라이드 N장을 한 번에.

## 워크플로우

1. **소스 라우팅** — 캡처할 HTML이 로컬 파일(`--html`)인지, 로컬 dev 서버/URL(`--url`)인지, 인라인 문자열(`--html-string`)인지 정한다.
2. **치수 결정** — 알려진 포맷이면 `--preset`(예: `instagram-carousel`), 아니면 `--width/--height`. 목록은 [`references/presets.json`](./references/presets.json).
3. **캡처** — `scripts/capture.mjs` 실행. 영역은 기본 viewport 통째, 특정 요소만이면 `--selector`.
4. **확인** — 출력 PNG/JPEG의 크기가 의도한 치수인지 본다(batch면 장수도).

## 스크립트

`scripts/capture.mjs` — Playwright(chromium) 기반 캡처 엔진. 호출자 스킬뿐 아니라 프로젝트 코드도 직접 호출 가능한 CLI.

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

주요 플래그: `--html|--url|--html-string`(소스), `--preset|--width/--height`, `--scale`, `--selector|--full-page`, `--delay <ms>`, `--wait-selector <css>`, `--format png|jpeg` `--quality`, `--no-freeze`, `--out`, `--manifest`.

## 셋업

Playwright + chromium 필요(최초 1회):

```bash
cd scripts && npm install && npx playwright install chromium
```

## 참고 자산

- [`references/presets.json`](./references/presets.json) — 비율·치수·배율 프리셋 카탈로그(수치 SSOT). 새 포맷은 여기 한 줄 추가하면 `--preset`으로 바로 쓴다.

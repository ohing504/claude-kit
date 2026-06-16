# Whiteboard — 디자인 시스템 참조

SKILL.md의 3·4·5단계(미학 커밋 · 스택 라우팅 · 단일 HTML 출력)에서 참조한다. 게이트(0단계)가 끝나 *무엇을 그릴지* 정해진 뒤의 산출 디테일이다.

## 1. 미학 패밀리 — 하나를 커밋한다

코딩 전에 내용 톤에 맞는 하나를 고른다(즉흥 generic 레이아웃 금지). 사용자가 지정하면 그걸 따른다.

| 패밀리 | 느낌 | 적합 |
|---|---|---|
| **Editorial Dark / Data-Dense** | 어두운 배경 + 선명한 액센트 1색, 세리프 디스플레이 | 분석·결정 자료, 진지한 기술 문서 (기본 추천) |
| **Editorial Minimalism** | 밝은 종이, 넉넉한 여백, 타이포 중심 | 개념 설명, 한 장 브리프 |
| **Swiss / Grid** | 격자·비대칭, 절제된 색 | 비교·구조 |
| **Terminal-Core** | 모노 폰트, 낮은 채도, 코드 친화 | 디버깅·흐름·시스템 |
| **Warm Editorial** | 따뜻한 톤, 잡지풍 | 가벼운 정리·회고 |

과한 스타일(Neon Brutalist·maximalist 등)은 진지한 맥락엔 피한다. 톤과 코드 복잡도를 일치시킨다(minimal이라면서 busy한 마크업을 내지 않기).

## 2. anti-slop — 이름으로 금지

막연한 "예쁘게" 대신, 학습데이터 중앙값의 다음 지문(指紋)을 *이름으로* 금지한다. 구체적 금지가 막연한 칭찬보다 훨씬 잘 듣는다.

- **폰트**: Inter · Roboto · Arial · Helvetica · Space Grotesk 금지. → 특징 있는 디스플레이 세리프(예: Fraunces, Newsreader) + 깔끔한 본문(예: IBM Plex Sans) + 모노(IBM Plex Mono) 조합.
- **색**: 보라→파랑 그라데이션, 틸(#16d5e6류) 액센트 금지. 보라-온-화이트 금지. → 지배색 1 + 선명한 액센트 1, CSS 변수로.
- **레이아웃**: 모든 카드에 좌측 액센트바, 3단 히어로 그리드, 2단계 초과 컨테이너 중첩, 전부 가운데 정렬 금지.
- **아이콘/장식**: 이모지를 아이콘으로 쓰기, 블링킹 상태 닷, 의미 없는 Lucide 아이콘 더미 금지.

## 3. 디자인 축 — 각각에 구체 규칙

"디자인"을 한 덩어리로 두지 말고 축별로 정한다:

- **타이포**: 고대비 페어링. 약한 웨이트(100/200) vs 강한 웨이트(800/900). 크기 점프 3배 이상. 디스플레이는 세리프, 데이터·라벨은 모노.
  - **가독성 하한 — 어떤 텍스트도 14px 미만으로 두지 않는다.** 테이블 헤더(`th`)·캡션·범례·작은 주석·모노 라벨이 가장 자주 위반한다. 본문 16px+, 보조 텍스트 14px+. "작게 = 세련됨"이 아니다 — 다시 읽으려고 만든 문서다.
- **색**: 지배색 + 날카로운 액센트(고르게 분산된 소심한 팔레트 금지). CSS 변수로 토큰화. 데이터 팔레트는 색맹 안전하게.
- **모션**: 기본은 1회 오케스트레이션된 페이지로드(staggered `animation-delay` reveal). 그 이상은 명시 요청 시만. `prefers-reduced-motion` 존중.
- **배경**: 평면이 지루하면 미묘한 질감(노이즈·그레인·그라데이션 메시) 하나. 과용 금지.

## 4. 스택 라우팅 — 내용유형 → 최소 라이브러리

| 내용 유형 | 라이브러리 | 비고 |
|---|---|---|
| 레이아웃·시각위계 | **Tailwind** (Play CDN) | 유틸 클래스로 문단→카드. 최대 레버리지. (Play CDN은 개발용 — 개인 산출물엔 충분) |
| 정량 데이터 | **Chart.js** (CDN) | config 객체 하나. 표준 차트의 기본값 |
| 정량(리치: heatmap·sankey·geo) | **ECharts** (CDN) | 순수 JSON option |
| 프로세스·흐름·관계·시퀀스 | **Mermaid** (CDN) | 자동 레이아웃, 좌표 환각 0. **단, 노드 4개 이상 LR 플로우는 SVG가 압축돼 텍스트가 작아짐** — 이 경우 순수 HTML/CSS flex 행(노드 + `→` 화살표) 으로 직접 구현이 가독성 우위. |
| 위계·아웃라인 | **Markmap** (CDN) | 중첩 마크다운 → 마인드맵 |
| 탭·필터·접기/펼치기 | **Alpine.js** (CDN) | HTML 속성만, React/빌드 불필요 |
| 비교 매트릭스·KPI·타임라인 | (라이브러리 없이) HTML+CSS | 표·그리드로 충분. 좌표 절대배치 타임라인은 깨지기 쉬우니 피하고 표/Mermaid로 |

**회피**: D3.js(저수준 명령형, 토큰·환각↑ — 맞춤 viz만), Recharts(React/JSX = 빌드 단계, 단일파일 깨짐). 손으로 그리는 absolute-position 타임라인·SVG 좌표도 피한다(라벨 겹침·부정확).

## 5. 단일 HTML 골격

자기완결 한 장의 뼈대. 핵심은 **견고한 Mermaid 초기화**(SKILL.md 5단계) — `startOnLoad:false` + 명시 `mermaid.run()`. 미학 토큰은 `:root` CSS 변수로, 다크/라이트는 클래스 토글.

```html
<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>…</title>
<!-- 필요한 것만 로드 -->
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,800&family=IBM+Plex+Sans:wght@300;400;600&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{ --bg:#0c0e13; --panel:#161a23; --hi:#f3efe6; --mid:#c2c5bb; --lo:#8c8f85; --accent:#f5b13d; }
  body.light{ --bg:#efeae0; --panel:#fbf8f1; --hi:#181a16; --mid:#43463e; --lo:#6c6f65; }
  body{ background:var(--bg); color:var(--hi); font-family:'IBM Plex Sans',sans-serif; margin:0; }
  h1,h2{ font-family:'Fraunces',serif; font-weight:800; }
  .mono{ font-family:'IBM Plex Mono',monospace; }
  /* 가독성 하한 — 본문 16px+, 보조 14px+, 어떤 텍스트도 14px 미만 금지 */
  table{ font-size:16px; } th{ font-size:14px; }
  .cap{ font-size:14px; color:var(--lo); }
  /* 다이어그램은 컨테이너 가운데 정렬 */
  .mermaid{ text-align:center; }
  .mermaid svg{ display:block; margin:0 auto; max-width:100%; height:auto; }
  .ink{ background:#10131a; border-radius:14px; } /* 다이어그램/차트 패널은 모드 무관 다크 고정 */
  @keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
  .rise{animation:rise .6s cubic-bezier(.2,.7,.2,1) both}
  @media (prefers-reduced-motion:reduce){.rise{animation:none}}
  @media print{ .noprint{display:none!important} .ink{-webkit-print-color-adjust:exact;print-color-adjust:exact} }
</style>
</head>
<body>
  <!-- 핵심 질문에 대한 답·추천을 맨 위에 고정 -->
  <!-- 섹션별 매체(매트릭스·다이어그램·차트). Mermaid는 <pre class="mermaid">…</pre> 또는 <div class="mermaid">…</div> -->

<script>
  // Chart.js: DOMContentLoaded 후 초기화
  window.addEventListener('DOMContentLoaded', () => {
    const ctx = document.getElementById('chart1');
    if (ctx && window.Chart) { new Chart(ctx, { /* type, data, options */ }); }
  });

  // Mermaid: 동적 import + 명시 run (startOnLoad 금지 — 타이밍 레이스로 raw 잔존 발생)
  import('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs')
    .then(async ({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false, theme: 'base', securityLevel: 'loose',
        fontFamily: 'IBM Plex Sans, sans-serif',
        themeVariables: { background:'#10131a', primaryColor:'#1b202b', primaryTextColor:'#f3efe6',
          primaryBorderColor:'#8aa8cf', lineColor:'#8aa8cf', fontSize:'16px' }
      });
      await mermaid.run({ querySelector: '.mermaid' }); // ← 반드시 명시 호출
    })
    .catch(e => console.warn('mermaid load failed', e));
</script>
</body>
</html>
```


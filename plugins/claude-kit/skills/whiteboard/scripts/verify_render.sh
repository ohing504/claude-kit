#!/usr/bin/env bash
# whiteboard/verify_render.sh — 생성한 단일 HTML이 *실제로 렌더되는지* headless 브라우저로 검증한다.
#
# 왜 필요한가: Claude가 Mermaid/Chart.js를 쓴 HTML을 만들면, 파일은 멀쩡히 열려도
# 다이어그램은 raw 소스("sequenceDiagram ...")가 텍스트로 떨어지는 일이 잦다(렌더 실패).
# 눈으로 안 열어보면 이걸 못 잡는다 — "텍스트 벽을 깨자"는 산출물이 텍스트 벽이 되는 사고.
# 이 스크립트는 렌더 후 DOM을 떠서 그 실패를 자동으로 잡는다.
#
# 사용: verify_render.sh <html-path>
# 종료코드: 0=통과, 1=렌더 실패(수정 필요), 2=입력 오류, 3=Chrome 없음(검증 건너뜀)
# pipefail 미사용: 검증은 grep 카운트가 많고, 매치 0(grep exit 1)은 정상 신호라
# 파이프 실패로 스크립트를 죽이면 안 된다.
set -eu

HTML="${1:?usage: verify_render.sh <html-file>}"
[ -f "$HTML" ] || { echo "FAIL: 파일 없음 — $HTML"; exit 2; }

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  CHROME="$(command -v google-chrome 2>/dev/null || command -v chromium 2>/dev/null || command -v 'Google Chrome' 2>/dev/null || true)"
fi
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  echo "SKIP: Chrome/Chromium을 못 찾음 — headless 렌더 검증 불가."
  echo "      사용자에게 브라우저로 직접 열어 다이어그램/차트가 그려졌는지 확인을 요청할 것."
  exit 3
fi

ABS="$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")"
DOM="$(mktemp -t whiteboard_dom)"
trap 'rm -f "$DOM"' EXIT

# 동적 import(Mermaid ESM)·Chart.js 초기화가 끝나도록 가상시간 예산을 넉넉히 준다.
"$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --virtual-time-budget=10000 --run-all-compositor-stages-before-draw \
  --dump-dom "file://$ABS" > "$DOM" 2>/dev/null || true

fail=0

# 1) 렌더 자체가 됐나. 로드에 실패하면 dump가 비어 <body>가 없다.
#    바이트 수를 임계로 쓰지 않는다 — 정상인 작은 페이지가 걸린다(실측: 유효한 49B 페이지가 FAIL).
bytes=$(wc -c < "$DOM" | tr -d ' ')
if ! grep -qi '<body' "$DOM"; then
  echo "FAIL: 렌더 DOM에 <body>가 없음(${bytes}B) — 페이지 로드 실패."
  exit 1
fi

# 2) Mermaid: 소스에 .mermaid 블록을 썼는데, 렌더 후 DOM에 raw 문법이 텍스트로 남아있으면 실패
# 출현 수로 센다 — `grep -c`는 행 수라, 한 행에 블록이 둘이면 아래 processed(출현 수)와 단위가 어긋난다.
# HTML 주석은 먼저 지운다 — design-system.md의 골격 템플릿은 `<pre class="mermaid">`를 주석으로
# 예시해 두어, 그대로 둔 채 세면 실제 블록보다 많이 나와 렌더가 성공해도 FAIL이 된다.
strip_comments() {
  if command -v perl >/dev/null 2>&1; then
    perl -0777 -pe 's/<!--.*?-->//gs' "$1" 2>/dev/null
  else
    cat "$1"
  fi
}
src_mermaid=$(strip_comments "$HTML" | grep -o 'class="mermaid"' | wc -l | tr -d ' ')
src_mermaid=${src_mermaid:-0}
if [ "$src_mermaid" -gt 0 ]; then
  processed=$(grep -o 'data-processed="true"' "$DOM" 2>/dev/null | wc -l | tr -d ' ')
  if grep -qE 'sequenceDiagram|flowchart (TD|LR|RL|BT)|graph (TD|LR|RL|BT)|classDiagram|stateDiagram|erDiagram|^[[:space:]]*classDef ' "$DOM"; then
    echo "FAIL: Mermaid raw 소스가 렌더 후에도 텍스트로 남음 — 다이어그램 렌더 실패 (.mermaid 블록 ${src_mermaid}개)."
    echo "      흔한 원인 ①: 동적 import + startOnLoad:true 조합 → 자동 렌더 타이밍을 놓침."
    echo "                   → startOnLoad:false 로 두고 import 후 'await mermaid.run()' 을 명시 호출."
    echo "      흔한 원인 ②: 라벨 특수문자(✕ → — '' \"\" 괄호) 파싱 에러 → 일반 텍스트로 치환."
    fail=1
  elif [ "$processed" -lt "$src_mermaid" ]; then
    echo "FAIL: Mermaid 블록 ${src_mermaid}개 중 ${processed}개만 처리됨 — 일부 다이어그램 렌더 실패."
    fail=1
  else
    echo "OK: Mermaid 다이어그램 ${src_mermaid}개 렌더됨."
  fi
fi

# 3) Chart.js: new Chart(...)를 썼는데 렌더 후 canvas가 없으면 실패
if grep -q 'new Chart(' "$HTML" 2>/dev/null; then
  if grep -q '<canvas' "$DOM"; then
    echo "OK: Chart.js canvas 존재."
  else
    echo "FAIL: new Chart() 를 썼는데 렌더 후 <canvas>가 없음 — 차트 렌더 실패(스크립트 에러 가능)."
    fail=1
  fi
fi

# 4) 라이브러리를 하나도 안 썼으면 검증할 동적 요소가 없다고 알림(정적 HTML)
if [ "$src_mermaid" -eq 0 ] && ! grep -q 'new Chart(' "$HTML" 2>/dev/null; then
  echo "NOTE: Mermaid/Chart.js 미사용 — 정적 HTML. 동적 렌더 검증 대상 없음(레이아웃은 브라우저로 확인)."
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS — 렌더 검증 통과."
  exit 0
else
  echo "—— 렌더 실패. 위 항목을 고친 뒤 다시 verify_render.sh 로 검증할 것."
  exit 1
fi

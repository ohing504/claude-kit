#!/usr/bin/env bash
#
# extract_carousel.sh — 인스타 이미지 게시물/캐러셀의 모든 슬라이드를 로그인 없이 받는다.
#
# 왜: 캐러셀은 슬라이드 이미지 '안의 텍스트'가 본문이다(예: 프롬프트·팁 모음).
# yt-dlp/gallery-dl은 비로그인이면 로그인 페이지로 리다이렉트돼 막히지만,
# /embed/captioned/ 엔드포인트는 공개 게시물의 gql_data(전 슬라이드 + 캡션)를
# 로그인 없이 내려준다. 그 데이터로 슬라이드를 받아온다.
#
# 경계(extract_frames와 동일): 추출=이 스크립트, 슬라이드 텍스트 '판독'=리뷰 LLM.
# 받은 slide_NN.jpg를 리뷰 LLM이 비전으로 읽어 본문을 뽑는다(스크립트는 OCR 안 함).
#
# 사용: extract_carousel.sh <인스타 게시물 URL>
# 환경: WORK_DIR (기본 /tmp/notes-digest-work)
# 출력: $WORK_DIR/carousel/slide_NN.jpg(+영상이면 .mp4) + contact.jpg
#       표준출력에 CAPTION + 슬라이드별 경로 + SLIDE_COUNT

set -uo pipefail
URL="${1:?사용: extract_carousel.sh <인스타 게시물 URL>}"
WORK="${WORK_DIR:-/tmp/notes-digest-work}"
CDIR="$WORK/carousel"; mkdir -p "$CDIR"
rm -f "$CDIR"/slide_*.jpg "$CDIR"/slide_*.mp4 "$CDIR"/contact.jpg

# shortcode 추출 (/p/ 또는 /reel/)
SHORT=$(printf '%s' "$URL" | sed -nE 's#.*/(p|reel)/([^/?]+).*#\2#p')
[[ -z "$SHORT" ]] && { echo "URL_PARSE_FAILED: $URL"; exit 0; }

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
HTML="$CDIR/embed.html"
curl -sL -A "$UA" --max-time 25 "https://www.instagram.com/p/$SHORT/embed/captioned/" -o "$HTML"
[[ ! -s "$HTML" ]] && { echo "EMBED_FETCH_FAILED: $URL"; exit 0; }

# gql_data(전 슬라이드 + 캡션) 파싱 후 슬라이드 다운로드
uv run --no-project python - "$HTML" "$CDIR" <<'PY'
import sys, json, urllib.request
html_path, outdir = sys.argv[1], sys.argv[2]
raw = open(html_path, encoding='utf-8', errors='replace').read()
i = raw.find('gql_data')
if i < 0:
    print("NO_GQL_DATA: 임베드에 캐러셀 데이터 없음(비공개·삭제·로그인 전용일 수 있음)"); sys.exit(0)
# 브레이스 매칭으로 gql_data 객체 추출(브레이스는 비이스케이프)
start = raw.find('{', i); depth = 0; end = None
for k in range(start, len(raw)):
    c = raw[k]
    if c == '{': depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0: end = k + 1; break
if end is None:
    print("GQL_PARSE_FAILED: 객체 경계 못 찾음"); sys.exit(0)
# 한 겹 unescape: \" -> "  ,  \/ -> /  ,  \\ -> \
blob = raw[start:end].replace('\\"', '"').replace('\\/', '/').replace('\\\\', '\\')
try:
    data = json.loads(blob)['shortcode_media']
except Exception as e:
    print("GQL_JSON_FAILED:", e); sys.exit(0)

cap = ""
try: cap = data['edge_media_to_caption']['edges'][0]['node']['text']
except Exception: pass
print("CAPTION:", cap.replace('\n', ' '))

if data.get('__typename') == 'GraphSidecar':
    nodes = [e['node'] for e in data['edge_sidecar_to_children']['edges']]
else:
    nodes = [data]

ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
n = 0
for node in nodes:
    is_v = bool(node.get('is_video'))
    u = node.get('video_url') if is_v else node.get('display_url')
    if not u: continue
    n += 1
    p = f"{outdir}/slide_{n:02d}.{'mp4' if is_v else 'jpg'}"
    try:
        req = urllib.request.Request(u, headers={'User-Agent': ua})
        open(p, 'wb').write(urllib.request.urlopen(req, timeout=30).read())
        print(f"SLIDE {n}: {'video' if is_v else 'image'} {p}")
    except Exception as e:
        print(f"SLIDE {n} DOWNLOAD_FAILED: {e}")
print("SLIDE_COUNT:", n)
PY

# 컨택트 시트(이미지 슬라이드 한눈 보기용 — 텍스트 판독은 개별 slide를 읽어라)
imgs=$(ls "$CDIR"/slide_*.jpg 2>/dev/null | wc -l | tr -d ' ')
if [[ "${imgs:-0}" -gt 0 ]]; then
  COLS=4; ROWS=$(( (imgs + COLS - 1) / COLS ))
  ffmpeg -y -framerate 1 -pattern_type glob -i "$CDIR/slide_*.jpg" \
    -vf "scale=400:-1,tile=${COLS}x${ROWS}:padding=6:color=white" -frames:v 1 "$CDIR/contact.jpg" 2>/dev/null
  echo "CONTACT_SHEET: $CDIR/contact.jpg"
fi
rm -f "$HTML"

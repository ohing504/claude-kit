#!/usr/bin/env bash
#
# enrich_video.sh — 영상 URL(인스타 릴스·유튜브·틱톡 등)에서 캡션·메타를 뽑고,
# 캡션이 얕으면 오디오를 받아 STT(음성→텍스트)까지 자동으로 수행한다.
#
# 왜: 인스타 릴스는 캡션이 "댓글 남겨주세요"·해시태그뿐인데 알맹이는 음성에 있는
# 경우가 많다. 캡션이 얕다 = 정보 없음이 아니라 "음성을 들어보라"는 신호다.
# 그래서 이 스크립트는 캡션이 짧으면 STT로 자동 전환한다. (살릴지/버릴지 판단은
# 호출자 LLM 몫 — 이 스크립트는 '데이터 뽑기'까지만.)
#
# 사용:
#   enrich_video.sh <URL> [캡션최소길이=50] [언어=ko]
#
# 환경:
#   SCRATCH_DIR  임시 오디오/STT 저장 위치 (기본 /tmp/notes-enrich)
#
# 출력(표준출력):
#   UPLOADER: ...
#   TITLE: ...
#   CAPTION: <캡션 전문>
#   [캡션이 얕을 때] STT_SOURCE: <엔진>  +  STT: <음성 전사 전문>
#   실패 시: EXTRACT_FAILED / AUDIO_FAILED / STT_UNAVAILABLE 한 줄
#
# 의존: yt-dlp, ffmpeg. STT는 mlx-whisper(맥) 또는 faster-whisper(whisper-ctranslate2).

set -euo pipefail

URL="${1:?사용: enrich_video.sh <URL> [캡션최소길이] [언어]}"
MIN_CAPTION="${2:-50}"
LANG="${3:-ko}"
MODEL="${WHISPER_MODEL:-mlx-community/whisper-large-v3-turbo}"
SCRATCH="${SCRATCH_DIR:-/tmp/notes-enrich}"
mkdir -p "$SCRATCH"

# 플랫폼별 STT 명령어 선택
SCR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_env.sh
source "$SCR/_env.sh"

# --- Threads 게시물: curl + OG bot UA로 추출 (yt-dlp Threads 미지원) ---
# Threads는 일반 브라우저 UA엔 SPA를 내리고, facebookexternalhit UA엔 OG 태그 포함 HTML을 돌려준다.
if [[ "$URL" =~ (threads\.net|threads\.com) ]]; then
  PAGE=$(curl -sL \
    -A "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)" \
    --max-time 15 "$URL" 2>/dev/null || true)
  if [[ -z "$PAGE" ]]; then
    echo "EXTRACT_FAILED: $URL"
    exit 0
  fi
  # og:title / og:description 추출 + HTML 엔티티 디코딩
  HTML_TMP="$SCRATCH/threads_page.html"
  printf '%s' "$PAGE" > "$HTML_TMP"
  OG_TITLE=$(uv run --no-project python -c "
import re
from html import unescape
html = open('$HTML_TMP').read()
m = re.search(r'property=\"og:title\"[^>]+content=\"([^\"]*)\"', html) or \
    re.search(r'content=\"([^\"]*)\"[^>]+property=\"og:title\"', html)
print(unescape(m.group(1)) if m else '')
" 2>/dev/null || true)
  OG_DESC=$(uv run --no-project python -c "
import re
from html import unescape
html = open('$HTML_TMP').read()
m = re.search(r'property=\"og:description\"[^>]+content=\"([^\"]*)\"', html) or \
    re.search(r'content=\"([^\"]*)\"[^>]+property=\"og:description\"', html)
print(unescape(m.group(1)) if m else '')
" 2>/dev/null || true)
  rm -f "$HTML_TMP"
  if [[ -z "$OG_DESC" ]]; then
    echo "EXTRACT_FAILED: $URL"
    exit 0
  fi
  printf 'UPLOADER: %s\n' "$OG_TITLE"
  printf 'CAPTION: %s\n' "$OG_DESC"
  exit 0
fi

# --- 1. 캡션·메타 (다운로드 없이) ---
if ! META=$(uvx yt-dlp --skip-download --no-warnings \
      --print "%(uploader)s" --print "%(title)s" --print "%(description)s" "$URL" 2>/dev/null); then
  # 인스타 /p/ 게시물은 이미지 캐러셀일 때 yt-dlp가 막힌다 — 슬라이드 텍스트가 본문이니
  # extract_carousel.sh로 슬라이드를 받아 리뷰 LLM이 비전 판독하라는 신호를 남긴다.
  if [[ "$URL" =~ instagram\.com/p/ ]]; then
    echo "IMAGE_POST: 이미지 게시물로 보임 → extract_carousel.sh \"$URL\" 로 슬라이드 추출 후 비전 판독"
  else
    echo "EXTRACT_FAILED: $URL"
  fi
  exit 0
fi
UPLOADER=$(printf '%s\n' "$META" | sed -n 1p)
TITLE=$(printf '%s\n' "$META" | sed -n 2p)
CAPTION=$(printf '%s\n' "$META" | tail -n +3)

printf 'UPLOADER: %s\n' "$UPLOADER"
printf 'TITLE: %s\n' "$TITLE"
printf 'CAPTION: %s\n' "$CAPTION"

# --- 2. 캡션이 충분하면 여기서 끝 ---
# 공백 제거 후 '문자수'로 판단. wc -m은 로케일에 따라 한글을 바이트로 세어
# 오판하므로(한글 1자=3바이트), python3로 유니코드 문자수를 정확히 센다.
CAPTION_LEN=$(printf '%s' "$CAPTION" | tr -d '[:space:]' | uv run --no-project python -c "import sys; print(len(sys.stdin.read()))")
if (( CAPTION_LEN >= MIN_CAPTION )); then
  exit 0
fi

# --- 3. 캡션이 얕으면 오디오 추출 → STT ---
echo "CAPTION_SHALLOW: len=${CAPTION_LEN} < ${MIN_CAPTION} → STT"
VID=$(uvx yt-dlp --skip-download --no-warnings --print "%(id)s" "$URL" 2>/dev/null)
if ! uvx yt-dlp -x --audio-format mp3 --no-warnings \
      -o "$SCRATCH/%(id)s.%(ext)s" "$URL" >/dev/null 2>&1; then
  echo "AUDIO_FAILED: $URL"
  exit 0
fi
AUDIO="$SCRATCH/$VID.mp3"

# STT 엔진은 _env.sh가 플랫폼에 따라 선택(CK_WHISPER_CMD)
if [[ "$(uname -m)" == "arm64" ]]; then
  echo "STT_SOURCE: mlx-whisper ($MODEL)"
  $CK_WHISPER_CMD "$AUDIO" --model "$MODEL" --language "$LANG" \
    --output-dir "$SCRATCH" --output-name "$VID" -f txt >/dev/null 2>&1
  echo "STT:"
  cat "$SCRATCH/$VID.txt"
else
  # faster-whisper CLI. 모델은 turbo 계열 이름이 다를 수 있어 large-v3로 폴백.
  FW_MODEL="${FASTER_WHISPER_MODEL:-large-v3}"
  echo "STT_SOURCE: faster-whisper ($FW_MODEL)"
  $CK_WHISPER_CMD "$AUDIO" --model "$FW_MODEL" --language "$LANG" \
    --output_dir "$SCRATCH" --output_format txt >/dev/null 2>&1
  echo "STT:"
  cat "$SCRATCH/$VID.txt"
fi

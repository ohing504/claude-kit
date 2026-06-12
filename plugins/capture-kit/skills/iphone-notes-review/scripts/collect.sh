#!/usr/bin/env bash
#
# collect.sh — 지정한 폴더의 메모를 추출하고, 그 안의 모든 영상 URL을
# enrich(캡션 + 캡션이 얕으면 STT)한다. 데이터 수집의 전 과정을 한 번에 굳힌다.
# 리뷰 작성·처분 판단(살릴지/버릴지)은 호출자(LLM) 몫 — 이 스크립트는 '수집'까지만.
#
# 사용:
#   collect.sh "폴더명" ["폴더명2" ...]
#
# 폴더를 반드시 명시한다. 전체를 묻지 않고 도는 것을 막기 위함이다 —
# 메모앱엔 잠긴 폴더·옛 개인글·민감정보가 섞여 있을 수 있으니, 먼저
# list_folders.sh로 폴더를 확인하고 사용자가 고른 폴더만 넘긴다.
#
# 환경:
#   WORK_DIR   결과 출력 위치 (기본 /tmp/notes-review-work)
#
# 출력:
#   $WORK_DIR/raw.txt        추출된 메모 원본(@@@NOTE@@@ 블록)
#   $WORK_DIR/enrich/NNN.txt 영상별 해석(URL + 캡션/메타 + 얕으면 STT 전사)
#   표준출력: 진행 카운트와 결과 경로

set -uo pipefail

if [[ $# -eq 0 ]]; then
  echo "사용: collect.sh \"폴더명\" [폴더명...]" >&2
  echo "      먼저 list_folders.sh로 폴더를 확인한 뒤, 처리할 폴더만 넘긴다." >&2
  exit 1
fi

SCR="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK_DIR:-/tmp/notes-review-work}"
rm -rf "$WORK"; mkdir -p "$WORK/enrich"
export SCRATCH_DIR="$WORK/scratch"

# 1. 추출 (지정 폴더들만)
: > "$WORK/raw.txt"
for folder in "$@"; do
  "$SCR/extract_notes.sh" "$folder" >> "$WORK/raw.txt" 2>/dev/null || {
    echo "경고: 폴더 '$folder' 추출 실패(이름 확인)" >&2; }
done
echo "처리 폴더: $*"
echo "추출 메모 수: $(grep -c '@@@NOTE@@@' "$WORK/raw.txt" 2>/dev/null || echo 0)"

# 2. 소셜 미디어 URL 유니크 추출 (인스타·유튜브·틱톡·Threads)
grep -oiE 'https?://[A-Za-z0-9./?=_&%~-]*(instagram\.com/(reel|p)|youtu\.be|youtube\.com/watch|tiktok\.com|threads\.net|threads\.com)[A-Za-z0-9./?=_&%~-]*' \
  "$WORK/raw.txt" 2>/dev/null | sort -u > "$WORK/video_urls.txt"
VCOUNT=$(grep -c . "$WORK/video_urls.txt" 2>/dev/null) || VCOUNT=0
echo "영상 URL 수: $VCOUNT"

# 3. enrich 루프 (캡션 + 얕으면 STT). 인스타 rate limit 회피로 사이에 쉼.
i=0
while IFS= read -r url; do
  [[ -z "$url" ]] && continue
  i=$((i+1)); f=$(printf '%03d' "$i")
  printf 'URL: %s\n' "$url" > "$WORK/enrich/$f.txt"
  "$SCR/enrich_video.sh" "$url" >> "$WORK/enrich/$f.txt" 2>&1
  echo "  [$f/$VCOUNT] $url"
  sleep 2
done < "$WORK/video_urls.txt"

echo "ENRICH_DONE: ${i}건"
echo "결과 위치: $WORK  (raw.txt=메모 원본, enrich/=영상 해석)"

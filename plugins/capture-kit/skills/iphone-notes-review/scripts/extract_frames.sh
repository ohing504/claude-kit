#!/usr/bin/env bash
#
# extract_frames.sh — 영상에서 '장면 전환'마다 프레임을 뽑아 컨택트 시트로 만든다.
# 음성(STT) 타임스탬프가 아니라 *화면 전환* 기준이라, 예시가 빠르게 바뀌는
# 영상(요리·촬영·플레이팅 등)의 시각 예시를 놓치지 않는다.
#
# 역할 분리: 추출(후보 생성)은 이 스크립트, 어느 컷을 쓸지 선별은 리뷰 LLM.
# LLM이 contact.jpg를 한눈에 보고 쓸 프레임을 고른다.
#
# 사용:
#   extract_frames.sh <URL> [시작초] [끝초]
#   - 시작/끝초를 주면 그 구간에서만 추출 (예: 특정 각도 설명 구간만)
#   - 안 주면 영상 전체에서 전환마다 추출
#
# 환경:
#   WORK_DIR                결과 위치 (기본 /tmp/notes-review-work)
#   FRAME_SCENE_THRESHOLD   장면 전환 민감도 0~1 (기본 0.3, 낮을수록 더 많이 뽑힘)
#
# 출력:
#   $WORK_DIR/frames/frame_*.jpg   전환별 개별 프레임
#   $WORK_DIR/frames/contact.jpg   한 장에 모은 타일 시트 (LLM이 한눈에 보기)

set -uo pipefail
URL="${1:?사용: extract_frames.sh <URL> [시작초] [끝초]}"
START="${2:-}"; END="${3:-}"
THRESHOLD="${FRAME_SCENE_THRESHOLD:-0.3}"
WORK="${WORK_DIR:-/tmp/notes-review-work}"
FDIR="$WORK/frames"; mkdir -p "$FDIR"
rm -f "$FDIR"/frame_*.jpg "$FDIR"/contact.jpg

# 영상 다운로드 (URL 해시로 캐시)
HASH=$(printf '%s' "$URL" | shasum | cut -c1-12)
VID="$WORK/vid_$HASH.mp4"
if [[ ! -f "$VID" ]]; then
  yt-dlp --no-warnings -o "$VID" "$URL" >&2 || { echo "다운로드 실패: $URL" >&2; exit 1; }
fi

# 구간 옵션 (input seek)
SEEK=(); [[ -n "$START" ]] && SEEK+=(-ss "$START"); [[ -n "$END" ]] && SEEK+=(-to "$END")

# 장면 전환 프레임 추출
ffmpeg -y "${SEEK[@]+"${SEEK[@]}"}" -i "$VID" \
  -vf "select='gt(scene,$THRESHOLD)',scale=720:-1" -vsync vfr \
  "$FDIR/frame_%04d.jpg" 2>/dev/null

COUNT=$(ls "$FDIR"/frame_*.jpg 2>/dev/null | wc -l | tr -d ' ')
echo "장면 전환 프레임: ${COUNT}장 (threshold=$THRESHOLD)"
[[ -n "$START$END" ]] && echo "구간: ${START:-0}~${END:-끝}초"

# 컨택트 시트 (한 장에 타일)
if (( COUNT > 0 )); then
  COLS=5; ROWS=$(( (COUNT + COLS - 1) / COLS ))
  ffmpeg -y -framerate 1 -pattern_type glob -i "$FDIR/frame_*.jpg" \
    -vf "scale=320:-1,tile=${COLS}x${ROWS}:padding=4:color=white" -frames:v 1 "$FDIR/contact.jpg" 2>/dev/null
  echo "컨택트 시트: $FDIR/contact.jpg"
fi
echo "개별 프레임: $FDIR/frame_*.jpg"

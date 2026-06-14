#!/usr/bin/env bash
#
# setup_env.sh — 스킬 전용 격리 환경(venv)을 한 번 부트스트랩하고 캐시한다.
#
# 왜: 영상 캡션·STT 도구(yt-dlp, mlx-whisper/faster-whisper)를 사용자의
# 시스템/homebrew 파이썬에 깔면 PEP 668 충돌·PATH 그림자·버전 오염이 난다.
# 대신 uv로 파이썬까지 격리 관리하는 전용 venv를 만들어 그 안에만 설치한다.
# 사용자 환경은 손대지 않고, 스크립트들은 _env.sh로 이 venv를 우선 참조한다.
#
# 멱등: 이미 준비됐으면 즉시 스킵. CK_FORCE_SETUP=1 이면 강제 재설치.
#
# 사용:
#   setup_env.sh            # 부트스트랩(또는 스킵)
#   CK_FORCE_SETUP=1 setup_env.sh   # 강제 재설치
#
# 환경:
#   CAPTURE_KIT_HOME    캐시 루트 (기본 ~/.cache/capture-kit)
#   CK_PYTHON_VERSION   venv 파이썬 버전 (기본 3.12 — mlx-whisper 휠 호환)
#
# 원칙: uv·ffmpeg(시스템 의존)는 자동 설치하지 않고 명령을 안내한다.
#       venv 안의 pip 패키지는 격리라 자동 설치한다(사용자 환경 무오염).

set -uo pipefail
SCR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_env.sh
source "$SCR/_env.sh"

PYVER="${CK_PYTHON_VERSION:-3.12}"

# 이미 준비됐으면 스킵
if [[ -z "${CK_FORCE_SETUP:-}" && -x "$CK_VENV_BIN/yt-dlp" && -n "$CK_WHISPER" ]]; then
  echo "SETUP_OK: 이미 준비됨 ($CK_VENV)"
  echo "  yt-dlp:  $CK_YTDLP"
  echo "  whisper: $CK_WHISPER ($CK_WHISPER_KIND)"
  [[ -z "$CK_FFMPEG" ]] && echo "  ⚠ ffmpeg 없음 — brew install ffmpeg"
  exit 0
fi

# uv 필요 (유일하게 사용자가 직접 깔아야 하는 것)
if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<'EOF'
SETUP_NEEDS_UV: uv가 없습니다. 아래 중 하나로 설치 후 다시 실행하세요.
  brew install uv
  # 또는
  curl -LsSf https://astral.sh/uv/install.sh | sh
EOF
  exit 2
fi

mkdir -p "$CK_HOME"

# venv 생성 (uv가 파이썬도 받아온다 — 시스템 파이썬 불필요)
if [[ ! -x "$CK_VENV_BIN/python" || -n "${CK_FORCE_SETUP:-}" ]]; then
  echo "SETUP: venv 생성 ($CK_VENV, python $PYVER)"
  uv venv --python "$PYVER" "$CK_VENV" || { echo "SETUP_FAILED: venv 생성 실패" >&2; exit 1; }
fi

# 공통: yt-dlp
echo "SETUP: yt-dlp 설치"
uv pip install --python "$CK_VENV_BIN/python" --quiet --upgrade yt-dlp \
  || { echo "SETUP_FAILED: yt-dlp 설치 실패" >&2; exit 1; }

# STT 엔진: Apple Silicon → mlx-whisper(Metal 네이티브, 빠름), 그 외 → faster-whisper
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  echo "SETUP: mlx-whisper 설치 (Apple Silicon)"
  uv pip install --python "$CK_VENV_BIN/python" --quiet mlx-whisper \
    || { echo "SETUP_FAILED: mlx-whisper 설치 실패" >&2; exit 1; }
else
  echo "SETUP: faster-whisper(whisper-ctranslate2) 설치"
  uv pip install --python "$CK_VENV_BIN/python" --quiet whisper-ctranslate2 \
    || { echo "SETUP_FAILED: whisper-ctranslate2 설치 실패" >&2; exit 1; }
fi

# 재해석 후 보고
source "$SCR/_env.sh"
echo "SETUP_OK: $CK_VENV"
echo "  python:  $CK_PYTHON"
echo "  yt-dlp:  $CK_YTDLP"
echo "  whisper: $CK_WHISPER ($CK_WHISPER_KIND)"
if [[ -z "$CK_FFMPEG" ]]; then
  echo "  ⚠ ffmpeg 없음 — 오디오/프레임 추출에 필요한 시스템 바이너리입니다."
  echo "    brew install ffmpeg   (pip 패키지가 아니라 venv에 담지 못함)"
fi

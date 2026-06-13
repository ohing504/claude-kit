#!/usr/bin/env bash
#
# _env.sh — capture-kit 도구 해석기. 다른 스크립트가 `source` 한다(직접 실행용 아님).
#
# 스킬 전용 격리 venv($CK_VENV)의 도구를 시스템 PATH보다 우선 쓰고, 없으면 PATH로 폴백한다.
# 목적: 사용자의 시스템/homebrew 파이썬을 건드리지 않는다(첫 실행 시 setup_env.sh가 venv를 만든다).
# set -e 류를 켜지 않는다 — source 하는 호출자의 셸 옵션을 바꾸지 않기 위함.

CK_HOME="${CAPTURE_KIT_HOME:-$HOME/.cache/capture-kit}"
CK_VENV="$CK_HOME/venv"
CK_VENV_BIN="$CK_VENV/bin"

# python: venv 우선, 없으면 시스템
if [[ -x "$CK_VENV_BIN/python" ]]; then
  CK_PYTHON="$CK_VENV_BIN/python"
else
  CK_PYTHON="$(command -v python3 || command -v python || true)"
fi

# yt-dlp: venv 우선
if [[ -x "$CK_VENV_BIN/yt-dlp" ]]; then
  CK_YTDLP="$CK_VENV_BIN/yt-dlp"
else
  CK_YTDLP="$(command -v yt-dlp || true)"
fi

# ffmpeg/ffprobe: 시스템 바이너리(pip 패키지가 아니라 venv에 못 담는다)
CK_FFMPEG="$(command -v ffmpeg || true)"
CK_FFPROBE="$(command -v ffprobe || true)"

# STT 엔진: venv mlx > venv faster-whisper > 시스템 폴백(옛 설치 호환)
CK_WHISPER=""
CK_WHISPER_KIND=""
if [[ -x "$CK_VENV_BIN/mlx_whisper" ]]; then
  CK_WHISPER="$CK_VENV_BIN/mlx_whisper"; CK_WHISPER_KIND="mlx"
elif [[ -x "$CK_VENV_BIN/whisper-ctranslate2" ]]; then
  CK_WHISPER="$CK_VENV_BIN/whisper-ctranslate2"; CK_WHISPER_KIND="faster"
elif command -v mlx_whisper >/dev/null 2>&1; then
  CK_WHISPER="$(command -v mlx_whisper)"; CK_WHISPER_KIND="mlx"
else
  for _p in "$HOME"/Library/Python/*/bin/mlx_whisper; do
    [[ -x "$_p" ]] && { CK_WHISPER="$_p"; CK_WHISPER_KIND="mlx"; break; }
  done
  if [[ -z "$CK_WHISPER" ]] && command -v whisper-ctranslate2 >/dev/null 2>&1; then
    CK_WHISPER="$(command -v whisper-ctranslate2)"; CK_WHISPER_KIND="faster"
  fi
fi

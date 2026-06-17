#!/usr/bin/env bash
# 플랫폼별 STT 명령어 선택. source하는 스크립트에서 CK_WHISPER_CMD를 사용한다.
if [[ "$(uname -m)" == "arm64" ]]; then
  CK_WHISPER_CMD="uvx mlx-whisper"
else
  CK_WHISPER_CMD="uvx --from whisper-ctranslate2 whisper-ctranslate2"
fi

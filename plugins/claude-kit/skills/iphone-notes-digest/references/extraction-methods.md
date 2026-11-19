# 추출 방식의 근거

스크립트의 추출 방식을 바꾸기 전에 읽는다. 2025-2026 조사이고 출처 URL은 기록하지 않았다. 도구 이름과 조사 시점만 있다.

## 본문은 AppleScript, 스캔과 첨부는 NoteStore.sqlite

| 방식 | 도구 | 장점 | 단점 |
|---|---|---|---|
| AppleScript | dogsheep/apple-notes-to-sqlite, storizzi/notes-exporter, Obsidian Importer | Apple이 저장 형식을 바꿔도 동작한다 | 스캔과 이미지 외 첨부를 읽지 못한다 |
| NoteStore.sqlite와 protobuf를 직접 읽기 | threeplanetssoftware/apple_cloud_notes_parser, RhetTbull/apple-notes-parser, kzaremski/apple-notes-exporter | 스캔, 이미지, 손글씨, 고정 여부, UUID를 읽는다 | Apple이 protobuf 형식을 바꾸면 읽지 못한다 |

- 본문과 링크는 저장 형식 변경에 영향받지 않는 AppleScript로 읽는다(`extract_notes.sh`).
- 스캔은 AppleScript `attachments`가 0개로 반환하므로 sqlite로 읽는다(`extract_scans.sh`).
- 변경된 메모만 다시 읽어야 하면 storizzi/notes-exporter(수정 시각 비교)와 kzaremski/apple-notes-exporter(`SyncWatermark.json`)의 방식을 본다.

## STT 엔진

Apple Silicon에서 mlx-whisper가 whisper.cpp보다 약 2배 빨랐다(2026-01 벤치마크, 출처 URL 미기록). `_env.sh`가 arm64에서 mlx-whisper를 고르는 근거다.

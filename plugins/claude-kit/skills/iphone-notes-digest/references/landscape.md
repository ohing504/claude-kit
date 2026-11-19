# 추출 방식과 기존 도구의 공백

스크립트의 추출 경로를 바꾸거나 이 스킬의 범위를 넓히려 할 때 읽는다. 2025-2026 조사이고 개별 URL은 기록하지 않았다. 도구명과 버전, 조사 시점만 있으므로 주장을 원출처로 확인하려면 해당 레포를 다시 연다.

## 추출 방식 — 본문은 AppleScript, 첨부는 NoteStore.sqlite 읽기전용

| 접근 | 대표 도구 | 강점 | 약점 |
|---|---|---|---|
| AppleScript, Shortcuts | dogsheep/apple-notes-to-sqlite, storizzi/notes-exporter, Obsidian Importer | 권한을 존중한다. Apple 포맷 변경에 강하다 | 느리다. 비이미지 첨부와 스캔을 못 잡는다 |
| NoteStore.sqlite 직파싱 + protobuf 역직렬화 | threeplanetssoftware/apple_cloud_notes_parser, RhetTbull/apple-notes-parser, kzaremski/apple-notes-exporter | 빠르다. 이미지, 스캔, 손글씨, pinned, UUID를 꺼낸다 | Apple protobuf 스키마가 바뀌면 깨진다 |

- **본문과 링크는 AppleScript로 읽는다.** 스키마 변경에 강한 쪽을 기본 경로로 둔다(`extract_notes.sh`).
- **스캔과 이미지 첨부만 sqlite로 읽는다.** AppleScript `attachments`가 스캔을 0개로 잡아서다(`extract_scans.sh`). 하이브리드가 2025-2026 도구들의 추세이기도 하다.
- **증분이나 pinned가 필요해지면 직파싱 도구의 방식을 참고한다.** storizzi는 modDate 증분(약 3배)과 x-coredata UUID, kzaremski는 `SyncWatermark.json` 증분을 쓴다(v2.0, 2026-05).
- **암호화된 잠긴 메모는 어느 도구로도 열 수 없다.** 그래서 `[LOCKED]`로 남기고 건수를 보고한다.

## STT — Apple Silicon에서 mlx-whisper

mlx-whisper가 whisper.cpp 대비 약 2배 빠르다(2026-01 벤치). `_env.sh`가 arm64에서 mlx-whisper를 고르는 근거다.

## 인스타그램과 틱톡 — 개별 공개 게시물만 다룬다

- 대량 수집은 로그인과 residential proxy가 사실상 필요하다. Instagram은 대부분 엔드포인트에 인증을 요구하고 GraphQL `doc_id`가 2~4주마다 바뀐다. datacenter IP는 rate limit 전에 차단된다. TikTok은 guest API를 2023년에 제거했다.
- 이 스킬은 메모에 든 개별 공개 게시물만 다루고 로그인 요구를 우회하지 않는다. `/embed/captioned/` 경로가 비로그인으로 캡션과 캐러셀 슬라이드를 준다.

## 이 스킬이 채우는 공백

조사 시점에 아래를 한 흐름으로 묶은 도구가 없었다.

- **추출 도구는 포맷 변환에서 멈춘다.** 위 표의 어느 도구도 메모 안 링크 뒤의 내용을 열어 해석하지 않는다.
- **Apple Notes MCP 약 20종은 대부분 CRUD 브릿지다.** enrichment가 없다.
- **영상 MCP는 자막을 그대로 쓴다.** 캡션이나 자막이 얕을 때 STT로 넘어가는 조건부 경로가 없다. `collect.sh`가 캡션 길이로 STT를 켜는 판단이 이 공백을 채운다.
- **read-later와 트리아지 도구(Readwise Reader, Karakeep, Obsidian Smart Connections)에는 영상 전사가 없다.** "이거 살릴까"를 묻는 결정 인터페이스를 낸 도구도 없었다.

capture, enrich, review, triage, route를 잇는 흐름 중 이 스킬은 enrich와 사실 다이제스트까지만 맡는다. triage와 route는 다이제스트를 받는 사용자나 그 노트 시스템이 정한다(SKILL.md 책임 경계).

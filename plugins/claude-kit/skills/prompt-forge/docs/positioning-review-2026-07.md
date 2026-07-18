# prompt-forge 포지셔닝 리뷰 (2026-07)

> 상태: reflect 정리·커밋 이후 착수 대기. 이 문서는 그 작업의 입력.

## TL;DR

prompt-forge는 뒤쳐지지 않았다. loop engineering 시대에 **값이 오르는 쪽**이다. 기법(의도추출→명세)은 유효, **포장·타깃만 경미한 재편** 권장. 폐기 근거는 사실무근.

핵심 오해: "prompt engineering(옛날) → loop engineering(요즘)"은 한 타임라인이 아니라 **다른 계층**이다("변수는 옛날 기술, 요즘은 CI/CD"와 같은 층위 혼동).
- **loop engineering** = 에이전트를 매 턴 직접 안 시키고 프롬프트·검증·재시도·중단을 자동화하는 **런타임 오케스트레이션**.
- **prompt-forge** = 실행 *전에* "뭘 시킬지" 의도를 뽑는 **명세(authoring)**.
- 대체가 아니라 **보완** — loop이 잘 돌려면 정밀 시드가 필수 입력.

## 왜 유효한가 (근거)

- **loop이 오지시를 증폭**: 자동 N회 반복에서 목표가 잘못 명세되면 "great efficiency로 N번 틀린 방향"으로 간다(Osmani/tosea). 자동화가 깊어질수록 정밀 시드 의도의 가치는 오히려 커진다.
- **죽은 건 문구질**: 매장된 "prompt engineering"은 매직 문구·손 튜닝·버려지는 일회성 프롬프트다(IEEE 헤드라인 "Prompt Engineering Is Dead"의 실제 부제 "Long live prompt engineering"). 의도/맥락 큐레이션은 살아남아 값이 올랐다.
- **흡수지 대체 아님**: Anthropic "context engineering은 prompt engineering의 *자연스러운 발전*". prompt engineering은 폐기가 아니라 상위개념에 흡수(subsume).
- **의도 명세가 2026 최고 값 활동**: Grove(OpenAI) "spec이 자산, 프롬프트는 버려짐" / GitHub Spec Kit "intent is the source of truth" / intent engineering("agent는 추론을 못 해서가 아니라 목표·제약이 under-specified라서 실패").
- **강한 모델일수록 정밀 의도↑**: 모호 입력을 "확신 있게 정교하게 틀린" 결과로 증폭(GPT-5 가이드 "강한 모델엔 모순·모호가 더 해롭다"). Fable 원샷 타깃 방향이 정확하다.
- prompt-forge 자기규정("문구 다듬기가 아니라 무엇을 시키려는지 인터뷰로 뽑는 게 본질")이 2026 담론과 문장 단위로 겹친다.

## 약점 3개 (기법 결함 아니라 포장·확장·실사용) → 액션

### 1. 이름·어휘가 2023년산
- "prompt"·"최종 프롬프트"가 낡은 첫인상을 그대로 맞는다(Willison "챗봇에 타이핑하는 허세 용어").
- **액션**: 산출물을 "의도 명세(intent spec)"로 재프레이밍. description·본문에 intent/spec/context 어휘를 얹는다. **리네임까지는 불필요**(기능이 아니라 라벨 문제).

### 2. loop/harness 타깃 없음
- 현재 타깃 델타 3종(ultracode/Fable/일반)은 "사람이 킥오프하는 단발 세션" 전제. 2026의 흔한 다운스트림은 loop이 매 실행 읽는 goal-file·verifier·skill이다.
- **액션**: "loop 시드" 타깃 델타 1종 추가 — 목표 + definition-of-done + 검증자/종료조건을 반복 실행에도 안정적인 "바깥에 적어두는 명세" 형태로 출력. **메커니즘 변경이 아니라 출력 포맷 1종 추가.**

### 3. 산출물이 길어 검토 부담 (실사용 갭)
- 긴 프롬프트를 사용자가 통독해야 의도 검토가 된다. 파일로 빼도(위치 이동) 검토 비용은 그대로.
- **액션**: (a) 프롬프트 **고밀도** 원칙 추가(의례·중복 제거, 정밀≠장황), (b) 5단계 출력에 **검토 요약**(의도 1줄 + 크리티컬 결정 3–5개) 동반 — 요약만으로 의도 일치 확인, 본문은 실행용.

## 착수 방법 (reflect 커밋 후)

두 액션 모두 SKILL.md 편집 수준(저비용). ai-doc-improver로 재프레이밍(어휘 축) + 타깃 델타 섹션에 loop 시드 1종 추가. 리네임·메커니즘 변경 없음.

## 핵심 출처

- Osmani, "Loop Engineering" (2026-06) — https://addyosmani.com/blog/loop-engineering/
- Anthropic, "Effective context engineering for AI agents" (2025-09) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Grove(OpenAI), "The New Code" (2025-06) — https://www.youtube.com/watch?v=BIvILtt164I
- GitHub Spec Kit (2025-09) — https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
- CMU, "What Prompts Don't Say" (arXiv 2505.13360) — under-specified 프롬프트 회귀 2배·정확도 20%+↓
- IEEE Spectrum, "AI Prompt Engineering Is Dead" (2024) — 부제 "Long live prompt engineering"

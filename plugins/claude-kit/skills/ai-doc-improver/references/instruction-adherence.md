---
topic: instruction framing — 긍정형 지시·대조 예시·negation salience가 준수율에 미치는 영향
source: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct
---

# Instruction Framing & Adherence for AI-Targeted Docs

## 요약

토큰 밀도가 "얼마나 효율적으로 읽히나"라면, 이 문서는 "지시를 **얼마나 따르나(instruction adherence)**"를 다룬다. AI가 읽는 문서(CLAUDE.md·SKILL.md·에이전트 정의)에서 같은 룰도 *프레이밍*에 따라 준수율이 달라진다. 세 레버 — 긍정형 지시, 대조 예시, negation salience — 가 한 방향을 가리킨다: **"하지 마라"를 길게 쓰는 것보다 "이렇게 하라"를 짧게 + 예시로 보이는 게 더 잘 따라진다.**

> [!note] 검증 강도 차이
> 긍정형 우선·few-shot 예시는 공식 가이드·실무에서 널리 정립. negation salience는 메커니즘상 타당하고 실무 통념이지만 정량 근거는 약함. "이모지 자체가 더 명확"은 가장 약한 주장 — 효과의 본질은 이모지가 아니라 *구조적 대조*다. 스킬에 넣을 땐 "준수율을 높이는 경향"으로 다루고 단정하지 않는다.

## 1. 긍정형 지시 — 원하는 행동을 직접 명시

- 모델은 "하지 마라"보다 "이렇게 하라"를 더 안정적으로 따른다. 부정 지시는 *대안 행동*을 주지 않아 모델이 빈칸을 추측한다.
- 처방: 금지를 만나면 그 이면의 원하는 행동으로 뒤집는다. `// 코드 재진술 주석 쓰지 마` → `주석은 "왜"만 — 코드가 말하는 "무엇"은 생략`.
- frontier 모델(Claude 4.x 등)은 부정문 처리가 과거보다 크게 개선됐다 — 금지 목록도 잘 따른다. 따라서 "부정은 절대 안 통한다"는 거짓이고, "긍정형이 *더 안정적*"인 정도다.

## 2. 대조 예시 — 추상 규칙 < 구체 good/bad

- 추상 규칙("간결히 써라")은 해석 폭이 넓다. 한 줄 대조 예시(`❌ I'll help you with that → ✅ 바로 본론`)가 규칙의 경계를 훨씬 좁게 고정한다(few-shot 효과).
- few-shot은 *경계 교정*만이 아니다 — 톤·출력 스타일·판단처럼 서술로 안 잡히는 것을 good/bad로 **시연**해 흉내로 가르친다. 대형 프로덕션 시스템 프롬프트도 규칙이 뼈대고, 예시는 *흉내가 서술보다 나은 지점*(톤·판단·거절)에만 외과적으로 쓴다.
- ✅/❌ 마커의 효과는 이모지 자체가 아니라 "따를 것 / 피할 것" 두 집합을 모델이 명확히 파싱하게 하는 **구조적 구분**이다. `Good:` / `Bad:` 라벨로도 같은 효과. 이모지 남발은 노이즈.
- 비용/ROI: 예시는 토큰을 쓴다 — 자명한 룰엔 순비용이라 생략. 고애매·반복 오해되는 지점(경계 교정 + 톤·출력형 시연)에선 준수율 이득이 토큰값을 넘는다(양의 ROI). 게이트: 고애매 AND 반복 오해 한정.

## 3. negation salience — 금지를 길게 묘사하면 역효과

- 금지 대상을 장황하게 서술하면 그 개념·표현이 컨텍스트에서 활성화(priming/salience)돼 오히려 출력 확률이 오른다("분홍 코끼리" 효과). 추론 시점엔 가중치 "학습"이 아니라 attention 활성화의 문제다.
- 처방: 금지는 **짧게, 한 줄로**. 피할 표현은 긴 설명 없이 라벨·예시로만 못박는다.
- 가시성과의 균형: 금지를 *명시적으로 분리*하는 것(묻히지 않게)과 *짧게*(salience 억제)는 양립한다 — 분리된 한 줄 금지가 정답. 장황한 단락 금지가 안티패턴.

## 핵심 인사이트

- 같은 룰도 프레이밍으로 준수율이 갈린다. 우선순위: **긍정형 지시 > (필요시) 짧은 대조 예시 > 짧은 명시적 금지**.
- 부정 제약은 "분리해서 잘 보이게"(가시성)와 "짧게"(salience)를 동시에 — 둘은 충돌하지 않는다.
- 토큰 밀도 축과 트레이드오프 — 자명한 룰엔 순비용(생략), 고애매·반복 오해 지점엔 양의 ROI(시연). 경계 교정뿐 아니라 톤·출력형 시연도 포함.

> 적용 시점의 점검 신호(어떤 문장을 만나면 무엇을 한다)는 `SKILL.md`의 "instruction 준수율" 섹션이 SSOT. 이 문서는 그 신호의 근거·메커니즘만 담는다.

## 관련 자료

- Anthropic, "Be clear and direct" (prompt engineering) — https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct
- Anthropic, "Use examples (multishot prompting)" — https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/multishot-prompting
- OpenAI, "Prompt engineering — tell the model what to do instead of what not to do" — https://platform.openai.com/docs/guides/prompt-engineering
- anthropics/claude-code 이슈 #58600 (Terse 6규칙 — 긍정형·대조 패턴 실사례) — https://github.com/anthropics/claude-code/issues/58600

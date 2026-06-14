---
topic: bullet 분해 vs 한 줄 산문 압축 — 토큰·정확도·검색 트레이드오프
source: https://arxiv.org/html/2411.10541v1
---

# Prompt Formatting & Token Density for AI-Targeted Docs

## 요약

AI agent가 읽는 문서(SKILL.md·spec·CLAUDE.md 등)에서 *bullet 분해 vs 한 줄 산문 압축* 트레이드오프. 세 축(포맷·검색 단위·위치 bias)이 한 방향을 가리킨다 — **장황의 단위는 줄 수가 아니라 토큰 밀도**이고, 통짜 paragraph보다 *표제 + sub-bullet 계층*이 토큰·정확도·검색 모두에서 우위. "줄 수 줄이려 한 줄 이어붙이기"는 안티패턴.

## 1. 포맷 축 — 구조화가 산문보다 토큰도 적고 정확도도 높다

- 마크다운 bullet/heading은 prose 대비 토큰 **10–20% 적음**, 해석 오류 **15–20% 감소**. 같은 정보를 한 줄 산문으로 이어붙이면 연결어("~하며", "~인 경우", "그리고")가 토큰을 더 소비한다.
- 포맷 효과는 모델·작업 의존이고 **보편 최적은 없음**. GPT-4급은 마크다운 선호, 큰 모델일수록 포맷 민감도 낮음. 같은 내용에 포맷만 바꿔도 일부 작업 점수가 2–3배 변동(통계적 유의).

## 2. 검색 단위 축 — grep 트레이드오프의 답은 "한 줄 압축"이 아니라 "계층"

- "한 줄에 다 있으면 grep 한 번에 맥락 / 분해하면 매칭 라인만 보임"은 RAG **chunk granularity** 문제와 동형: 작은 청크(분해) → 정밀 매칭·노이즈↓ / 큰 청크(한 줄에 다) → 맥락↑이지만 무관 정보 섞여 노이즈↑·정밀도↓.
- 정답은 **parent-child 계층** — 표제(parent)가 grep 앵커, sub-bullet(child)이 정밀 단위. 계층 접근은 복잡 쿼리 정밀도 **15–20%↑**. 표제+sub-bullet은 grep 앵커와 인접 맥락을 동시에 충족.

## 3. lost-in-the-middle — 통짜 다층 문장의 중간 룰은 묻힌다

- 긴 컨텍스트 중간 정보는 정확도 **30%+ 하락**(U자형 attention bias — 앞·뒤 토큰에 attention 쏠림). 한 항목에 다층 정보를 압축하면 중간 sub-rule이 묻힌다. 표제로 핵심을 앞에 두고 sub-bullet로 분리하면 각 항목이 자기 시작점에 핵심을 둔다.

## 핵심 인사이트

- "압축 = 줄 수 줄이기"는 틀렸다. 분해(줄 수 ↑)가 오히려 토큰을 줄인다 — 연결어 제거 때문. 한 줄 산문 압축은 prose화라 토큰↑·노이즈↑.
- grep 맥락 우려는 한 줄 압축이 아니라 *계층*으로 푼다. AI는 표제에 grep 매칭 후 그 블록을 읽으므로, 표제(앵커)+sub-bullet(정밀)이 정밀도와 맥락을 동시에 만족.

## 적용 기준

- **측정은 토큰 밀도, 줄 수는 중립** — 줄 수 감소는 목표가 아님. 한 줄 이어붙이기는 안티패턴.
- **한 항목 = 한 의미 단위** — 과분해(한 룰을 억지로 여러 줄로 쪼개 맥락 끊기)도 노이즈. 분해 단위는 *의미*지 *줄*이 아님.
- **다층 정보 = 계층 분해** — 통짜 paragraph는 *표제 한 줄(핵심·grep 앵커) + sub-bullet(조건·예외)*로.

## 관련 자료

- "Does Prompt Formatting Have Any Impact on LLM Performance?" (Microsoft, arXiv 2411.10541) — https://arxiv.org/html/2411.10541v1
- SearchCans, "Format Markdown for LLMs" — https://www.searchcans.com/blog/markdown-formatting-strategies-llm-understanding/
- ReleasePad, "HTML vs Markdown for LLM Ingestion" — https://www.releasepad.io/blog/html-vs-markdown-the-optimal-format-for-llm-content-ingestion/
- RagAboutIt, "The Chunking Blind Spot" — https://ragaboutit.com/the-chunking-blind-spot-why-your-rag-accuracy-collapses-when-context-boundaries-matter-most/
- Firecrawl, "Best Chunking Strategies for RAG (2026)" — https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- "Lost in the Middle" (Stanford/UW) — https://www.getmaxim.ai/articles/solving-the-lost-in-the-middle-problem-advanced-rag-techniques-for-long-context-llms/

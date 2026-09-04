---
topic: bullet 분해와 한 줄 산문 압축의 트레이드오프 — 토큰, 정확도, 검색
source: https://arxiv.org/html/2411.10541v1
---

# Prompt Formatting & Token Density for AI-Targeted Docs

## 요약

AI agent가 읽는 문서(SKILL.md, spec, CLAUDE.md)에서 *bullet 분해와 한 줄 산문 압축* 중 무엇을 고를지의 트레이드오프를 다룬다. 포맷, 검색 단위, 위치 bias가 한 방향을 가리킨다 — **장황함을 재는 단위는 줄 수가 아니라 토큰 밀도**이고, 통짜 paragraph보다 *표제 + sub-bullet 계층*이 토큰과 정확도와 검색 모두에서 낫다. "줄 수 줄이려 한 줄로 이어붙이기"는 안티패턴이다.

## 1. 포맷 — 구조화가 산문보다 토큰도 적고 정확도도 높다

- 마크다운 bullet과 heading은 prose 대비 토큰이 **10–20% 적고** 해석 오류가 **15–20% 줄었다**. 같은 정보를 한 줄 산문으로 이어붙이면 연결어("~하며", "~인 경우", "그리고")가 토큰을 더 소비한다.
- 포맷 효과는 모델과 작업에 따라 달라지고 **보편 최적은 없다**. GPT-4급은 마크다운을 선호하고, 큰 모델일수록 포맷 민감도가 낮다. 같은 내용에 포맷만 바꿔도 일부 작업 점수가 2–3배 변동했다(통계적으로 유의).

## 2. 검색 단위 — grep 트레이드오프의 답은 "한 줄 압축"이 아니라 "계층"

- "한 줄에 다 있으면 grep 한 번으로 맥락을 얻고, 분해하면 매칭 라인만 보인다"는 문제는 RAG **chunk granularity** 문제와 같은 구조다. 작은 청크(분해)는 정밀 매칭이 되고 노이즈가 줄지만, 큰 청크(한 줄에 다)는 맥락이 늘어나는 대신 무관 정보가 섞여 노이즈가 늘고 정밀도가 떨어진다.
- 답은 **parent-child 계층**이다. 표제(parent)가 grep 앵커, sub-bullet(child)이 정밀 단위다. 계층 접근은 복잡한 쿼리의 정밀도를 **15–20% 높였다**. 표제와 sub-bullet 조합은 grep 앵커와 인접 맥락을 동시에 충족한다.

## 3. lost-in-the-middle — 통짜 다층 문장의 중간 규칙은 읽히지 않는다

- 긴 컨텍스트 중간에 놓인 정보는 정확도가 **30% 넘게 떨어진다**(U자형 attention bias — 앞뒤 토큰에 attention이 쏠린다). 한 항목에 여러 층위의 정보를 압축하면 중간의 sub-rule을 모델이 놓친다. 표제로 핵심을 앞에 두고 sub-bullet으로 분리하면 각 항목이 자기 시작점에 핵심을 둔다.

## 핵심 인사이트

- "압축 = 줄 수 줄이기"는 틀렸다. 분해로 줄 수가 늘어도 연결어가 빠져 토큰은 준다. 한 줄 산문 압축은 산문이 되면서 토큰과 노이즈를 함께 늘린다.
- grep 맥락 우려는 한 줄 압축이 아니라 *계층*으로 푼다. AI는 표제에 grep으로 매칭한 뒤 그 블록을 읽으므로, 표제(앵커)와 sub-bullet(정밀)이 정밀도와 맥락을 동시에 만족한다.

## 적용 기준

- **측정 단위는 토큰 밀도, 줄 수는 판단 기준이 아니다** — 줄 수 감소는 목표가 아니다. 한 줄로 이어붙이기는 안티패턴이다.
- **한 항목 = 한 의미 단위** — 한 규칙을 억지로 여러 줄로 쪼개 맥락을 끊는 것도 노이즈다. 분해 단위는 *의미*지 *줄*이 아니다.
- **여러 층위의 정보는 계층으로 분해한다** — 통짜 paragraph는 *표제 한 줄(핵심과 grep 앵커)과 sub-bullet(조건과 예외)*으로 나눈다.

## 관련 자료

- "Does Prompt Formatting Have Any Impact on LLM Performance?" (Microsoft, arXiv 2411.10541) — <https://arxiv.org/html/2411.10541v1>
- SearchCans, "Format Markdown for LLMs" — <https://www.searchcans.com/blog/markdown-formatting-strategies-llm-understanding/>
- ReleasePad, "HTML vs Markdown for LLM Ingestion" — <https://www.releasepad.io/blog/html-vs-markdown-the-optimal-format-for-llm-content-ingestion/>
- RagAboutIt, "The Chunking Blind Spot" — <https://ragaboutit.com/the-chunking-blind-spot-why-your-rag-accuracy-collapses-when-context-boundaries-matter-most/>
- Firecrawl, "Best Chunking Strategies for RAG (2026)" — <https://www.firecrawl.dev/blog/best-chunking-strategies-rag>
- "Lost in the Middle" (Stanford/UW) — <https://www.getmaxim.ai/articles/solving-the-lost-in-the-middle-problem-advanced-rag-techniques-for-long-context-llms/>

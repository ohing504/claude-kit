"""요청이 지나가며 컨텍스트에 남긴 항목의 원장.

sqlite를 모른다 — `Request`/`ToolCall` 값만 받는다. `usage index` 경유(corpus.py)와
transcript 직독(session.py) 양쪽이 같은 코드를 돌아야 교차 검증이 성립한다.

`growth(i) = context(i+1) - context(i)`를 실측 토큰으로 쓰고, `result_chars`는 한 요청에
도구가 여럿일 때 growth를 나누는 배분 키로만 쓴다 — 자 수를 토큰으로 환산하지 않는다.
"""

from dataclasses import dataclass, field
from itertools import pairwise

from .session import Request, ToolCall

BASE = "base"
TOOL = "tool"
OUTPUT = "output"
UNATTRIBUTED = "unattributed"
COMPACTION = "compaction"


@dataclass
class Item:
    """살아 있다가 닫힌 항목 하나.

    잔존은 `size × (end_order - start_order + 1)`이다 — 그 크기로 몇 번째 요청부터 몇 번째
    요청까지 컨텍스트에 얹혀 있었는지를 곱한다.
    """

    kind: str
    size: int
    start_order: int
    end_order: int
    segment: int = 0
    tool_name: str = ""
    target: str = ""
    file_path: str = ""

    @property
    def residual(self) -> int:
        return self.size * (self.end_order - self.start_order + 1)


@dataclass
class Ledger:
    items: list[Item] = field(default_factory=list)
    eviction_events: int = 0

    @property
    def total_residual(self) -> int:
        return sum(i.residual for i in self.items)


def _close(items: list[Item], done: list[Item], end_order: int) -> None:
    for it in items:
        it.end_order = end_order
        done.append(it)


def build(
    requests: list[Request],
    tool_calls: list[ToolCall],
    boundaries: set[int] | None = None,
) -> Ledger:
    """스코프(세션, 또는 그 안의 서브에이전트 하나) 하나를 원장으로 만든다.

    `requests`는 `order_in_scope` 순으로 주행하며, 그 순서로 오지 않았으면 여기서 정렬한다.
    `boundaries`는 압축이 일어난 요청의 `order` 집합이다 — 그 자리에서 살아 있던 항목을 전부
    닫고 크기 `context(경계)`인 `compaction` 항목 하나를 새로 연다. 압축이 아닌 컨텍스트 감소는
    퇴장으로 다룬다 — 오래된 항목부터 덜어내되, `base`는 가장 나중에 손댄다.
    """
    boundaries = boundaries or set()
    reqs = sorted(requests, key=lambda r: r.order)
    if not reqs:
        return Ledger()

    calls_by_order: dict[int, list[ToolCall]] = {}
    for c in tool_calls:
        calls_by_order.setdefault(c.order, []).append(c)

    done: list[Item] = []
    segment = 0
    first = reqs[0]
    alive: list[Item] = [
        Item(
            kind=BASE,
            size=first.context,
            start_order=first.order,
            end_order=first.order,
            segment=segment,
        )
    ]
    prev_context = first.context
    eviction_events = 0

    for prev, cur in pairwise(reqs):
        if cur.order in boundaries:
            _close(alive, done, prev.order)
            segment += 1
            alive = [
                Item(
                    kind=COMPACTION,
                    size=cur.context,
                    start_order=cur.order,
                    end_order=cur.order,
                    segment=segment,
                )
            ]
            prev_context = cur.context
            continue

        growth = cur.context - prev_context
        if growth > 0:
            by_output = min(prev.output, growth)
            if by_output > 0:
                alive.append(
                    Item(
                        kind=OUTPUT,
                        size=by_output,
                        start_order=cur.order,
                        end_order=cur.order,
                        segment=segment,
                    )
                )
            by_tools = growth - by_output
            calls = calls_by_order.get(prev.order, [])
            if calls and by_tools > 0:
                total_chars = sum(c.result_chars for c in calls)
                allocated = 0
                for i, c in enumerate(calls):
                    if i == len(calls) - 1:
                        amt = by_tools - allocated
                    elif total_chars > 0:
                        amt = round(by_tools * c.result_chars / total_chars)
                        allocated += amt
                    else:
                        amt = by_tools // len(calls)
                        allocated += amt
                    if amt > 0:
                        alive.append(
                            Item(
                                kind=TOOL,
                                size=amt,
                                start_order=cur.order,
                                end_order=cur.order,
                                segment=segment,
                                tool_name=c.name,
                                target=c.target,
                                file_path=c.path,
                            )
                        )
            elif by_tools > 0:
                alive.append(
                    Item(
                        kind=UNATTRIBUTED,
                        size=by_tools,
                        start_order=cur.order,
                        end_order=cur.order,
                        segment=segment,
                    )
                )
        elif growth < 0:
            eviction_events += 1
            to_remove = -growth
            # base는 분해되지 않고 시스템 프롬프트, 지침, 메모리가 뭉쳐 있어 가장 나중에 덜어낸다.
            ordered = sorted(alive, key=lambda it: (it.kind == BASE, it.start_order))
            new_alive: list[Item] = []
            for it in ordered:
                if to_remove <= 0:
                    new_alive.append(it)
                    continue
                if it.size <= to_remove:
                    to_remove -= it.size
                    it.end_order = prev.order
                    done.append(it)
                else:
                    # 부분 퇴장 — 지금까지의 크기로 한 항목을 닫고, 남은 크기로 새 항목을 이어 연다.
                    # 그대로 크기만 줄이면 이전에 더 큰 크기로 살아 있던 구간의 잔존이 사라진다.
                    remaining = it.size - to_remove
                    it.end_order = prev.order
                    done.append(it)
                    new_alive.append(
                        Item(
                            kind=it.kind,
                            size=remaining,
                            start_order=cur.order,
                            end_order=cur.order,
                            segment=segment,
                            tool_name=it.tool_name,
                            target=it.target,
                            file_path=it.file_path,
                        )
                    )
                    to_remove = 0
            alive = new_alive
        prev_context = cur.context

    _close(alive, done, reqs[-1].order)
    return Ledger(items=done, eviction_events=eviction_events)


def thinking_diagnostic(requests: list[Request], tool_calls: list[ToolCall]) -> tuple[int, int]:
    """`thinking_tokens`가 다음 턴 컨텍스트에서 벗겨지는지 남는지, 두 가설의 오차를 잰다.

    도구 호출이 없는 요청만 본다 — growth를 tool 항목이 나눠 갖지 않아 output과 직접 댈 수
    있다. 가설을 코드(build())에 박지 않고, 요청마다의 오차 합으로만 낸다.

    가설 A(남는다): `growth ≈ output`. 가설 B(벗겨진다): `growth ≈ output − thinking`.
    반환값은 `(가설 A의 오차 합, 가설 B의 오차 합)` — 작은 쪽이 실제에 더 맞는 가설이다.
    """
    reqs = sorted(requests, key=lambda r: r.order)
    calls_by_order: dict[int, list[ToolCall]] = {}
    for c in tool_calls:
        calls_by_order.setdefault(c.order, []).append(c)

    err_kept = err_stripped = 0
    for prev, cur in pairwise(reqs):
        if calls_by_order.get(prev.order):
            continue
        growth = cur.context - prev.context
        err_kept += abs(growth - prev.output)
        err_stripped += abs(growth - (prev.output - prev.thinking))
    return err_kept, err_stripped

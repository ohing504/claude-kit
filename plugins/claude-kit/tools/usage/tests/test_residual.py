"""잔존 비용 원장(`residual.py`)이 정하는 규칙.

`잔존(item) = size × 그 항목이 컨텍스트에 남아 있던 요청 수`. 이 파일이 그 계산 규칙의 정본이다.
"""

from usage.residual import BASE, COMPACTION, OUTPUT, TOOL, UNATTRIBUTED, build, thinking_diagnostic
from usage.session import Request, ToolCall


def _req(order: int, context: int, output: int = 0, thinking: int = 0) -> Request:
    return Request(order=order, context=context, output=output, timestamp="", thinking=thinking)


def test_the_first_request_costs_its_whole_context_once() -> None:
    ledger = build([_req(1, 5_000)], [])

    assert len(ledger.items) == 1
    item = ledger.items[0]
    assert item.kind == BASE
    assert item.size == 5_000
    assert item.residual == 5_000  # 요청 한 번짜리 스코프이므로 한 번만 곱해진다


def test_growth_from_one_tool_call_becomes_that_tools_own_item() -> None:
    reqs = [_req(1, 1_000, output=100), _req(2, 1_300)]
    calls = [ToolCall(order=1, name="Read", result_chars=800, path="a.py")]

    ledger = build(reqs, calls)

    tool_items = [i for i in ledger.items if i.kind == TOOL]
    assert len(tool_items) == 1
    assert tool_items[0].size == 200  # growth(300) - output(100)
    assert tool_items[0].tool_name == "Read"
    assert tool_items[0].file_path == "a.py"


def test_growth_split_across_several_tool_calls_by_result_chars() -> None:
    reqs = [_req(1, 1_000), _req(2, 1_900)]  # growth 900, output 0
    calls = [
        ToolCall(order=1, name="Read", result_chars=600, path="a.py"),
        ToolCall(order=1, name="Read", result_chars=300, path="b.py"),
    ]

    ledger = build(reqs, calls)

    tool_items = {i.file_path: i.size for i in ledger.items if i.kind == TOOL}
    assert tool_items == {"a.py": 600, "b.py": 300}  # 2:1 비율대로 900을 나눈다


def test_output_growth_is_its_own_item_not_a_tool_result() -> None:
    reqs = [_req(1, 1_000, output=150), _req(2, 1_150)]

    ledger = build(reqs, [])

    output_items = [i for i in ledger.items if i.kind == OUTPUT]
    assert len(output_items) == 1
    assert output_items[0].size == 150
    assert not any(i.kind == TOOL for i in ledger.items)


def test_growth_with_no_explaining_tool_call_is_unattributed() -> None:
    reqs = [_req(1, 1_000), _req(2, 1_500, output=0)]  # 붙여넣기 같은, 도구 없는 성장

    ledger = build(reqs, [])

    unattributed = [i for i in ledger.items if i.kind == UNATTRIBUTED]
    assert len(unattributed) == 1
    assert unattributed[0].size == 500


def test_the_ledger_total_residual_equals_the_sum_of_context_over_all_requests() -> None:
    reqs = [_req(1, 1_000), _req(2, 1_300, output=50), _req(3, 1_100), _req(4, 1_400, output=200)]
    calls = [
        ToolCall(order=1, name="Read", result_chars=250, path="a.py"),
        ToolCall(order=3, name="Bash", result_chars=100),
    ]

    ledger = build(reqs, calls)

    assert ledger.total_residual == sum(r.context for r in reqs)


def test_a_compaction_closes_every_item_alive_at_that_point_and_opens_one_new_item() -> None:
    reqs = [_req(1, 5_000), _req(2, 5_800, output=200), _req(3, 2_000)]
    calls = [ToolCall(order=1, name="Read", result_chars=600, path="a.py")]

    ledger = build(reqs, calls, boundaries={3})

    # 경계 이전 항목은 전부 order 2에서 닫힌다
    pre_boundary = [i for i in ledger.items if i.segment == 0]
    assert all(i.end_order == 2 for i in pre_boundary)
    # 경계에서 크기 context(3)인 compaction 항목이 하나 새로 열린다
    compaction_items = [i for i in ledger.items if i.kind == COMPACTION]
    assert len(compaction_items) == 1
    assert compaction_items[0].size == 2_000
    assert compaction_items[0].start_order == 3
    assert compaction_items[0].segment == 1
    # 항등식은 압축 뒤에도 성립한다
    assert ledger.total_residual == sum(r.context for r in reqs)


def test_a_drop_in_context_without_a_compaction_evicts_the_oldest_items_first() -> None:
    reqs = [_req(1, 1_000), _req(2, 1_500), _req(3, 1_200)]  # 압축 경계 없이 300 감소
    calls = [ToolCall(order=1, name="Read", result_chars=500, path="a.py")]

    ledger = build(reqs, calls, boundaries=set())

    assert ledger.eviction_events == 1
    # base(1000, order 1)는 손대지 않고, 먼저 연 tool 항목(500, order 2)부터 깎인다
    base_items = [i for i in ledger.items if i.kind == BASE]
    assert len(base_items) == 1
    assert base_items[0].size == 1_000
    assert base_items[0].end_order == 3  # 끝까지 온전히 남는다
    tool_items = sorted((i for i in ledger.items if i.kind == TOOL), key=lambda i: i.start_order)
    assert [(i.size, i.start_order, i.end_order) for i in tool_items] == [(500, 2, 2), (200, 3, 3)]
    assert ledger.total_residual == sum(r.context for r in reqs)


def test_a_partial_eviction_splits_an_item_instead_of_losing_its_earlier_residual() -> None:
    # order 2에서 튼 tool 항목(800)이 order 3에서 300만큼 깎인다 — 남는 건 500.
    reqs = [_req(1, 1_000), _req(2, 1_800), _req(3, 1_500), _req(4, 1_500)]
    calls = [ToolCall(order=1, name="Read", result_chars=800, path="a.py")]

    ledger = build(reqs, calls, boundaries=set())

    tool_items = sorted((i for i in ledger.items if i.kind == TOOL), key=lambda i: i.start_order)
    assert len(tool_items) == 2
    first, second = tool_items
    assert (first.size, first.start_order, first.end_order) == (
        800,
        2,
        2,
    )  # 원래 크기로 order 2까지만
    assert (second.size, second.start_order, second.end_order) == (
        500,
        3,
        4,
    )  # 줄어든 크기로 이어짐
    assert ledger.total_residual == sum(r.context for r in reqs)


def test_two_equal_sized_tool_results_cost_differently_depending_on_when_they_were_called() -> None:
    # 같은 크기(500)의 도구 결과 두 개. 하나는 스코프 시작 직후, 하나는 끝나기 직전에 부른다.
    early = [_req(1, 1_000), _req(2, 1_500)] + [_req(i, 1_500) for i in range(3, 11)]
    late = [_req(1, 1_000)] + [_req(i, 1_000) for i in range(2, 10)] + [_req(10, 1_500)]
    early_calls = [ToolCall(order=1, name="Read", result_chars=500, path="a.py")]
    late_calls = [ToolCall(order=9, name="Read", result_chars=500, path="a.py")]

    early_item = next(i for i in build(early, early_calls).items if i.kind == TOOL)
    late_item = next(i for i in build(late, late_calls).items if i.kind == TOOL)

    assert early_item.size == late_item.size == 500
    assert early_item.residual > late_item.residual  # 일찍 부를수록 더 오래 남아 더 비싸다


def test_thinking_diagnostic_skips_requests_that_called_a_tool() -> None:
    # order 1이 도구를 불렀으니 growth를 tool 항목이 나눠 가져 output과 직접 못 댄다 — 뺀다.
    reqs = [_req(1, 1_000, output=100, thinking=20), _req(2, 1_300)]
    calls = [ToolCall(order=1, name="Read", result_chars=800, path="a.py")]

    err_kept, err_stripped = thinking_diagnostic(reqs, calls)

    assert (err_kept, err_stripped) == (0, 0)


def test_thinking_diagnostic_prefers_the_hypothesis_that_matches_growth() -> None:
    # growth(120) == output(120) 정확히 맞는다 — thinking을 벗기면 오히려 어긋난다.
    reqs = [_req(1, 1_000, output=120, thinking=20), _req(2, 1_120)]

    err_kept, err_stripped = thinking_diagnostic(reqs, [])

    assert err_kept == 0
    assert err_stripped == 20  # |growth - (output - thinking)| = |120 - 100|

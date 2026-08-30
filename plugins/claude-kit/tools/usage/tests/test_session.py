"""transcript에서 무엇을 어떻게 세는가 — 이 파일이 계측 규칙의 판정자다."""

import base64
import json
from pathlib import Path

import pytest

from usage.session import find_transcript, read_session


def _row(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def _assistant(usage: dict, ts: str, tools: list[str] | None = None, mid: str | None = None) -> str:
    content = [
        {"type": "tool_use", "id": f"t{i}", "name": n, "input": {}}
        for i, n in enumerate(tools or [])
    ]
    message: dict = {
        "role": "assistant",
        "model": "claude-opus-5",
        "usage": usage,
        "content": content,
    }
    if mid:
        message["id"] = mid
    return _row(type="assistant", timestamp=ts, message=message)


def _usage(read=0, write=0, out=0, inp=0, ttl_5m=None, ttl_1h=None) -> dict:
    u: dict = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    if ttl_5m is not None or ttl_1h is not None:
        u["cache_creation"] = {
            "ephemeral_5m_input_tokens": ttl_5m or 0,
            "ephemeral_1h_input_tokens": ttl_1h or 0,
        }
    return u


@pytest.fixture
def project(tmp_path: Path) -> Path:
    d = tmp_path / "projects" / "-Users-x-repo"
    d.mkdir(parents=True)
    return d


def _write_main(project: Path, session_id: str, rows: list[str]) -> Path:
    p = project / f"{session_id}.jsonl"
    p.write_text("".join(rows), encoding="utf-8")
    return p


def test_main_totals_count_only_rows_that_carry_usage(project: Path) -> None:
    """API 호출 수는 usage가 붙은 행의 개수다 — 도구 결과 행까지 세면 호출 수가 부푼다."""
    _write_main(
        project,
        "s1",
        [
            _row(
                type="user",
                timestamp="2026-08-20T12:00:00.000Z",
                message={"role": "user", "content": "안녕"},
            ),
            _assistant(_usage(read=1000, write=200, out=50), "2026-08-20T12:00:10.000Z"),
            _assistant(_usage(read=2000, write=300, out=70), "2026-08-20T12:01:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.calls == 2
    assert s.main.cache_read == 3000
    assert s.main.cache_write == 500
    assert s.main.output == 120


def test_one_response_split_across_rows_is_one_call(project: Path) -> None:
    """한 응답의 블록마다 행이 하나씩 쓰이고 그 행 전부가 같은 `usage`를 갖는다 —
    행을 세면 호출 수와 토큰이 블록 수만큼 부푼다. `message.id`가 같으면 같은 호출이다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, write=200, out=50), "2026-08-20T12:00:00.000Z", mid="m1"),
            _assistant(
                _usage(read=1000, write=200, out=50),
                "2026-08-20T12:00:01.000Z",
                tools=["Read"],
                mid="m1",
            ),
            _assistant(
                _usage(read=1000, write=200, out=50),
                "2026-08-20T12:00:02.000Z",
                tools=["Read"],
                mid="m1",
            ),
            _assistant(_usage(read=3000, write=100, out=20), "2026-08-20T12:01:00.000Z", mid="m2"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.calls == 2
    assert s.main.cache_read == 4000
    assert s.main.cache_write == 300
    assert s.main.output == 70
    assert s.main.models == {"claude-opus-5": 2}
    assert s.main.tools == {"Read": 2}  # 도구는 행마다 실재하므로 합쳐 세지 않는다


def test_cache_write_splits_by_ttl(project: Path) -> None:
    """5분 캐시와 1시간 캐시는 단가가 달라, 합계만 보면 같은 토큰 수가 다른 비용이 된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(write=1000, ttl_5m=400, ttl_1h=600), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(write=500, ttl_5m=500), "2026-08-20T12:00:30.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.cache_write == 1500
    assert s.main.cache_write_5m == 900
    assert s.main.cache_write_1h == 600


def test_duration_spans_earliest_and_latest_timestamp(project: Path) -> None:
    """행이 늘 시각 순으로 쓰이지는 않는다 — 첫 행과 마지막 행으로 재면 소요가 줄어든다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T14:30:00.000Z"),
            _row(type="system", timestamp="2026-08-20T13:00:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(150.0)


def test_tools_are_counted_by_name(project: Path) -> None:
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", tools=["Bash", "Read"]),
            _assistant(_usage(out=1), "2026-08-20T12:00:10.000Z", tools=["Bash"]),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.tools == {"Bash": 2, "Read": 1}


def test_subagents_are_counted_separately(project: Path) -> None:
    """서브에이전트는 isSidechain 레코드가 아니라 별도 파일에 있다 — 메인만 보면 통째로 빠진다."""
    _write_main(project, "s1", [_assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z")])
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _row(
            type="user",
            agentId="aaa",
            timestamp="2026-08-20T12:01:00.000Z",
            message={"role": "user", "content": "일해"},
        )
        + _assistant(
            _usage(read=5000, write=800, out=200), "2026-08-20T12:09:00.000Z", tools=["Read"]
        ),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.cache_read == 100
    assert len(s.agents) == 1
    a = s.agents[0]
    assert a.agent_id == "aaa"
    assert a.totals.calls == 1
    assert a.totals.cache_read == 5000
    assert a.totals.minutes == pytest.approx(8.0)
    assert a.totals.tools == {"Read": 1}


def test_agent_kind_and_order_come_from_the_main_transcript(project: Path) -> None:
    """어느 에이전트였는지는 서브에이전트 파일에 없다 — 메인의 Agent 호출이 그것을 갖는다."""
    launched = (
        "Async agent launched successfully.\nagentId: bbb (internal ID - do not mention to user.)"
    )
    _write_main(
        project,
        "s1",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00.000Z",
                message={
                    "role": "assistant",
                    "usage": _usage(out=1),
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "Agent",
                            "input": {
                                "subagent_type": "demo:reader-a",
                                "description": "배치 1 판독",
                            },
                        }
                    ],
                },
            ),
            _row(
                type="user",
                timestamp="2026-08-20T12:00:05.000Z",
                message={
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu1",
                            "content": [{"type": "text", "text": launched}],
                        }
                    ],
                },
            ),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-bbb.jsonl").write_text(
        _assistant(_usage(out=5), "2026-08-20T12:00:06.000Z"), encoding="utf-8"
    )
    s = read_session(find_transcript("s1", project.parent))
    a = s.agents[0]
    assert a.kind == "demo:reader-a"
    assert a.label == "배치 1 판독"
    assert a.order == 1


def test_a_nested_agent_takes_its_kind_from_its_meta_file(project: Path) -> None:
    """서브에이전트가 띄운 서브에이전트는 메인의 Agent 호출에 없다.

    그 종류와 설명은 같은 폴더의 `agent-<id>.meta.json`이 갖는다. 안 읽으면 판독 배치가
    전부 `?`로 나와 어느 배치가 무엇을 얼마나 썼는지가 사라진다.
    """
    launched = (
        "Async agent launched successfully.\nagentId: aa0 (internal ID - do not mention to user.)"
    )
    _write_main(
        project,
        "s1",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00.000Z",
                message={
                    "role": "assistant",
                    "usage": _usage(out=1),
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "Agent",
                            "input": {
                                "subagent_type": "general-purpose",
                                "description": "미디어 인덱싱",
                            },
                        }
                    ],
                },
            ),
            _row(
                type="user",
                timestamp="2026-08-20T12:00:05.000Z",
                message={
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu1",
                            "content": [{"type": "text", "text": launched}],
                        }
                    ],
                },
            ),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aa0.jsonl").write_text(
        _assistant(_usage(read=100, out=5), "2026-08-20T12:00:06.000Z"), encoding="utf-8"
    )
    (sub / "agent-bb1.jsonl").write_text(
        _assistant(_usage(read=900, out=7), "2026-08-20T12:00:20.000Z"), encoding="utf-8"
    )
    (sub / "agent-bb1.meta.json").write_text(
        json.dumps(
            {
                "agentType": "demo:reader-b",
                "description": "배치1 판독",
                "parentAgentId": "aa0",
                "spawnDepth": 2,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    kid = next(a for a in s.agents if a.agent_id == "bb1")
    assert kid.kind == "demo:reader-b"
    assert kid.label == "배치1 판독"
    assert [a.agent_id for a in s.agents] == ["aa0", "bb1"]


def test_a_nested_agent_stays_when_its_parent_is_inside_the_cut(project: Path) -> None:
    """`--until`은 구간 밖에서 뜬 에이전트를 뺀다 — 부모가 구간 안이면 그 손자도 구간 안이다."""
    launched = (
        "Async agent launched successfully.\nagentId: aa0 (internal ID - do not mention to user.)"
    )
    _write_main(
        project,
        "s1",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00.000Z",
                message={
                    "role": "assistant",
                    "usage": _usage(out=1),
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "Agent",
                            "input": {"subagent_type": "general-purpose", "description": "인덱싱"},
                        }
                    ],
                },
            ),
            _row(
                type="user",
                timestamp="2026-08-20T12:00:05.000Z",
                message={
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu1",
                            "content": [{"type": "text", "text": launched}],
                        }
                    ],
                },
            ),
            _assistant(_usage(read=10, out=1), "2026-08-20T12:00:30.000Z"),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aa0.jsonl").write_text(
        _assistant(_usage(read=100, out=5), "2026-08-20T12:00:06.000Z"), encoding="utf-8"
    )
    (sub / "agent-bb1.jsonl").write_text(
        _assistant(_usage(read=900, out=7), "2026-08-20T12:00:20.000Z"), encoding="utf-8"
    )
    (sub / "agent-bb1.meta.json").write_text(
        json.dumps({"agentType": "x", "parentAgentId": "aa0", "spawnDepth": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent), until=1)
    assert sorted(a.agent_id for a in s.agents) == ["aa0", "bb1"]


def test_a_great_grandchild_inherits_the_order_of_the_launched_ancestor(project: Path) -> None:
    """3대째는 부모도 메인의 Agent 호출에 없다 — 직계 부모만 보면 순번이 `?`가 되고

    `--until`이 그 토큰을 통째로 뺀다.
    """
    launched = (
        "Async agent launched successfully.\nagentId: aa0 (internal ID - do not mention to user.)"
    )
    _write_main(
        project,
        "s1",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00.000Z",
                message={
                    "role": "assistant",
                    "usage": _usage(out=1),
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "Agent",
                            "input": {"subagent_type": "general-purpose", "description": "인덱싱"},
                        }
                    ],
                },
            ),
            _row(
                type="user",
                timestamp="2026-08-20T12:00:05.000Z",
                message={
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu1",
                            "content": [{"type": "text", "text": launched}],
                        }
                    ],
                },
            ),
            _assistant(_usage(read=10, out=1), "2026-08-20T12:00:30.000Z"),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    for name, stamp in (("aa0", "06"), ("bb1", "20"), ("cc2", "25")):
        (sub / f"agent-{name}.jsonl").write_text(
            _assistant(_usage(read=100, out=5), f"2026-08-20T12:00:{stamp}.000Z"), encoding="utf-8"
        )
    (sub / "agent-bb1.meta.json").write_text(
        json.dumps({"agentType": "x", "parentAgentId": "aa0", "spawnDepth": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (sub / "agent-cc2.meta.json").write_text(
        json.dumps({"agentType": "y", "parentAgentId": "bb1", "spawnDepth": 3}, ensure_ascii=False),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent), until=1)
    assert sorted(a.agent_id for a in s.agents) == ["aa0", "bb1", "cc2"]
    assert {a.agent_id: a.order for a in s.agents} == {"aa0": 1, "bb1": 1, "cc2": 1}


def test_unmatched_agent_file_is_still_counted(project: Path) -> None:
    """호출을 못 찾아도 토큰은 실재한다 — 빼면 합계가 조용히 작아진다."""
    _write_main(project, "s1", [_assistant(_usage(out=1), "2026-08-20T12:00:00.000Z")])
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-ccc.jsonl").write_text(
        _assistant(_usage(read=700, out=3), "2026-08-20T12:02:00.000Z"), encoding="utf-8"
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.agents[0].kind == "?"
    assert s.agents[0].order == 0
    assert s.agents[0].totals.cache_read == 700


def test_session_is_found_across_project_slugs(tmp_path: Path) -> None:
    """세션 파일이 어느 슬러그에 들어가는지는 실행 당시 cwd가 정한다 — 저장소 슬러그에만 없다."""
    root = tmp_path / "projects"
    (root / "-Users-x-repo").mkdir(parents=True)
    other = root / "-Users-x-repo-other"
    other.mkdir(parents=True)
    (other / "s9.jsonl").write_text(
        _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z"), encoding="utf-8"
    )
    assert find_transcript("s9", root) == other / "s9.jsonl"


def test_session_is_found_by_id_prefix(tmp_path: Path) -> None:
    """세션 ID는 36자라 사람은 앞자리만 옮겨 적는다 — 그것으로 찾지 못하면 매번 find를 다시 돌린다."""
    root = tmp_path / "projects"
    project = root / "-Users-x-repo"
    project.mkdir(parents=True)
    full = project / "29c1f31a-db21-5a1b-99d8-e381ab2684a8.jsonl"
    full.write_text(_assistant(_usage(out=1), "2026-08-20T12:00:00.000Z"), encoding="utf-8")
    assert find_transcript("29c1f31a", root) == full


def test_ambiguous_prefix_names_every_match(tmp_path: Path) -> None:
    """앞자리가 같은 세션이 둘이면 아무거나 고르지 않는다 — 엉뚱한 세션의 수치로 결론이 난다."""
    root = tmp_path / "projects"
    project = root / "-Users-x-repo"
    project.mkdir(parents=True)
    for tail in ("aaaa", "bbbb"):
        (project / f"29c1f31a-{tail}.jsonl").write_text(
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z"), encoding="utf-8"
        )
    with pytest.raises(FileNotFoundError, match="29c1f31a-aaaa"):
        find_transcript("29c1f31a", root)


def test_full_id_wins_over_prefix_match(tmp_path: Path) -> None:
    """전체 ID를 준 세션이 다른 세션의 앞자리이기도 하면 그 세션 자신을 낸다."""
    root = tmp_path / "projects"
    project = root / "-Users-x-repo"
    project.mkdir(parents=True)
    exact = project / "s1.jsonl"
    for name in ("s1.jsonl", "s1-later.jsonl"):
        (project / name).write_text(
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z"), encoding="utf-8"
        )
    assert find_transcript("s1", root) == exact


def test_missing_session_names_where_it_looked(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="s404"):
        find_transcript("s404", root)


def _human(text: str, ts: str) -> str:
    return _row(
        type="user",
        timestamp=ts,
        promptSource="sdk",
        origin={"kind": "human"},
        message={"role": "user", "content": text},
    )


def test_idle_is_the_wait_before_each_human_turn(project: Path) -> None:
    """사람이 답을 쓰는 동안은 아무것도 돌지 않는다 — 소요에 섞이면 최적화 효과가 묻힌다."""
    _write_main(
        project,
        "s1",
        [
            _human("시작", "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:10:00.000Z"),
            _human("이어서", "2026-08-20T12:40:00.000Z"),  # 30분 대기
            _assistant(_usage(out=1), "2026-08-20T12:50:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(50.0)
    assert s.idle_minutes == pytest.approx(30.0)
    assert s.working_minutes == pytest.approx(20.0)


def test_first_human_turn_is_not_idle(project: Path) -> None:
    """세션의 첫 발화 앞에는 기다린 것이 없다."""
    _write_main(
        project,
        "s1",
        [
            _human("시작", "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:05:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.idle_minutes == pytest.approx(0.0)


def test_tool_results_and_notifications_are_not_human_turns(project: Path) -> None:
    """도구 결과와 완료 알림도 user 행으로 기록된다 — 그것을 대기로 세면 idle이 통째로 부푼다."""
    _write_main(
        project,
        "s1",
        [
            _human("시작", "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:01:00.000Z"),
            _row(
                type="user",
                timestamp="2026-08-20T12:20:00.000Z",
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "됨"}],
                },
            ),
            _row(
                type="user",
                timestamp="2026-08-20T12:40:00.000Z",
                promptSource="sdk",
                origin={"kind": "task-notification"},
                message={"role": "user", "content": "<task-notification>끝</task-notification>"},
            ),
            _assistant(_usage(out=1), "2026-08-20T12:41:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.idle_minutes == pytest.approx(0.0)


def test_agent_wait_for_the_next_coordinator_message_is_idle(project: Path) -> None:
    """SendMessage로 다시 부르기까지 서브에이전트는 놀고 있다 — 재호출 간격을 소요로 세면 부푼다."""
    _write_main(project, "s1", [_assistant(_usage(out=1), "2026-08-20T12:00:00.000Z")])
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-ddd.jsonl").write_text(
        _row(
            type="user",
            timestamp="2026-08-20T12:00:00.000Z",
            origin={"kind": "coordinator"},
            message={"role": "user", "content": "초안을 써라"},
        )
        + _assistant(_usage(out=5), "2026-08-20T12:10:00.000Z")
        + _row(
            type="user",
            timestamp="2026-08-20T12:40:00.000Z",  # 30분 놀았다
            origin={"kind": "coordinator"},
            message={"role": "user", "content": "지적을 반영해라"},
        )
        + _assistant(_usage(out=5), "2026-08-20T12:50:00.000Z"),
        encoding="utf-8",
    )
    t = read_session(find_transcript("s1", project.parent)).agents[0].totals
    assert t.minutes == pytest.approx(50.0)
    assert t.idle_minutes == pytest.approx(30.0)
    assert t.working_minutes == pytest.approx(20.0)


def test_broken_lines_do_not_stop_the_count(project: Path) -> None:
    """transcript는 쓰는 중에 읽힐 수 있다 — 마지막 행이 잘려도 앞의 집계는 유효하다."""
    p = _write_main(
        project, "s1", [_assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z")]
    )
    with p.open("a", encoding="utf-8") as f:
        f.write('{"type": "assistant", "mess')
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.calls == 1


def _spawned(name: str, kind: str, team: str, ts: str) -> str:
    """teammate로 뜬 서브에이전트는 Agent 도구가 아니라 이 결과로 기록된다."""
    return _row(
        type="user",
        timestamp=ts,
        toolUseResult={
            "status": "teammate_spawned",
            "agent_type": kind,
            "name": name,
            "team_name": team,
            "model": "opus",
        },
        message={"role": "user", "content": []},
    )


def test_teammate_sessions_are_counted_as_subagents(project: Path) -> None:
    """teammate로 뜬 서브에이전트는 subagents/가 아니라 top-level 세션 파일에 남는다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", mid="m1"),
            _spawned("reader-1", "demo:reader-b", "session-s1", "2026-08-20T12:00:01.000Z"),
        ],
    )
    (project / "sub9.jsonl").write_text(
        _row(
            type="user",
            teamName="session-s1",
            agentName="reader-1",
            timestamp="2026-08-20T12:00:02.000Z",
            message={"role": "user", "content": "판독해라"},
        )
        + _assistant(_usage(read=5000, write=800, out=200), "2026-08-20T12:09:00.000Z", mid="m2"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert len(s.agents) == 1
    a = s.agents[0]
    assert a.kind == "demo:reader-b"
    assert a.label == "reader-1"
    assert a.order == 1
    assert a.totals.cache_read == 5000
    assert s.combined.cache_read == 5100


def test_other_teams_sessions_are_not_counted(project: Path) -> None:
    """같은 폴더에 남의 세션이 쌓인다 — 팀명이 다르면 이 세션의 서브에이전트가 아니다."""
    _write_main(project, "s1", [_assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1")])
    (project / "남의세션.jsonl").write_text(
        _row(
            type="user",
            teamName="session-other",
            agentName="reader-1",
            timestamp="2026-08-20T12:00:02.000Z",
            message={"role": "user", "content": "일해"},
        )
        + _assistant(_usage(read=9_999_999, out=1), "2026-08-20T12:01:00.000Z", mid="m2"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.agents == []


def test_spawned_agent_without_a_transcript_is_reported(project: Path) -> None:
    """찾지 못한 서브에이전트를 알리지 않으면 합계가 조용히 작아진다 — 그것이 이 도구의 실패 방식이었다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1"),
            _spawned("reader-1", "demo:reader-b", "session-s1", "2026-08-20T12:00:01.000Z"),
            _spawned("reader-2", "demo:reader-b", "session-s1", "2026-08-20T12:00:02.000Z"),
        ],
    )
    (project / "sub9.jsonl").write_text(
        _row(
            type="user",
            teamName="session-s1",
            agentName="reader-1",
            timestamp="2026-08-20T12:00:03.000Z",
            message={"role": "user", "content": "판독해라"},
        )
        + _assistant(_usage(read=5000, out=1), "2026-08-20T12:09:00.000Z", mid="m2"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.launched == 2
    assert len(s.agents) == 1
    assert s.missing == ["reader-2"]


def test_queue_operation_marks_a_wait(project: Path) -> None:
    """사람이 큐에 넣은 자리는 그 앞이 대기다 — 작업으로 세면 실행 구간이 부푼다.

    사람이 백그라운드 에이전트를 멈추면 `user` 행이 남지만 `origin`이 없어 그것으로는 못 가른다.
    """
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1"),
            _assistant(_usage(out=1), "2026-08-20T12:07:00.000Z", mid="m2"),
            _row(
                type="queue-operation",
                operation="enqueue",
                timestamp="2026-08-20T12:29:00.000Z",
                content="멈춰",
            ),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m3"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(30.0)
    assert s.idle_minutes == pytest.approx(22.0)
    assert s.working_minutes == pytest.approx(8.0)


def test_queued_task_notifications_are_not_a_wait(project: Path) -> None:
    """서브에이전트 완료 알림도 큐를 거친다 — 그 앞은 그 에이전트가 돈 시간이지 사람을 기다린 것이 아니다.

    이 행에는 `origin`이 없어 완료 알림을 거르는 규칙이 닿지 않는다. `content`로 가른다.
    """
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1", tools=["Agent"]),
            _row(
                type="queue-operation",
                operation="enqueue",
                timestamp="2026-08-20T12:20:00.000Z",
                content="<task-notification>\n<task-id>a1</task-id>\n</task-notification>",
            ),
            _row(type="queue-operation", operation="dequeue", timestamp="2026-08-20T12:20:01.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(30.0)
    assert s.idle_minutes == pytest.approx(0.0)


def test_dequeue_and_remove_are_not_a_wait(project: Path) -> None:
    """대기는 큐에 넣기 전까지다 — 꺼내거나 지운 자리 앞은 그 항목이 큐에 있던 시간이다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1"),
            _row(type="queue-operation", operation="dequeue", timestamp="2026-08-20T12:20:00.000Z"),
            _row(type="queue-operation", operation="remove", timestamp="2026-08-20T12:25:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.idle_minutes == pytest.approx(0.0)


def test_thinking_is_split_out_of_output(project: Path) -> None:
    """thinking 블록의 본문은 transcript에 남지 않는다 — 양은 usage가 갖는다."""
    _write_main(
        project,
        "s1",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00.000Z",
                message={
                    "role": "assistant",
                    "id": "m1",
                    "model": "claude-opus-5",
                    "usage": {
                        "output_tokens": 6426,
                        "output_tokens_details": {"thinking_tokens": 2254},
                    },
                    "content": [],
                },
            ),
            _row(
                type="assistant",
                timestamp="2026-08-20T12:01:00.000Z",
                message={
                    "role": "assistant",
                    "id": "m2",
                    "model": "claude-opus-5",
                    "usage": {"output_tokens": 400},
                    "content": [],
                },
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.output == 6826
    assert s.main.thinking == 2254


def test_out_of_order_rows_do_not_inflate_idle(project: Path) -> None:
    """행이 늘 시각 순으로 쓰이지는 않는다 — 쓰인 순서로 앞 행을 고르면 시각이 거꾸로 간 자리의
    간격까지 대기로 더해져, 대기가 전체 소요를 넘고 작업 시간이 음수가 된다."""
    _write_main(
        project,
        "s1",
        [
            _human("시작", "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:50:00.000Z"),
            _row(type="system", timestamp="2026-08-20T12:01:00.000Z"),  # 늦게 쓰인 이른 행
            _human("이어서", "2026-08-20T13:00:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T13:10:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(70.0)
    assert s.idle_minutes == pytest.approx(10.0)
    assert s.working_minutes == pytest.approx(60.0)


def test_teammate_in_another_project_folder_is_counted(project: Path) -> None:
    """teammate 세션 파일은 자기 cwd가 정한 폴더에 남는다 — 메인의 폴더만 보면 통째로 빠진다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", mid="m1"),
            _spawned("reader-1", "demo:reader-b", "session-s1", "2026-08-20T12:00:01.000Z"),
        ],
    )
    other = project.parent / "-Users-x-repo-other"
    other.mkdir()
    (other / "sub9.jsonl").write_text(
        _row(
            type="user",
            teamName="session-s1",
            agentName="reader-1",
            timestamp="2026-08-20T12:00:02.000Z",
            message={"role": "user", "content": "판독해라"},
        )
        + _assistant(_usage(read=5000, out=200), "2026-08-20T12:09:00.000Z", mid="m2"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [a.label for a in s.agents] == ["reader-1"]
    assert s.combined.cache_read == 5100
    assert s.missing == []


def _jpeg(width: int, height: int) -> bytes:
    """SOF0만 든 최소 JPEG — 판독기가 가로세로를 어디서 읽는지만 검사한다."""
    return (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        + b"\xff\xd9"
    )


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )


def _tool_call(call_id: str, name: str, usage: dict, ts: str, command: str = "") -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": usage,
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": {"command": command} if command else {},
                }
            ],
        },
    )


def _result(tool_use_id: str, text: str, ts: str) -> str:
    return _row(
        type="user",
        timestamp=ts,
        message={
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": text}],
        },
    )


def _image_result(tool_use_id: str, raw: bytes, ts: str) -> str:
    return _row(
        type="user",
        timestamp=ts,
        message={
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(raw).decode(),
                            },
                        }
                    ],
                }
            ],
        },
    )


def test_context_size_is_recorded_for_each_request(project: Path) -> None:
    """요청마다 그 시점에 실린 컨텍스트를 남긴다 — 합계만으로는 어디서 커졌는지 못 본다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(
                _usage(read=10_000, write=4_000, inp=100, out=50), "2026-08-20T12:00:00.000Z"
            ),
            _assistant(
                _usage(read=20_000, write=2_000, inp=10, out=50), "2026-08-20T12:01:00.000Z"
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [r.order for r in s.main.requests] == [1, 2]
    assert [r.context for r in s.main.requests] == [14_100, 22_010]


def test_compaction_is_where_context_falls_away(project: Path) -> None:
    """압축은 쌓인 컨텍스트를 버리고 다시 시작한다 — 그 뒤 요청의 cache read가 통째로 작아진다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=200_000, out=50), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=260_000, out=50), "2026-08-20T12:01:00.000Z"),
            _assistant(_usage(read=90_000, out=50), "2026-08-20T12:02:00.000Z"),
            _assistant(_usage(read=110_000, out=50), "2026-08-20T12:03:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.compaction_at == [3]


def test_small_context_dips_are_not_compaction(project: Path) -> None:
    """세션 앞머리는 컨텍스트가 작아 오르내림이 압축과 구별되지 않는다 — 절대 크기로 거른다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=14_000, out=50), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=3_000, out=50), "2026-08-20T12:01:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.compaction_at == []


def test_result_size_goes_to_the_tool_that_produced_it(project: Path) -> None:
    """도구 결과는 `tool_use_id`로 귀속한다 — 직전 호출에 붙이면 결과가 엉뚱한 도구로 간다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("run", "Bash", _usage(read=100, out=50), "2026-08-20T12:00:00.000Z"),
            _tool_call("open", "Read", _usage(read=200, out=50), "2026-08-20T12:00:10.000Z"),
            _result("run", "짧은 출력", "2026-08-20T12:00:20.000Z"),
            _result("open", "x" * 5000, "2026-08-20T12:00:30.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.result_chars["Bash"] == len("짧은 출력")
    assert s.main.result_chars["Read"] == 5000


def test_image_results_are_counted_as_tokens_not_characters(project: Path) -> None:
    """이미지는 base64라 자 수가 크지만 토큰은 픽셀 수가 정한다 — 자 수로 세면 비중을 잘못 읽는다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("open", "Read", _usage(read=100, out=50), "2026-08-20T12:00:00.000Z"),
            _image_result("open", _jpeg(2000, 1500), "2026-08-20T12:00:10.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.images == 1
    # 2000x1500은 고해상도 계층의 긴 변 상한(2576) 안이라 축소 없이 28×28 패치 수 그대로다.
    assert s.main.image_tokens == 72 * 54
    assert "Read" not in s.main.result_chars


def test_png_dimensions_are_read_too(project: Path) -> None:
    _write_main(
        project,
        "s1",
        [
            _tool_call("open", "Read", _usage(read=100, out=50), "2026-08-20T12:00:00.000Z"),
            _image_result("open", _png(1000, 750), "2026-08-20T12:00:10.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.image_tokens == 36 * 27


def test_image_results_are_counted_on_the_agent_that_opened_them(project: Path) -> None:
    """판독 배치가 사진을 몇 장 열었고 장당 토큰이 얼마인지는 그 에이전트 행에서만 갈린다.

    메인과 합계만으로는 배치마다의 장수를 못 낸다 — 배치를 몇 장으로 끊을지가 이 값으로 정해진다.
    """
    p = _write_main(
        project,
        "s1",
        [
            _agent_call(
                "call", "reader", "판독 1", _usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"
            ),
            _result("call", "agentId: aaa 로 떴다", "2026-08-20T12:00:10.000Z"),
        ],
    )
    sub = p.parent / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _tool_call("open1", "Read", _usage(read=100, out=5), "2026-08-20T12:00:20.000Z")
        + _image_result("open1", _jpeg(2000, 1500), "2026-08-20T12:00:30.000Z")
        + _tool_call("open2", "Read", _usage(read=200, out=5), "2026-08-20T12:00:40.000Z")
        + _image_result("open2", _png(1000, 750), "2026-08-20T12:00:50.000Z"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [(a.totals.images, a.totals.image_tokens) for a in s.agents] == [(2, 72 * 54 + 36 * 27)]
    assert s.main.images == 0
    assert s.combined.images == 2


def test_until_cuts_the_count_at_that_request(project: Path) -> None:
    """두 조건은 같은 요청 수로 도달하는 지점에서 끊어야 비교된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=2000, out=20), "2026-08-20T12:01:00.000Z"),
            _assistant(_usage(read=4000, out=40), "2026-08-20T12:02:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent), until=2)
    assert s.main.calls == 2
    assert s.main.cache_read == 3000
    assert s.main.output == 30


def _agent_call(call_id: str, kind: str, label: str, usage: dict, ts: str) -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": usage,
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": "Agent",
                    "input": {"subagent_type": kind, "description": label},
                }
            ],
        },
    )


def test_until_drops_agents_launched_after_the_cut(project: Path) -> None:
    """구간 밖에서 뜬 서브에이전트를 합계에 넣으면 자른 의미가 없어진다."""
    p = _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _agent_call(
                "call-early",
                "reader",
                "이른 판독",
                _usage(read=2000, out=20),
                "2026-08-20T12:01:00.000Z",
            ),
            _result("call-early", "agentId: aaa 로 떴다", "2026-08-20T12:01:30.000Z"),
            _agent_call(
                "call-late",
                "reviewer",
                "늦은 검수",
                _usage(read=4000, out=40),
                "2026-08-20T12:02:00.000Z",
            ),
            _result("call-late", "agentId: bbb 로 떴다", "2026-08-20T12:02:30.000Z"),
        ],
    )
    sub = p.parent / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _assistant(_usage(read=500, out=5), "2026-08-20T12:01:40.000Z"), encoding="utf-8"
    )
    (sub / "agent-bbb.jsonl").write_text(
        _assistant(_usage(read=900, out=9), "2026-08-20T12:02:40.000Z"), encoding="utf-8"
    )

    whole = read_session(find_transcript("s1", project.parent))
    assert {a.agent_id for a in whole.agents} == {"aaa", "bbb"}

    cut = read_session(find_transcript("s1", project.parent), until=2)
    assert [a.agent_id for a in cut.agents] == ["aaa"]
    assert cut.combined.cache_read == 1000 + 2000 + 500


def test_each_request_records_the_tools_it_called(project: Path) -> None:
    """구간을 어디서 자를지는 위임이 난 요청 번호로 정한다 — 그 번호가 여기서만 나온다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("run", "Bash", _usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _tool_call("go", "Agent", _usage(read=2000, out=20), "2026-08-20T12:01:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [r.tools for r in s.main.requests] == [["Bash"], ["Agent"]]


def _fanout_rows() -> list[str]:
    return [
        _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z", mid="m1"),
        _assistant(_usage(read=1000, out=10), "2026-08-20T12:01:00.000Z", ["Read"], mid="m2"),
        _assistant(
            _usage(read=1000, out=10),
            "2026-08-20T12:02:00.000Z",
            ["Read", "Read", "Bash"],
            mid="m3",
        ),
        _assistant(_usage(read=1000, out=10), "2026-08-20T12:03:00.000Z", ["Bash"], mid="m4"),
    ]


def test_tools_per_request_is_split_by_how_many_one_request_carried(project: Path) -> None:
    """서로 의존하지 않는 읽기를 한 요청에 담았는지는 요청당 도구 수로만 보인다.

    도구를 하나도 부르지 않은 요청은 담을 것이 없어 분모에서 뺀다 — 넣으면 사람에게 답만 한
    요청까지 분모가 되어 준수율이 실제보다 낮게 나온다.
    """
    _write_main(project, "s1", _fanout_rows())
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.tools_per_request.spread == {1: 2, 3: 1}
    assert s.main.tools_per_request.calling == 3
    assert s.main.tools_per_request.joined == 1


def test_tools_per_request_counts_only_the_cut_section(project: Path) -> None:
    """`--until`로 자른 구간 밖의 요청을 세면 두 조건을 같은 자리에서 대조할 수 없다."""
    _write_main(project, "s1", _fanout_rows())
    s = read_session(find_transcript("s1", project.parent), until=2)
    assert s.main.tools_per_request.spread == {1: 1}
    assert s.main.tools_per_request.calling == 1
    assert s.main.tools_per_request.joined == 0


def _tool_result_row(tool_use_id: str, text: str, ts: str) -> str:
    """도구가 결과를 돌려준 행. `origin.kind`가 사람이 아니라 도구다."""
    return _row(
        type="user",
        timestamp=ts,
        origin={"kind": "tool"},
        message={
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": text}],
        },
    )


def test_elapsed_splits_into_tool_wait_and_model_time(project: Path) -> None:
    """소요를 도구가 도는 동안과 모델이 무는 동안으로 가른다 — 어느 쪽을 고칠지가 이 값으로 갈린다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("run", "Bash", _usage(read=100, out=10), "2026-08-20T12:00:00.000Z"),
            # 도구가 60초 돌았다
            _tool_result_row("run", "끝", "2026-08-20T12:01:00.000Z"),
            # 모델이 30초 물었다
            _assistant(_usage(read=200, out=20), "2026-08-20T12:01:30.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.tool_minutes == pytest.approx(1.0)
    assert s.main.model_minutes == pytest.approx(0.5)


def test_slowest_tool_calls_are_named(project: Path) -> None:
    """60초를 넘긴 도구 호출은 무엇을 기다렸는지 명령까지 낸다 — 폴링은 여기서만 보인다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("fast", "Bash", _usage(read=100, out=10), "2026-08-20T12:00:00.000Z"),
            _tool_result_row("fast", "끝", "2026-08-20T12:00:05.000Z"),
            _tool_call("slow", "Bash", _usage(read=200, out=20), "2026-08-20T12:00:10.000Z"),
            _tool_result_row("slow", "끝", "2026-08-20T12:08:10.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [(c.name, round(c.minutes, 1)) for c in s.main.slow_calls] == [("Bash", 8.0)]


def test_elapsed_ends_at_the_last_request_not_the_last_row(project: Path) -> None:
    """마지막 요청 뒤에 붙는 행은 다음 요청의 것이다 — 그것까지 세면 소요가 대기만큼 늘어난다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=2000, out=20), "2026-08-20T12:10:00.000Z"),
            _human("한참 뒤에 이어서", "2026-08-20T13:10:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(10.0)


def test_bash_calls_are_split_by_how_commands_are_joined(project: Path) -> None:
    """묶인 호출이 어디서 멈췄는지는 `;`로 이어야 출력에 남는다 — 지켜졌는지를 여기서 본다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call(
                "a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", 'echo "== 하나 =="; cat x'
            ),
            _tool_call("b", "Bash", _usage(out=1), "2026-08-20T12:00:10.000Z", "cat x && cat y"),
            _tool_call("c", "Bash", _usage(out=1), "2026-08-20T12:00:20.000Z", "ls"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.total == 3
    assert s.main.bash.joined_semicolon == 1
    assert s.main.bash.joined_and == 1
    assert s.main.bash.single == 1
    assert s.main.bash.marked == 1


def test_a_leading_cd_is_not_a_command(project: Path) -> None:
    """`cd`는 그 다음 명령이 어디서 도는지를 정할 뿐 따로 세는 명령이 아니다.

    선행 `cd`를 명령으로 세면 검사 하나를 단독으로 낸 호출이 전부 이음으로 잡혀,
    묶기 기준을 지켰는지가 출력에서 뒤집힌다.
    """
    _write_main(
        project,
        "s1",
        [
            _tool_call("a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", "cd /repo; ls"),
            _tool_call(
                "b",
                "Bash",
                _usage(out=1),
                "2026-08-20T12:00:10.000Z",
                "cd /repo && demo-cli prepare x.json",
            ),
            _tool_call(
                "c",
                "Bash",
                _usage(out=1),
                "2026-08-20T12:00:20.000Z",
                'cd /repo; echo "== 하나 =="; cat x',
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.single == 2
    assert s.main.bash.joined_and == 0
    assert s.main.bash.joined_semicolon == 1


def test_a_test_bracket_before_and_is_a_condition_not_a_join(project: Path) -> None:
    """`[ ... ] && ...`의 `&&`는 앞 명령의 성패로 갈리는 분기지 명령을 잇는 자리가 아니다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call(
                "a",
                "Bash",
                _usage(out=1),
                "2026-08-20T12:00:00.000Z",
                '[ -f source/x ] && echo "OK" || echo "없음"',
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.joined_and == 0
    assert s.main.bash.single == 1


def test_joined_counts_only_calls_that_carry_more_than_one_command(project: Path) -> None:
    """구획 마커 준수율의 분모다 — 단독 호출까지 분모에 넣으면 마커를 뺀 만큼 비율이 낮게 나온다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", "ls"),
            _tool_call(
                "b", "Bash", _usage(out=1), "2026-08-20T12:00:10.000Z", 'echo "== 하나 =="; cat x'
            ),
            _tool_call("c", "Bash", _usage(out=1), "2026-08-20T12:00:20.000Z", "cat x; cat y"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.total == 3
    assert s.main.bash.joined == 2


def test_a_marker_on_a_single_command_call_is_not_counted(project: Path) -> None:
    """마커 수는 준수율의 분자다 — 단독 호출에서 세면 분자가 분모(이은 호출)보다 커진다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call(
                "a",
                "Bash",
                _usage(out=1),
                "2026-08-20T12:00:00.000Z",
                '[ -f source/x ] && echo "== 있음 =="',
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.joined == 0
    assert s.main.bash.marked == 0


def test_a_leading_cd_joined_by_a_newline_is_not_a_command(project: Path) -> None:
    """줄바꿈으로 이은 `cd`는 `;`로 이은 것과 같은 자리다 — 한쪽만 빼면 같은 호출이 갈린다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", "cd /repo\nls"),
            _tool_call(
                "b",
                "Bash",
                _usage(out=1),
                "2026-08-20T12:00:10.000Z",
                "cd $(git rev-parse --show-toplevel) && ls",
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.single == 2
    assert s.main.bash.joined == 0


def test_a_marker_inside_a_string_is_not_a_marker(project: Path) -> None:
    """`echo`가 내는 구획 마커만 센다 — grep 패턴에 든 `==`를 마커로 세면 준수율이 부푼다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", 'grep "a == b" x'),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.marked == 0


def test_streamed_usage_takes_the_largest_value_per_message(project: Path) -> None:
    """한 응답의 행들이 늘 같은 usage를 갖지는 않는다 — 값이 누적되며 갱신되는 형식이 있다.

    첫 행만 세면 그 응답의 output이 거의 0으로 잡힌다.
    """
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=1), "2026-08-20T12:00:00.000Z", mid="m1"),
            _assistant(_usage(read=1000, out=120), "2026-08-20T12:00:05.000Z", mid="m1"),
            _assistant(_usage(read=2000, out=30), "2026-08-20T12:00:10.000Z", mid="m2"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.calls == 2
    assert s.main.output == 150
    assert s.main.cache_read == 3000


def test_oversized_image_is_counted_at_the_downscaled_size(project: Path) -> None:
    """긴 변이 상한을 넘긴 장은 축소된 뒤 세어진다 — 원본 크기로 세면 장당 토큰이 부푼다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("open", "Read", _usage(read=100, out=50), "2026-08-20T12:00:00.000Z"),
            _image_result("open", _jpeg(4000, 3000), "2026-08-20T12:00:10.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    # 4000x3000은 긴 변에 맞춰 줄여도 패치 수가 상한을 넘어 장당 토큰 천장에 걸린다.
    assert s.main.image_tokens == 4784


def test_fill_bytes_before_the_size_marker_do_not_hide_it(project: Path) -> None:
    """마커 앞 `0xFF` 채움 바이트를 길이 필드로 읽으면 SOF를 지나쳐 토큰이 0으로 잡힌다."""
    raw = _jpeg(800, 600)
    padded = raw[:2] + b"\xff\xff\xff" + raw[2:]
    _write_main(
        project,
        "s1",
        [
            _tool_call("open", "Read", _usage(read=100, out=50), "2026-08-20T12:00:00.000Z"),
            _image_result("open", padded, "2026-08-20T12:00:10.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.image_tokens == 29 * 22


def _parallel_calls(usage: dict, ts: str, ids: list[str]) -> str:
    """한 응답이 도구를 여럿 부른 행. 그 호출들은 같은 시간에 돈다."""
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": usage,
            "content": [
                {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": "ls"}}
                for i in ids
            ],
        },
    )


def test_calls_that_ran_at_the_same_time_are_counted_once(project: Path) -> None:
    """겹친 호출을 하나씩 더하면 도구 시간이 벽시계 시간을 넘고 모델 시간이 음수가 된다."""
    _write_main(
        project,
        "s1",
        [
            _parallel_calls(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", ["a", "b"]),
            _tool_result_row("a", "끝", "2026-08-20T12:02:00.000Z"),
            _tool_result_row("b", "끝", "2026-08-20T12:02:00.000Z"),
            _assistant(_usage(read=200, out=20), "2026-08-20T12:03:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.tool_minutes == pytest.approx(2.0)
    assert s.main.model_minutes == pytest.approx(1.0)


def test_tool_time_after_the_last_request_is_not_counted(project: Path) -> None:
    """소요가 마지막 요청에서 끝나므로 그 뒤로 돈 도구까지 세면 모델 시간이 음수가 된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z"),
            _tool_call("run", "Bash", _usage(read=200, out=20), "2026-08-20T12:01:00.000Z"),
            _tool_result_row("run", "끝", "2026-08-20T12:09:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(1.0)
    assert s.main.tool_minutes == pytest.approx(0.0)
    assert s.main.model_minutes == pytest.approx(1.0)


def test_a_semicolon_inside_quotes_is_not_a_join(project: Path) -> None:
    """따옴표 안의 `;`는 셸이 잇는 자리가 아니라 인자의 글자다 — 세면 준수율이 부푼다."""
    _write_main(
        project,
        "s1",
        [
            _tool_call("a", "Bash", _usage(out=1), "2026-08-20T12:00:00.000Z", "grep 'a;b' x"),
            _tool_call("b", "Bash", _usage(out=1), "2026-08-20T12:00:10.000Z", 'awk "a && b" y'),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.bash.single == 2
    assert s.main.bash.joined_semicolon == 0
    assert s.main.bash.joined_and == 0


def test_time_a_subagent_runs_is_not_main_model_time(project: Path) -> None:
    """위임한 동안 메인은 멈춰 있다 — 모델이 문 시간으로 세면 메인 프롬프트가 무거워 보인다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1", tools=["Agent"]),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-t0.jsonl").write_text(
        _assistant(_usage(out=5), "2026-08-20T12:02:00.000Z")
        + _assistant(_usage(out=5), "2026-08-20T12:22:00.000Z"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(30.0)
    assert s.main.delegated_minutes == pytest.approx(20.0)
    assert s.main.model_minutes == pytest.approx(10.0)


def test_delegated_time_does_not_double_count_the_main_tools(project: Path) -> None:
    """위임한 동안 메인이 도구를 돌리기도 한다 — 둘을 각각 더하면 모델이 문 시간이 음수가 된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1", tools=["Agent"]),
            _row(
                type="user",
                timestamp="2026-08-20T12:20:00.000Z",
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "됨"}],
                },
            ),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-t0.jsonl").write_text(
        _assistant(_usage(out=5), "2026-08-20T12:05:00.000Z")
        + _assistant(_usage(out=5), "2026-08-20T12:25:00.000Z"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.tool_minutes == pytest.approx(20.0)
    assert s.main.delegated_minutes == pytest.approx(5.0)  # 12:20~12:25만 도구 밖이다
    assert s.main.model_minutes == pytest.approx(5.0)


def test_an_enqueue_without_content_is_still_a_wait(project: Path) -> None:
    """옛 transcript의 enqueue 행에는 `content`가 없다 — 없다고 빼면 사람이 쓴 시간이 사라진다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1"),
            _row(type="queue-operation", operation="enqueue", timestamp="2026-08-20T12:20:00.000Z"),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.idle_minutes == pytest.approx(20.0)


def test_a_subagent_running_while_a_person_writes_is_not_counted_twice(project: Path) -> None:
    """사람이 답을 쓰는 동안에도 서브는 돈다 — 대기와 위임에 각각 더하면 모델이 문 시간이 음수가 된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(out=1), "2026-08-20T12:00:00.000Z", mid="m1", tools=["Agent"]),
            _row(
                type="queue-operation",
                operation="enqueue",
                timestamp="2026-08-20T12:25:00.000Z",
                content="계속",
            ),
            _assistant(_usage(out=1), "2026-08-20T12:30:00.000Z", mid="m2"),
        ],
    )
    sub = project / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-t0.jsonl").write_text(
        _assistant(_usage(out=5), "2026-08-20T12:05:00.000Z")
        + _assistant(_usage(out=5), "2026-08-20T12:20:00.000Z"),
        encoding="utf-8",
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.main.minutes == pytest.approx(30.0)
    assert s.idle_minutes == pytest.approx(25.0)
    assert s.main.delegated_minutes == pytest.approx(0.0)  # 15분 전부가 대기 안이다
    assert s.main.model_minutes == pytest.approx(5.0)


def _produced(
    ts: str,
    text: str = "",
    tool: tuple[str, dict] | None = None,
    out: int = 0,
    mid: str = "msg_a",
) -> str:
    """assistant 행 하나 — 낸 글자와 그때 기록된 output 토큰을 함께 정한다."""
    content: list[dict] = []
    if text:
        content.append({"type": "text", "text": text})
    if tool:
        content.append({"type": "tool_use", "id": "t0", "name": tool[0], "input": tool[1]})
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "id": mid,
            "usage": _usage(out=out),
            "content": content,
        },
    )


def test_produced_chars_count_text_and_tool_input(project: Path) -> None:
    said, wrote = "아홉 글자다", {"a": "bb"}
    path = _write_main(
        project,
        "s-chars",
        [
            _produced("2026-08-22T00:00:00Z", text=said, out=9),
            _produced("2026-08-22T00:00:01Z", tool=("Write", wrote), out=9),
        ],
    )
    main = read_session(path).main
    assert main.produced_chars == len(said) + len(json.dumps(wrote, ensure_ascii=False))


def test_output_tokens_are_unreliable_when_chars_far_exceed_them(project: Path) -> None:
    """서브에이전트 transcript는 큰 응답의 output_tokens가 1에서 멈춘다."""
    path = _write_main(
        project,
        "s-unreliable",
        [_produced("2026-08-22T00:00:00Z", tool=("Write", {"body": "x" * 5000}), out=1)],
    )
    main = read_session(path).main
    assert main.produced_chars > 5000
    assert main.output_reliable is False


def test_output_tokens_stay_reliable_at_a_normal_ratio(project: Path) -> None:
    path = _write_main(
        project,
        "s-reliable",
        [_produced("2026-08-22T00:00:00Z", text="가" * 300, out=200)],
    )
    main = read_session(path).main
    assert main.output_reliable is True


def test_one_stopped_response_is_not_covered_by_the_others(project: Path) -> None:
    """합계로만 재면 온전한 응답이 멈춘 응답을 덮어 자/토큰이 상한 아래로 내려간다."""
    path = _write_main(
        project,
        "s-mixed",
        [
            _produced(
                "2026-08-22T00:00:00Z",
                tool=("Write", {"body": "x" * 80000}),
                out=1,
                mid="msg_1",
            ),
            _produced("2026-08-22T00:00:01Z", text="가" * 60000, out=50000, mid="msg_2"),
        ],
    )
    main = read_session(path).main
    assert main.produced_chars < main.output * 4  # 합계로는 걸리지 않는다
    assert main.stale_requests == 1
    assert main.output_reliable is False


def _read_call(call_id: str, path: str, usage: dict, ts: str) -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": usage,
            "content": [
                {"type": "tool_use", "id": call_id, "name": "Read", "input": {"file_path": path}}
            ],
        },
    )


def test_the_same_file_opened_in_two_requests_is_counted_twice(project: Path) -> None:
    """한 편에서 같은 문서가 몇 번 컨텍스트에 올랐는지는 파일별 요청 수로만 보인다."""
    _write_main(
        project,
        "s-reads",
        [
            _read_call("a", "/w/notes-a.md", _usage(read=100, out=10), "2026-08-20T12:00:00Z"),
            _read_call("b", "/w/notes-a.md", _usage(read=200, out=10), "2026-08-20T12:01:00Z"),
            _read_call("c", "/w/guide.md", _usage(read=300, out=10), "2026-08-20T12:02:00Z"),
        ],
    )
    main = read_session(find_transcript("s-reads", project.parent)).main
    assert main.file_reads["/w/notes-a.md"] == 2
    assert main.file_reads["/w/guide.md"] == 1


def test_two_reads_of_one_file_in_one_request_are_one_context_entry(project: Path) -> None:
    """한 요청에 담아 연 것은 결과가 한 번에 실려 컨텍스트에 한 번 오른다."""
    _write_main(
        project,
        "s-reads-joined",
        [
            _row(
                type="assistant",
                timestamp="2026-08-20T12:00:00Z",
                message={
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "usage": _usage(read=100, out=10),
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "a",
                            "name": "Read",
                            "input": {"file_path": "/w/notes.md"},
                        },
                        {
                            "type": "tool_use",
                            "id": "b",
                            "name": "Read",
                            "input": {"file_path": "/w/notes.md"},
                        },
                    ],
                },
            )
        ],
    )
    main = read_session(find_transcript("s-reads-joined", project.parent)).main
    assert main.file_reads["/w/notes.md"] == 1


def _bash_call(call_id: str, command: str, usage: dict, ts: str, cwd: str = "/w") -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        cwd=cwd,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": usage,
            "content": [
                {"type": "tool_use", "id": call_id, "name": "Bash", "input": {"command": command}}
            ],
        },
    )


def test_bash_openers_count_as_opening_the_file(project: Path) -> None:
    """세션은 문서를 Read로도 열고 셸로도 연다 — 한쪽만 세면 나눠 연 자리가 안 보인다."""
    _write_main(
        project,
        "s-bash-reads",
        [
            _bash_call("a", "cat notes.md", _usage(read=100, out=10), "2026-08-20T12:00:00Z"),
            _bash_call(
                "b", "sed -n '1,25p' notes.md", _usage(read=100, out=10), "2026-08-20T12:01:00Z"
            ),
            _read_call("c", "/w/notes.md", _usage(read=100, out=10), "2026-08-20T12:02:00Z"),
        ],
    )
    main = read_session(find_transcript("s-bash-reads", project.parent)).main
    assert main.file_reads["/w/notes.md"] == 3


def test_a_leading_cd_moves_the_base_of_the_relative_path(project: Path) -> None:
    _write_main(
        project,
        "s-bash-cd",
        [
            _bash_call(
                "a",
                "cd /w/sub/dir && cat notes-a.md",
                _usage(read=100, out=10),
                "2026-08-20T12:00:00Z",
            )
        ],
    )
    main = read_session(find_transcript("s-bash-cd", project.parent)).main
    assert main.file_reads == {"/w/sub/dir/notes-a.md": 1}


def test_searching_and_writing_are_not_opening(project: Path) -> None:
    """`grep`은 맞은 줄만 결과에 실리고 리다이렉션은 파일을 쓴다 — 둘 다 전문이 오르지 않는다."""
    _write_main(
        project,
        "s-bash-nonreads",
        [
            _bash_call(
                "a", "grep -n '## ' notes.md", _usage(read=100, out=10), "2026-08-20T12:00Z"
            ),
            _bash_call("b", "wc -c notes.md", _usage(read=100, out=10), "2026-08-20T12:01Z"),
            _bash_call("c", "cat > out.md", _usage(read=100, out=10), "2026-08-20T12:02Z"),
        ],
    )
    main = read_session(find_transcript("s-bash-nonreads", project.parent)).main
    assert main.file_reads == {}


def test_stderr_redirection_does_not_hide_the_opened_file(project: Path) -> None:
    _write_main(
        project,
        "s-bash-stderr",
        [
            _bash_call(
                "a",
                "head -40 docs/pool.md 2>/dev/null",
                _usage(read=100, out=10),
                "2026-08-20T12:00Z",
            )
        ],
    )
    main = read_session(find_transcript("s-bash-stderr", project.parent)).main
    assert main.file_reads == {"/w/docs/pool.md": 1}


def test_a_relative_cd_is_resolved_against_the_row_cwd(project: Path) -> None:
    """워크스페이스로 내려가 여는 것이 흔하다 — 기준이 상대경로로 남으면 Read가 연 같은 파일과 갈린다."""
    _write_main(
        project,
        "s-bash-cd-relative",
        [
            _bash_call(
                "a",
                "cd sub/dir && cat notes-a.md",
                _usage(read=100, out=10),
                "2026-08-20T12:00:00Z",
                cwd="/repo",
            ),
            _read_call(
                "b",
                "/repo/sub/dir/notes-a.md",
                _usage(read=100, out=10),
                "2026-08-20T12:01:00Z",
            ),
        ],
    )
    main = read_session(find_transcript("s-bash-cd-relative", project.parent)).main
    assert main.file_reads == {"/repo/sub/dir/notes-a.md": 2}


def test_a_parent_segment_in_the_path_is_normalized(project: Path) -> None:
    """`../`가 남으면 같은 파일이 두 경로로 세어져 두 번 연 것이 한 번씩으로 보인다."""
    _write_main(
        project,
        "s-bash-parent",
        [
            _bash_call(
                "a",
                "cat ../notes.md",
                _usage(read=100, out=10),
                "2026-08-20T12:00:00Z",
                cwd="/w/sub",
            ),
            _read_call("b", "/w/notes.md", _usage(read=100, out=10), "2026-08-20T12:01:00Z"),
        ],
    )
    main = read_session(find_transcript("s-bash-parent", project.parent)).main
    assert main.file_reads == {"/w/notes.md": 2}


def test_since_starts_the_count_at_that_request(project: Path) -> None:
    """단계 하나만 재려면 앞 단계가 쓴 것이 합계에 들어오면 안 된다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=2000, out=20), "2026-08-20T12:01:00.000Z"),
            _assistant(_usage(read=4000, out=40), "2026-08-20T12:02:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent), since=2)
    assert s.main.calls == 2
    assert s.main.cache_read == 6000
    assert s.main.output == 60


def test_since_and_until_take_the_requests_between_them(project: Path) -> None:
    """구간은 양끝을 포함한다 — 경계 요청 자체가 그 단계를 여는 명령이다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=2000, out=20), "2026-08-20T12:01:00.000Z"),
            _assistant(_usage(read=4000, out=40), "2026-08-20T12:02:00.000Z"),
            _assistant(_usage(read=8000, out=80), "2026-08-20T12:03:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent), since=2, until=3)
    assert s.main.calls == 2
    assert s.main.cache_read == 6000


def test_since_keeps_the_request_numbers_of_the_whole_session(project: Path) -> None:
    """구간 안에서 번호를 다시 세면 `--marks`가 준 번호와 어긋나 다음 구간을 못 자른다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=1000, out=10), "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=2000, out=20), "2026-08-20T12:01:00.000Z"),
            _assistant(_usage(read=4000, out=40), "2026-08-20T12:02:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent), since=2)
    assert [r.order for r in s.main.requests] == [2, 3]


def test_since_drops_agents_launched_before_it(project: Path) -> None:
    """앞 단계가 띄운 서브에이전트를 합계에 넣으면 그 단계의 값이 이 구간에 섞인다."""
    p = _write_main(
        project,
        "s1",
        [
            _agent_call(
                "call-early",
                "reader",
                "이른 판독",
                _usage(read=1000, out=10),
                "2026-08-20T12:00:00.000Z",
            ),
            _result("call-early", "agentId: aaa 로 떴다", "2026-08-20T12:00:30.000Z"),
            _agent_call(
                "call-late",
                "reviewer",
                "늦은 검수",
                _usage(read=2000, out=20),
                "2026-08-20T12:01:00.000Z",
            ),
            _result("call-late", "agentId: bbb 로 떴다", "2026-08-20T12:01:30.000Z"),
        ],
    )
    sub = p.parent / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _assistant(_usage(read=500, out=5), "2026-08-20T12:00:40.000Z"), encoding="utf-8"
    )
    (sub / "agent-bbb.jsonl").write_text(
        _assistant(_usage(read=900, out=9), "2026-08-20T12:01:40.000Z"), encoding="utf-8"
    )

    s = read_session(find_transcript("s1", project.parent), since=2)
    assert [a.agent_id for a in s.agents] == ["bbb"]
    assert s.combined.cache_read == 2000 + 900


def _skill_call(skill: str, ts: str) -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": _usage(read=100, out=1),
            "content": [
                {"type": "tool_use", "id": "sk1", "name": "Skill", "input": {"skill": skill}}
            ],
        },
    )


def _tool_bash(command: str, ts: str) -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": _usage(read=100, out=1),
            "content": [
                {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": command}}
            ],
        },
    )


def test_marks_number_the_stage_boundary_candidates(project: Path) -> None:
    """구간을 어디서 자를지는 단계를 여는 호출이 정한다 — 그 요청 번호가 여기서만 나온다."""
    _write_main(
        project,
        "s1",
        [
            _assistant(_usage(read=100, out=1), "2026-08-20T12:00:00.000Z"),
            _skill_call("demo:stage", "2026-08-20T12:01:00.000Z"),
            _agent_call(
                "call-1",
                "demo:reader-b",
                "판독 1",
                _usage(read=100, out=1),
                "2026-08-20T12:02:00.000Z",
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert [(m.order, m.name, m.detail) for m in s.marks] == [
        (2, "Skill", "demo:stage"),
        (3, "Agent", "demo:reader-b"),
    ]


def test_marks_leave_out_shell_calls_unless_a_pattern_is_given(project: Path) -> None:
    """어느 셸 호출이 단계를 여는지는 저장소마다 다르다 — 도구가 정하면 저장소마다 고쳐야 한다."""
    _write_main(
        project,
        "s1",
        [
            _tool_bash("cat input.md", "2026-08-20T12:00:00.000Z"),
            _tool_bash(
                'uv run --project "/x/tools/alpha" alpha normalize contents/a',
                "2026-08-20T12:01:00.000Z",
            ),
        ],
    )
    s = read_session(find_transcript("s1", project.parent))
    assert s.marks == []


def test_marks_bash_pattern_joins_capture_groups_into_the_detail(project: Path) -> None:
    """패턴을 주면 그 패턴에 맞는 셸 호출만 남고, 잡은 그룹이 이름이 된다."""
    _write_main(
        project,
        "s1",
        [
            _tool_bash("cat input.md", "2026-08-20T12:00:00.000Z"),
            _tool_bash(
                'uv run --project "/x/tools/alpha" alpha normalize contents/a',
                "2026-08-20T12:01:00.000Z",
            ),
        ],
    )
    s = read_session(
        find_transcript("s1", project.parent),
        marks_bash=r"/tools/[\w-]+\"?\s+([\w-]+)\s+([\w-]+)",
    )
    assert [(m.order, m.name, m.detail) for m in s.marks] == [(2, "Bash", "alpha normalize")]


def test_marks_bash_pattern_without_groups_keeps_what_it_matched(project: Path) -> None:
    """그룹을 두지 않은 패턴도 쓸 수 있어야 한다 — 그때는 잡은 문자열이 그대로 이름이 된다."""
    _write_main(
        project,
        "s1",
        [
            _tool_bash("make deploy", "2026-08-20T12:00:00.000Z"),
            _tool_bash("cat input.md", "2026-08-20T12:01:00.000Z"),
        ],
    )
    s = read_session(find_transcript("s1", project.parent), marks_bash=r"make \w+")
    assert [(m.order, m.name, m.detail) for m in s.marks] == [(1, "Bash", "make deploy")]


def test_marks_stay_inside_the_window_but_keep_absolute_numbers(project: Path) -> None:
    """구간을 자르면 그 안의 경계만 남되 번호는 세션 전체 기준이어야 다음 구간이 이어진다."""
    _write_main(
        project,
        "s1",
        [
            _skill_call("demo:stage", "2026-08-20T12:00:00.000Z"),
            _assistant(_usage(read=100, out=1), "2026-08-20T12:01:00.000Z"),
            _tool_bash(
                'uv run --project "/x/tools/beta" beta begin contents/a',
                "2026-08-20T12:02:00.000Z",
            ),
        ],
    )
    s = read_session(
        find_transcript("s1", project.parent),
        since=2,
        marks_bash=r"/tools/[\w-]+\"?\s+([\w-]+)\s+([\w-]+)",
    )
    assert [(m.order, m.detail) for m in s.marks] == [(3, "beta begin")]

"""코퍼스를 무엇으로 쪼개 어떤 값을 담는가 — 이 파일이 적재 규칙의 판정자다."""

import json
import sqlite3
from pathlib import Path

import pytest

from usage.index import index_corpus


def _row(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def _usage(read=0, write=0, out=0, inp=0) -> dict:
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }


def _assistant(usage: dict, ts: str, mid: str, content: list | None = None) -> str:
    return _row(
        type="assistant",
        timestamp=ts,
        message={
            "role": "assistant",
            "model": "claude-opus-5",
            "id": mid,
            "usage": usage,
            "content": content or [],
        },
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    d = tmp_path / "projects"
    (d / "-Users-x-repo").mkdir(parents=True)
    return d


def _query(db: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(db) as c:
        return c.execute(sql).fetchall()


def test_a_session_becomes_one_row_with_its_requests_and_tool_calls(root: Path) -> None:
    """적재 단위는 요청 하나와 도구 호출 하나다 — 세션 집계만 담으면 지표를 새로 못 만든다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _assistant(
            _usage(read=100, write=50, out=10),
            "2026-08-20T12:00:00.000Z",
            "m1",
            [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/w/a.md"}}],
        )
        + _row(
            type="user",
            timestamp="2026-08-20T12:00:30.000Z",
            message={
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "가" * 400}],
            },
        ),
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT session_id, project_slug, status FROM sessions") == [
        ("s1", "-Users-x-repo", "ok")
    ]
    assert _query(
        db,
        "SELECT order_in_scope, model, cache_read_tokens, cache_write_tokens,"
        " output_tokens, context_tokens FROM requests",
    ) == [(1, "claude-opus-5", 100, 50, 10, 150)]
    assert _query(
        db,
        "SELECT order_in_scope, tool_name, file_path, result_chars, minutes FROM tool_calls",
    ) == [(1, "Read", "/w/a.md", 400, 0.5)]


def test_shell_command_text_is_never_stored(root: Path) -> None:
    """셸 명령 원문은 담지 않는다 — API 키와 내부 호스트명이 그대로 들어간다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _assistant(
            _usage(read=100, out=10),
            "2026-08-20T12:00:00.000Z",
            "m1",
            [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Bash",
                    "input": {"command": "curl -H 'x-api-key: sk-비밀' https://내부호스트/x"},
                }
            ],
        ),
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert "sk-비밀" not in db.read_bytes().decode("utf-8", "replace")
    assert _query(db, "SELECT tool_name, file_path FROM tool_calls") == [("Bash", "")]


def test_a_session_with_no_usage_row_is_marked_empty(root: Path) -> None:
    """수치가 한 건도 없는 파일은 오류가 아니라 잴 것이 없는 상태다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _row(type="user", timestamp="2026-08-20T12:00:00.000Z", message={"role": "user"}),
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT session_id, status FROM sessions") == [("s1", "empty")]


def test_one_unreadable_session_does_not_stop_the_rest(root: Path) -> None:
    """세션 하나가 읽히지 않아도 나머지는 적재한다 — 전체를 멈추면 코퍼스를 못 훑는다."""
    good = root / "-Users-x-repo" / "s1.jsonl"
    good.write_text(_assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"))
    (root / "-Users-x-repo" / "s2.jsonl").mkdir()
    db = root.parent / "index.db"
    report = index_corpus(root, db)
    rows = dict(_query(db, "SELECT session_id, status FROM sessions"))
    assert rows["s1"] == "ok"
    assert rows["s2"] == "error"
    assert _query(db, "SELECT error_message FROM sessions WHERE session_id = 's2'")[0][0]
    assert (report.indexed, report.failed) == (1, 1)


def test_a_line_that_is_not_json_is_skipped_not_an_error(root: Path) -> None:
    """쓰는 중인 세션은 마지막 행이 잘려 있다 — 그 행을 오류로 보면 살아 있는 세션이 전부 오류가 된다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1")
        + '{"type": "assistant", "message": {"usa',
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT status FROM sessions") == [("ok",)]
    assert _query(db, "SELECT COUNT(*) FROM requests") == [(1,)]


def test_subagent_rows_carry_their_agent_id(root: Path) -> None:
    """서브에이전트의 요청은 메인의 것과 섞이면 안 된다 — 어느 쪽이 썼는지가 위임 손익의 분모다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1")
    )
    sub = root / "-Users-x-repo" / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _assistant(_usage(read=5000, out=200), "2026-08-20T12:01:00.000Z", "m2"), encoding="utf-8"
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT agent_id, session_id, depth FROM agents") == [("aaa", "s1", 1)]
    assert _query(db, "SELECT agent_id, cache_read_tokens FROM requests ORDER BY id") == [
        (None, 100),
        ("aaa", 5000),
    ]


def test_an_unchanged_file_is_not_parsed_again(root: Path) -> None:
    """크기와 수정 시각이 그대로면 다시 파싱하지 않는다 — 코퍼스 전체를 매번 읽으면 못 쓴다."""
    p = root / "-Users-x-repo" / "s1.jsonl"
    p.write_text(_assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"))
    db = root.parent / "index.db"
    assert index_corpus(root, db).indexed == 1
    assert index_corpus(root, db).skipped == 1


def test_a_changed_file_replaces_its_old_rows(root: Path) -> None:
    """다시 읽은 세션의 옛 행은 남기지 않는다 — 남기면 같은 요청이 두 번 세어진다."""
    p = root / "-Users-x-repo" / "s1.jsonl"
    p.write_text(_assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"))
    db = root.parent / "index.db"
    index_corpus(root, db)
    p.write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1")
        + _assistant(_usage(read=200, out=20), "2026-08-20T12:01:00.000Z", "m2"),
        encoding="utf-8",
    )
    index_corpus(root, db)
    assert _query(db, "SELECT order_in_scope, cache_read_tokens FROM requests") == [
        (1, 100),
        (2, 200),
    ]


def test_a_compaction_boundary_is_marked_on_the_request(root: Path) -> None:
    """압축은 쌓인 것을 버리고 다시 시작한다 — 그 자리를 표시해야 전후를 견줄 수 있다."""
    rows = [_assistant(_usage(read=200_000, out=10), "2026-08-20T12:00:00.000Z", "m1")]
    rows.append(_assistant(_usage(read=20_000, out=10), "2026-08-20T12:01:00.000Z", "m2"))
    (root / "-Users-x-repo" / "s1.jsonl").write_text("".join(rows), encoding="utf-8")
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT order_in_scope, is_compaction_boundary FROM requests") == [
        (1, 0),
        (2, 1),
    ]


def test_a_teammate_session_is_not_stored_twice(root: Path) -> None:
    """teammate 세션 파일은 메인 세션의 agent 행으로 이미 담긴다 — 자기 세션으로 또 담으면
    코퍼스 합계에서 그 요청이 두 번 세어진다."""
    (root / "-Users-x-repo" / "abcdefgh-1111.jsonl").write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"), encoding="utf-8"
    )
    (root / "-Users-x-repo" / "teammate-0001.jsonl").write_text(
        _row(
            type="assistant",
            timestamp="2026-08-20T12:01:00.000Z",
            teamName="session-abcdefgh",
            agentName="reader-a",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "id": "m2",
                "usage": _usage(read=5000, out=200),
                "content": [],
            },
        ),
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    assert _query(db, "SELECT session_id, status FROM sessions ORDER BY session_id") == [
        ("abcdefgh-1111", "ok"),
        ("teammate-0001", "teammate"),
    ]
    assert _query(
        db, "SELECT session_id, agent_id, cache_read_tokens FROM requests ORDER BY id"
    ) == [
        ("abcdefgh-1111", None, 100),
        ("abcdefgh-1111", "teammate-0001", 5000),
    ]
    assert _query(db, "SELECT sum(cache_read_tokens) FROM requests") == [(5100,)]


def test_a_session_that_failed_to_read_is_tried_again(root: Path) -> None:
    """읽지 못한 세션은 다음 실행에서 다시 읽는다 — 크기와 시각만 보면 도구를 고쳐도 영영 error로 남는다."""
    broken = root / "-Users-x-repo" / "s1.jsonl"
    broken.mkdir()
    db = root.parent / "index.db"
    assert index_corpus(root, db).failed == 1
    assert index_corpus(root, db).failed == 1
    assert _query(db, "SELECT status FROM sessions") == [("error",)]


def test_a_grown_subagent_file_makes_its_session_be_read_again(root: Path) -> None:
    """서브에이전트가 쓴 것은 메인 세션의 행으로 담긴다 — 메인 파일만 보면 늘어난 요청이 영영 빠진다."""
    (root / "-Users-x-repo" / "s1.jsonl").write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"), encoding="utf-8"
    )
    sub = root / "-Users-x-repo" / "s1" / "subagents"
    sub.mkdir(parents=True)
    agent = sub / "agent-aaa.jsonl"
    agent.write_text(
        _assistant(_usage(read=5000, out=200), "2026-08-20T12:01:00.000Z", "m2"), encoding="utf-8"
    )
    db = root.parent / "index.db"
    index_corpus(root, db)
    agent.write_text(
        _assistant(_usage(read=5000, out=200), "2026-08-20T12:01:00.000Z", "m2")
        + _assistant(_usage(read=7000, out=300), "2026-08-20T12:02:00.000Z", "m3"),
        encoding="utf-8",
    )
    assert index_corpus(root, db).indexed == 1
    assert _query(db, "SELECT sum(cache_read_tokens) FROM requests") == [(12100,)]


def test_a_grown_teammate_file_makes_its_main_session_be_read_again(root: Path) -> None:
    """teammate가 쓴 것도 메인 세션의 행으로 담긴다 — 판정 대상은 세션 하나를 이루는 파일 전부다."""

    def teammate(*usages: tuple[str, str, dict]) -> str:
        return "".join(
            _row(
                type="assistant",
                timestamp=ts,
                teamName="session-abcdefgh",
                agentName="reader-a",
                message={
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "id": mid,
                    "usage": u,
                    "content": [],
                },
            )
            for ts, mid, u in usages
        )

    (root / "-Users-x-repo" / "abcdefgh-1111.jsonl").write_text(
        _assistant(_usage(read=100, out=10), "2026-08-20T12:00:00.000Z", "m1"), encoding="utf-8"
    )
    mate = root / "-Users-x-repo" / "teammate-0001.jsonl"
    first = ("2026-08-20T12:01:00.000Z", "m2", _usage(read=5000, out=200))
    mate.write_text(teammate(first), encoding="utf-8")
    db = root.parent / "index.db"
    index_corpus(root, db)
    mate.write_text(
        teammate(first, ("2026-08-20T12:02:00.000Z", "m3", _usage(read=7000, out=300))),
        encoding="utf-8",
    )
    index_corpus(root, db)
    assert _query(db, "SELECT sum(cache_read_tokens) FROM requests") == [(12100,)]

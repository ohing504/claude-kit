"""CLI가 무엇을 출력에 담는가."""

import base64
import json
from pathlib import Path

import pytest

from usage.cli import main


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    p = tmp_path / "s1.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 3000,
                    "cache_read_input_tokens": 2_500_000,
                    "cache_creation_input_tokens": 12_000,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 2_000,
                        "ephemeral_1h_input_tokens": 10_000,
                    },
                },
                "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
            },
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T12:30:00.000Z",
            message={"role": "assistant", "model": "claude-opus-5", "usage": {"output_tokens": 1}},
        ),
        encoding="utf-8",
    )
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-zzz.jsonl").write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:05:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-sonnet-5",
                "usage": {"output_tokens": 200, "cache_read_input_tokens": 900_000},
            },
        ),
        encoding="utf-8",
    )
    return p


def test_report_shows_main_and_subagents_and_ttl(transcript: Path, capsys) -> None:
    assert main(["session", str(transcript), "--table"]) == 0
    out = capsys.readouterr().out
    assert "메인" in out
    assert "서브 1개" in out
    assert "합계" in out
    assert "2.50M" in out  # 메인 cache read
    assert "(2.0k/10.0k)" in out  # TTL 분리
    assert "claude-opus-5 2" in out
    assert "Bash 1" in out


def test_json_gives_raw_numbers(transcript: Path, capsys) -> None:
    """단위를 줄인 표는 전후 비교에 쓸 수 없다 — 기계가 읽을 값이 따로 나와야 한다."""
    assert main(["session", str(transcript)]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["main"]["cache_read"] == 2_500_000
    assert got["main"]["cache_write_1h"] == 10_000
    assert got["agents"][0]["totals"]["cache_read"] == 900_000
    assert got["combined"]["cache_read"] == 3_400_000


def test_report_splits_model_time_from_tool_and_user_wait(tmp_path: Path, capsys) -> None:
    p = tmp_path / "s2.jsonl"
    p.write_text(
        _line(
            type="user",
            timestamp="2026-08-20T12:00:00.000Z",
            origin={"kind": "human"},
            message={"role": "user", "content": "시작"},
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T12:10:00.000Z",
            message={"role": "assistant", "model": "claude-opus-5", "usage": {"output_tokens": 1}},
        )
        + _line(
            type="user",
            timestamp="2026-08-20T13:10:00.000Z",
            origin={"kind": "human"},
            message={"role": "user", "content": "이어서"},
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T13:20:00.000Z",
            message={"role": "assistant", "model": "claude-opus-5", "usage": {"output_tokens": 1}},
        ),
        encoding="utf-8",
    )
    assert main(["session", str(p), "--table"]) == 0
    assert "모델 20.0분, 도구 0.0분, 위임 0.0분, 사용자 대기 60.0분" in capsys.readouterr().out


def test_json_carries_idle_and_working(tmp_path: Path, capsys) -> None:
    p = tmp_path / "s3.jsonl"
    p.write_text(
        _line(
            type="user",
            timestamp="2026-08-20T12:00:00.000Z",
            origin={"kind": "human"},
            message={"role": "user", "content": "시작"},
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T12:05:00.000Z",
            message={"role": "assistant", "usage": {"output_tokens": 1}},
        )
        + _line(
            type="user",
            timestamp="2026-08-20T12:35:00.000Z",
            origin={"kind": "human"},
            message={"role": "user", "content": "또"},
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T12:40:00.000Z",
            message={"role": "assistant", "usage": {"output_tokens": 1}},
        ),
        encoding="utf-8",
    )
    assert main(["session", str(p)]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["idle_minutes"] == 30.0
    assert got["working_minutes"] == 10.0


def test_unknown_session_reports_and_fails(tmp_path: Path, capsys) -> None:
    assert main(["session", str(tmp_path / "없는파일.jsonl")]) == 1
    assert "찾지 못했다" in capsys.readouterr().err


def test_until_below_one_is_rejected(tmp_path: Path, capsys) -> None:
    p = tmp_path / "s4.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={"role": "assistant", "usage": {"output_tokens": 1}},
        ),
        encoding="utf-8",
    )
    assert main(["session", str(p), "--until", "0"]) == 1
    assert "1 이상" in capsys.readouterr().err


def test_json_survives_a_finished_tool_call(tmp_path: Path, capsys) -> None:
    """도구 구간은 `datetime` 쌍이라 그대로 담으면 JSON이 나가지 못한다."""
    p = tmp_path / "s4.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"output_tokens": 1},
                "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
            },
        )
        + _line(
            type="user",
            timestamp="2026-08-20T12:05:00.000Z",
            message={
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "됨"}],
            },
        )
        + _line(
            type="assistant",
            timestamp="2026-08-20T12:10:00.000Z",
            message={"role": "assistant", "model": "claude-opus-5", "usage": {"output_tokens": 1}},
        ),
        encoding="utf-8",
    )
    assert main(["session", str(p)]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["main"]["tool_minutes"] == pytest.approx(5.0)


def test_report_shows_produced_chars_and_marks_unreliable_output(tmp_path: Path, capsys) -> None:
    """서브에이전트 transcript는 큰 응답의 `output_tokens`가 1에서 멈춘다 — 낸 글자와 함께 봐야 안다."""
    p = tmp_path / "s5.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"output_tokens": 1},
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Write", "input": {"b": "x" * 5000}}
                ],
            },
        ),
        encoding="utf-8",
    )
    assert main(["session", str(p), "--table"]) == 0
    out = capsys.readouterr().out
    assert "낸 글자" in out
    assert "5.0k" in out
    assert "1?" in out


def test_json_carries_produced_chars_for_agents(transcript: Path, capsys) -> None:
    assert main(["session", str(transcript)]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["main"]["produced_chars"] == len("{}")
    assert got["agents"][0]["totals"]["produced_chars"] == 0


def test_report_shows_the_prompt_size_and_model_on_the_subagent_row(
    transcript: Path, capsys
) -> None:
    """어느 담당에 무엇을 얼마나 실어 어느 모델로 돌렸는지는 행마다 있어야 담당끼리 견준다."""
    assert main(["session", str(transcript), "--table"]) == 0
    out = capsys.readouterr().out
    row = next(line for line in out.splitlines() if "agent-zzz" in line or "sonnet-5" in line)
    assert "sonnet-5" in row
    assert "900.0k" in row  # 첫 요청에 실린 컨텍스트 = 프롬프트 크기


def _image_transcript(tmp_path: Path) -> Path:
    """사진을 연 서브에이전트가 하나 있는 세션."""
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x11\x08"
        + (1500).to_bytes(2, "big")
        + (2000).to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        + b"\xff\xd9"
    )
    p = tmp_path / "s6.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"output_tokens": 1},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call",
                        "name": "Agent",
                        "input": {"subagent_type": "reader", "description": "판독 1"},
                    }
                ],
            },
        )
        + _line(
            type="user",
            timestamp="2026-08-20T12:00:10.000Z",
            message={
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call", "content": "agentId: aaa"}
                ],
            },
        ),
        encoding="utf-8",
    )
    sub = tmp_path / "s6" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-aaa.jsonl").write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:20.000Z",
            message={
                "role": "assistant",
                "model": "claude-sonnet-5",
                "usage": {"output_tokens": 5},
                "content": [
                    {"type": "tool_use", "id": "open", "name": "Read", "input": {"file_path": "a"}}
                ],
            },
        )
        + _line(
            type="user",
            timestamp="2026-08-20T12:00:30.000Z",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "open",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64.b64encode(jpeg).decode(),
                                },
                            }
                        ],
                    }
                ],
            },
        ),
        encoding="utf-8",
    )
    return p


def test_report_shows_images_on_the_subagent_row(tmp_path: Path, capsys) -> None:
    """배치마다 몇 장을 열었는지는 서브에이전트 행에 있어야 배치별로 읽힌다."""
    assert main(["session", str(_image_transcript(tmp_path)), "--table"]) == 0
    out = capsys.readouterr().out
    row = next(line for line in out.splitlines() if "reader" in line)
    assert "1장" in row
    assert "3.9k" in row  # 72×54 패치


def test_json_carries_images_for_agents(tmp_path: Path, capsys) -> None:
    assert main(["session", str(_image_transcript(tmp_path))]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["agents"][0]["totals"]["images"] == 1
    assert got["agents"][0]["totals"]["image_tokens"] == 72 * 54


def _fanout_transcript(tmp_path: Path) -> Path:
    def response(mid: str, ts: str, tools: list[str]) -> str:
        return _line(
            type="assistant",
            timestamp=ts,
            message={
                "role": "assistant",
                "id": mid,
                "model": "claude-opus-5",
                "usage": {"output_tokens": 1},
                "content": [
                    {"type": "tool_use", "id": f"{mid}-{i}", "name": n, "input": {}}
                    for i, n in enumerate(tools)
                ],
            },
        )

    p = tmp_path / "s7.jsonl"
    p.write_text(
        response("m1", "2026-08-20T12:00:00.000Z", ["Read"])
        + response("m2", "2026-08-20T12:01:00.000Z", ["Read", "Read", "Bash"])
        + response("m3", "2026-08-20T12:02:00.000Z", ["Bash", "Read"])
        + response("m4", "2026-08-20T12:03:00.000Z", []),
        encoding="utf-8",
    )
    return p


def test_report_shows_how_many_tools_each_request_carried(tmp_path: Path, capsys) -> None:
    assert main(["session", str(_fanout_transcript(tmp_path)), "--table"]) == 0
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("도구 담기 (메인)"))
    assert "1개 1, 2개 1, 3개 1" in line
    assert "2/3 (66%)" in line


def test_json_carries_the_tool_count_per_request(tmp_path: Path, capsys) -> None:
    assert main(["session", str(_fanout_transcript(tmp_path))]) == 0
    got = json.loads(capsys.readouterr().out)
    fan = got["main"]["tools_per_request"]
    assert fan["spread"] == {"1": 1, "2": 1, "3": 1}
    assert fan["calling"] == 3
    assert fan["joined"] == 2


def _tiny(tmp_path: Path, name: str) -> Path:
    p = tmp_path / f"{name}.jsonl"
    p.write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "usage": {"output_tokens": 1},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "s1",
                        "name": "Skill",
                        "input": {"skill": "demo:writer"},
                    }
                ],
            },
        ),
        encoding="utf-8",
    )
    return p


def test_from_below_one_is_rejected(tmp_path: Path, capsys) -> None:
    assert main(["session", str(_tiny(tmp_path, "s5")), "--from", "0"]) == 1
    assert "1 이상" in capsys.readouterr().err


def test_from_after_until_is_rejected(tmp_path: Path, capsys) -> None:
    """빈 구간을 재면 0이 나오고, 0이 개선의 근거로 읽힌다."""
    assert main(["session", str(_tiny(tmp_path, "s6")), "--from", "5", "--until", "3"]) == 1
    assert "--from" in capsys.readouterr().err


def test_marks_lists_the_boundary_candidates(tmp_path: Path, capsys) -> None:
    assert main(["session", str(_tiny(tmp_path, "s7")), "--marks"]) == 0
    out = capsys.readouterr().out
    assert "경계 후보" in out
    assert "demo:writer" in out


def test_marks_bash_without_marks_is_rejected(tmp_path: Path, capsys) -> None:
    """`--marks-bash`만 주면 아무 데도 쓰이지 않아, 준 사람은 낸 줄 알고 넘어간다."""
    assert main(["session", str(_tiny(tmp_path, "s8")), "--marks-bash", "make \\w+"]) == 1
    assert "--marks" in capsys.readouterr().err


def test_marks_bash_with_a_broken_pattern_is_rejected(tmp_path: Path, capsys) -> None:
    """정규식을 읽지 못한 채로 돌면 셸 호출이 하나도 없는 것과 같은 출력이 나온다."""
    assert main(["session", str(_tiny(tmp_path, "s9")), "--marks", "--marks-bash", "make ("]) == 1
    assert "정규식" in capsys.readouterr().err


def test_the_default_output_is_the_one_agents_parse(transcript: Path, capsys) -> None:
    """이 도구를 부르는 쪽은 대부분 에이전트다 — 사람이 읽을 표를 기본으로 두면 매번 옵션을 붙여야 한다."""
    assert main(["session", str(transcript)]) == 0
    assert json.loads(capsys.readouterr().out)["main"]["cache_read"] == 2_500_000


def test_index_builds_the_database_at_the_given_path(tmp_path: Path, capsys) -> None:
    """인덱스는 저장소 밖에 둔다 — 세션 기록에는 실제 파일 경로와 작업 내용이 들어간다."""
    root = tmp_path / "projects" / "-Users-x-repo"
    root.mkdir(parents=True)
    (root / "s1.jsonl").write_text(
        _line(
            type="assistant",
            timestamp="2026-08-20T12:00:00.000Z",
            message={
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"output_tokens": 10, "cache_read_input_tokens": 100},
                "content": [],
            },
        ),
        encoding="utf-8",
    )
    db = tmp_path / "index.db"
    assert main(["index", "--root", str(tmp_path / "projects"), "--db", str(db)]) == 0
    assert db.is_file()
    assert json.loads(capsys.readouterr().out) == {
        "db": str(db),
        "indexed": 1,
        "skipped": 0,
        "empty": 0,
        "failed": 0,
    }

"""코퍼스 전체를 SQLite 한 파일에 적재한다.

세션 파일은 읽기만 한다. 원래 위치에서 옮기지도 고치지도 않는다 — 그 파일은 Claude Code가
관리하고, 손대면 그 세션의 대화가 변질된다.

적재 단위는 요청 하나와 도구 호출 하나다. 세션 집계만 담으면 나중에 지표를 새로 만들 때
코퍼스를 다시 전부 읽어야 한다.
"""

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .session import Agent, Session, Totals, read_session, scan_teams

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id     TEXT PRIMARY KEY,
  project_slug   TEXT NOT NULL,
  file_path      TEXT NOT NULL,
  total_size     INTEGER NOT NULL,
  latest_mtime   REAL NOT NULL,
  indexed_at     TEXT NOT NULL,
  status         TEXT NOT NULL,
  error_message  TEXT
);

CREATE TABLE IF NOT EXISTS agents (
  session_id       TEXT NOT NULL,
  agent_id         TEXT NOT NULL,
  kind             TEXT NOT NULL,
  label            TEXT NOT NULL,
  parent_agent_id  TEXT NOT NULL,
  depth            INTEGER NOT NULL,
  order_in_session INTEGER NOT NULL,
  PRIMARY KEY (session_id, agent_id)
);

CREATE TABLE IF NOT EXISTS requests (
  id                     INTEGER PRIMARY KEY,
  session_id             TEXT NOT NULL,
  agent_id               TEXT,
  order_in_scope         INTEGER NOT NULL,
  timestamp              TEXT NOT NULL,
  model                  TEXT NOT NULL,
  input_tokens           INTEGER NOT NULL,
  cache_read_tokens      INTEGER NOT NULL,
  cache_write_tokens     INTEGER NOT NULL,
  output_tokens          INTEGER NOT NULL,
  produced_chars         INTEGER NOT NULL,
  context_tokens         INTEGER NOT NULL,
  is_compaction_boundary INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
  id             INTEGER PRIMARY KEY,
  session_id     TEXT NOT NULL,
  agent_id       TEXT,
  order_in_scope INTEGER NOT NULL,
  tool_name      TEXT NOT NULL,
  file_path      TEXT NOT NULL,
  result_chars   INTEGER NOT NULL,
  minutes        REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_file ON tool_calls(file_path);
"""


@dataclass
class Report:
    """한 번 돈 결과. 무엇을 다시 읽었고 무엇을 건너뛰었는지가 다음 실행의 판단 근거다."""

    indexed: int = 0
    skipped: int = 0
    empty: int = 0
    failed: int = 0
    teammate: int = 0


# 이만큼 읽을 때마다 commit한다. 매 세션 commit하면 fsync가 그만큼 늘고, 한 번에 몰면
# 중간에 멈출 때 그때까지 읽은 것이 전부 사라진다.
_COMMIT_EVERY = 200


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def _clear(conn: sqlite3.Connection, session_id: str) -> None:
    """다시 읽은 세션의 옛 행을 지운다 — 남기면 같은 요청이 두 번 세어진다."""
    for table in ("agents", "requests", "tool_calls"):
        conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))


def _put_totals(
    conn: sqlite3.Connection,
    session_id: str,
    agent_id: str | None,
    totals: Totals,
    boundaries: set[int],
) -> None:
    conn.executemany(
        "INSERT INTO requests (session_id, agent_id, order_in_scope, timestamp, model,"
        " input_tokens, cache_read_tokens, cache_write_tokens, output_tokens, produced_chars,"
        " context_tokens, is_compaction_boundary)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                session_id,
                agent_id,
                r.order,
                r.timestamp,
                r.model,
                r.input,
                r.cache_read,
                r.cache_write,
                r.output,
                r.produced_chars,
                r.context,
                int(r.order in boundaries),
            )
            for r in totals.requests
        ],
    )
    conn.executemany(
        "INSERT INTO tool_calls (session_id, agent_id, order_in_scope, tool_name, file_path,"
        " result_chars, minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (session_id, agent_id, c.order, c.name, c.path, c.result_chars, c.minutes)
            for c in totals.tool_calls
        ],
    )


def _put_agent(conn: sqlite3.Connection, session_id: str, a: Agent) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO agents (session_id, agent_id, kind, label, parent_agent_id,"
        " depth, order_in_session) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, a.agent_id, a.kind, a.label, a.parent, a.depth, a.order),
    )


def _store(conn: sqlite3.Connection, s: Session) -> None:
    boundaries = set(s.compaction_at)
    _put_totals(conn, s.session_id, None, s.main, boundaries)
    for a in s.agents:
        _put_agent(conn, s.session_id, a)
        _put_totals(conn, s.session_id, a.agent_id, a.totals, set())


def _fingerprint(path: Path, mates: Sequence[Path]) -> tuple[int, float]:
    """세션 하나를 이루는 파일 전부의 크기 합과 가장 늦은 수정 시각.

    서브에이전트와 teammate가 쓴 것은 메인 세션의 행으로 담기는데, 그 파일이 자라도 메인 파일의
    크기와 시각은 그대로다. 메인만 보면 늘어난 요청이 영영 담기지 않는다.
    """
    session_id = path.stem
    parts = [path, *sorted(path.parent.glob(f"{session_id}/subagents/**/agent-*.jsonl")), *mates]
    size, mtime = 0, 0.0
    for part in parts:
        try:
            stat = part.stat()
        except OSError:
            continue  # 읽히지 않는 파일 하나가 세션 전체의 판정을 막지 않는다
        size += stat.st_size
        mtime = max(mtime, stat.st_mtime)
    return size, mtime


def _unchanged(conn: sqlite3.Connection, session_id: str, size: int, mtime: float) -> bool:
    """다시 읽지 않아도 되는가.

    읽지 못한 세션은 크기와 시각이 그대로여도 다시 읽는다 — 파일이 아니라 도구가 원인일 수 있고,
    건너뛰면 도구를 고친 뒤에도 그 세션이 영영 `error`로 남는다.
    """
    row = conn.execute(
        "SELECT total_size, latest_mtime, status FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return False
    return bool(row[0] == size and row[1] == mtime and row[2] != "error")


def _teammate_paths(teams: Mapping[str, list[tuple[Path, str]]]) -> set[Path]:
    """다른 세션의 teammate로 이미 담기는 파일.

    teammate 세션은 `subagents/` 아래가 아니라 top-level 세션 파일로 남는다. 메인 세션의 agent
    행으로 한 번 담긴 뒤 자기 세션으로 또 담기면 코퍼스 합계에서 그 요청이 두 번 세어진다.
    팀명(`session-<메인 ID 앞 8자>`)이 가리키는 메인 세션 자신은 여기 넣지 않는다.
    """
    out: set[Path] = set()
    for team, members in teams.items():
        head = team.removeprefix("session-")
        out.update(p for p, _ in members if not p.stem.startswith(head))
    return out


def _mates_of(teams: Mapping[str, list[tuple[Path, str]]], path: Path) -> list[Path]:
    """이 세션에 붙는 teammate 파일. 팀명은 `session-<메인 ID 앞 8자>`다."""
    return [p for p, _ in teams.get(f"session-{path.stem[:8]}", ()) if p != path]


def index_corpus(root: Path, db_path: Path) -> Report:
    """`root` 아래 세션 파일을 전부 훑어 `db_path`에 적재한다.

    세션 하나를 이루는 파일 전부(메인, 서브에이전트, teammate)의 크기 합과 가장 늦은 수정
    시각이 지난번과 같으면 건너뛴다. 다르면 그 세션의 행을 전부 지우고 파일을 처음부터 다시
    읽는다 — 뒤에 붙은 행만 이어 넣으면 압축 지점과 쉰 구간의 판정이 어긋난다.

    다른 세션의 teammate인 파일은 `status='teammate'`로 두고 요청과 도구 호출을 담지 않는다.
    그 행은 메인 세션의 agent 행으로 이미 들어가 있다.

    세션 하나가 읽히지 않아도 나머지는 적재한다. 그 세션은 `status='error'`로 남는다.
    """
    report = Report()
    teams = scan_teams(root)
    teammates = _teammate_paths(teams)
    with closing(_connect(db_path)) as conn:
        done = 0
        for path in sorted(root.glob("*/*.jsonl")):
            session_id = path.stem
            if not path.is_file():
                # 세션 파일이 아닌 것은 크기를 잴 수 없다 — 읽기를 시도해 `error`로 남긴다.
                size, mtime = 0, 0.0
            else:
                size, mtime = _fingerprint(path, _mates_of(teams, path))
            if _unchanged(conn, session_id, size, mtime):
                report.skipped += 1
                continue
            _clear(conn, session_id)
            status, message = "ok", None
            if path in teammates:
                status = "teammate"
                report.teammate += 1
            else:
                try:
                    s = read_session(path, teams=teams)
                except Exception as e:  # 어떤 행이 어떻게 깨졌는지는 파일마다 다르다
                    status, message = "error", f"{type(e).__name__}: {e}"
                    report.failed += 1
                else:
                    if not s.main.requests and not s.agents:
                        status = "empty"
                        report.empty += 1
                    else:
                        report.indexed += 1
                    _store(conn, s)
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, project_slug, file_path, total_size,"
                " latest_mtime, indexed_at, status, error_message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    path.parent.name,
                    str(path),
                    size,
                    mtime,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    status,
                    message,
                ),
            )
            # 코퍼스 전체를 한 트랜잭션에 담으면 중간에 멈출 때 그때까지 읽은 것이 전부 사라진다.
            done += 1
            if done % _COMMIT_EVERY == 0:
                conn.commit()
        conn.commit()
    return report

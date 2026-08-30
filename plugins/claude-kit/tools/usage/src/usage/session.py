"""세션 transcript에서 호출 수와 토큰과 소요를 센다.

세는 규칙은 `tests/test_session.py`가 갖는다 — 여기 다시 적지 않는다.
"""

import base64
import json
import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath

_PROJECTS = Path.home() / ".claude" / "projects"
_AGENT_ID = re.compile(r"agentId:\s*([0-9a-f]+)")

# 압축을 컨텍스트 급락으로 찾는 임계값. 비율만 보면 세션 앞머리의 작은 오르내림이 걸리고,
# 절대 크기만 보면 압축이 걸리지 않는다.
_COMPACT_RATIO = 0.6
_COMPACT_FLOOR = 20_000

# 이미지 토큰은 28×28 패치 수가 정한다 — JPEG quality를 낮춰도 줄지 않는다. 긴 변이나 패치 수가
# 모델 상한을 넘으면 비율을 지켜 축소된 뒤 세어지므로 장당 토큰에 천장이 있다. 값은 고해상도
# 계층(Claude 4.7 이후) 기준이다
# (platform.claude.com/docs/en/build-with-claude/vision, 2026-08-22 조회).
_PATCH_PX = 28
_MAX_LONG_EDGE = 2576
_MAX_IMAGE_TOKENS = 4784


@dataclass
class Request:
    """요청 하나에 실린 컨텍스트. 합계만으로는 어디서 커졌고 어디서 버려졌는지 못 본다."""

    order: int
    context: int
    output: int
    timestamp: str
    tools: list[str] = field(default_factory=list)
    produced_chars: int = 0


@dataclass
class Mark:
    """단계를 여는 호출 하나. 구간을 어디서 자를지가 이 번호로 정해진다."""

    order: int
    name: str
    detail: str


@dataclass
class Call:
    """도구 호출 하나와 그 결과가 돌아오기까지의 시간."""

    name: str
    minutes: float
    detail: str = ""


@dataclass
class Bash:
    """Bash 호출을 명령을 어떻게 이었는지로 가른 수."""

    total: int = 0
    single: int = 0
    joined_semicolon: int = 0
    joined_and: int = 0
    marked: int = 0

    @property
    def joined(self) -> int:
        """명령을 둘 이상 담은 호출. 구획 마커를 요구하는 대상이자 그 준수율의 분모다."""
        return self.joined_semicolon + self.joined_and


@dataclass
class ToolsPerRequest:
    """한 요청에 도구를 몇 개 담았는지.

    도구를 하나도 부르지 않은 요청은 담을 것이 없어 세지 않는다 — 사람에게 답만 한 요청까지
    분모에 넣으면 묶기 준수율이 실제보다 낮게 나온다.
    """

    calling: int = 0
    joined: int = 0
    spread: dict[int, int] = field(default_factory=dict)


# 한 토큰이 담는 글자 수의 상한. 값이 온전한 파일에서 1.43(메인)과 0.97(teammate)이 나오고
# ASCII JSON의 이론상한이 3~4자다. 4를 넘으면 토큰 수가 그 응답의 것이 아니다.
_MAX_CHARS_PER_TOKEN = 4


@dataclass
class Totals:
    calls: int = 0
    input: int = 0
    output: int = 0
    produced_chars: int = 0
    stale_requests: int = 0
    thinking: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    minutes: float = 0.0
    idle_minutes: float = 0.0
    delegated_minutes: float = 0.0
    tools: dict[str, int] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)
    result_chars: dict[str, int] = field(default_factory=dict)
    file_reads: dict[str, int] = field(default_factory=dict)
    images: int = 0
    image_tokens: int = 0
    requests: list[Request] = field(default_factory=list)
    tool_minutes: float = 0.0
    tool_spans: list[tuple[datetime, datetime]] = field(default_factory=list)
    slow_calls: list[Call] = field(default_factory=list)
    bash: Bash = field(default_factory=Bash)
    tools_per_request: ToolsPerRequest = field(default_factory=ToolsPerRequest)

    @property
    def working_minutes(self) -> float:
        return self.minutes - self.idle_minutes

    @property
    def model_minutes(self) -> float:
        """소요에서 도구가 돈 시간과 사람을 기다린 시간과 위임한 동안을 뺀 나머지."""
        return self.minutes - self.tool_minutes - self.idle_minutes - self.delegated_minutes

    @property
    def output_reliable(self) -> bool:
        """`output`이 그 응답들이 실제로 낸 양인지.

        서브에이전트 transcript는 `output_tokens`가 스트리밍 중간 스냅샷에서 멈추고
        최종값으로 갱신되지 않는다 — 77,837자를 낸 `Write` 응답이 1로 적힌다. 낸 글자 수와
        견주면 드러나므로 자/토큰이 상한을 넘는 응답이 하나라도 있으면 거짓이다. 합계로만
        재면 온전한 응답이 그 응답을 덮는다 — 77.2k 토큰에 253.9k자인 작성 에이전트가
        자/토큰 3.29로 참이 되고, 그 파일의 응답 대부분이 1과 3에서 멈춰 있다.
        """
        return self.stale_requests == 0


@dataclass
class Agent:
    agent_id: str
    kind: str
    label: str
    order: int
    totals: Totals
    parent: str = ""
    depth: int = 1


@dataclass
class Session:
    session_id: str
    path: Path
    main: Totals
    agents: list[Agent]
    launched: int = 0
    missing: list[str] = field(default_factory=list)
    compaction_at: list[int] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)

    @property
    def idle_minutes(self) -> float:
        return self.main.idle_minutes

    @property
    def working_minutes(self) -> float:
        return self.main.working_minutes

    @property
    def combined(self) -> Totals:
        t = Totals(
            calls=self.main.calls,
            input=self.main.input,
            output=self.main.output,
            produced_chars=self.main.produced_chars,
            stale_requests=self.main.stale_requests,
            thinking=self.main.thinking,
            cache_read=self.main.cache_read,
            cache_write=self.main.cache_write,
            cache_write_5m=self.main.cache_write_5m,
            cache_write_1h=self.main.cache_write_1h,
            minutes=self.main.minutes,
            idle_minutes=self.main.idle_minutes,
            tools=dict(self.main.tools),
            models=dict(self.main.models),
            result_chars=dict(self.main.result_chars),
            images=self.main.images,
            image_tokens=self.main.image_tokens,
            requests=list(self.main.requests),
        )
        for a in self.agents:
            t.calls += a.totals.calls
            t.input += a.totals.input
            t.output += a.totals.output
            t.produced_chars += a.totals.produced_chars
            t.stale_requests += a.totals.stale_requests
            t.thinking += a.totals.thinking
            t.cache_read += a.totals.cache_read
            t.cache_write += a.totals.cache_write
            t.cache_write_5m += a.totals.cache_write_5m
            t.cache_write_1h += a.totals.cache_write_1h
            for name, n in a.totals.tools.items():
                t.tools[name] = t.tools.get(name, 0) + n
            for name, n in a.totals.models.items():
                t.models[name] = t.models.get(name, 0) + n
            for name, n in a.totals.result_chars.items():
                t.result_chars[name] = t.result_chars.get(name, 0) + n
            t.images += a.totals.images
            t.image_tokens += a.totals.image_tokens
        return t


def find_transcript(session_id: str, root: Path | None = None) -> Path:
    """세션 파일을 찾는다. 어느 프로젝트 폴더에 들어갔는지는 실행 당시 cwd가 정한다.

    전체 ID가 없으면 앞자리로 찾는다 — ID가 36자라 사람은 앞자리만 옮겨 적는다. 앞자리가 같은
    세션이 둘 이상이면 고르지 않고 그 이름들을 낸다.
    """
    base = root or _PROJECTS
    found = sorted(base.glob(f"*/{session_id}.jsonl"))
    if found:
        return found[0]
    prefixed = sorted(base.glob(f"*/{session_id}*.jsonl"))
    if len(prefixed) == 1:
        return prefixed[0]
    if prefixed:
        names = ", ".join(p.stem for p in prefixed)
        raise FileNotFoundError(f"세션 {session_id}로 시작하는 transcript가 여럿이다 — {names}")
    raise FileNotFoundError(f"{base} 아래에서 세션 {session_id}의 transcript를 찾지 못했다")


def _rows(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 쓰는 중에 읽으면 마지막 행이 잘려 있다
    return out


def _moment(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _minutes(stamps: list[str], last: str | None = None) -> float:
    """첫 행부터 마지막 요청까지.

    마지막 요청 뒤에 붙는 행은 다음 요청을 위한 것이다 — 사람이 다시 친 발화, 세션을 닫은
    기록, 재개 표시가 그렇다. 그것까지 세면 소요가 그 대기만큼 늘어난다.
    """
    if len(stamps) < 2:
        return 0.0
    moments = [_moment(s) for s in stamps]
    end = _moment(last) if last else max(moments)
    return (max(min(end, max(moments)), min(moments)) - min(moments)).total_seconds() / 60


def _pixels(raw: bytes) -> tuple[int, int] | None:
    """JPEG의 SOFn과 PNG의 IHDR에서 가로세로를 읽는다. 그 밖의 형식은 재지 않는다."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
        return (
            int.from_bytes(raw[16:20], "big"),
            int.from_bytes(raw[20:24], "big"),
        )
    if raw[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(raw):
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker == 0xFF:
            # 마커 앞의 채움 바이트다. 길이 필드로 읽으면 엉뚱한 자리로 건너뛰어 SOF를 놓친다.
            i += 1
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return (
                int.from_bytes(raw[i + 7 : i + 9], "big"),
                int.from_bytes(raw[i + 5 : i + 7], "big"),
            )
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        i += 2 + int.from_bytes(raw[i + 2 : i + 4], "big")
    return None


def _image_tokens(source: dict) -> int:
    """이미지 토큰은 픽셀 수만으로 정해진다 — base64 자 수와도 파일 크기와도 무관하다."""
    data = source.get("data")
    if not isinstance(data, str):
        return 0
    # 앞머리만 디코드한다 — 가로세로는 헤더에 있고, 전체를 디코드하면 장당 수백 KB를 만든다.
    # EXIF 썸네일이 들어가면 SOF 마커가 뒤로 밀리므로 48KB까지 본다.
    head = data[: min(len(data), 65536) // 4 * 4]
    try:
        raw = base64.b64decode(head, validate=False)
    except Exception:
        return 0
    size = _pixels(raw)
    if size is None:
        return 0
    return _patch_tokens(*size)


def _patch_tokens(width: int, height: int) -> int:
    """축소 뒤의 28×28 패치 수. 상한을 넘긴 장을 원본 크기로 세면 실제보다 크게 나온다."""
    long_edge = max(width, height)
    if long_edge > _MAX_LONG_EDGE:
        scale = _MAX_LONG_EDGE / long_edge
        width = max(1, int(width * scale))
        height = max(1, int(height * scale))
    tokens = -(-width // _PATCH_PX) * -(-height // _PATCH_PX)
    return min(tokens, _MAX_IMAGE_TOKENS)


_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _merged_usage(rows: list[dict]) -> dict[str, dict]:
    """응답 하나의 `usage`를 그 응답의 행들에서 필드마다 최댓값으로 모은다.

    한 응답이 블록마다 행 하나로 쓰이는데, 그 행들이 늘 같은 `usage`를 갖지는 않는다 —
    값이 누적되며 갱신되는 형식이 있다. 첫 행만 세면 그 응답의 output이 거의 0으로 잡힌다.
    """
    best: dict[str, dict] = {}
    for i, r in enumerate(rows):
        message = r.get("message") or {}
        u = message.get("usage")
        if not u:
            continue
        raw_id = message.get("id")
        key = str(raw_id) if raw_id is not None else f"#{i}"
        into = best.setdefault(key, {})
        for name in _USAGE_FIELDS:
            into[name] = max(into.get(name, 0), u.get(name) or 0)
        details = u.get("output_tokens_details")
        if isinstance(details, dict):
            into["thinking"] = max(into.get("thinking", 0), details.get("thinking_tokens") or 0)
        ttl = u.get("cache_creation")
        if isinstance(ttl, dict):
            into["5m"] = max(into.get("5m", 0), ttl.get("ephemeral_5m_input_tokens") or 0)
            into["1h"] = max(into.get("1h", 0), ttl.get("ephemeral_1h_input_tokens") or 0)
    return best


def _produced(t: Totals, chars: int) -> None:
    """낸 글자를 합계와 그 응답 양쪽에 더한다 — 응답마다 재야 온전한 응답이 멈춘 값을 덮지 않는다."""
    t.produced_chars += chars
    if t.requests:
        t.requests[-1].produced_chars += chars


def _tally(rows: list[dict], start: int = 0) -> Totals:
    """`start`는 이 행 목록 앞에서 이미 지나간 요청 수다 — 구간을 잘라도 번호가 세션 전체 기준이다."""
    t = Totals()
    merged = _merged_usage(rows)
    tools: Counter[str] = Counter()
    models: Counter[str] = Counter()
    chars: Counter[str] = Counter()
    reads: Counter[str] = Counter()
    # 한 요청에 담아 연 파일은 결과가 한 번에 실려 컨텍스트에 한 번 오른다 — 요청 단위로 센다.
    read_in: set[tuple[str, str]] = set()
    stamps: list[str] = []
    counted: set[str] = set()
    named: dict[str, str] = {}
    for i, r in enumerate(rows):
        if r.get("timestamp"):
            stamps.append(r["timestamp"])
        message = r.get("message") or {}
        raw_id = message.get("id")
        key = str(raw_id) if raw_id is not None else f"#{i}"
        if message.get("usage") and key not in counted:
            counted.add(key)
            u = merged[key]
            t.calls += 1
            models[str(message.get("model") or "?")] += 1
            t.input += u.get("input_tokens", 0)
            t.output += u.get("output_tokens", 0)
            t.thinking += u.get("thinking", 0)
            t.cache_read += u.get("cache_read_input_tokens", 0)
            t.cache_write += u.get("cache_creation_input_tokens", 0)
            t.cache_write_5m += u.get("5m", 0)
            t.cache_write_1h += u.get("1h", 0)
            t.requests.append(
                Request(
                    order=start + t.calls,
                    context=u.get("input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0),
                    output=u.get("output_tokens", 0),
                    timestamp=str(r.get("timestamp") or ""),
                )
            )
        answering = r.get("type") == "assistant"
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if answering and block.get("type") == "text":
                # 사람이 쓴 글자를 세지 않으려고 답한 행에서만 센다. thinking 블록은 본문이
                # 빈 문자열로 저장돼 셀 것이 없다(스키마 근거는 결정 문서).
                _produced(t, len(block.get("text") or ""))
            if block.get("type") == "tool_use":
                tools[str(block.get("name"))] += 1
                named[str(block.get("id"))] = str(block.get("name"))
                if answering:
                    _produced(t, len(json.dumps(block.get("input") or {}, ensure_ascii=False)))
                if t.requests:
                    t.requests[-1].tools.append(str(block.get("name")))
                opened: list[str] = []
                if block.get("name") == "Read":
                    opened = [str((block.get("input") or {}).get("file_path") or "")]
                if block.get("name") == "Bash":
                    command = str((block.get("input") or {}).get("command") or "")
                    _count_bash(t.bash, command)
                    opened = _opened_files(command, str(r.get("cwd") or ""))
                for path in opened:
                    if path and (key, path) not in read_in:
                        read_in.add((key, path))
                        reads[path] += 1
            elif block.get("type") == "tool_result":
                name = named.get(str(block.get("tool_use_id")), "?")
                text, images, image_tokens = _result_size(block.get("content"))
                if text:
                    chars[name] += text
                t.images += images
                t.image_tokens += image_tokens
    t.stale_requests = sum(
        1 for r in t.requests if r.produced_chars > r.output * _MAX_CHARS_PER_TOKEN
    )
    # 요청은 `--until`이 이미 자른 뒤라 구간 밖의 것이 여기 들어오지 않는다.
    spread: Counter[int] = Counter(len(r.tools) for r in t.requests if r.tools)
    t.tools_per_request = ToolsPerRequest(
        calling=sum(spread.values()),
        joined=sum(n for size, n in spread.items() if size > 1),
        spread=dict(sorted(spread.items())),
    )
    end = t.requests[-1].timestamp if t.requests else None
    t.minutes = _minutes(stamps, end)
    t.idle_minutes = _idle_minutes(rows, end)
    t.tool_minutes, t.slow_calls, t.tool_spans = _tool_time(rows, end)
    t.tools = dict(tools)
    t.models = dict(models)
    t.result_chars = dict(chars)
    t.file_reads = dict(reads)
    return t


# 파일 전문을 결과에 싣는 셸 명령. `grep`은 맞은 줄만, `wc`와 `ls`는 수와 이름만 실어
# 파일이 컨텍스트에 오르지 않는다.
_OPENER = re.compile(r"^\s*(?:cat|head|tail|sed|bat|less|more)\b")

# 확장자를 가진 토큰만 파일로 본다 — `sed -n '1,25p'`의 스크립트가 인자로 걸리지 않는다.
_PATHY = re.compile(r"[^\s'\";|]*\.(?:md|txt|json|jsonl|toml|py|yaml|yml|csv|jsonc)\b")

# `2>/dev/null`은 오류를 버리는 것이지 파일을 쓰는 리다이렉션이 아니다.
_STDERR = re.compile(r"2>(?:&\d|\S+)")


def _absolute(path: str, base: str) -> str:
    """기준 경로로 절대화하고 `.`과 `..`을 지운다 — 같은 파일이 두 경로로 세어지지 않게."""
    if not path.startswith("/"):
        path = str(PurePosixPath(base) / path)
    return posixpath.normpath(path)


def _opened_files(command: str, cwd: str) -> list[str]:
    """셸 명령이 전문을 실은 파일의 경로. 상대경로는 실행 시점의 기준 경로로 절대화한다."""
    base = cwd
    found: list[str] = []
    for raw in re.split(r"&&|\|\||\||;|\n", command):
        part = _STDERR.sub("", raw)
        cd = re.match(r"\s*cd\s+(\S+)", part)
        if cd:
            base = _absolute(cd.group(1), base)
            part = part[cd.end() :]
        if ">" in part or "<<" in part or not _OPENER.match(part):
            continue
        for token in _PATHY.findall(part):
            found.append(_absolute(token, base))
    return found


# 구획 마커는 `echo`가 내는 것만 센다 — grep 패턴에 든 `==`는 출력에 나오지 않는다.
_MARKER = re.compile(r"""echo\s+['"]?\s*==""")

# 따옴표 안의 `;`와 `&&`는 셸이 잇는 자리가 아니라 인자의 글자다 — `grep 'a;b' x`는 명령 하나다.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")

# 선행 `cd`는 다음 명령이 어디서 도는지를 정할 뿐이라 따로 세는 명령이 아니다. 경로가
# `$( ... )`로 오는 자리와 줄바꿈으로 이은 자리도 같은 `cd`다.
_LEADING_CD = re.compile(
    r"^[ \t]*cd[ \t]+(?:'[^']*'|\"[^\"]*\"|\$\([^)]*\)|\S+)[ \t]*(?:;|&&|\n)\s*"
)

# `[ ... ] && ...`와 `(( ... )) && ...`의 `&&`는 앞 명령의 성패로 갈리는 분기지 이음이 아니다.
_CONDITION_AND = re.compile(r"(?:\]\]?|\)\)) *&&")


def _count_bash(b: Bash, command: str) -> None:
    """한 호출에 명령을 몇 개 담았고 어떻게 이었는지를 센다.

    `&&`로 이으면 앞이 실패할 때 뒤가 돌지 않고 마커도 나오지 않아, 어느 명령에서 멈췄는지가
    출력에 남지 않는다.
    """
    b.total += 1
    bare = _CONDITION_AND.sub("]", _QUOTED.sub("", _LEADING_CD.sub("", command, count=1)))
    if "&&" in bare:
        b.joined_and += 1
    elif ";" in bare or "\n" in bare.strip():
        b.joined_semicolon += 1
    else:
        # 마커는 이은 호출에만 요구한다 — 단독 호출에서 세면 준수율의 분자가 분모보다 커진다.
        b.single += 1
        return
    if _MARKER.search(command):
        b.marked += 1


def _result_size(content: object) -> tuple[int, int, int]:
    """도구 결과에서 (글자 수, 이미지 장수, 이미지 토큰)을 낸다.

    이미지는 base64라 글자 수가 텍스트 결과를 압도한다. 같은 수로 세면 어느 도구가
    컨텍스트를 무엇으로 채웠는지가 뒤집힌다.
    """
    if isinstance(content, str):
        return len(content), 0, 0
    if not isinstance(content, list):
        return 0, 0, 0
    text = images = tokens = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            source = block.get("source")
            if isinstance(source, dict):
                images += 1
                tokens += _image_tokens(source)
        elif isinstance(block.get("text"), str):
            text += len(block["text"])
    return text, images, tokens


# 이보다 오래 걸린 도구 호출은 무엇을 기다렸는지 따로 낸다.
_SLOW_CALL_MINUTES = 1.0


def _tool_time(
    rows: list[dict], last: str | None = None
) -> tuple[float, list[Call], list[tuple[datetime, datetime]]]:
    """도구를 부른 시각부터 그 결과가 돌아온 시각까지가 겹치지 않게 덮은 시간.

    소요에서 이 몫을 빼야 남는 것이 모델이 문 시간이다. 둘을 섞으면 프롬프트를 줄여야 할지
    도구를 고쳐야 할지가 갈리지 않는다.

    한 응답이 도구를 여럿 부르면 그 호출들이 같은 시간에 돈다. 하나씩 더하면 합이 벽시계
    시간을 넘어 모델이 문 시간이 음수가 된다. 마지막 요청 뒤로 넘어간 몫도 뺀다 — 소요가
    거기서 끝나므로 세면 같은 일이 일어난다.
    """
    called: dict[str, tuple[str, datetime, str]] = {}
    spans: list[tuple[datetime, datetime]] = []
    slow: list[Call] = []
    for r in rows:
        stamp = r.get("timestamp")
        if not stamp:
            continue
        moment = _moment(stamp)
        for block in (r.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                i = block.get("input") or {}
                detail = str(i.get("command") or i.get("file_path") or i.get("description") or "")
                called[str(block.get("id"))] = (str(block.get("name")), moment, detail)
            elif block.get("type") == "tool_result":
                call = called.pop(str(block.get("tool_use_id")), None)
                if call is None:
                    continue
                name, started, detail = call
                minutes = (moment - started).total_seconds() / 60
                if minutes < 0:
                    continue  # 행이 시각 순으로 쓰이지 않은 자리
                spans.append((started, moment))
                if minutes >= _SLOW_CALL_MINUTES:
                    slow.append(Call(name, minutes, detail))
    slow.sort(key=lambda c: -c.minutes)
    return _covered_minutes(spans, _moment(last) if last else None), slow, spans


def _covered_minutes(spans: list[tuple[datetime, datetime]], end: datetime | None) -> float:
    """구간들이 덮은 시간의 합. 겹친 자리는 한 번만 세고, `end` 뒤는 세지 않는다."""
    merged: list[tuple[datetime, datetime]] = []
    for begin, finish in sorted(spans):
        if end is not None:
            if begin >= end:
                break
            finish = min(finish, end)
        if merged and begin <= merged[-1][1]:
            start, stop = merged[-1]
            if finish > stop:
                merged[-1] = (start, finish)
        else:
            merged.append((begin, finish))
    return sum(((stop - start).total_seconds() / 60 for start, stop in merged), 0.0)


def _queued_by_hand(row: dict) -> bool:
    """사람이 큐에 넣은 행인가. 서브에이전트 완료 알림도 같은 큐를 거쳐 같은 행으로 남는다.

    완료 알림만 뺀다 — `content`가 없는 enqueue 행도 있고(옛 transcript), 그것까지 빼면 사람이
    쓴 시간이 대기에서 빠진다.
    """
    if row.get("type") != "queue-operation" or row.get("operation") != "enqueue":
        return False
    content = row.get("content")
    return not (isinstance(content, str) and content.lstrip().startswith("<task-notification>"))


def _idle_spans(rows: list[dict], last: str | None = None) -> list[tuple[datetime, datetime]]:
    """다음 지시를 기다리며 아무것도 돌지 않은 구간.

    마지막 요청까지만 센다 — 그 뒤의 대기는 다음 요청의 것이고, 세면 대기가 소요를 넘는다.

    메인은 사람이 답을 쓰는 동안(`human`), 서브에이전트는 메인이 다시 부를 때까지
    (`coordinator`) 기다린다. 도구 결과와 완료 알림도 `user` 행이라 `origin.kind`로 가른다.
    사람이 큐에 넣은 자리(`queue-operation`의 `enqueue`)도 그 앞이 대기다 — 그 행에는
    `origin`이 없어 위 가름이 닿지 않고, `content`로 사람이 쓴 것과 완료 알림을 나눈다.
    꺼내고 지운 자리(`dequeue`, `remove`)는 그 앞이 큐에 있던 시간이라 세지 않는다.

    행 순서가 아니라 시각 순서로 잰다. 파일에 쓰인 순서는 시각 순이 아니라서, 쓰인 순서로
    앞 행을 고르면 시각이 거꾸로 간 자리의 간격까지 대기로 더해진다.
    """
    marks: list[tuple[datetime, bool]] = []
    for r in rows:
        stamp = r.get("timestamp")
        if not stamp:
            continue
        origin = r.get("origin")
        waited = (
            isinstance(origin, dict) and origin.get("kind") in ("human", "coordinator")
        ) or _queued_by_hand(r)
        marks.append((_moment(stamp), waited))
    marks.sort(key=lambda m: m[0])
    if last:
        end = _moment(last)
        marks = [m for m in marks if m[0] <= end]

    spans: list[tuple[datetime, datetime]] = []
    previous: datetime | None = None
    for moment, waited in marks:
        if waited and previous is not None:
            spans.append((previous, moment))
        previous = moment
    return spans


def _idle_minutes(rows: list[dict], last: str | None = None) -> float:
    """대기 구간의 합. 구간은 잇닿은 두 행 사이라 서로 겹치지 않는다."""
    return sum((stop - start).total_seconds() / 60 for start, stop in _idle_spans(rows, last))


def _from_meta(path: Path) -> tuple[str, str, str, int]:
    """서브에이전트가 띄운 서브에이전트의 (종류, 이름, 부모 id, 깊이).

    메인의 Agent 호출에는 손자가 없다. 그 종류와 설명은 같은 폴더의 `agent-<id>.meta.json`에만
    있어, 안 읽으면 판독 배치가 전부 `?`로 나온다.
    """
    meta_path = path.with_suffix(".meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "?", "", "", 1
    if not isinstance(meta, dict):
        return "?", "", "", 1
    try:
        depth = int(meta.get("spawnDepth") or 1)
    except (TypeError, ValueError):
        depth = 1
    return (
        str(meta.get("agentType") or "?"),
        str(meta.get("description") or ""),
        str(meta.get("parentAgentId") or ""),
        depth,
    )


def _launches(rows: list[dict]) -> dict[str, tuple[str, str, int]]:
    """메인이 띄운 서브에이전트마다 (종류, 이름, 호출 순서)를 뽑는다.

    키는 서브에이전트 파일을 찾는 방식에 따라 갈린다 — Agent 도구로 띄운 것은 `agentId`,
    teammate로 띄운 것은 `agentName`이다.
    """
    calls: dict[str, tuple[str, str]] = {}
    order = 0
    out: dict[str, tuple[str, str, int]] = {}
    for r in rows:
        spawned = r.get("toolUseResult")
        if isinstance(spawned, dict) and spawned.get("status") == "teammate_spawned":
            name = str(spawned.get("name") or "?")
            if name not in out:
                order += 1
                out[name] = (str(spawned.get("agent_type") or "?"), name, order)
        for block in (r.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Agent":
                i = block.get("input") or {}
                calls[str(block.get("id"))] = (
                    str(i.get("subagent_type") or "?"),
                    str(i.get("description") or ""),
                )
            elif block.get("type") == "tool_result":
                call = calls.get(str(block.get("tool_use_id")))
                if not call:
                    continue
                found = _AGENT_ID.search(json.dumps(block.get("content"), ensure_ascii=False))
                if found and found.group(1) not in out:
                    order += 1
                    out[found.group(1)] = (*call, order)
    return out


def _mentions(path: Path, team: str) -> bool:
    """팀명이 파일 어딘가에 있는지만 본다 — 없으면 파싱조차 하지 않는다."""
    needle = team.encode()
    with path.open("rb") as f:
        tail = b""
        while chunk := f.read(1 << 20):
            if needle in tail + chunk:
                return True
            tail = chunk[-len(needle) :]
    return False


def _member_of(path: Path, team: str) -> str | None:
    """이 파일이 그 팀의 teammate 것이면 에이전트 이름을 낸다.

    팀명이 든 행만 파싱한다 — 프로젝트 폴더 전체에 세션 파일이 수천 개 쌓이므로 전부 파싱하면 느리다.
    """
    if not _mentions(path, team):
        return None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if team not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("teamName") == team:
                return str(r.get("agentName") or "")
    return None


def _cut(rows: list[dict], until: int) -> list[dict]:
    """`until`번째 요청까지만 남긴다.

    요청 하나가 끝난 자리가 아니라 다음 요청이 시작하는 행 앞에서 자른다 — 그 사이에 오는
    도구 결과 행에 서브에이전트의 `agentId`가 들어 있어, 먼저 자르면 그 에이전트를 못 찾는다.
    """
    counted: set[str] = set()
    seen = 0
    for i, r in enumerate(rows):
        message = r.get("message") or {}
        if not message.get("usage"):
            continue
        raw_id = message.get("id")
        call_id = None if raw_id is None else str(raw_id)
        if call_id is not None and call_id in counted:
            continue
        if seen >= until:
            return rows[:i]
        if call_id is not None:
            counted.add(call_id)
        seen += 1
    return rows


def _drop(rows: list[dict], since: int) -> list[dict]:
    """`since`번째 요청이 시작하는 행부터 남긴다.

    그 앞에 오는 도구 결과 행은 앞 요청이 부른 도구의 것이라 이 구간에 넣지 않는다.
    """
    seen = 0
    counted: set[str] = set()
    for i, r in enumerate(rows):
        message = r.get("message") or {}
        if not message.get("usage"):
            continue
        raw_id = message.get("id")
        call_id = None if raw_id is None else str(raw_id)
        if call_id is not None and call_id in counted:
            continue
        seen += 1
        if seen >= since:
            return rows[i:]
        if call_id is not None:
            counted.add(call_id)
    return []


def _marks(
    rows: list[dict], start: int = 0, bash_pattern: re.Pattern[str] | None = None
) -> list[Mark]:
    """단계를 여는 호출을 요청 번호와 함께 낸다.

    `Skill`과 `Agent` 호출을 낸다. 이 둘은 Claude Code가 정한 도구 이름이므로 저장소가 무엇이든
    같은 뜻을 갖는다. 셸 호출은 `bash_pattern`을 받았을 때만, 그 정규식에 맞는 것만 낸다.
    어느 셸 명령이 단계를 여는지는 저장소마다 다르고, 그 판정을 이 함수에 적으면 저장소가 늘
    때마다 이 함수를 고쳐야 한다. 셸 호출을 조건 없이 전부 내면 한 세션에 백 건을 넘어 경계를
    고를 수 없다.

    `bash_pattern`에 잡는 그룹이 있으면 잡은 값을 공백으로 이어 이름으로 쓰고, 그룹이 없으면
    정규식에 맞은 문자열 전체를 이름으로 쓴다.

    단계 이름은 붙이지 않는다. 무엇이 어느 단계인지는 저장소마다 달라, 여기 적으면 저장소가
    늘 때마다 이 함수를 고쳐야 한다.
    """
    out: list[Mark] = []
    order = start
    counted: set[str] = set()
    for i, r in enumerate(rows):
        message = r.get("message") or {}
        raw_id = message.get("id")
        key = str(raw_id) if raw_id is not None else f"#{i}"
        if message.get("usage") and key not in counted:
            counted.add(key)
            order += 1
        if r.get("type") != "assistant":
            continue
        for block in message.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name"))
            i_ = block.get("input") or {}
            if name == "Skill":
                out.append(Mark(order, name, str(i_.get("skill") or "")))
            elif name == "Agent":
                out.append(Mark(order, name, str(i_.get("subagent_type") or "")))
            elif name == "Bash" and bash_pattern is not None:
                found = bash_pattern.search(str(i_.get("command") or ""))
                if found:
                    caught = [g for g in found.groups() if g]
                    out.append(Mark(order, name, " ".join(caught) if caught else found.group(0)))
    return out


def _compaction_at(requests: list[Request]) -> list[int]:
    """컨텍스트가 급락한 요청 순번. 압축은 쌓인 것을 버리고 다시 시작한다."""
    out: list[int] = []
    for previous, current in pairwise(requests):
        if (
            previous.context >= _COMPACT_FLOOR
            and current.context < previous.context * _COMPACT_RATIO
        ):
            out.append(current.order)
    return out


def read_session(
    path: Path,
    until: int | None = None,
    since: int | None = None,
    marks_bash: str | None = None,
) -> Session:
    session_id = path.stem
    bash_pattern = re.compile(marks_bash) if marks_bash else None
    rows = _rows(path)
    if until is not None:
        rows = _cut(rows, until)
    if since is not None:
        rows = _drop(rows, since)
    start = since - 1 if since else 0
    launches = _launches(rows)
    agents: list[Agent] = []
    # 워크플로가 띄운 에이전트는 subagents/workflows/wf_<id>/ 안에 있다 — 바로 아래만 보면 통째로 빠진다.
    for p in sorted(path.parent.glob(f"{session_id}/subagents/**/agent-*.jsonl")):
        agent_id = p.stem.removeprefix("agent-")
        parent, depth = "", 1
        if agent_id in launches:
            kind, label, order = launches[agent_id]
        else:
            kind, label, parent, depth = _from_meta(p)
            # 손자는 메인의 Agent 호출에 없다 — 부모의 순번을 물려받아 부모 뒤에 붙는다.
            order = launches.get(parent, ("", "", 0))[2]
        agents.append(Agent(agent_id, kind, label, order, _tally(_rows(p)), parent, depth))

    # 부모도 메인의 Agent 호출에 없을 수 있다(3대 이상) — 조상을 따라 올라가 순번을 찾는다.
    by_id = {a.agent_id: a for a in agents}
    for a in agents:
        if a.order or not a.parent:
            continue
        walked = {a.agent_id}
        node = by_id.get(a.parent)
        while node is not None and node.agent_id not in walked:
            walked.add(node.agent_id)
            if node.order:
                a.order = node.order
                break
            node = by_id.get(node.parent)

    # teammate는 자기 cwd가 정한 프로젝트 폴더에 남는다 — 메인과 다른 폴더에 있을 수 있어
    # 프로젝트 폴더 전체를 훑는다. 한 폴더만 보면 그 teammate의 토큰이 합계에서 빠진다.
    team = f"session-{session_id[:8]}"
    for p in sorted(path.parent.parent.glob("*/*.jsonl")):
        if p == path:
            continue
        name = _member_of(p, team)
        if name is None:
            continue
        kind, label, order = launches.get(name, ("?", name, 0))
        agents.append(Agent(p.stem, kind, label, order, _tally(_rows(p))))

    if until is not None or since is not None:
        # 구간 밖에서 뜬 서브에이전트를 합계에 넣으면 자른 의미가 없어진다.
        # 부모가 구간 안이면 그 손자도 구간 안이다.
        agents = [
            a
            for a in agents
            if a.agent_id in launches or a.label in launches or (a.parent and a.order)
        ]
    agents.sort(key=lambda a: (a.order == 0, a.order, a.depth, a.label, a.agent_id))
    found = {a.label for a in agents} | {a.agent_id for a in agents}
    missing = [name for name in launches if name not in found]
    main = _tally(rows, start)
    main.delegated_minutes = _delegated_minutes(main, agents, rows)
    return Session(
        session_id,
        path,
        main,
        agents,
        len(launches),
        missing,
        _compaction_at(main.requests),
        _marks(rows, start, bash_pattern),
    )


def _delegated_minutes(main: Totals, agents: list[Agent], rows: list[dict]) -> float:
    """서브에이전트가 돈 시간 중 메인의 도구도 돌지 않고 사람을 기다리지도 않던 몫.

    Agent 호출은 바로 돌아오고 완료는 알림으로 오므로 이 시간은 도구 시간에 잡히지 않는다.
    빼지 않으면 메인이 멈춰 있던 시간이 모델이 문 시간으로 들어가 프롬프트가 무거워 보인다.

    메인이 다른 도구를 돌리는 동안에도, 사람이 답을 쓰는 동안에도 서브가 돈다. 도구 구간과
    대기 구간을 덮은 시간을 먼저 재고 거기에 서브 구간을 더해 다시 재, 늘어난 만큼만 낸다 —
    이미 다른 이름으로 세어진 자리를 두 번 세면 모델이 문 시간이 그만큼 줄고 음수까지 간다.
    """
    last = main.requests[-1].timestamp if main.requests else None
    end = _moment(last) if last else None
    counted = main.tool_spans + _idle_spans(rows, last)
    delegated: list[tuple[datetime, datetime]] = []
    for a in agents:
        stamps = [r.timestamp for r in a.totals.requests if r.timestamp]
        if len(stamps) < 2:
            continue
        delegated.append((_moment(min(stamps)), _moment(max(stamps))))
    return _covered_minutes(counted + delegated, end) - _covered_minutes(counted, end)

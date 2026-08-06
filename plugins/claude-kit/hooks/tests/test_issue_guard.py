#!/usr/bin/env python3
"""issue-guard hook 판정 테스트.

hook을 실제 프로세스로 띄워 stdin으로 PreToolUse 입력을 주고, 판정(deny/allow)을
대조한다. 구현 언어가 바뀌어도 이 파일은 그대로 쓴다.

실행: python3 plugins/claude-kit/hooks/tests/test_issue_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "issue-guard.sh")

LONG = "가" * 1300   # 상한 1,200자 초과
SHORT = "가" * 100


class GuardCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.long_file = os.path.join(cls.tmp.name, "long.md")
        cls.short_file = os.path.join(cls.tmp.name, "short.md")
        with open(cls.long_file, "w", encoding="utf-8") as f:
            f.write(LONG)
        with open(cls.short_file, "w", encoding="utf-8") as f:
            f.write(SHORT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def verdict(self, command, transcript=None):
        """hook을 실행해 'deny' 또는 'allow'를 돌려준다."""
        payload = {"tool_input": {"command": command}}
        if transcript:
            payload["transcript_path"] = transcript
        proc = subprocess.run(
            ["bash", HOOK],
            input=json.dumps(payload),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, f"hook 비정상 종료: {proc.stderr}")
        if not proc.stdout.strip():
            return "allow"
        out = json.loads(proc.stdout)
        return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")

    def system_message(self, command, transcript):
        proc = subprocess.run(
            ["bash", HOOK],
            input=json.dumps({"tool_input": {"command": command},
                              "transcript_path": transcript}),
            capture_output=True, text=True, check=False,
        )
        if not proc.stdout.strip():
            return None
        return json.loads(proc.stdout).get("systemMessage")

    def write_transcript(self, *user_messages):
        path = os.path.join(self.tmp.name, "transcript.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for m in user_messages:
                f.write(json.dumps({"type": "user", "message": {"content": m}}) + "\n")
        return path


class MentionIsNotInvocation(GuardCase):
    """명령을 실행하지 않고 문자열로 언급만 하는 경우는 판정 대상이 아니다."""

    def test_commit_message_mentions_flags(self):
        cmd = ("git commit -m \"$(cat <<'MSGEOF'\n"
               "fix: 본문 길이 가드 확장\n\n"
               "- gh issue edit --body-file 로 상한을 우회할 수 있었다\n"
               "- --body-file - 는 검사 불가라 차단\n"
               "MSGEOF\n)\"")
        self.assertEqual(self.verdict(cmd), "allow")

    def test_mention_at_line_start(self):
        cmd = ("git commit -m \"$(cat <<'MSGEOF'\n"
               f"gh issue create --body-file {self.long_file} 형태를 막는다\n"
               "MSGEOF\n)\"")
        self.assertEqual(self.verdict(cmd), "allow")

    def test_mention_inside_quotes_same_line(self):
        self.assertEqual(
            self.verdict(f"echo 'run gh issue create --body-file {self.long_file}'"),
            "allow")

    def test_grep_for_the_hook(self):
        self.assertEqual(self.verdict("grep -rn 'gh issue create' plugins/"), "allow")

    def test_commit_message_mentions_gh_api(self):
        self.assertEqual(self.verdict("git commit -m 'fix: gh api 우회 경로 차단'"),
                         "allow")


class BodyLengthOverLimit(GuardCase):
    """본문이 상한을 넘으면 차단한다. 본문 전달 형태를 모두 덮는다."""

    def test_create_body_file(self):
        self.assertEqual(self.verdict(f"gh issue create --body-file {self.long_file}"),
                         "deny")

    def test_edit_body_file(self):
        self.assertEqual(self.verdict(f"gh issue edit 12 --body-file {self.long_file}"),
                         "deny")

    def test_invocation_after_separator(self):
        self.assertEqual(self.verdict(f"git status && gh issue edit 12 -F {self.long_file}"),
                         "deny")

    def test_chain_measures_every_body_file(self):
        """마지막 하나만 재면 앞의 긴 본문이 통과한다."""
        self.assertEqual(
            self.verdict(f"gh issue create -F {self.long_file} && "
                         f"gh issue create -F {self.short_file}"),
            "deny")

    def test_heredoc_body(self):
        cmd = f"gh issue edit 12 --body \"$(cat <<'EOF'\n{LONG}\nEOF\n)\""
        self.assertEqual(self.verdict(cmd), "deny")

    def test_inline_body(self):
        self.assertEqual(self.verdict(f"gh issue create -b '{LONG}'"), "deny")

    def test_chain_measures_every_inline_body(self):
        """첫 하나만 재면 체인 뒤쪽의 긴 본문이 통과한다."""
        self.assertEqual(
            self.verdict(f"gh issue create -b '{SHORT}' && gh issue create -b '{LONG}'"),
            "deny")

    def test_env_prefixed_invocation(self):
        self.assertEqual(
            self.verdict(f"env GH_TOKEN=x gh issue create --body-file {self.long_file}"),
            "deny")

    def test_here_string_does_not_swallow_next_line(self):
        """`<<<`는 heredoc이 아니다. 여는 줄로 오인하면 다음 줄의 호출이 판정에서 빠진다."""
        self.assertEqual(
            self.verdict(f"grep foo <<<bar\ngh issue create --body-file {self.long_file}"),
            "deny")


class UnmeasurablePaths(GuardCase):
    """길이를 잴 수 없는 전달 경로는 막는다 — 재지 못하면 상한이 없는 것과 같다."""

    def test_stdin_body_file(self):
        self.assertEqual(
            self.verdict(f"cat {self.long_file} | gh issue create --body-file -"),
            "deny")

    def test_gh_api_with_body_field(self):
        self.assertEqual(
            self.verdict('gh api repos/o/r/issues -f title=T -f body="$(cat x.md)"'),
            "deny")

    def test_gh_api_after_issue_command_in_chain(self):
        """앞의 issue 호출만 보고 넘기면 뒤의 api 우회가 통과한다."""
        self.assertEqual(
            self.verdict(f"gh issue create -F {self.short_file} && "
                         'gh api repos/o/r/issues -f body="$(cat x.md)"'),
            "deny")

    def test_gh_api_with_input_file(self):
        """`--input`은 임의 JSON이라 본문이 들어 있어도 길이를 잴 수 없다."""
        self.assertEqual(
            self.verdict("gh api repos/o/r/issues --input payload.json"), "deny")

    def test_comments_in_path_name_is_not_an_exemption(self):
        """면제는 코멘트 엔드포인트에만. 경로 이름에 comments가 있다고 통과시키지 않는다."""
        self.assertEqual(
            self.verdict('gh api repos/o/r/issues -f body="$(cat docs/comments.md)"'),
            "deny")


class AllowedInvocations(GuardCase):
    """정상 길이와 본문을 쓰지 않는 호출은 통과한다."""

    def test_create_within_limit(self):
        self.assertEqual(self.verdict(f"gh issue create --body-file {self.short_file}"),
                         "allow")

    def test_edit_within_limit(self):
        self.assertEqual(self.verdict(f"gh issue edit 12 --body-file {self.short_file}"),
                         "allow")

    def test_edit_label_only(self):
        self.assertEqual(self.verdict("gh issue edit 12 --add-label now"), "allow")

    def test_api_read(self):
        self.assertEqual(self.verdict("gh api repos/o/r/issues --jq '.[].number'"),
                         "allow")

    def test_api_state_change(self):
        self.assertEqual(self.verdict("gh api repos/o/r/issues/3 -f state=closed"),
                         "allow")

    def test_api_comment_is_not_gated(self):
        """코멘트는 길이 규격 대상이 아니다."""
        self.assertEqual(
            self.verdict(f'gh api repos/o/r/issues/3/comments -f body="$(cat {self.long_file})"'),
            "allow")

    def test_issue_list(self):
        self.assertEqual(self.verdict("gh issue list --label now"), "allow")

    def test_unrelated_heredoc_before_short_issue(self):
        """이슈 본문과 무관한 heredoc은 재지 않는다."""
        cmd = (f"cat > notes.md <<'EOF'\n{LONG}\nEOF\n"
               f"gh issue create -F {self.short_file}")
        self.assertEqual(self.verdict(cmd), "allow")


class UnrequestedCreateWarning(GuardCase):
    """직전 발화에 이슈 요청이 없으면 경고한다 — 차단은 하지 않는다."""

    def test_warns_when_user_did_not_ask(self):
        t = self.write_transcript("이 함수 리팩터링해줘")
        self.assertEqual(self.verdict(f"gh issue create -F {self.short_file}", t), "allow")
        self.assertIsNotNone(self.system_message(f"gh issue create -F {self.short_file}", t))

    def test_silent_when_user_asked(self):
        t = self.write_transcript("이슈로 남겨줘")
        self.assertIsNone(self.system_message(f"gh issue create -F {self.short_file}", t))

    def test_edit_never_warns(self):
        """edit은 기존 이슈 정리라 요청 발화가 없는 게 정상이다."""
        t = self.write_transcript("이 함수 리팩터링해줘")
        self.assertIsNone(self.system_message(f"gh issue edit 12 -F {self.short_file}", t))


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import issue_guard  # noqa: E402


class SplitHeredocs(unittest.TestCase):
    """판정의 전제. 여기가 어긋나면 위 판정이 전부 어긋난다."""

    def test_body_is_removed_from_executed_part(self):
        cmd = "cat <<'EOF'\n본문\nEOF\necho done"
        cmd_exec, heredocs = issue_guard.split_heredocs(cmd)
        self.assertEqual(cmd_exec, "cat <<'EOF'\necho done")
        self.assertEqual(heredocs, [("cat <<'EOF'", "본문")])

    def test_closing_tag_is_read_from_opening_line(self):
        """EOF 외 라벨도 그 라벨로 닫는다."""
        _, heredocs = issue_guard.split_heredocs("cat <<MSGEOF\nEOF\n본문\nMSGEOF")
        self.assertEqual(heredocs, [("cat <<MSGEOF", "EOF\n본문")])

    def test_indented_form(self):
        _, heredocs = issue_guard.split_heredocs("cat <<-'EOF'\n\t본문\n\tEOF")
        self.assertEqual(heredocs, [("cat <<-'EOF'", "\t본문")])

    def test_multiple_heredocs(self):
        cmd = "cat <<'A'\n하나\nA\ncat <<'B'\n둘\nB"
        _, heredocs = issue_guard.split_heredocs(cmd)
        self.assertEqual([b for _, b in heredocs], ["하나", "둘"])


class DetectActions(unittest.TestCase):
    def test_command_positions(self):
        for cmd in ("gh issue create -F x", "ls && gh issue create -F x",
                    "ls; gh issue create -F x", "$(gh issue create -F x)",
                    "ls | gh issue create -F x", "ls\ngh issue create -F x",
                    "env GH_TOKEN=x gh issue create -F x"):
            self.assertEqual(issue_guard.detect_actions(cmd), {"create"}, cmd)

    def test_collects_every_invocation(self):
        self.assertEqual(
            issue_guard.detect_actions("gh issue create -F x && gh api repos/o/r/issues"),
            {"create", "api"})

    def test_mentions_are_not_invocations(self):
        for cmd in ("echo 'gh issue create'", "- gh issue create 를 막는다",
                    "git commit -m 'fix gh api 우회'"):
            self.assertEqual(issue_guard.detect_actions(cmd), set(), cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2, argv=[sys.argv[0]] + sys.argv[1:])

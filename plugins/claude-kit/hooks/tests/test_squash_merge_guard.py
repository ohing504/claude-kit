#!/usr/bin/env python3
"""squash-merge-guard hook 판정 테스트.

hook을 실제 프로세스로 띄워 stdin으로 PreToolUse 입력을 주고, 판정(deny/allow)을
대조한다. 구현 언어가 바뀌어도 이 파일은 그대로 쓴다.

실행: python3 plugins/claude-kit/hooks/tests/test_squash_merge_guard.py
"""
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "squash-merge-guard.sh")

MERGE = "gh pr merge 12"


class GuardCase(unittest.TestCase):
    def run_hook(self, command):
        proc = subprocess.run(
            ["bash", HOOK],
            input=json.dumps({"tool_input": {"command": command}}),
            capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if not proc.stdout.strip():
            return {}
        return json.loads(proc.stdout)

    def assertDenied(self, command, contains=None):
        out = self.run_hook(command)
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
        self.assertEqual(decision, "deny", command)
        if contains:
            self.assertIn(
                contains,
                out["hookSpecificOutput"]["permissionDecisionReason"], command)

    def assertAllowed(self, command):
        out = self.run_hook(command)
        self.assertNotEqual(
            out.get("hookSpecificOutput", {}).get("permissionDecision"),
            "deny", command)


class DeleteBranch(GuardCase):
    def test_long_flag(self):
        self.assertDenied(f"{MERGE} --squash --delete-branch -t a -b b",
                          contains="--delete-branch")

    def test_short_flag_cluster(self):
        """`-sd`처럼 묶여 오면 squash 감지와 -d 감지 둘 다 묶음을 봐야 한다."""
        self.assertDenied(f"{MERGE} -sd -t a -b b", contains="--delete-branch")

    def test_not_squash(self):
        """squash가 아닌 머지는 이 가드의 대상이 아니다."""
        self.assertAllowed(f"{MERGE} --merge --delete-branch")

    def test_git_push_delete_in_chain(self):
        """체인 뒤의 `git push origin --delete`는 gh의 플래그가 아니다."""
        self.assertAllowed(
            f"{MERGE} --squash -t a -b b && git push origin --delete feat/x")

    def test_git_push_short_delete_before_merge(self):
        self.assertAllowed(f"git push -d origin feat/x && {MERGE} --squash -t a -b b")


class SubjectAndBody(GuardCase):
    def test_missing_both(self):
        self.assertDenied(f"{MERGE} --squash", contains="--subject")

    def test_missing_body(self):
        self.assertDenied(f"{MERGE} --squash --subject a")

    def test_short_flags(self):
        self.assertAllowed(f"{MERGE} --squash -t a -b b")

    def test_body_file(self):
        self.assertAllowed(f"{MERGE} --squash --subject a --body-file msg.md")

    def test_heredoc_body(self):
        """스킬 Step 4의 실제 형태 — 본문이 heredoc으로 온다."""
        self.assertAllowed(
            f"{MERGE} --squash --subject \"fix: x\" --body \"$(cat <<'EOF'\n"
            "- 변경 요약\nEOF\n)\"")


class MentionsAreNotInvocations(GuardCase):
    """부분일치로 판정하던 시절 이 가드를 설명하는 커밋 메시지가 스스로 차단됐다."""

    def test_commit_message_heredoc(self):
        self.assertAllowed(
            "git commit -m \"$(cat <<'EOF'\n"
            "fix(squash-merge): --delete-branch 제거\n"
            "\n"
            f"- {MERGE} --squash --delete-branch 는 로컬까지 정리한다\n"
            "EOF\n)\"")

    def test_inline_quoted_mention(self):
        self.assertAllowed(f"echo '{MERGE} --squash --delete-branch'")

    def test_grep_for_flag(self):
        self.assertAllowed("grep -r -- '--delete-branch' plugins/")

    def test_unrelated_command(self):
        self.assertAllowed("git push origin --delete feat/x")


class CommandPositions(GuardCase):
    def test_after_separators(self):
        for prefix in ("", "ls && ", "ls; ", "ls\n"):
            self.assertDenied(f"{prefix}{MERGE} --squash --delete-branch -t a -b b")

    def test_env_wrapper(self):
        self.assertDenied(f"env GH_TOKEN=x {MERGE} --squash --delete-branch -t a -b b")


if __name__ == "__main__":
    unittest.main(verbosity=2, argv=[sys.argv[0]] + sys.argv[1:])

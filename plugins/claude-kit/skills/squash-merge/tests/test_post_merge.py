#!/usr/bin/env python3
"""post_merge.sh가 실행 위치마다 약속한 동작을 실제 git 저장소로 확인한다.

임시 폴더에 bare origin과 clone을 만들고, 원격 base에 squash 커밋이 들어간 머지 직후
상태에서 스크립트를 실행한 뒤 브랜치, 워크트리, 파일을 다시 읽어 대조한다.

실행: python3 plugins/claude-kit/skills/squash-merge/tests/test_post_merge.py
"""
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts",
                      "post_merge.sh")

HEAD = "feat/x"
BASE = "main"


def git(cwd, *args, check=True):
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, text=True,
                          capture_output=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} 실패: {proc.stderr}")
    return proc.stdout.strip()


def commit(cwd, name):
    with open(os.path.join(cwd, name), "w") as f:
        f.write(name)
    git(cwd, "add", name)
    git(cwd, "commit", "-m", name)
    return git(cwd, "rev-parse", "HEAD")


class PostMergeCase(unittest.TestCase):
    repo_name = "repo"

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.origin = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "--bare", "-b", BASE, self.origin)
        self.repo = os.path.join(self.tmp, self.repo_name)
        git(self.tmp, "clone", self.origin, self.repo)
        git(self.repo, "checkout", "-b", BASE)
        commit(self.repo, "base.txt")
        git(self.repo, "push", "-u", "origin", BASE)
        git(self.repo, "checkout", "-b", HEAD)
        self.head_oid = commit(self.repo, "feature.txt")
        git(self.repo, "push", "-u", "origin", HEAD)
        # 다른 clone에서 base에 squash 커밋을 넣어 머지 직후 원격 상태를 만든다.
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-b", BASE, self.origin, other)
        self.merged_oid = commit(other, "squash.txt")
        git(other, "push", "origin", BASE)

    def run_script(self, cwd):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        proc = subprocess.run(["bash", SCRIPT, HEAD, BASE, self.head_oid], cwd=cwd,
                              env=env, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def local_branch_exists(self):
        return bool(git(self.repo, "branch", "--list", HEAD))

    def remote_branch_exists(self):
        return bool(git(self.origin, "branch", "--list", HEAD))

    def local_base(self):
        return git(self.repo, "rev-parse", BASE)

    def current_branch(self, cwd=None):
        return git(cwd or self.repo, "branch", "--show-current")

    def add_worktree(self, name, *checkout):
        path = os.path.join(self.tmp, name)
        git(self.repo, "worktree", "add", path, *checkout)
        return path


class MainCheckout(PostMergeCase):
    def test_on_merged_branch_moves_to_updated_base_and_deletes_branch(self):
        self.run_script(self.repo)
        self.assertEqual(self.current_branch(), BASE)
        self.assertFalse(self.local_branch_exists())
        self.assertFalse(self.remote_branch_exists())
        self.assertEqual(self.local_base(), self.merged_oid)

    def test_uncommitted_change_on_merged_branch_keeps_checkout_and_branch(self):
        with open(os.path.join(self.repo, "wip.txt"), "w") as f:
            f.write("wip")
        out = self.run_script(self.repo)
        self.assertEqual(self.current_branch(), HEAD)
        self.assertTrue(self.local_branch_exists())
        self.assertTrue(os.path.exists(os.path.join(self.repo, "wip.txt")))
        self.assertEqual(self.local_base(), self.merged_oid)
        self.assertIn("미커밋 변경", out)

    def test_uncommitted_change_on_base_skips_sync(self):
        git(self.repo, "checkout", BASE)
        before = self.local_base()
        with open(os.path.join(self.repo, "wip.txt"), "w") as f:
            f.write("wip")
        out = self.run_script(self.repo)
        self.assertEqual(self.local_base(), before)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "wip.txt")))
        self.assertIn("동기화 건너뜀", out)

    def test_on_unrelated_branch_stays_there_and_updates_base_ref(self):
        git(self.repo, "checkout", "-b", "other", BASE)
        self.run_script(self.repo)
        self.assertEqual(self.current_branch(), "other")
        self.assertFalse(self.local_branch_exists())
        self.assertEqual(self.local_base(), self.merged_oid)

    def test_commit_not_in_pr_keeps_local_branch(self):
        commit(self.repo, "unpushed.txt")
        git(self.repo, "checkout", BASE)
        out = self.run_script(self.repo)
        self.assertTrue(self.local_branch_exists())
        self.assertIn("PR에 없는 커밋", out)

    def test_branch_used_by_other_worktree_is_left_untouched(self):
        git(self.repo, "checkout", BASE)
        other = self.add_worktree("session-b", HEAD)
        with open(os.path.join(other, "wip.txt"), "w") as f:
            f.write("wip")
        out = self.run_script(self.repo)
        self.assertTrue(os.path.exists(os.path.join(other, "wip.txt")))
        self.assertEqual(self.current_branch(other), HEAD)
        self.assertIn(other, out)

    def test_remote_branch_already_deleted_is_not_a_failure(self):
        git(self.origin, "branch", "-D", HEAD)
        out = self.run_script(self.repo)
        self.assertNotIn("실패", out)
        self.assertFalse(self.local_branch_exists())


class MainCheckoutPathWithSpace(MainCheckout):
    """사람용 `git worktree list` 출력을 공백으로 자르면 linked로 오판하는 경로."""
    repo_name = "My Documents repo"


class LinkedWorktree(PostMergeCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "checkout", BASE)
        self.worktree = self.add_worktree("session", HEAD)

    def assert_left_in_place(self):
        self.assertEqual(self.current_branch(self.worktree), HEAD)
        self.assertTrue(self.local_branch_exists())
        self.assertFalse(self.remote_branch_exists())
        self.assertEqual(self.current_branch(), BASE)

    def test_desktop_worktree_is_left_to_the_app(self):
        git_dir = git(self.worktree, "rev-parse", "--absolute-git-dir")
        open(os.path.join(git_dir, "claude-desktop-worktree"), "w").close()
        out = self.run_script(self.worktree)
        self.assert_left_in_place()
        self.assertIn("데스크톱 앱", out)

    def test_other_worktree_points_to_exit_prompt(self):
        out = self.run_script(self.worktree)
        self.assert_left_in_place()
        self.assertIn("종료 프롬프트", out)


if __name__ == "__main__":
    unittest.main()

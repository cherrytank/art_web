"""使用臨時本機倉庫驗證多人發布，不連到使用者的 GitHub。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import git_publish


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        git_publish.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.repo = self.root / "editor-a"
        git_publish.git(self.root, "clone", str(self.remote), str(self.repo))
        self.identity(self.repo)
        (self.repo / "content").mkdir()
        (self.repo / "content/site.json").write_text("{}")
        git_publish.git(self.repo, "add", ".")
        git_publish.git(self.repo, "commit", "-m", "initial")
        git_publish.git(self.repo, "push", "origin", "main")

    def identity(self, repo):
        git_publish.git(repo, "config", "user.name", "Local Test")
        git_publish.git(repo, "config", "user.email", "local@example.invalid")

    def test_publish_commits_sources_not_unrelated_documents(self):
        (self.repo / "content/site.json").write_text('{"title":"updated"}')
        (self.repo / "private.docx").write_text("not for publishing")
        build = Mock()
        self.assertIn("推送成功", git_publish.publish(self.repo, "update", Mock(), build))
        build.assert_called_once()
        self.assertEqual(git_publish.git(self.repo, "rev-parse", "HEAD"), git_publish.git(self.repo, "rev-parse", "origin/main"))
        self.assertIn("private.docx", git_publish.git(self.repo, "status", "--porcelain"))

    def test_other_editor_update_blocks_publish_then_clean_sync_succeeds(self):
        other = self.root / "editor-b"
        git_publish.git(self.root, "clone", str(self.remote), str(other))
        self.identity(other)
        (other / "content/site.json").write_text('{"other":true}')
        git_publish.publish(other, "other editor", Mock(), Mock())
        build = Mock()
        with self.assertRaisesRegex(ValueError, "尚未整合"):
            git_publish.publish(self.repo, "must not overwrite", Mock(), build)
        build.assert_not_called()
        git_publish.sync(self.repo, Mock())
        self.assertEqual((self.repo / "content/site.json").read_text(), '{"other":true}')
        (self.repo / "content/site.json").write_text("local edits")
        with self.assertRaisesRegex(ValueError, "未提交"):
            git_publish.sync(self.repo, Mock())

    def test_existing_staged_files_stop_publish(self):
        (self.repo / "staged.txt").write_text("separate work")
        git_publish.git(self.repo, "add", "staged.txt")
        with self.assertRaisesRegex(ValueError, "暫存"):
            git_publish.publish(self.repo, "no", Mock(), Mock())

    def test_command_timeout_is_actionable(self):
        with patch.object(git_publish.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 120)):
            with self.assertRaisesRegex(ValueError, "逾時"):
                git_publish.git(self.repo, "push")

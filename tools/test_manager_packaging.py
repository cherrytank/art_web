"""確認打包啟動不會把管理器 EXE 當成 Python 執行。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manager_packaging


class PackagingTests(unittest.TestCase):
    def test_frozen_without_python_reports_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(manager_packaging.sys, "frozen", True, create=True), patch.object(manager_packaging.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Python 3.10"):
                manager_packaging.find_python(Path(folder))

    def test_existing_environment_is_probed(self):
        root = Path(__file__).resolve().parents[1]
        if not (root / ".codex-work/exe-venv/Scripts/python.exe").exists():
            self.skipTest("沒有本機打包環境")
        command = manager_packaging.find_python(root)
        self.assertEqual(command, [str(root / ".codex-work/exe-venv/Scripts/python.exe")])

    def test_missing_project_script_does_not_start_build(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(manager_packaging.sys, "platform", "win32"):
            with self.assertRaisesRegex(ValueError, "完整專案"):
                manager_packaging.package_manager(Path(folder), lambda _: None)


if __name__ == "__main__": unittest.main()

"""確認打包啟動不會把管理器 EXE 當成 Python 執行。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manager_packaging
import replace_manager


class PackagingTests(unittest.TestCase):
    def test_replace_retries_locked_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "new.exe"
            target = Path(folder) / "old.exe"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            original = Path.replace
            calls = []
            def replace(path, destination):
                calls.append(path)
                if len(calls) == 1:
                    raise PermissionError("使用中")
                return original(path, destination)
            with patch.object(Path, "replace", replace), patch.object(replace_manager.time, "sleep"):
                replace_manager.replace_when_available(source, target, attempts=2)
            self.assertEqual(target.read_bytes(), b"new")
            self.assertFalse(source.exists())

    def test_replace_timeout_preserves_new_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "new.exe"
            source.write_bytes(b"new")
            with patch.object(Path, "replace", side_effect=PermissionError), patch.object(replace_manager.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "逾時"):
                    replace_manager.replace_when_available(source, Path(folder) / "old.exe", attempts=2)
            self.assertEqual(source.read_bytes(), b"new")

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

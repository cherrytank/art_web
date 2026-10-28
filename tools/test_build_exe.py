"""驗證打包子程序的路徑、輸出與失敗處理。"""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from build_exe import run_step


class BuildExeTests(unittest.TestCase):
    def test_runs_in_project_with_spaces_and_keeps_output(self):
        with tempfile.TemporaryDirectory(prefix="打包 test ") as folder:
            log = io.StringIO()
            with redirect_stdout(io.StringIO()):
                run_step("測試", [sys.executable, "-c",
                    "import pathlib, sys; print(pathlib.Path.cwd()); "
                    "print('錯誤串流', file=sys.stderr)"], Path(folder), log)
            self.assertIn(str(Path(folder).resolve()), log.getvalue())
            self.assertIn("錯誤串流", log.getvalue())

    def test_nonzero_exit_stops_build_and_keeps_error(self):
        with tempfile.TemporaryDirectory() as folder:
            log = io.StringIO()
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "結束碼 7"):
                run_step("安裝套件", [sys.executable, "-c",
                    "print('安裝失敗原因'); raise SystemExit(7)"], Path(folder), log)
            self.assertIn("安裝失敗原因", log.getvalue())


if __name__ == "__main__":
    unittest.main()

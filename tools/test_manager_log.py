"""驗證紀錄輪替、憑證遮罩與背景工作完整錯誤堆疊。"""
from pathlib import Path
import tempfile
import unittest
import manager_log
from local_jobs import LocalJob


class ManagerLogTests(unittest.TestCase):
    def test_traceback_redaction_and_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            try:
                path = manager_log.configure(Path(directory))
                manager_log.logger.info("https://user:secret@example.com/repo token=abc Authorization: Bearer xyz ghp_example123")
                job = LocalJob(lambda progress: 1 / 0)
                job.start()
                job.thread.join(timeout=3)
                self.assertFalse(job.thread.is_alive())
                text = path.read_text(encoding="utf-8")
                for secret in ("user:secret", "token=abc", "Bearer xyz", "ghp_example123"):
                    self.assertNotIn(secret, text)
                self.assertIn("ZeroDivisionError", text)
                self.assertIn("Traceback", text)
                self.assertIn("+08:00", text)
                self.assertIn("content-job", text)
                handler = manager_log.logger.handlers[0]
                handler.maxBytes = 200
                for index in range(20):
                    manager_log.logger.info("輪替測試 %s %s", index, "a" * 100)
                self.assertTrue(path.with_suffix(".log.1").exists())
                self.assertLessEqual(len(list(path.parent.glob("manager.log*"))), 4)
                self.assertIn("19", manager_log.tail())
            finally:
                for handler in list(manager_log.logger.handlers):
                    manager_log.logger.removeHandler(handler)
                    handler.close()
                manager_log.log_path = None

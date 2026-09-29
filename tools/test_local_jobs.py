"""Regression tests for non-blocking editing, safe preview and image reuse."""
from pathlib import Path
from queue import Empty
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import gc
from urllib.request import urlopen

from PIL import Image
import build_site
import image_pipeline
from local_jobs import LocalJob


class BuildSafetyTests(unittest.TestCase):
    def test_failed_build_preserves_previous_site(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = root / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("old site")
            with patch.object(build_site, "ROOT", root), patch.object(build_site, "DIST", dist), patch.object(build_site, "_build_current", side_effect=ValueError("bad image")):
                with self.assertRaisesRegex(ValueError, "bad image"):
                    build_site.build()
                self.assertEqual(build_site.DIST, dist)
            self.assertEqual((dist / "index.html").read_text(), "old site")
            self.assertFalse(list((root / ".codex-work").glob("site-build-*")))

    def test_cache_reuses_images_and_invalidates_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            picture = source / "sample.png"
            Image.new("RGB", (60, 40), "red").save(picture)
            with patch.object(image_pipeline, "_generate_one", wraps=image_pipeline._generate_one) as generate:
                first, _ = image_pipeline.build_responsive_images(source, root / "one", cache_dir=root / "cache")
                second, _ = image_pipeline.build_responsive_images(source, root / "two", cache_dir=root / "cache")
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(first, second)
                Image.new("RGB", (60, 40), "blue").save(picture)
                image_pipeline.build_responsive_images(source, root / "three", cache_dir=root / "cache")
                self.assertEqual(generate.call_count, 2)

    def test_worker_errors_are_reported_without_raising_on_ui_thread(self):
        job = LocalJob(lambda progress: 1 / 0)
        job.start()
        kind, value = job.events.get(timeout=2)
        self.assertEqual(kind, "error")
        self.assertIn("division", value)


class ResponsiveGuiTests(unittest.TestCase):
    def setUp(self):
        # Finalize destroyed Tk windows on the main thread before starting any
        # worker/server thread (cyclic collection may otherwise run there).
        gc.collect()
        import tkinter
        import content_manager
        self.manager = content_manager
        try:
            self.app = content_manager.ContentManager()
            self.app.withdraw()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        self.addCleanup(self.app.destroy)

    def wait_job(self):
        deadline = time.monotonic() + 4
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)

    def test_ui_heartbeat_runs_during_background_work_and_rejects_overlap(self):
        gate = threading.Event()
        heartbeat = []
        ui_thread = threading.get_ident()
        results = []
        self.app.after(20, lambda: (heartbeat.append(True), gate.set()))
        def work(progress):
            self.assertNotEqual(threading.get_ident(), ui_thread)
            progress("working")
            if not gate.wait(2):
                raise RuntimeError("UI event loop blocked")
            return 42
        def complete(value):
            self.assertEqual(threading.get_ident(), ui_thread)
            results.append(value)
        self.app._run_job("test", work, complete)
        duplicate = Mock()
        self.app._run_job("duplicate", duplicate, complete)
        self.wait_job()
        self.assertTrue(heartbeat)
        self.assertEqual(results, [42])
        duplicate.assert_not_called()

    def test_failure_releases_controls_and_allows_retry(self):
        def fail(progress):
            raise ValueError("test failure")
        with patch.object(self.manager.messagebox, "showerror") as error:
            self.app._run_job("test", fail, Mock())
            self.wait_job()
            error.assert_called_once()
        done = Mock()
        self.app._run_job("retry", lambda progress: "ok", done)
        self.wait_job()
        done.assert_called_once_with("ok")

    def test_preview_chooses_own_port_if_8000_is_occupied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dist").mkdir()
            (root / "dist/index.html").write_text("correct preview", encoding="utf-8")
            occupied = None
            try:
                occupied = ThreadingHTTPServer(("127.0.0.1", 8000), partial(SimpleHTTPRequestHandler, directory=directory))
            except OSError:
                pass  # An existing local process already occupies the test port.
            try:
                with patch.object(self.manager, "ROOT", root), patch.object(self.manager.webbrowser, "open"):
                    url = self.app._launch_preview()
                    self.assertNotEqual(self.app.preview_server.server_port, 8000)
                    with urlopen(url, timeout=5) as response:
                        self.assertEqual(response.read(), b"correct preview")
            finally:
                if occupied:
                    occupied.server_close()
                self.app.preview_server.shutdown()
                self.app.preview_server.server_close()
                self.app.preview_server = None


if __name__ == "__main__":
    unittest.main()

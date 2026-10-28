"""Background work without any Tk calls on the worker thread."""
from queue import Queue
import threading
from manager_log import logger


class LocalJob:
    def __init__(self, work):
        self.events = Queue()
        self.thread = threading.Thread(target=self._run, args=(work,), daemon=True, name="content-job")

    def _run(self, work):
        def progress(text):
            logger.info("進度：%s", text)
            self.events.put(("progress", text))
        try:
            result = work(progress)
        except Exception as error:
            logger.exception("背景工作失敗")
            self.events.put(("error", str(error)))
        else:
            self.events.put(("done", result))

    def start(self):
        self.thread.start()

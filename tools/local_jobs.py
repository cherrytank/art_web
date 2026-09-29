"""Background work without any Tk calls on the worker thread."""
from queue import Queue
import threading


class LocalJob:
    def __init__(self, work):
        self.events = Queue()
        self.thread = threading.Thread(target=self._run, args=(work,), daemon=True, name="content-job")

    def _run(self, work):
        try:
            result = work(lambda text: self.events.put(("progress", text)))
        except Exception as error:
            self.events.put(("error", str(error)))
        else:
            self.events.put(("done", result))

    def start(self):
        self.thread.start()

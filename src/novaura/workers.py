from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


class TaskWorker(QThread):
    progress = Signal(str, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[Callable[[str, int], None]], Any], parent=None):
        super().__init__(parent)
        self.task = task
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        def report(message: str, percent: int = -1) -> None:
            self.progress.emit(str(message), max(-1, min(100, int(percent))))

        report.cancel_event = self.cancel_event
        try:
            result = self.task(report)
            if self.cancel_event.is_set():
                raise InterruptedError("Операция отменена.")
            self.succeeded.emit(result)
        except Exception as exc:
            log.exception("Background task failed")
            self.failed.emit(str(exc) or exc.__class__.__name__)

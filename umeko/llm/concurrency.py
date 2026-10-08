"""Per-model FIFO admission shared by every LLM client in this process."""
from __future__ import annotations

import threading
from collections import deque
from contextlib import contextmanager
from typing import Callable, Iterator

from ..cancellation import CancelCheck, raise_if_cancelled


def validate_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("模型并发上限必须是非负整数（0 = 不限制）")
    return value


class ModelCallQueue:
    def __init__(self, limit: int = 0):
        self._limit = validate_limit(limit)
        self._active = 0
        self._waiting: deque[object] = deque()
        self._condition = threading.Condition()

    def set_limit(self, limit: int) -> None:
        with self._condition:
            self._limit = validate_limit(limit)
            self._condition.notify_all()

    def snapshot(self) -> dict:
        with self._condition:
            return {"limit": self._limit, "active": self._active, "waiting": len(self._waiting)}

    @contextmanager
    def slot(
        self, should_cancel: CancelCheck = None,
        on_wait: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        raise_if_cancelled(should_cancel)
        ticket = object()
        with self._condition:
            self._waiting.append(ticket)
        notified = False
        try:
            while True:
                with self._condition:
                    raise_if_cancelled(should_cancel)
                    if (self._waiting[0] is ticket
                            and (self._limit == 0 or self._active < self._limit)):
                        self._waiting.popleft()
                        self._active += 1
                        self._condition.notify_all()
                        break
                    notify = not notified
                    notified = True
                    if not notify:
                        self._condition.wait(timeout=0.05)
                # Call user callbacks without holding the admission lock.
                if notify and on_wait is not None:
                    on_wait()
        except BaseException:
            with self._condition:
                self._waiting.remove(ticket)
                self._condition.notify_all()
            raise
        try:
            raise_if_cancelled(should_cancel)
            yield
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()


_queues: dict[str, ModelCallQueue] = {}
_registry_lock = threading.Lock()


def model_call_queue(model_id: str, initial_limit: int = 0) -> ModelCallQueue:
    with _registry_lock:
        queue = _queues.get(model_id)
        if queue is None:
            queue = _queues[model_id] = ModelCallQueue(initial_limit)
        return queue


def set_model_limit(model_id: str, limit: int) -> None:
    model_call_queue(model_id, limit).set_limit(limit)

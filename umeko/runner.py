"""Run 生命周期（L1）：一次用户输入 -> 一次可取消、可订阅事件的运行。

从 server 上提，CLI / Web / IDE 共用：
- Web：把 run.events 转成 SSE 推流；
- CLI：轮询 events_after 增量打印；
- IDE：进程内订阅或本地 HTTP 复用同一份实现。
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import events as ev

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Run:
    """一次运行的状态与事件缓冲。事件为 SSE 友好的 dict 形态（含自增 id）。"""

    id: str
    session_id: str
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None
    reply: str | None = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    _event_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def finished(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def emit(self, event_type: str, **data) -> dict:
        with self._event_lock:
            event = {
                "id": len(self.events) + 1,
                "run_id": self.id,
                "session_id": self.session_id,
                "type": event_type,
                "timestamp": _now(),
                "data": data,
            }
            self.events.append(event)
            return event

    def events_after(self, event_id: int) -> list[dict]:
        with self._event_lock:
            return [event for event in self.events if event["id"] > event_id]

    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        if self.finished:
            return
        self._cancel_event.set()
        if self.status != "cancelling":
            self.status = "cancelling"
            self.emit(ev.RUN_CANCELLING)

    def finish(self, status: str, *, reply: str | None = None, error: str | None = None) -> None:
        """宿主在执行结束后调用：落定状态并发终态事件。"""
        self.status = status
        self.completed_at = _now()
        if reply is not None:
            self.reply = reply
        if error is not None:
            self.error = error
        if status == "completed":
            self.emit(ev.RUN_COMPLETED, reply=self.reply)
        elif status == "failed":
            self.emit(ev.RUN_FAILED, error=self.error)
        elif status == "cancelled":
            self.emit(ev.RUN_CANCELLED, reply=self.reply)


class RunManager:
    """Run 注册表 + 执行线程池。单进程内所有交付端共用一个实例即可。"""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="umeko-run"
        )
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str, *, emit_queued: bool = True) -> Run:
        run = Run(f"run_{uuid.uuid4().hex}", session_id)
        if emit_queued:
            run.emit(ev.RUN_QUEUED)
        with self._lock:
            self.runs[run.id] = run
        return run

    def submit(self, run: Run, fn: Callable[[], None]) -> None:
        """把执行体丢进线程池；fn 内部负责调 run.finish() 落定终态。"""
        self._executor.submit(fn)

    def get(self, run_id: str) -> Run:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise KeyError(f"未知运行：{run_id}") from exc

    def cancel(self, run_id: str) -> Run:
        run = self.get(run_id)
        run.request_cancel()
        return run

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

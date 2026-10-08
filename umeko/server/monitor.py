"""Low overhead process/host telemetry. Sampling runs outside request handlers."""
from __future__ import annotations

import copy
import os
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone

import psutil

from ..llm.concurrency import model_call_queue


class ResourceMonitor:
    def __init__(self, service, tasks, interval=5):
        self.service, self.tasks, self.interval = service, tasks, interval
        self.process = psutil.Process()
        self.process.cpu_percent(None)
        psutil.cpu_percent(None)
        self._history = deque(maxlen=120)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.started = time.monotonic()
        self._sample()

    def start(self):
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="umeko-monitor", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self._sample()
            except (OSError, psutil.Error):
                pass

    def _sample(self):
        vm, pm = psutil.virtual_memory(), self.process.memory_info()
        disk = psutil.disk_usage(str(self.service.data_root))
        with self.service.store.connect() as db:
            sessions = db.execute("SELECT COUNT(*) FROM agent_sessions WHERE purpose='chat'").fetchone()[0]
            machine_sessions = db.execute("SELECT COUNT(*) FROM agent_sessions WHERE purpose='task'").fetchone()[0]
        with self.service.run_manager._lock:
            statuses = dict(Counter(r.status for r in self.service.runs.values()))
        models = [{"id": m["id"], "name": m["name"], "provider": p["name"],
                   **model_call_queue(m["id"], m["max_concurrent_requests"]).snapshot()}
                  for p in self.service.store.list_providers() for m in p["models"]]
        db_bytes = sum(p.stat().st_size for p in [self.service.store.path,
                      self.service.store.path.with_name(self.service.store.path.name + "-wal")]
                       if p.is_file())
        sample = {
            "timestamp": datetime.now(timezone.utc).isoformat(), "uptime_seconds": round(time.monotonic() - self.started),
            "host": {"cpu_percent": psutil.cpu_percent(None), "cpu_count": psutil.cpu_count() or 1,
                     "memory_total": vm.total, "memory_used": vm.total - vm.available, "memory_percent": vm.percent,
                     "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free, "disk_percent": disk.percent},
            "process": {"pid": os.getpid(), "cpu_percent": self.process.cpu_percent(None),
                        "memory_rss": pm.rss, "threads": self.process.num_threads()},
            "service": {"chat_sessions": sessions, "machine_sessions": machine_sessions,
                        "loaded_sessions": len(self.service.sessions), "runs": statuses, "database_bytes": db_bytes},
            "tasks": self.tasks.snapshot(), "models": models,
        }
        with self._lock:
            self._history.append(sample)

    def snapshot(self):
        with self._lock:
            return {"current": copy.deepcopy(self._history[-1]), "history": copy.deepcopy(list(self._history)),
                    "interval_seconds": self.interval}

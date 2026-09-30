"""网页控制台的后台任务管理。

下载 / 扫码登录 / 字幕转换都是耗时操作，在线程池里执行；
前端通过轮询 ``/api/tasks`` 获取进度与日志。
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

_LOG_LIMIT = 200  # 每个任务最多保留的日志行数


@dataclass
class Task:
    id: str
    kind: str  # download | info | login | convert
    title: str
    status: str = "running"  # running | ok | failed
    created: float = field(default_factory=time.time)
    progress_done: int = 0
    progress_total: int | None = None
    log: list[str] = field(default_factory=list)
    result: dict | None = None
    qr_png: Path | None = None  # 扫码登录任务的二维码文件

    def log_line(self, message: str) -> None:
        for line in str(message).splitlines() or [""]:
            if line.strip():
                self.log.append(line)
        del self.log[:-_LOG_LIMIT]

    def set_progress(self, done: int, total: int | None) -> None:
        self.progress_done = done
        if total:
            self.progress_total = total

    def to_dict(self, log_tail: int = 8) -> dict:
        qr_base64 = None
        if self.qr_png is not None:
            try:
                import base64

                qr_base64 = "data:image/png;base64," + base64.b64encode(
                    self.qr_png.read_bytes()
                ).decode("ascii")
            except OSError:
                qr_base64 = None
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "created": self.created,
            "progress_done": self.progress_done,
            "progress_total": self.progress_total,
            "log": self.log[-log_tail:],
            "result": self.result,
            "qr_base64": qr_base64,
        }


class TaskManager:
    """进程内任务注册表；任务在 daemon 线程中执行。"""

    def __init__(self, keep: int = 100) -> None:
        self._tasks: OrderedDict[str, Task] = OrderedDict()
        self._keep = keep
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def submit(self, kind: str, title: str, fn: Callable[[Task], None]) -> Task:
        task = Task(id="t%04d" % next(self._counter), kind=kind, title=title)
        with self._lock:
            self._tasks[task.id] = task
            while len(self._tasks) > self._keep:
                self._tasks.popitem(last=False)

        def runner() -> None:
            try:
                fn(task)
            except Exception as e:  # 后台线程兜底，任何异常都变成任务失败
                task.status = "failed"
                task.log_line(f"错误: {e}")
            else:
                if task.status == "running":
                    task.status = "ok"

        threading.Thread(target=runner, name=f"vidporter-{task.id}", daemon=True).start()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list(self, log_tail: int = 8) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [t.to_dict(log_tail=log_tail) for t in reversed(tasks)]

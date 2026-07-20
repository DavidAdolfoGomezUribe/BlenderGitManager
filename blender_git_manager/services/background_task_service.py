"""Generic thread-based background task queue used by future non-UI integrations.

Blender-facing operators use a modal timer so that Blender data is only touched on
the main thread. This service remains Blender-independent and can be reused by a
future persistent task center.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from queue import Empty, SimpleQueue
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


@dataclass(slots=True)
class TaskCompletion:
    task_id: str
    label: str
    result: Any = None
    error: Exception | None = None


class BackgroundTaskService:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bgm-task")
        self._completed: SimpleQueue[TaskCompletion] = SimpleQueue()
        self._futures: dict[str, Future] = {}
        self._lock = Lock()
        self._closed = False

    def submit(self, label: str, function: Callable[[], Any]) -> str:
        task_id = uuid4().hex
        with self._lock:
            if self._closed:
                raise RuntimeError("Background task service is shut down.")
            future = self._executor.submit(function)
            self._futures[task_id] = future

        def completed(done: Future) -> None:
            try:
                self._completed.put(TaskCompletion(task_id, label, result=done.result()))
            except Exception as exc:  # noqa: BLE001
                self._completed.put(TaskCompletion(task_id, label, error=exc))
            finally:
                with self._lock:
                    self._futures.pop(task_id, None)

        future.add_done_callback(completed)
        return task_id

    def poll(self) -> list[TaskCompletion]:
        items: list[TaskCompletion] = []
        while True:
            try:
                items.append(self._completed.get_nowait())
            except Empty:
                break
        return items

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            future = self._futures.get(task_id)
        return bool(future and not future.done())

    def has_running_tasks(self) -> bool:
        with self._lock:
            return any(not future.done() for future in self._futures.values())

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            future = self._futures.get(task_id)
        return bool(future and future.cancel())

    def cancel_all(self) -> None:
        with self._lock:
            futures = tuple(self._futures.values())
        for future in futures:
            future.cancel()

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            futures = tuple(self._futures.values())
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=wait, cancel_futures=True)

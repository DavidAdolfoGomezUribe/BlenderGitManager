"""Generic thread-based background task queue used by future non-UI integrations.

Blender-facing operators use a modal timer so that Blender data is only touched on
the main thread. This service remains Blender-independent and can be reused by a
future persistent task center.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from queue import SimpleQueue
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

    def submit(self, label: str, function: Callable[[], Any]) -> str:
        task_id = uuid4().hex
        future = self._executor.submit(function)
        self._futures[task_id] = future

        def completed(done: Future) -> None:
            try:
                self._completed.put(TaskCompletion(task_id, label, result=done.result()))
            except Exception as exc:  # noqa: BLE001
                self._completed.put(TaskCompletion(task_id, label, error=exc))
            finally:
                self._futures.pop(task_id, None)

        future.add_done_callback(completed)
        return task_id

    def poll(self) -> list[TaskCompletion]:
        items: list[TaskCompletion] = []
        while not self._completed.empty():
            items.append(self._completed.get())
        return items

    def is_running(self, task_id: str) -> bool:
        future = self._futures.get(task_id)
        return bool(future and not future.done())

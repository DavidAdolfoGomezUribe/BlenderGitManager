from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_git_manager.operators import history_runtime
from blender_git_manager.services.background_task_service import TaskCompletion
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService


def wait_until(predicate, label: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history_runtime._poll_history_tasks()
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError(f"Timed out waiting for {label}.")


def wait_for_runtime_idle() -> None:
    def idle() -> bool:
        service = history_runtime._TASK_SERVICE
        return (
            not history_runtime._ACTIVE_HISTORY_TASK
            and not history_runtime._ACTIVE_DETAIL_TASK
            and history_runtime._PENDING_HISTORY_REQUEST is None
            and history_runtime._PENDING_DETAIL_REQUEST is None
            and (service is None or not service.has_running_tasks())
        )

    wait_until(idle, "History runtime to become idle")


def run_git(git: GitService, root: Path, *arguments: str) -> None:
    git._run_checked(list(arguments), root, timeout=60)


def commit_file(git: GitService, root: Path, name: str, message: str) -> str:
    (root / name).write_text(f"{message}\n", encoding="utf-8")
    run_git(git, root, "add", "--all")
    run_git(git, root, "commit", "-m", message)
    return git.head_commit(root)


def main() -> None:
    assert bpy.ops.preferences.addon_enable(
        module="blender_git_manager"
    ) == {"FINISHED"}
    temporary = tempfile.TemporaryDirectory(prefix="blender-history-runtime-")
    source_scene = None
    try:
        root = Path(temporary.name) / "repository"
        root.mkdir()
        git = GitService(process=ProcessService(echo_console=False))
        run_git(git, root, "init", "-b", "main")
        run_git(git, root, "config", "user.name", "Runtime Test")
        run_git(git, root, "config", "user.email", "runtime@example.invalid")
        first_hash = commit_file(git, root, "one.txt", "one")

        active_scene = bpy.context.scene
        active_state = active_scene.git_manager
        assert len(active_state.commits) == 0

        source_scene = bpy.data.scenes.new("History Runtime Origin")
        source_state = source_scene.git_manager
        source_state.repository_path = str(root)
        source_state.history_repository_signature = "signature-v1"
        source_state.active_tab = "HISTORY"
        source_context = SimpleNamespace(
            scene=source_scene,
            preferences=bpy.context.preferences,
        )

        history_runtime.request_history_refresh(source_context, force=True)
        wait_until(
            lambda: source_state.history_loaded and not source_state.history_loading,
            "origin-scene History load",
        )
        assert source_state.commits[0].full_hash == first_hash
        # The active Blender context never pointed at source_scene. Completion
        # must still update only the Scene that originated the request.
        assert len(active_state.commits) == 0
        assert any(
            "Loaded 1 commit(s)" in line.message
            for line in source_state.output_lines
        )
        assert not any(
            "Loaded 1 commit(s)" in line.message
            for line in active_state.output_lines
        )

        second_hash = commit_file(git, root, "two.txt", "two")
        history_runtime.request_history_refresh(source_context, force=True)
        active_task = history_runtime._ACTIVE_HISTORY_TASK
        active_process = history_runtime._TASK_PROCESSES[active_task]
        history_runtime.repository_summary_changed(
            source_context,
            "signature-v2",
        )
        assert active_process._cancel_requested.is_set()
        wait_for_runtime_idle()
        # The cancelled v1 result cannot overwrite the Scene after its epoch
        # and repository signature change.
        assert len(source_state.commits) == 1
        assert source_state.history_dirty

        history_runtime.request_history_refresh(source_context, force=True)
        wait_until(
            lambda: (
                len(source_state.commits) == 2
                and source_state.commits[0].full_hash == second_hash
                and not source_state.history_loading
            ),
            "post-invalidation History load",
        )
        assert not source_state.history_dirty

        source_state.commits_index = 0
        history_runtime.request_history_details(source_context)
        wait_until(
            lambda: (
                source_state.history_detail_hash == second_hash
                and not source_state.history_detail_loading
            ),
            "commit details",
        )

        # Errors preserve the last usable page and keep it explicitly dirty so
        # a later refresh is not incorrectly served as current cache data.
        scene_reference = history_runtime._scene_ref_from_context(source_context)
        assert scene_reference is not None
        error_generation = 900_001
        source_state.history_generation = error_generation
        source_state.history_dirty = False
        request = history_runtime._HistoryRequest(
            generation=error_generation,
            scene=scene_reference,
            scene_epoch=history_runtime._scene_epoch(scene_reference),
            repository_signature=source_state.history_repository_signature,
            repository=str(root),
            repository_key=history_runtime._repository_key(str(root)),
            git_executable="git",
            query=history_runtime._query_from_state(source_state),
        )
        history_runtime._complete_history(
            TaskCompletion(
                task_id="synthetic-error",
                label="synthetic-error",
                error=RuntimeError("synthetic history error"),
            ),
            request,
        )
        assert source_state.history_loaded
        assert source_state.history_dirty
        assert "synthetic history error" in source_state.history_error

        page = next(iter(history_runtime._HISTORY_CACHE.values()))
        for index in range(history_runtime._HISTORY_CACHE_LIMIT + 3):
            history_runtime._history_cache_put(f"history-{index}", page)
        assert len(history_runtime._HISTORY_CACHE) == (
            history_runtime._HISTORY_CACHE_LIMIT
        )
        assert "history-0" not in history_runtime._HISTORY_CACHE

        details = next(iter(history_runtime._DETAIL_CACHE.values()))
        for index in range(history_runtime._DETAIL_CACHE_LIMIT + 3):
            history_runtime._detail_cache_put(
                "repository",
                f"{index:040x}",
                details,
            )
        assert len(history_runtime._DETAIL_CACHE) == (
            history_runtime._DETAIL_CACHE_LIMIT
        )
        assert ("repository", f"{0:040x}") not in history_runtime._DETAIL_CACHE
        print("HISTORY_RUNTIME_HARDENING_SMOKE_OK")
    finally:
        history_runtime.cancel_history_runtime()
        if source_scene is not None:
            bpy.data.scenes.remove(source_scene)
        bpy.ops.preferences.addon_disable(module="blender_git_manager")
        temporary.cleanup()


if __name__ == "__main__":
    main()

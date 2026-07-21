from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_git_manager.operators import history_runtime
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state


SCREENSHOT = ROOT / "dist" / "history_ui_0.1.8.png"
TEMPORARY_ROOT = Path(tempfile.mkdtemp(prefix="blender-history-ui-"))
STARTED_AT = time.monotonic()


def run_git(git: GitService, repository: Path, *arguments: str) -> None:
    git._run_checked(list(arguments), repository, timeout=60)


def commit_file(
    git: GitService,
    repository: Path,
    filename: str,
    message: str,
) -> str:
    (repository / filename).write_text(f"{message}\n", encoding="utf-8")
    run_git(git, repository, "add", "--all")
    run_git(git, repository, "commit", "-m", message)
    return git.head_commit(repository)


def finish(exit_code: int) -> None:
    shutil.rmtree(TEMPORARY_ROOT, ignore_errors=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)


def capture_popup() -> None:
    try:
        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        result = bpy.ops.screen.screenshot(
            filepath=str(SCREENSHOT),
            check_existing=False,
        )
        assert result == {"FINISHED"}, result
        assert SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0
        state = bpy.context.scene.git_manager
        print(
            "HISTORY_UI_SMOKE_OK",
            len(state.commits),
            state.history_graph_lane_count,
            SCREENSHOT,
        )
        finish(0)
    except Exception:
        import traceback

        traceback.print_exc()
        finish(1)


def open_when_loaded():
    history_runtime._poll_history_tasks()
    state = bpy.context.scene.git_manager
    if state.history_error:
        raise AssertionError(state.history_error)
    if state.history_loaded and not state.history_loading:
        assert len(state.commits) == 4, len(state.commits)
        assert state.history_graph_lane_count >= 2
        result = bpy.ops.git_manager.open_manager("INVOKE_DEFAULT")
        assert result == {"RUNNING_MODAL"}, result
        bpy.app.timers.register(capture_popup, first_interval=1.0)
        return None
    if time.monotonic() - STARTED_AT > 20:
        raise AssertionError("History UI did not load in time.")
    return 0.1


def main() -> None:
    assert bpy.ops.preferences.addon_enable(
        module="blender_git_manager"
    ) == {"FINISHED"}

    repository = TEMPORARY_ROOT / "repository"
    repository.mkdir()
    git = GitService(process=ProcessService(echo_console=False))
    run_git(git, repository, "init", "-b", "main")
    run_git(git, repository, "config", "user.name", "History UI Test")
    run_git(git, repository, "config", "user.email", "ui@example.invalid")

    bpy.ops.wm.save_as_mainfile(filepath=str(repository / "scene.blend"))
    base = commit_file(git, repository, "base.txt", "Base scene")
    run_git(git, repository, "switch", "-c", "feature/materials")
    feature = commit_file(
        git,
        repository,
        "materials.txt",
        "Create material branch",
    )
    run_git(git, repository, "switch", "main")
    commit_file(git, repository, "lighting.txt", "Update lighting")
    run_git(
        git,
        repository,
        "merge",
        "--no-ff",
        "feature/materials",
        "-m",
        "Merge material branch",
    )
    run_git(git, repository, "tag", "v1.0", feature)
    run_git(git, repository, "switch", "--detach", base)

    state = bpy.context.scene.git_manager
    state.git_installed = True
    state.repository_path = str(repository)
    assert refresh_repository_state(
        bpy.context,
        include_dependencies=False,
        include_history=False,
    )
    state.active_tab = "HISTORY"
    history_runtime.request_history_refresh(bpy.context, force=True)
    bpy.app.timers.register(open_when_loaded, first_interval=0.1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        finish(1)

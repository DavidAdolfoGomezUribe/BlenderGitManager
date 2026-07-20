"""Blender-only smoke test for branch operations starting from detached HEAD."""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import bpy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from blender_git_manager.operators import branches as branch_operators
from blender_git_manager.operators import history as history_operators
from blender_git_manager.preferences import get_addon_preferences
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def failure_text(invoke: Callable[[], set[str]]) -> str:
    try:
        result = invoke()
    except RuntimeError as exc:
        return str(exc)
    require(result == {"CANCELLED"}, f"Expected branch switch cancellation, got {result}.")
    return "\n".join(line.message for line in bpy.context.scene.git_manager.output_lines)


def require_locks_cleared() -> None:
    state = bpy.context.scene.git_manager
    require(
        branch_operators._pending_blend_reload is None,
        "The branch reload guard was not cleared.",
    )
    require(
        history_operators._pending_commit_reload is None,
        "The commit reload guard was not cleared.",
    )
    require(not state.task_running, "The branch task lock was not cleared.")
    require(not state.task_label, "The branch task label was not cleared.")


git_executable = shutil.which("git")
if not git_executable:
    raise RuntimeError("Git is required for the detached branch smoke test.")

enable_result = bpy.ops.preferences.addon_enable(module="blender_git_manager")
require(enable_result == {"FINISHED"}, "Blender Git Manager could not be enabled.")
try:
    with tempfile.TemporaryDirectory(prefix="blender-git-manager-detached-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        blend_path = repository / "scene.blend"
        sidecar = repository / "assets" / "marker.txt"
        sidecar.parent.mkdir()

        git = GitService(
            git_executable,
            process=ProcessService(echo_console=False),
        )
        git.initialize(repository, "main")
        git.config_set("user.name", "Blender Git Manager Test", repository)
        git.config_set("user.email", "test@example.com", repository)

        scene = bpy.context.scene
        scene.git_manager.repository_path = str(repository)
        scene["detached_marker"] = "source"
        sidecar.write_text("source sidecar", encoding="utf-8")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        git.add_all(repository)
        git.commit(repository, "Detached branch source")
        source_commit = git.head_commit(repository)

        refresh_repository_state(bpy.context, include_dependencies=True)
        get_addon_preferences(bpy.context).create_backup_before_checkout = False
        git.checkout_commit(repository, source_commit)
        refresh_repository_state(bpy.context, include_dependencies=False)
        require(git.head_branch(repository) == "", "The fixture did not enter detached HEAD.")

        # `git switch -c` can attach the requested branch and still return nonzero
        # when post-checkout reports an error. The operator must accept the verified result.
        hook = repository / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        created_branch = "created-from-detached-hook"
        create_result = bpy.ops.git_manager.create_branch(
            branch_name=created_branch,
            switch_to_branch=True,
        )
        require(
            create_result == {"FINISHED"},
            "A verified branch creation was rejected because its checkout hook returned nonzero.",
        )
        require(
            git.head_branch(repository) == created_branch,
            "The requested branch was not attached after the hook warning.",
        )
        require(
            git.head_commit(repository) == source_commit,
            "The created branch moved away from the detached source commit.",
        )
        require(
            bpy.context.scene.git_manager.active_branch == created_branch,
            "The UI was not refreshed to the created branch.",
        )
        warning_output = "\n".join(
            line.message for line in bpy.context.scene.git_manager.output_lines
        )
        require(
            "checkout hook reported an error" in warning_output,
            "The successful branch creation did not retain its checkout-hook warning.",
        )
        require(
            bpy.context.scene.get("detached_marker") == "source",
            "Creating a branch from detached HEAD changed the in-memory scene.",
        )
        require(
            sidecar.read_text(encoding="utf-8") == "source sidecar",
            "Creating a branch from detached HEAD changed the sidecar.",
        )
        require(not git.repository_has_changes(repository), "Branch creation left repository changes.")
        require_locks_cleared()

        # A successful hook that mutates a tracked path must make detached->branch
        # switching fail and roll back to the exact detached source commit.
        hook.unlink()
        target_branch = "hook-mutated-target"
        git.create_branch(repository, target_branch, switch=False)
        git.checkout_commit(repository, source_commit)
        refresh_repository_state(bpy.context, include_dependencies=False)
        require(git.head_branch(repository) == "", "The second fixture did not detach HEAD.")

        hook.write_text(
            "#!/bin/sh\n"
            'branch="$(git branch --show-current)"\n'
            f'if test "$branch" = "{target_branch}"; then\n'
            "  printf 'changed by post-checkout' > 'assets/marker.txt'\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
            newline="\n",
        )
        switch_error = failure_text(
            lambda: bpy.ops.git_manager.switch_branch(branch_name=target_branch)
        )
        require(
            "Restored detached HEAD" in switch_error,
            "The hook-mutated switch did not report rollback to detached HEAD.",
        )
        require(
            git.head_branch(repository) == "",
            "The hook-mutated switch did not restore detached HEAD.",
        )
        require(
            git.head_commit(repository) == source_commit,
            "The hook-mutated switch did not restore the exact source commit.",
        )
        require(
            bpy.context.scene.git_manager.active_branch == "Detached HEAD",
            "The UI was not refreshed to detached HEAD after rollback.",
        )
        require(
            bpy.context.scene.get("detached_marker") == "source",
            "The hook-mutated switch changed the in-memory scene.",
        )
        require(
            sidecar.read_text(encoding="utf-8") == "source sidecar",
            "Whole-tree rollback did not restore the tracked sidecar.",
        )
        require(
            not git.repository_has_changes(repository),
            "The hook-mutated switch rollback left repository changes.",
        )
        require_locks_cleared()
        print("DETACHED_BRANCH_SMOKE_OK")
finally:
    bpy.ops.preferences.addon_disable(module="blender_git_manager")

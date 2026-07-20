"""Blender-only end-to-end smoke test for branch switching and .blend reloading."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import bpy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from blender_git_manager.operators import branches as branch_operators
from blender_git_manager.preferences import get_addon_preferences
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


git_executable = shutil.which("git")
if not git_executable:
    raise RuntimeError("Git is required for the Blender branch reload smoke test.")

enable_result = bpy.ops.preferences.addon_enable(module="blender_git_manager")
require(enable_result == {"FINISHED"}, "Blender Git Manager could not be enabled.")
try:
    with tempfile.TemporaryDirectory(prefix="blender-git-manager-reload-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        blend_path = repository / "scene.blend"
        git = GitService(
            git_executable,
            process=ProcessService(echo_console=False),
        )
        git.initialize(repository, "main")
        git.config_set("user.name", "Blender Git Manager Test", repository)
        git.config_set("user.email", "test@example.com", repository)

        scene = bpy.context.scene
        scene["branch_marker"] = "main"
        cube = bpy.data.objects.get("Cube")
        require(cube is not None, "Factory startup Cube was not found.")
        cube.location.x = 1.0
        scene.git_manager.repository_path = str(repository)
        scene.git_manager.task_running = True
        scene.git_manager.task_label = "State that must not persist"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        scene.git_manager.task_running = False
        scene.git_manager.task_label = ""
        git.add_all(repository)
        git.commit(repository, "Main scene")

        git.create_branch(repository, "feature", switch=True)
        bpy.context.scene["branch_marker"] = "feature"
        bpy.data.objects["Cube"].location.x = 9.0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        git.add_all(repository)
        git.commit(repository, "Feature scene")

        refresh_repository_state(bpy.context, include_dependencies=True)
        get_addon_preferences(bpy.context).create_backup_before_checkout = False

        switch_result = bpy.ops.git_manager.switch_branch(branch_name="main")

        require(switch_result == {"FINISHED"}, "Branch switch operator did not finish.")
        require(git.active_branch(repository) == "main", "Git did not switch to main.")
        require(bpy.data.filepath == str(blend_path), "The reloaded Blender filepath changed.")
        require(
            branch_operators._pending_blend_reload is None,
            "The synchronous branch reload guard was not cleared.",
        )
        require(
            not bpy.context.scene.git_manager.task_running,
            "The pending reload task lock was not cleared.",
        )
        require(bpy.context.scene.get("branch_marker") == "main", "The main scene was not reloaded.")
        require(abs(bpy.data.objects["Cube"].location.x - 1.0) < 1e-6, "Main scene data was not restored.")
        require(
            bpy.context.scene.git_manager.active_branch == "main",
            "Repository state was not refreshed after reloading.",
        )
        require(not bpy.data.is_dirty, "The branch reload left the Blender file dirty.")

        git.create_branch(repository, "broken", switch=True)
        blend_path.write_bytes(b"\x28\xb5\x2f\xfdcorrupt Blender payload")
        git.add_all(repository)
        git.commit(repository, "Broken scene fixture")
        git.switch_branch(repository, "main")

        try:
            broken_result = bpy.ops.git_manager.switch_branch(branch_name="broken")
        except RuntimeError as exc:
            broken_error = str(exc)
        else:
            require(
                broken_result == {"CANCELLED"},
                "The corrupt target .blend did not cancel the branch switch.",
            )
            broken_error = "\n".join(
                line.message for line in bpy.context.scene.git_manager.output_lines
            )
        require(
            "Restored branch 'main'" in broken_error,
            "The corrupt target .blend did not report a successful rollback.",
        )
        require(
            git.active_branch(repository) == "main",
            "A corrupt target .blend did not roll Git back to the source branch.",
        )
        require(
            bpy.context.scene.get("branch_marker") == "main",
            "A failed reload changed the in-memory scene.",
        )
        require(
            branch_operators._pending_blend_reload is None,
            "A failed reload left the synchronous guard active.",
        )
        require(
            not bpy.context.scene.git_manager.task_running,
            "A failed reload left the task lock active.",
        )
        require(
            not bpy.context.scene.git_manager.task_label,
            "A failed reload left the task label active.",
        )

        git.create_branch(repository, "hook-failure", switch=False)
        hook = repository / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        try:
            bpy.ops.git_manager.switch_branch(branch_name="hook-failure")
        except RuntimeError as exc:
            hook_error = str(exc)
        else:
            raise AssertionError("A failing post-checkout hook did not report an operator error.")
        require(
            "Restored branch 'main'" in hook_error,
            "A nonzero checkout after changing HEAD did not report a successful rollback.",
        )
        require(
            git.active_branch(repository) == "main",
            "A nonzero checkout after changing HEAD did not restore the source branch.",
        )
        require(
            bpy.context.scene.get("branch_marker") == "main",
            "A nonzero checkout changed the in-memory scene.",
        )
        require(
            branch_operators._pending_blend_reload is None,
            "A nonzero checkout left the synchronous guard active.",
        )
        require(
            not bpy.context.scene.git_manager.task_running,
            "A nonzero checkout left the task lock active.",
        )
        print("BRANCH_RELOAD_SMOKE_OK")
finally:
    bpy.ops.preferences.addon_disable(module="blender_git_manager")

"""Blender-only end-to-end smoke test for historical commit checkout."""

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
from blender_git_manager.services.lfs_service import LFSService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def commit_index(state, commit_hash: str) -> int:
    for index, commit in enumerate(state.commits):
        if commit.full_hash == commit_hash:
            return index
    raise AssertionError(f"Commit {commit_hash[:8]} was not found in History.")


def require_history_head(commit_hash: str) -> None:
    state = bpy.context.scene.git_manager
    require(state.active_tab == "HISTORY", "Commit checkout did not select the History tab.")
    require(
        0 <= state.commits_index < len(state.commits),
        "History has no selected commit after checkout.",
    )
    selected = state.commits[state.commits_index]
    require(
        selected.full_hash == commit_hash,
        "History did not select the checked-out commit.",
    )
    require(selected.is_head, "The selected History commit is not marked as HEAD.")
    head_items = [commit.full_hash for commit in state.commits if commit.is_head]
    require(
        head_items == [commit_hash],
        f"History HEAD markers are incorrect: {head_items}",
    )


def require_locks_cleared() -> None:
    state = bpy.context.scene.git_manager
    require(
        history_operators._pending_commit_reload is None,
        "The commit reload guard was not cleared.",
    )
    require(
        branch_operators._pending_blend_reload is None,
        "The branch reload guard was not cleared.",
    )
    require(not state.task_running, "The checkout task lock was not cleared.")
    require(not state.task_label, "The checkout task label was not cleared.")


def failure_text(invoke: Callable[[], set[str]]) -> str:
    try:
        result = invoke()
    except RuntimeError as exc:
        return str(exc)
    require(result == {"CANCELLED"}, f"Expected checkout cancellation, got {result}.")
    return "\n".join(line.message for line in bpy.context.scene.git_manager.output_lines)


git_executable = shutil.which("git")
if not git_executable:
    raise RuntimeError("Git is required for the Blender commit checkout smoke test.")

enable_result = bpy.ops.preferences.addon_enable(module="blender_git_manager")
require(enable_result == {"FINISHED"}, "Blender Git Manager could not be enabled.")
try:
    with tempfile.TemporaryDirectory(prefix="blender-git-manager-commit-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        blend_path = repository / "scene.blend"
        sidecar = repository / "assets" / "marker.txt"
        only_c2 = repository / "assets" / "only-c2.txt"
        corrupt_only = repository / "assets" / "corrupt-only.txt"
        sidecar.parent.mkdir()

        git = GitService(
            git_executable,
            process=ProcessService(echo_console=False),
        )
        git.initialize(repository, "main")
        git.config_set("user.name", "Blender Git Manager Test", repository)
        git.config_set("user.email", "test@example.com", repository)

        scene = bpy.context.scene
        cube = bpy.data.objects.get("Cube")
        require(cube is not None, "Factory startup Cube was not found.")
        scene.git_manager.repository_path = str(repository)
        scene["commit_marker"] = "C1"
        cube.location.x = 1.0
        sidecar.write_text("sidecar C1", encoding="utf-8")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        git.add_all(repository)
        git.commit(repository, "Commit C1")
        commit_c1 = git.head_commit(repository)

        bpy.context.scene["commit_marker"] = "C2"
        bpy.data.objects["Cube"].location.x = 2.0
        sidecar.write_text("sidecar C2", encoding="utf-8")
        only_c2.write_text("created by C2", encoding="utf-8")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        git.add_all(repository)
        git.commit(repository, "Commit C2")
        commit_c2 = git.head_commit(repository)

        require(commit_c1 != commit_c2, "The C1 and C2 fixtures resolved to the same commit.")
        require(not git.repository_has_changes(repository), "The initial repository is not clean.")
        refresh_repository_state(
            bpy.context,
            include_dependencies=True,
            include_history=True,
        )
        get_addon_preferences(bpy.context).create_backup_before_checkout = False

        # Attached main/C2 -> detached C1. This must materialize the whole tree and scene.
        state = bpy.context.scene.git_manager
        checkout_c1 = bpy.ops.git_manager.checkout_commit(
            commit_hash=commit_c1,
            commit_index=commit_index(state, commit_c1),
        )
        require(checkout_c1 == {"FINISHED"}, "Checkout from main/C2 to detached C1 failed.")
        require(git.active_branch(repository) == "", "C1 checkout did not detach HEAD.")
        require(git.head_commit(repository) == commit_c1, "HEAD is not the exact C1 commit.")
        require(bpy.data.filepath == str(blend_path), "C1 reload changed the Blender filepath.")
        require(
            bpy.context.scene.get("commit_marker") == "C1",
            "The C1 Blender scene was not reloaded.",
        )
        require(
            abs(bpy.data.objects["Cube"].location.x - 1.0) < 1e-6,
            "The C1 scene data was not restored.",
        )
        require(sidecar.read_text(encoding="utf-8") == "sidecar C1", "The C1 sidecar was not restored.")
        require(not only_c2.exists(), "A C2-only file survived checkout of the C1 tree.")
        require(not git.repository_has_changes(repository), "C1 checkout left repository changes.")
        require(
            bpy.context.scene.git_manager.active_branch == "Detached HEAD",
            "The UI does not report detached HEAD at C1.",
        )
        require_history_head(commit_c1)
        require_locks_cleared()

        # Detached C1 -> detached C2.
        state = bpy.context.scene.git_manager
        checkout_c2 = bpy.ops.git_manager.checkout_commit(
            commit_hash=commit_c2,
            commit_index=commit_index(state, commit_c2),
        )
        require(checkout_c2 == {"FINISHED"}, "Checkout from detached C1 to detached C2 failed.")
        require(git.active_branch(repository) == "", "C2 checkout unexpectedly attached HEAD.")
        require(git.head_commit(repository) == commit_c2, "HEAD is not the exact C2 commit.")
        require(
            bpy.context.scene.get("commit_marker") == "C2",
            "The C2 Blender scene was not reloaded.",
        )
        require(
            abs(bpy.data.objects["Cube"].location.x - 2.0) < 1e-6,
            "The C2 scene data was not restored.",
        )
        require(sidecar.read_text(encoding="utf-8") == "sidecar C2", "The C2 sidecar was not restored.")
        require(only_c2.read_text(encoding="utf-8") == "created by C2", "The C2-only file is missing.")
        require(not git.repository_has_changes(repository), "C2 checkout left repository changes.")
        require_history_head(commit_c2)
        require_locks_cleared()

        # Detached C2 -> attached main at the same exact commit.
        branch_result = bpy.ops.git_manager.switch_branch(branch_name="main")
        require(branch_result == {"FINISHED"}, "Switching from detached C2 to main failed.")
        require(git.active_branch(repository) == "main", "HEAD did not attach to main.")
        require(git.head_commit(repository) == commit_c2, "main does not point to C2 after switching.")
        require(
            bpy.context.scene.get("commit_marker") == "C2",
            "Switching from detached HEAD did not preserve the C2 scene.",
        )
        require(sidecar.read_text(encoding="utf-8") == "sidecar C2", "main did not restore the C2 tree.")
        require(
            bpy.context.scene.git_manager.active_branch == "main",
            "The UI did not return to branch main.",
        )
        require_locks_cleared()

        # A commit without the current .blend must be rejected before changing HEAD.
        git.create_branch(repository, "missing-blend-fixture", switch=True)
        blend_path.unlink()
        sidecar.write_text("missing blend fixture", encoding="utf-8")
        git.add_all(repository)
        git.commit(repository, "Commit without scene")
        missing_commit = git.head_commit(repository)
        git.switch_branch(repository, "main")
        refresh_repository_state(
            bpy.context,
            include_dependencies=False,
            include_history=True,
        )

        state = bpy.context.scene.git_manager
        missing_error = failure_text(
            lambda: bpy.ops.git_manager.checkout_commit(
                commit_hash=missing_commit,
                commit_index=commit_index(state, missing_commit),
            )
        )
        require(
            "does not exist as a regular file" in missing_error,
            "The missing .blend commit did not report the expected preflight error.",
        )
        require(git.active_branch(repository) == "main", "Missing .blend checkout changed the branch.")
        require(git.head_commit(repository) == commit_c2, "Missing .blend checkout changed HEAD.")
        require(
            bpy.context.scene.get("commit_marker") == "C2",
            "Missing .blend checkout changed the in-memory scene.",
        )
        require(sidecar.read_text(encoding="utf-8") == "sidecar C2", "Missing checkout changed the tree.")
        require_locks_cleared()

        # A header-valid but corrupt .blend reaches open_mainfile, then must roll back all files.
        git.create_branch(repository, "corrupt-blend-fixture", switch=True)
        blend_path.write_bytes(b"\x28\xb5\x2f\xfdcorrupt Blender payload")
        sidecar.write_text("corrupt sidecar", encoding="utf-8")
        corrupt_only.write_text("must disappear on rollback", encoding="utf-8")
        git.add_all(repository)
        git.commit(repository, "Commit with corrupt scene")
        corrupt_commit = git.head_commit(repository)
        git.switch_branch(repository, "main")
        refresh_repository_state(
            bpy.context,
            include_dependencies=False,
            include_history=True,
        )

        state = bpy.context.scene.git_manager
        corrupt_error = failure_text(
            lambda: bpy.ops.git_manager.checkout_commit(
                commit_hash=corrupt_commit,
                commit_index=commit_index(state, corrupt_commit),
            )
        )
        require(
            "Restored branch 'main'" in corrupt_error,
            "The corrupt commit did not report a successful rollback to main.",
        )
        require(git.active_branch(repository) == "main", "Corrupt checkout did not restore main.")
        require(git.head_commit(repository) == commit_c2, "Corrupt checkout did not restore C2.")
        require(
            bpy.context.scene.get("commit_marker") == "C2",
            "Corrupt checkout changed the in-memory scene.",
        )
        require(
            abs(bpy.data.objects["Cube"].location.x - 2.0) < 1e-6,
            "Corrupt checkout changed the in-memory C2 scene data.",
        )
        require(sidecar.read_text(encoding="utf-8") == "sidecar C2", "Rollback did not restore sidecar C2.")
        require(only_c2.read_text(encoding="utf-8") == "created by C2", "Rollback lost the C2-only file.")
        require(not corrupt_only.exists(), "Rollback left a corrupt-commit-only file in the tree.")
        require(not git.repository_has_changes(repository), "Corrupt checkout rollback left changes.")
        require_locks_cleared()

        # A real missing local LFS object must fail checkout and restore the complete B tree.
        lfs = LFSService(
            git_executable,
            process=ProcessService(echo_console=False),
        )
        if not lfs.version().successful:
            print("COMMIT_CHECKOUT_LFS_MISSING_SKIPPED")
        else:
            lfs_target_only = repository / "assets" / "lfs-target-only.txt"
            git.create_branch(repository, "lfs-missing-fixture", switch=True)
            lfs.initialize_local(repository)
            lfs.track(repository, "scene.blend")
            sidecar.write_text("LFS target A sidecar", encoding="utf-8")
            lfs_target_only.write_text("created only by LFS target A", encoding="utf-8")
            git._run_checked(
                ["add", "--renormalize", "--", "scene.blend"],
                repository,
                timeout=120,
            )
            git.add_all(repository)
            git.commit(repository, "Commit with missing LFS scene object")
            lfs_missing_commit = git.head_commit(repository)

            tracked_blends = [
                item
                for item in lfs.ls_files(repository)
                if item.path.replace("\\", "/") == "scene.blend"
            ]
            require(
                len(tracked_blends) == 1,
                f"Expected one LFS scene.blend entry, got {tracked_blends}.",
            )
            lfs_oid = tracked_blends[0].oid
            require(len(lfs_oid) == 64, f"Git LFS returned an invalid object ID: {lfs_oid}")
            lfs_object = (
                repository
                / ".git"
                / "lfs"
                / "objects"
                / lfs_oid[:2]
                / lfs_oid[2:4]
                / lfs_oid
            )
            require(lfs_object.is_file(), "The local LFS object fixture was not created.")

            git.switch_branch(repository, "main")
            lfs_object.unlink()
            require(not lfs_object.exists(), "The local LFS object fixture was not deleted.")
            refresh_repository_state(
                bpy.context,
                include_dependencies=False,
                include_history=True,
            )

            state = bpy.context.scene.git_manager
            lfs_error = failure_text(
                lambda: bpy.ops.git_manager.checkout_commit(
                    commit_hash=lfs_missing_commit,
                    commit_index=commit_index(state, lfs_missing_commit),
                )
            )
            require(
                "Restored branch 'main'" in lfs_error,
                "The missing LFS object did not report rollback to source branch main.",
            )
            require(
                git.active_branch(repository) == "main",
                "The missing LFS object checkout did not restore branch main.",
            )
            require(
                git.head_commit(repository) == commit_c2,
                "The missing LFS object checkout did not restore source commit C2.",
            )
            require(
                bpy.context.scene.get("commit_marker") == "C2",
                "The missing LFS object checkout changed the in-memory B scene.",
            )
            require(
                abs(bpy.data.objects["Cube"].location.x - 2.0) < 1e-6,
                "The missing LFS object checkout changed the in-memory B scene data.",
            )
            require(
                sidecar.read_text(encoding="utf-8") == "sidecar C2",
                "The missing LFS object rollback did not restore the B sidecar.",
            )
            require(
                only_c2.read_text(encoding="utf-8") == "created by C2",
                "The missing LFS object rollback lost the B-only file.",
            )
            require(
                not lfs_target_only.exists(),
                "The missing LFS object rollback left a target-A-only file.",
            )
            require(
                not (repository / ".gitattributes").exists(),
                "The missing LFS object rollback left target LFS attributes.",
            )
            require(
                not git.repository_has_changes(repository),
                "The missing LFS object rollback left repository changes.",
            )
            require_locks_cleared()
            print("COMMIT_CHECKOUT_LFS_MISSING_OK")
        print("COMMIT_CHECKOUT_SMOKE_OK")
finally:
    bpy.ops.preferences.addon_disable(module="blender_git_manager")

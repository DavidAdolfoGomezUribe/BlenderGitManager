from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import blender_git_manager
from blender_git_manager.operators import history_runtime
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state


def wait_until(predicate, label: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history_runtime._poll_history_tasks()
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {label}.")


def run_git(git: GitService, root: Path, *arguments: str):
    return git._run_checked(list(arguments), root, timeout=60)


def commit_all(git: GitService, root: Path, message: str) -> str:
    run_git(git, root, "add", "--all")
    run_git(git, root, "commit", "-m", message)
    return git.head_commit(root)


def main() -> None:
    enable_result = bpy.ops.preferences.addon_enable(module="blender_git_manager")
    assert enable_result == {"FINISHED"}, enable_result
    temporary = tempfile.TemporaryDirectory(prefix="blender-git-graph-")
    try:
        root = Path(temporary.name) / "repository"
        root.mkdir()
        git = GitService(process=ProcessService(echo_console=False))
        run_git(git, root, "init", "-b", "main")
        run_git(git, root, "config", "user.name", "History Blender Test")
        run_git(git, root, "config", "user.email", "history@example.invalid")

        blend_path = root / "scene.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        (root / "base.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(git, root, "base")

        run_git(git, root, "switch", "-c", "feature")
        (root / "feature.txt").write_text("feature\n", encoding="utf-8")
        feature = commit_all(git, root, "feature work")

        run_git(git, root, "switch", "main")
        (root / "main.txt").write_text("main\n", encoding="utf-8")
        commit_all(git, root, "main work")
        run_git(git, root, "merge", "--no-ff", "feature", "-m", "merge feature")
        merge = git.head_commit(root)
        run_git(git, root, "tag", "v1.0", feature)
        run_git(git, root, "remote", "add", "origin", "https://github.com/example/project.git")
        run_git(git, root, "update-ref", "refs/remotes/origin/main", merge)

        state = bpy.context.scene.git_manager
        state.git_installed = True
        state.repository_path = str(root)
        assert refresh_repository_state(
            bpy.context,
            include_dependencies=False,
            include_history=False,
        )
        state.active_tab = "HISTORY"
        history_runtime.request_history_refresh(bpy.context, force=True)
        wait_until(
            lambda: state.history_loaded and not state.history_loading,
            "asynchronous history",
        )

        assert len(state.commits) == 4, len(state.commits)
        assert state.commits[0].full_hash == merge
        assert state.commits[0].is_merge
        assert len(state.commits[0].parent_lane_indexes.split()) == 2
        assert state.history_graph_lane_count >= 2
        assert state.commits[0].is_head
        assert "main" in state.commits[0].local_branches.splitlines()
        assert "origin/main" in state.commits[0].remote_branches.splitlines()
        feature_item = next(item for item in state.commits if item.full_hash == feature)
        assert "v1.0" in feature_item.tags.splitlines()

        state.commits_index = 0
        history_runtime.request_history_details(bpy.context)
        wait_until(
            lambda: (
                state.history_detail_hash == merge
                and not state.history_detail_loading
                and state.history_detail_file_count > 0
            ),
            "commit details",
        )
        assert "feature.txt" in {item.path for item in state.history_detail_files}

        state.history_search = "feature work"
        assert history_runtime._apply_cached_history(bpy.context)
        assert len(state.commits) == 1
        assert state.commits[0].full_hash == feature
        state.history_search = ""
        assert history_runtime._apply_cached_history(bpy.context)
        assert len(state.commits) == 4

        assert "history_commit_click" not in dir(bpy.ops.git_manager)
        assert "checkout_commit" in dir(bpy.ops.git_manager)
        icon_items = (
            bpy.types.UILayout.bl_rna.functions["label"]
            .parameters["icon"]
            .enum_items
        )
        icon_names = {item.identifier for item in icon_items}
        required_icons = {
            "KEYTYPE_KEYFRAME_VEC",
            "KEYTYPE_BREAKDOWN_VEC",
            "KEYTYPE_EXTREME_VEC",
            "KEYTYPE_JITTER_VEC",
            "KEYTYPE_MOVING_HOLD_VEC",
            "NODETREE",
            "DECORATE_LINKED",
            "COPYDOWN",
            "LOOP_BACK",
        }
        assert required_icons <= icon_names, required_icons - icon_names
        assert base
        print("HISTORY_GRAPH_SMOKE_OK")
    finally:
        history_runtime.cancel_history_runtime()
        bpy.ops.preferences.addon_disable(module="blender_git_manager")
        temporary.cleanup()


if __name__ == "__main__":
    main()

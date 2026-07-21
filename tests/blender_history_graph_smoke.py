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

import blender_git_manager
from blender_git_manager.operators import history_runtime
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.state_sync import refresh_repository_state
from blender_git_manager.ui.dashboard import _draw_history, _draw_history_controls
from blender_git_manager.ui.graph_icons import (
    graph_cell_style,
    graph_icon_id,
    graph_icon_image_count,
)


class StrictHistoryLayout:
    """Small layout recorder with Blender 5.2's keyword-only prop_search API."""

    def __init__(self) -> None:
        self.prop_search_calls = 0
        self.enabled = True
        self.alert = False
        self.scale_y = 1.0
        self.operator_context = "EXEC_DEFAULT"

    def box(self):
        return self

    def row(self, *, align=False):
        return self

    def grid_flow(self, **_kwargs):
        return self

    def operator(self, *_args, **_kwargs):
        return SimpleNamespace()

    def prop(self, *_args, **_kwargs):
        return None

    def prop_search(
        self,
        _data,
        _property,
        _search_data,
        _search_property,
        *,
        text="",
        icon="NONE",
        **_kwargs,
    ):
        self.prop_search_calls += 1
        assert isinstance(text, str)
        assert isinstance(icon, str)

    def label(self, *_args, **_kwargs):
        return None

    def template_list(self, *_args, **_kwargs):
        return None


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

        merge_item = state.commits[0]
        merge_node = graph_cell_style(merge_item, merge_item.lane_index)
        side_lane = next(
            lane
            for lane in map(int, merge_item.parent_lane_indexes.split())
            if lane != merge_item.lane_index
        )
        side_connection = graph_cell_style(merge_item, side_lane)
        assert merge_node.node
        assert merge_node.left or merge_node.right
        assert side_connection.left or side_connection.right
        assert graph_icon_id(merge_node) > 0
        assert graph_icon_id(side_connection) > 0
        assert graph_icon_image_count() > 0

        layout = StrictHistoryLayout()
        _draw_history_controls(layout, state)
        assert layout.prop_search_calls == 1
        _draw_history(layout, bpy.context, state, expanded=True)

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

        run_git(git, root, "switch", "--detach", base)
        assert refresh_repository_state(
            bpy.context,
            include_dependencies=False,
            include_history=False,
        )
        history_runtime.request_history_refresh(bpy.context, force=True)
        wait_until(
            lambda: (
                state.history_loaded
                and not state.history_loading
                and any(
                    item.full_hash == base and item.is_head
                    for item in state.commits
                )
            ),
            "detached-HEAD graph",
        )
        assert state.active_branch == "Detached HEAD"
        assert any(item.full_hash == merge for item in state.commits)
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
        assert graph_icon_image_count() == 0
        temporary.cleanup()


if __name__ == "__main__":
    main()

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _call_history_runtime(function_name: str, context) -> None:
    """Forward RNA updates without importing Blender operators at module load."""
    try:
        from .operators import history_runtime

        function = getattr(history_runtime, function_name)
        function(context)
    except (AttributeError, ImportError, ReferenceError, RuntimeError):
        # Property updates can also run while a file/add-on is being torn down.
        pass


def _history_tab_updated(_state, context) -> None:
    _call_history_runtime("on_history_tab_changed", context)


def _history_filter_updated(_state, context) -> None:
    _call_history_runtime("schedule_history_filter", context)


def _history_query_updated(_state, context) -> None:
    _call_history_runtime("schedule_history_refresh", context)


def _history_selection_updated(_state, context) -> None:
    _call_history_runtime("schedule_history_details", context)


class GitFileChangeItem(bpy.types.PropertyGroup):
    selected: BoolProperty(name="Selected", default=False)
    index_status: StringProperty()
    worktree_status: StringProperty()
    status_code: StringProperty()
    path: StringProperty()
    original_path: StringProperty()
    size_label: StringProperty()
    uses_lfs: BoolProperty(default=False)
    staged: BoolProperty(default=False)
    conflicted: BoolProperty(default=False)
    untracked: BoolProperty(default=False)


class GitCommitItem(bpy.types.PropertyGroup):
    full_hash: StringProperty()
    short_hash: StringProperty()
    subject: StringProperty()
    body: StringProperty()
    author_name: StringProperty()
    author_email: StringProperty()
    authored_at: StringProperty()
    decorations: StringProperty()
    parent_hashes: StringProperty()
    local_branches: StringProperty()
    remote_branches: StringProperty()
    tags: StringProperty()
    display_date: StringProperty()
    lane_index: IntProperty(default=0)
    parent_lane_indexes: StringProperty()
    active_lane_indexes: StringProperty()
    outgoing_lane_indexes: StringProperty()
    graph_lane_count: IntProperty(default=1)
    is_merge: BoolProperty(default=False)
    is_head: BoolProperty(default=False)


class GitCommitFileItem(bpy.types.PropertyGroup):
    status: StringProperty()
    path: StringProperty()
    old_path: StringProperty()
    additions: IntProperty(default=0)
    deletions: IntProperty(default=0)
    binary: BoolProperty(default=False)


class GitBranchItem(bpy.types.PropertyGroup):
    name: StringProperty()
    full_ref: StringProperty()
    current: BoolProperty(default=False)
    remote: BoolProperty(default=False)
    upstream: StringProperty()
    short_hash: StringProperty()
    subject: StringProperty()
    author: StringProperty()
    authored_at: StringProperty()


class GitOutputLine(bpy.types.PropertyGroup):
    timestamp: StringProperty()
    level: EnumProperty(
        items=(
            ("INFO", "Info", ""),
            ("SUCCESS", "Success", ""),
            ("WARNING", "Warning", ""),
            ("ERROR", "Error", ""),
        ),
        default="INFO",
    )
    message: StringProperty()


class GitManagerState(bpy.types.PropertyGroup):
    repository_path: StringProperty(name="Repository path", subtype="DIR_PATH")
    repository_name: StringProperty()
    remote_url: StringProperty()
    active_branch: StringProperty()
    upstream: StringProperty()
    ahead: IntProperty(default=0)
    behind: IntProperty(default=0)
    sync_label: StringProperty(default="Not checked")
    last_commit_hash: StringProperty()
    last_commit_subject: StringProperty()
    last_commit_author: StringProperty()

    git_installed: BoolProperty(default=False)
    lfs_installed: BoolProperty(default=False)
    gh_installed: BoolProperty(default=False)
    git_version: StringProperty()
    lfs_version: StringProperty()
    gh_version: StringProperty()
    lfs_active: BoolProperty(default=False)
    github_authenticated: BoolProperty(default=False)
    github_user: StringProperty()

    blend_unsaved: BoolProperty(default=False)
    task_running: BoolProperty(default=False, options={"SKIP_SAVE"})
    task_label: StringProperty(options={"SKIP_SAVE"})
    status_message: StringProperty()

    commit_message: StringProperty(name="Commit message")
    commit_description: StringProperty(name="Extended description")
    save_before_commit: BoolProperty(name="Save Blender file before commit", default=True)

    active_tab: EnumProperty(
        name="Section",
        items=(
            ("CHANGES", "Changes", "Repository changes", "FILE_REFRESH", 0),
            ("HISTORY", "History", "Commit history", "TIME", 1),
            ("BRANCHES", "Branches", "Local and remote branches", "OUTLINER_OB_ARMATURE", 2),
            ("LFS", "Git LFS", "Large file configuration", "PACKAGE", 3),
            ("OUTPUT", "Output", "Command output", "CONSOLE", 4),
        ),
        default="CHANGES",
        update=_history_tab_updated,
    )

    changes: CollectionProperty(type=GitFileChangeItem)
    changes_index: IntProperty(default=0)
    commits: CollectionProperty(type=GitCommitItem, options={"SKIP_SAVE"})
    commits_index: IntProperty(
        default=0,
        options={"SKIP_SAVE"},
        update=_history_selection_updated,
    )
    branches: CollectionProperty(type=GitBranchItem)
    branches_index: IntProperty(default=0)
    output_lines: CollectionProperty(type=GitOutputLine, options={"SKIP_SAVE"})
    output_index: IntProperty(default=0, options={"SKIP_SAVE"})

    history_search: StringProperty(
        name="Search",
        description="Filter by commit message, author, email or hash",
        options={"TEXTEDIT_UPDATE", "SKIP_SAVE"},
        update=_history_filter_updated,
    )
    history_branch_filter: StringProperty(
        name="Branch Filter",
        description="Limit history to commits reachable from this local or remote branch",
        options={"SKIP_SAVE"},
        update=_history_query_updated,
    )
    history_author_filter: StringProperty(
        name="Author Filter",
        description="Filter by author name or email",
        options={"TEXTEDIT_UPDATE", "SKIP_SAVE"},
        update=_history_filter_updated,
    )
    history_show_all_branches: BoolProperty(
        name="Show All Branches",
        default=True,
        options={"SKIP_SAVE"},
        update=_history_query_updated,
    )
    history_show_remotes: BoolProperty(
        name="Show Remotes",
        default=True,
        options={"SKIP_SAVE"},
        update=_history_query_updated,
    )
    history_show_tags: BoolProperty(
        name="Show Tags",
        default=True,
        options={"SKIP_SAVE"},
        update=_history_query_updated,
    )
    history_limit: IntProperty(default=200, min=100, max=1000, options={"SKIP_SAVE"})
    history_loaded: BoolProperty(default=False, options={"SKIP_SAVE"})
    history_loading: BoolProperty(default=False, options={"SKIP_SAVE"})
    history_dirty: BoolProperty(default=True, options={"SKIP_SAVE"})
    history_has_more: BoolProperty(default=False, options={"SKIP_SAVE"})
    history_error: StringProperty(options={"SKIP_SAVE"})
    history_loaded_count: IntProperty(default=0, options={"SKIP_SAVE"})
    history_visible_count: IntProperty(default=0, options={"SKIP_SAVE"})
    history_graph_lane_count: IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    history_show_details: BoolProperty(
        name="Show Commit Details",
        default=False,
        options={"SKIP_SAVE"},
    )
    history_generation: IntProperty(default=0, options={"SKIP_SAVE"})
    history_repository_signature: StringProperty(options={"SKIP_SAVE"})

    history_detail_hash: StringProperty(options={"SKIP_SAVE"})
    history_detail_loading: BoolProperty(default=False, options={"SKIP_SAVE"})
    history_detail_error: StringProperty(options={"SKIP_SAVE"})
    history_detail_message: StringProperty(options={"SKIP_SAVE"})
    history_detail_body: StringProperty(options={"SKIP_SAVE"})
    history_detail_author_name: StringProperty(options={"SKIP_SAVE"})
    history_detail_author_email: StringProperty(options={"SKIP_SAVE"})
    history_detail_date: StringProperty(options={"SKIP_SAVE"})
    history_detail_parents: StringProperty(options={"SKIP_SAVE"})
    history_detail_local_branches: StringProperty(options={"SKIP_SAVE"})
    history_detail_remote_branches: StringProperty(options={"SKIP_SAVE"})
    history_detail_tags: StringProperty(options={"SKIP_SAVE"})
    history_detail_file_count: IntProperty(default=0, options={"SKIP_SAVE"})
    history_detail_additions: IntProperty(default=0, options={"SKIP_SAVE"})
    history_detail_deletions: IntProperty(default=0, options={"SKIP_SAVE"})
    history_detail_files: CollectionProperty(type=GitCommitFileItem, options={"SKIP_SAVE"})
    history_detail_files_index: IntProperty(default=0, options={"SKIP_SAVE"})


CLASSES = (
    GitFileChangeItem,
    GitCommitItem,
    GitCommitFileItem,
    GitBranchItem,
    GitOutputLine,
    GitManagerState,
)


def register_properties() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.git_manager = PointerProperty(type=GitManagerState)


def unregister_properties() -> None:
    if hasattr(bpy.types.Scene, "git_manager"):
        del bpy.types.Scene.git_manager
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

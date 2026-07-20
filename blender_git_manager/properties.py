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
    is_merge: BoolProperty(default=False)


class GitBranchItem(bpy.types.PropertyGroup):
    name: StringProperty()
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
    )

    changes: CollectionProperty(type=GitFileChangeItem)
    changes_index: IntProperty(default=0)
    commits: CollectionProperty(type=GitCommitItem)
    commits_index: IntProperty(default=0)
    branches: CollectionProperty(type=GitBranchItem)
    branches_index: IntProperty(default=0)
    output_lines: CollectionProperty(type=GitOutputLine, options={"SKIP_SAVE"})
    output_index: IntProperty(default=0, options={"SKIP_SAVE"})


CLASSES = (
    GitFileChangeItem,
    GitCommitItem,
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

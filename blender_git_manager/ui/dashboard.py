from __future__ import annotations

import bpy


def _dependency_row(layout, label: str, installed: bool, version: str):
    row = layout.row(align=True)
    row.label(text=label)
    row.label(text="Installed" if installed else "Missing", icon="CHECKMARK" if installed else "ERROR")
    if version:
        row.label(text=version[:70])


def _draw_dependencies(layout, state):
    box = layout.box()
    box.label(text="Dependencies", icon="TOOL_SETTINGS")
    _dependency_row(box, "Git", state.git_installed, state.git_version)
    _dependency_row(box, "Git LFS", state.lfs_installed, state.lfs_version)
    _dependency_row(box, "GitHub CLI", state.gh_installed, state.gh_version)
    if state.gh_installed:
        row = box.row(align=True)
        if state.github_authenticated:
            row.label(text=f"GitHub: {state.github_user or 'Authenticated'}", icon="CHECKMARK")
            row.operator("git_manager.github_logout", text="Disconnect")
        else:
            row.label(text="GitHub: Not authenticated", icon="ERROR")
            row.operator("git_manager.github_login", text="Connect in Browser", icon="URL")


def _draw_onboarding(layout, state):
    box = layout.box()
    box.scale_y = 1.3
    box.label(text="No Git repository detected", icon="INFO")
    box.label(text="Create a repository for the current Blender project, open an existing one, or clone from GitHub.")
    column = box.column(align=True)
    column.operator("git_manager.initialize_repository", text="Initialize Repository", icon="ADD")
    column.operator("git_manager.open_repository", text="Open Existing Repository", icon="FILE_FOLDER")
    column.operator("git_manager.clone_repository", text="Clone from GitHub", icon="IMPORT")
    if not state.git_installed:
        box.label(text="Install Git first or configure its executable path in Settings.", icon="ERROR")
        box.operator("git_manager.open_preferences", text="Settings", icon="PREFERENCES")


def _draw_header(layout, state):
    box = layout.box()
    row = box.row(align=True)
    row.label(text=state.repository_name or "Repository", icon="FILE_FOLDER")
    row.label(text=f"Branch: {state.active_branch}", icon="OUTLINER_OB_ARMATURE")
    row.label(text=state.sync_label, icon="CHECKMARK" if state.ahead == 0 and state.behind == 0 else "ERROR")
    row.operator("git_manager.refresh", text="", icon="FILE_REFRESH")

    grid = box.grid_flow(columns=2, even_columns=False, even_rows=False, align=True)
    grid.label(text=f"Path: {state.repository_path}")
    grid.label(text=f"Remote: {state.remote_url or 'Not configured'}")
    grid.label(text=f"Last commit: {state.last_commit_hash} {state.last_commit_subject}")
    grid.label(text=f"Author: {state.last_commit_author or '-'}")

    row = box.row(align=True)
    row.operator("git_manager.open_folder", icon="FILE_FOLDER")
    if state.remote_url:
        row.operator("git_manager.open_remote", icon="URL")
    else:
        row.operator("git_manager.connect_remote", icon="LINKED")
        if state.github_authenticated:
            row.operator("git_manager.create_github_repository", text="Create on GitHub", icon="URL")
    row.operator("git_manager.open_preferences", text="Settings", icon="PREFERENCES")


def _draw_sync(layout, state):
    box = layout.box()
    row = box.row(align=True)
    row.label(text=f"Upstream: {state.upstream or 'Not configured'}")
    for operation, label, icon in (
        ("FETCH", "Fetch", "IMPORT"),
        ("PULL", "Pull", "TRIA_DOWN"),
        ("PUSH", "Push", "TRIA_UP"),
        ("SYNC", "Sync", "FILE_REFRESH"),
    ):
        operator = row.operator("git_manager.synchronize", text=label, icon=icon)
        operator.operation = operation


def _draw_changes(layout, state):
    row = layout.row()
    row.template_list("GITMANAGER_UL_changes", "", state, "changes", state, "changes_index", rows=10)

    actions = layout.row(align=True)
    operator = actions.operator("git_manager.stage", text="Stage Selected", icon="ADD")
    operator.stage_all = False
    operator = actions.operator("git_manager.stage", text="Stage All", icon="CHECKMARK")
    operator.stage_all = True
    operator = actions.operator("git_manager.unstage", text="Unstage Selected", icon="REMOVE")
    operator.unstage_all = False
    operator = actions.operator("git_manager.unstage", text="Unstage All", icon="X")
    operator.unstage_all = True
    actions.operator("git_manager.discard_changes", text="Discard Selected", icon="TRASH")

    commit = layout.box()
    commit.label(text="Create Commit", icon="CHECKMARK")
    commit.prop(state, "commit_message")
    commit.prop(state, "commit_description")
    commit.prop(state, "save_before_commit")
    staged_count = sum(1 for item in state.changes if item.staged)
    commit.label(text=f"Staged files: {staged_count}")
    row = commit.row(align=True)
    operator = row.operator("git_manager.commit", text="Commit", icon="CHECKMARK")
    operator.push_after = False
    operator = row.operator("git_manager.commit", text="Commit and Push", icon="EXPORT")
    operator.push_after = True


def _draw_history(layout, state):
    layout.template_list("GITMANAGER_UL_commits", "", state, "commits", state, "commits_index", rows=12)
    if 0 <= state.commits_index < len(state.commits):
        commit = state.commits[state.commits_index]
        details = layout.box()
        details.label(text=commit.subject, icon="INFO")
        details.label(text=f"Hash: {commit.full_hash}")
        details.label(text=f"Author: {commit.author_name} <{commit.author_email}>")
        details.label(text=f"Date: {commit.authored_at}")
        details.label(text=f"Parents: {commit.parent_hashes or '-'}")
        details.label(text=f"Refs: {commit.decorations or '-'}")
        if commit.body:
            for line in commit.body.splitlines()[:8]:
                details.label(text=line)


def _draw_branches(layout, state):
    row = layout.row(align=True)
    row.operator("git_manager.create_branch", icon="ADD")
    row.label(text="Branch switching is blocked while the .blend has unsaved changes.")
    layout.template_list("GITMANAGER_UL_branches", "", state, "branches", state, "branches_index", rows=12)


def _draw_lfs(layout, state):
    box = layout.box()
    box.label(text=f"Git LFS: {'Active' if state.lfs_active else 'Inactive'}", icon="PACKAGE")
    box.label(text="Git LFS stores large binary content outside normal Git objects and tracks pointers in Git.")
    box.label(text="After changing patterns, stage and commit .gitattributes.", icon="INFO")
    row = box.row(align=True)
    row.operator("git_manager.lfs_track", text="Track Pattern", icon="ADD")
    row.operator("git_manager.lfs_untrack", text="Untrack Pattern", icon="REMOVE")
    lfs_changes = [item.path for item in state.changes if item.uses_lfs]
    box.label(text=f"Changed files currently recognized by LFS: {len(lfs_changes)}")
    for path in lfs_changes[:15]:
        box.label(text=path, icon="FILE")


def _draw_output(layout, state):
    layout.template_list("GITMANAGER_UL_output", "", state, "output_lines", state, "output_index", rows=14)


def draw_dashboard(layout, context: bpy.types.Context, expanded: bool = False):
    state = context.scene.git_manager
    if state.task_running:
        task = layout.box()
        task.label(text=f"Running: {state.task_label}", icon="TIME")
        task.label(text="Press Esc to cancel the external process.")

    if expanded or not state.git_installed or not state.repository_path:
        _draw_dependencies(layout, state)

    if not state.repository_path or not state.repository_name:
        _draw_onboarding(layout, state)
        if state.output_lines:
            output = layout.box()
            output.label(text="Git Output", icon="CONSOLE")
            _draw_output(output, state)
        return

    _draw_header(layout, state)
    _draw_sync(layout, state)
    layout.prop(state, "active_tab", expand=True)

    if state.active_tab == "CHANGES":
        _draw_changes(layout, state)
    elif state.active_tab == "HISTORY":
        _draw_history(layout, state)
    elif state.active_tab == "BRANCHES":
        _draw_branches(layout, state)
    elif state.active_tab == "LFS":
        _draw_lfs(layout, state)
    else:
        _draw_output(layout, state)

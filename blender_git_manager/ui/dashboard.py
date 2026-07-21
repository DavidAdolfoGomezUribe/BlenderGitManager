from __future__ import annotations

import traceback

import bpy

from .lists import draw_commit_list_header


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


def _draw_header(layout, state, *, compact: bool = False):
    box = layout.box()
    row = box.row(align=True)
    row.label(text=state.repository_name or "Repository", icon="FILE_FOLDER")
    row.label(text=f"Branch: {state.active_branch}", icon="OUTLINER_OB_ARMATURE")
    row.label(text=state.sync_label, icon="CHECKMARK" if state.ahead == 0 and state.behind == 0 else "ERROR")
    row.operator("git_manager.refresh", text="", icon="FILE_REFRESH")

    if compact:
        row = box.row(align=True)
        row.label(
            text=(
                f"Last commit: {state.last_commit_hash} "
                f"{state.last_commit_subject}"
            )
        )
        row.label(text=f"Author: {state.last_commit_author or '-'}")
        row.operator("git_manager.open_folder", text="", icon="FILE_FOLDER")
        if state.remote_url:
            row.operator("git_manager.open_remote", text="", icon="URL")
        row.operator("git_manager.open_preferences", text="", icon="PREFERENCES")
        return

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
    if state.active_branch == "Detached HEAD":
        commit.label(
            text="Create or switch to a branch before committing this historical version.",
            icon="ERROR",
        )
    row = commit.row(align=True)
    row.enabled = state.active_branch != "Detached HEAD"
    operator = row.operator("git_manager.commit", text="Commit", icon="CHECKMARK")
    operator.push_after = False
    operator = row.operator("git_manager.commit", text="Commit and Push", icon="EXPORT")
    operator.push_after = True


def _draw_history_controls(layout, state):
    controls = layout.box()
    top = controls.row(align=True)
    top.operator("git_manager.history_refresh", text="Refresh", icon="FILE_REFRESH")
    top.prop(state, "history_search", text="", icon="VIEWZOOM")
    top.operator("git_manager.history_load_more", text="Load More", icon="ADD")

    filters = controls.row(align=True)
    try:
        filters.prop_search(
            state,
            "history_branch_filter",
            state,
            "branches",
            text="Branch",
            icon="OUTLINER_OB_ARMATURE",
        )
    except TypeError as exc:
        print(
            "[Blender Git Manager][UI][WARNING] "
            f"Branch search control fell back to a text field: {exc}"
        )
        filters.prop(
            state,
            "history_branch_filter",
            text="Branch",
            icon="OUTLINER_OB_ARMATURE",
        )
    filters.prop(state, "history_author_filter", text="Author", icon="USER")
    filters.prop(
        state,
        "history_show_all_branches",
        text="All",
        toggle=True,
        icon="COMMUNITY",
    )
    filters.prop(
        state,
        "history_show_remotes",
        text="Remotes",
        toggle=True,
        icon="URL",
    )
    filters.prop(
        state,
        "history_show_tags",
        text="Tags",
        toggle=True,
        icon="BOOKMARKS",
    )
    filters.label(
        text=(
            f"{state.history_visible_count} visible / "
            f"{state.history_loaded_count} loaded"
        )
    )


def _draw_history_graph(layout, context, state, rows: int):
    graph = layout.box()
    title = graph.row(align=True)
    title.label(text="Git Graph", icon="NODETREE")
    if state.history_loading:
        title.label(text="Loading in background…", icon="TIME")
    elif state.history_error:
        title.label(text="Could not load history", icon="ERROR")
    elif state.history_dirty:
        title.label(text="Update pending", icon="FILE_REFRESH")

    draw_commit_list_header(context, graph, state)

    if state.history_error:
        error = graph.box()
        error.alert = True
        error.label(text=state.history_error[:240], icon="ERROR")

    if state.commits:
        graph.template_list(
            "GITMANAGER_UL_commits",
            "",
            state,
            "commits",
            state,
            "commits_index",
            rows=rows,
        )
    elif state.history_loading:
        graph.label(text="Reading commits and calculating graph lanes…", icon="TIME")
    elif state.history_loaded:
        graph.label(text="No commits match the current history filters.", icon="INFO")
    else:
        graph.label(text="History has not been loaded yet.", icon="INFO")

    if 0 <= state.commits_index < len(state.commits):
        commit = state.commits[state.commits_index]
        action = graph.row(align=True)
        action.operator_context = "INVOKE_DEFAULT"
        operator = action.operator(
            "git_manager.checkout_commit",
            text="Load Selected Commit",
            icon="FILE_REFRESH",
        )
        operator.commit_hash = commit.full_hash
        operator.commit_index = state.commits_index

    pagination = graph.row(align=True)
    pagination.enabled = bool(state.history_has_more and not state.history_loading)
    pagination.operator(
        "git_manager.history_load_more",
        text=f"Load {min(100, max(0, 1000 - state.history_limit))} More Commits",
        icon="TRIA_DOWN",
    )


def _draw_history_details(layout, state):
    details = layout.box()
    details.label(text="Commit Details", icon="INFO")
    if not (0 <= state.commits_index < len(state.commits)):
        details.label(text="Select a commit to inspect it.")
        return

    commit = state.commits[state.commits_index]
    details.label(text=commit.subject or "(No commit message)", icon="DECORATE_LINKED" if commit.is_merge else "DOT")
    if commit.body:
        for line in commit.body.splitlines()[:8]:
            details.label(text=line[:160])

    identity = details.column(align=True)
    identity.label(text=f"Hash: {commit.full_hash}")
    identity.label(text=f"Author: {commit.author_name} <{commit.author_email}>")
    identity.label(text=f"Date: {commit.authored_at}")
    identity.label(text=f"Parents: {commit.parent_hashes or 'Root commit'}")
    if commit.local_branches:
        identity.label(text=f"Branches: {', '.join(commit.local_branches.splitlines())}", icon="OUTLINER_OB_ARMATURE")
    if commit.remote_branches:
        identity.label(text=f"Remotes: {', '.join(commit.remote_branches.splitlines())}", icon="URL")
    if commit.tags:
        identity.label(text=f"Tags: {', '.join(commit.tags.splitlines())}", icon="BOOKMARKS")
    if commit.is_head:
        identity.label(text="HEAD / current repository position", icon="RADIOBUT_ON")

    actions = details.grid_flow(columns=2, even_columns=True, even_rows=True, align=True)
    copy = actions.operator("git_manager.copy_commit_hash", text="Copy Commit Hash", icon="COPYDOWN")
    copy.commit_hash = commit.full_hash
    branch = actions.operator(
        "git_manager.create_branch_from_commit",
        text="Create Branch from Commit",
        icon="ADD",
    )
    branch.commit_hash = commit.full_hash
    tag = actions.operator("git_manager.create_tag_from_commit", text="Create Tag", icon="BOOKMARKS")
    tag.commit_hash = commit.full_hash
    open_remote = actions.operator(
        "git_manager.open_commit_remote",
        text="Open Commit on GitHub",
        icon="URL",
    )
    open_remote.commit_hash = commit.full_hash

    destructive = details.row(align=True)
    revert = destructive.operator(
        "git_manager.revert_commit",
        text="Revert Commit",
        icon="LOOP_BACK",
    )
    revert.commit_hash = commit.full_hash

    files = details.box()
    if state.history_detail_loading and state.history_detail_hash == commit.full_hash:
        files.label(text="Loading changed files and statistics…", icon="TIME")
    elif state.history_detail_error and state.history_detail_hash == commit.full_hash:
        files.alert = True
        files.label(text=state.history_detail_error[:220], icon="ERROR")
    elif state.history_detail_hash == commit.full_hash:
        files.label(
            text=(
                f"{state.history_detail_file_count} file(s)   "
                f"+{state.history_detail_additions}   "
                f"-{state.history_detail_deletions}"
            ),
            icon="FILE",
        )
        if state.history_detail_files:
            files.template_list(
                "GITMANAGER_UL_commit_files",
                "",
                state,
                "history_detail_files",
                state,
                "history_detail_files_index",
                rows=7,
            )
        else:
            files.label(text="This commit has no file changes to display.")
    else:
        files.label(text="Select a commit to load its changed files.", icon="INFO")


def _draw_history(layout, context, state, expanded: bool):
    _draw_history_controls(layout, state)
    region_height = int(getattr(getattr(context, "region", None), "height", 720))
    if expanded:
        rows = max(6, min(12, (region_height - 300) // 22))
    else:
        rows = 8
    _draw_history_graph(layout, context, state, rows=rows)

    detail_toggle = layout.row(align=True)
    detail_toggle.prop(
        state,
        "history_show_details",
        text=(
            "Hide Commit Details"
            if state.history_show_details
            else "Show Commit Details"
        ),
        toggle=True,
        icon="TRIA_DOWN" if state.history_show_details else "TRIA_RIGHT",
    )
    if state.history_show_details:
        _draw_history_details(layout, state)


def _draw_branches(layout, state):
    row = layout.row(align=True)
    row.operator("git_manager.create_branch", icon="ADD")
    row.label(text="Branch switching requires a clean repository and a saved .blend.")
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
        if "GitHub browser authentication" in state.task_label:
            task.operator(
                "git_manager.show_github_device_code",
                text="Show GitHub Device Code",
                icon="INFO",
            )

    history_mode = state.active_tab == "HISTORY"
    if (
        not state.git_installed
        or not state.repository_path
        or (expanded and not history_mode)
    ):
        _draw_dependencies(layout, state)

    if not state.repository_path or not state.repository_name:
        _draw_onboarding(layout, state)
        if state.output_lines:
            output = layout.box()
            output.label(text="Git Output", icon="CONSOLE")
            _draw_output(output, state)
        return

    _draw_header(layout, state, compact=bool(expanded and history_mode))
    _draw_sync(layout, state)
    layout.prop(state, "active_tab", expand=True)

    if state.active_tab == "CHANGES":
        _draw_changes(layout, state)
    elif state.active_tab == "HISTORY":
        try:
            _draw_history(layout, context, state, expanded)
        except Exception as exc:
            print(f"[Blender Git Manager][UI][ERROR] History draw failed: {exc}")
            traceback.print_exc()
            error = layout.box()
            error.alert = True
            error.label(text="History could not be drawn.", icon="ERROR")
            error.label(text=str(exc)[:240])
            error.operator(
                "git_manager.history_refresh",
                text="Retry History",
                icon="FILE_REFRESH",
            )
    elif state.active_tab == "BRANCHES":
        _draw_branches(layout, state)
    elif state.active_tab == "LFS":
        _draw_lfs(layout, state)
    else:
        _draw_output(layout, state)

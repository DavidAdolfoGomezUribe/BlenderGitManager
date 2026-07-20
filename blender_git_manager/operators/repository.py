from __future__ import annotations

from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..models import InitConfig, InitReport
from ..preferences import get_addon_preferences
from ..state_sync import append_output, build_services, refresh_repository_state
from ..utils.validation import ValidationError, validate_remote_url, validate_repository_name
from .base import AsyncModalMixin, reject_if_task_running


class GITMANAGER_OT_open_manager(bpy.types.Operator):
    bl_idname = "git_manager.open_manager"
    bl_label = "Blender Git Manager"

    def invoke(self, context, _event):
        refresh_repository_state(context)
        return context.window_manager.invoke_popup(self, width=960)

    def draw(self, context):
        from ..ui.dashboard import draw_dashboard

        draw_dashboard(self.layout, context, expanded=True)

    def execute(self, _context):
        return {"FINISHED"}


class GITMANAGER_OT_open_repository(bpy.types.Operator):
    bl_idname = "git_manager.open_repository"
    bl_label = "Open Existing Repository"

    directory: StringProperty(name="Repository folder", subtype="DIR_PATH")

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        git, _lfs, _github, _repository = build_services(context)
        root = git.detect_root(self.directory)
        if not root:
            self.report({"ERROR"}, "The selected folder is not inside a Git repository.")
            return {"CANCELLED"}
        context.scene.git_manager.repository_path = str(root)
        refresh_repository_state(context)
        append_output(context, f"Opened repository: {root}", "SUCCESS")
        return {"FINISHED"}


class GITMANAGER_OT_initialize_repository(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.initialize_repository"
    bl_label = "Initialize Repository"
    bl_description = "Create a Git repository, configure Git LFS and optionally create the first commit"

    directory: StringProperty(name="Repository folder", subtype="DIR_PATH")
    repository_name: StringProperty(name="Repository name")
    initial_branch: StringProperty(name="Initial branch", default="main")
    author_name: StringProperty(name="Git author name")
    author_email: StringProperty(name="Git author email")
    apply_identity_globally: BoolProperty(name="Apply identity globally", default=False)
    save_blend_inside_repository: BoolProperty(name="Save current .blend inside repository", default=True)
    create_gitignore: BoolProperty(name="Create Blender .gitignore", default=True)
    overwrite_gitignore: BoolProperty(name="Overwrite existing .gitignore", default=False)
    enable_lfs: BoolProperty(name="Enable Git LFS", default=True)
    track_blend: BoolProperty(name="Track *.blend", default=True)
    track_fbx: BoolProperty(name="Track *.fbx", default=True)
    track_glb: BoolProperty(name="Track *.glb and *.gltf", default=True)
    track_textures: BoolProperty(name="Track large texture sources", default=False)
    create_initial_commit: BoolProperty(name="Create initial commit", default=True)
    initial_commit_message: StringProperty(name="Initial commit message", default="Initial commit")
    stage_mode: EnumProperty(
        name="Initial staging",
        items=(
            ("ALL", "Stage All", "Stage every non-ignored project file"),
            ("RECOMMENDED", "Stage Recommended", "Stage .gitignore, .gitattributes and root .blend files"),
            ("NONE", "Skip Staging", "Create the repository without staging files"),
        ),
        default="ALL",
    )
    connect_github: BoolProperty(name="Create and connect GitHub repository", default=False)
    github_owner: StringProperty(name="Owner or organization")
    github_visibility: EnumProperty(
        name="Visibility",
        items=(("private", "Private", ""), ("public", "Public", "")),
        default="private",
    )
    github_description: StringProperty(name="Description")
    push_initial_branch: BoolProperty(name="Push initial branch", default=True)

    def invoke(self, context, _event):
        preferences = get_addon_preferences(context)
        git, _lfs, _github, _repository = build_services(context)
        if bpy.data.filepath:
            folder = Path(bpy.data.filepath).resolve().parent
            self.directory = str(folder)
            self.repository_name = folder.name
        else:
            default_folder = Path.home() / "BlenderProjects" / "UntitledProject"
            self.directory = str(default_folder)
            self.repository_name = default_folder.name
        self.initial_branch = preferences.default_branch
        self.author_name = git.config_get("user.name", global_scope=True)
        self.author_email = git.config_get("user.email", global_scope=True)
        return context.window_manager.invoke_props_dialog(self, width=680)

    def draw(self, context):
        layout = self.layout
        state = context.scene.git_manager

        location = layout.box()
        location.label(text="1. Repository", icon="FILE_FOLDER")
        location.prop(self, "directory")
        location.prop(self, "repository_name")
        location.prop(self, "initial_branch")
        location.prop(self, "save_blend_inside_repository")

        identity = layout.box()
        identity.label(text="2. Git identity", icon="USER")
        identity.prop(self, "author_name")
        identity.prop(self, "author_email")
        identity.prop(self, "apply_identity_globally")

        files = layout.box()
        files.label(text="3. Project files", icon="FILE")
        row = files.row(align=True)
        row.prop(self, "create_gitignore")
        row.prop(self, "overwrite_gitignore")
        files.prop(self, "enable_lfs")
        if self.enable_lfs:
            row = files.row(align=True)
            row.prop(self, "track_blend")
            row.prop(self, "track_fbx")
            row.prop(self, "track_glb")
            row.prop(self, "track_textures")

        commit = layout.box()
        commit.label(text="4. Initial commit", icon="CHECKMARK")
        commit.prop(self, "stage_mode")
        commit.prop(self, "create_initial_commit")
        if self.create_initial_commit:
            commit.prop(self, "initial_commit_message")

        remote = layout.box()
        remote.label(text="5. GitHub (optional)", icon="URL")
        remote.prop(self, "connect_github")
        if self.connect_github:
            if not state.github_authenticated:
                remote.label(text="Authenticate with GitHub before running this wizard.", icon="ERROR")
                remote.operator("git_manager.github_login", icon="URL")
            remote.prop(self, "github_owner")
            remote.prop(self, "github_visibility")
            remote.prop(self, "github_description")
            remote.prop(self, "push_initial_branch")

    def _save_blend(self) -> None:
        if not self.save_blend_inside_repository:
            return
        root = Path(self.directory).expanduser().resolve(strict=False)
        root.mkdir(parents=True, exist_ok=True)
        current = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
        if current and current.parent == root:
            bpy.ops.wm.save_mainfile()
            return
        target_name = f"{validate_repository_name(self.repository_name)}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(root / target_name), copy=False)

    def execute(self, context):
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        try:
            self._save_blend()
        except Exception as exc:
            self.report({"ERROR"}, f"Could not save the Blender file: {exc}")
            return {"CANCELLED"}

        patterns: list[str] = []
        if self.track_blend:
            patterns.append("*.blend")
        if self.track_fbx:
            patterns.append("*.fbx")
        if self.track_glb:
            patterns.extend(("*.glb", "*.gltf"))
        if self.track_textures:
            patterns.extend(("*.psd", "*.tif", "*.tiff", "*.exr", "*.hdr"))

        config = InitConfig(
            repository_path=Path(self.directory),
            repository_name=self.repository_name,
            initial_branch=self.initial_branch,
            author_name=self.author_name,
            author_email=self.author_email,
            apply_identity_globally=self.apply_identity_globally,
            create_gitignore=self.create_gitignore,
            overwrite_gitignore=self.overwrite_gitignore,
            enable_lfs=self.enable_lfs,
            lfs_patterns=tuple(dict.fromkeys(patterns)),
            create_initial_commit=self.create_initial_commit,
            initial_commit_message=self.initial_commit_message,
            stage_mode=self.stage_mode,
            connect_github=self.connect_github,
            github_owner=self.github_owner,
            github_visibility=self.github_visibility,
            github_description=self.github_description,
            remote_name=get_addon_preferences(context).default_remote,
            push_initial_branch=self.push_initial_branch,
        )
        git, _lfs, _github, repository = build_services(context)
        return self.start_async(
            context,
            "Repository initialization",
            lambda: repository.initialize_repository(config),
            process=git.process,
        )

    def on_async_success(self, context, report: InitReport):
        for step in report.steps:
            level = "SUCCESS" if step.state == "completed" else "ERROR" if step.state == "failed" else "INFO"
            append_output(context, f"[{step.state.upper()}] {step.label}: {step.detail}", level)
        if not report.successful:
            failed = next((step for step in report.steps if step.state == "failed"), None)
            raise RuntimeError(failed.detail if failed else "Repository initialization failed.")
        context.scene.git_manager.repository_path = str(report.repository_path)
        refresh_repository_state(context)
        self.report({"INFO"}, "Repository initialized successfully.")


class GITMANAGER_OT_clone_repository(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.clone_repository"
    bl_label = "Clone Repository"

    repository: StringProperty(name="Repository URL or owner/repository")
    destination: StringProperty(name="Destination folder", subtype="DIR_PATH")
    use_github_cli: BoolProperty(name="Use GitHub CLI", default=True)
    open_blend_after_clone: BoolProperty(name="List .blend files after clone", default=True)

    def invoke(self, context, _event):
        self.destination = str(Path.home() / "BlenderProjects" / "cloned-project")
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "repository")
        layout.prop(self, "destination")
        layout.prop(self, "use_github_cli")
        layout.prop(self, "open_blend_after_clone")

    def execute(self, context):
        try:
            repository_value = validate_remote_url(self.repository)
        except ValidationError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        destination = Path(self.destination).expanduser().resolve(strict=False)
        _git, _lfs, _github, repository_service = build_services(context)
        return self.start_async(
            context,
            "Clone repository",
            lambda: repository_service.clone_repository(repository_value, destination, self.use_github_cli),
            process=repository_service.git.process,
        )

    def on_async_success(self, context, root: Path):
        context.scene.git_manager.repository_path = str(root)
        if self.open_blend_after_clone:
            blends = sorted(root.rglob("*.blend"))
            if blends:
                append_output(context, "Blend files found: " + ", ".join(str(path.relative_to(root)) for path in blends[:20]))
            else:
                append_output(context, "No .blend files were found in the cloned repository.", "WARNING")
        refresh_repository_state(context)
        self.report({"INFO"}, "Repository cloned successfully.")


class GITMANAGER_OT_connect_remote(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.connect_remote"
    bl_label = "Connect Existing Remote"

    remote_name: StringProperty(name="Remote name", default="origin")
    remote_url: StringProperty(name="Remote URL")
    push_after_connect: BoolProperty(name="Push current branch", default=True)

    def invoke(self, context, _event):
        self.remote_name = get_addon_preferences(context).default_remote
        return context.window_manager.invoke_props_dialog(self, width=560)

    def execute(self, context):
        state = context.scene.git_manager
        if not state.repository_path:
            self.report({"ERROR"}, "Open a repository first.")
            return {"CANCELLED"}
        git, _lfs, _github, _repository = build_services(context)
        repository_path = str(state.repository_path)
        remote_name = self.remote_name.strip()
        push_after_connect = bool(self.push_after_connect)
        if not remote_name:
            self.report({"ERROR"}, "Remote name is required.")
            return {"CANCELLED"}
        try:
            remote_url = validate_remote_url(self.remote_url)
        except ValidationError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        def worker():
            names = {remote.name for remote in git.remotes(repository_path)}
            if remote_name in names:
                result = git.set_remote_url(repository_path, remote_name, remote_url)
            else:
                result = git.add_remote(repository_path, remote_name, remote_url)
            if push_after_connect:
                branch = git.active_branch(repository_path)
                if not branch:
                    raise RuntimeError("Pushing requires an active branch and cannot run in detached HEAD.")
                return git.push(repository_path, remote_name, branch, set_upstream=True)
            return result

        return self.start_async(
            context,
            "Connect remote and push" if push_after_connect else "Connect remote",
            worker,
            process=git.process,
        )

    def on_async_success(self, context, result):
        append_output(context, result.stdout or result.stderr or "Remote connected.", "SUCCESS")
        refresh_repository_state(context, include_dependencies=False)

class GITMANAGER_OT_create_initial_commit(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.create_initial_commit"
    bl_label = "Create Initial Commit"

    commit_message: StringProperty(name="Commit message", default="Initial commit")
    stage_all: BoolProperty(name="Stage all project files", default=True)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def execute(self, context):
        state = context.scene.git_manager
        if not state.repository_path:
            self.report({"ERROR"}, "Open or initialize a repository first.")
            return {"CANCELLED"}
        git, _lfs, _github, _repository = build_services(context)

        def worker():
            if self.stage_all:
                git.add_all(state.repository_path)
            if not git.staged_files(state.repository_path):
                raise RuntimeError("There are no staged files for the initial commit.")
            return git.commit(state.repository_path, self.commit_message)

        return self.start_async(context, "Create initial commit", worker, process=git.process)

    def on_async_success(self, context, result):
        append_output(context, result.stdout or "Initial commit created.", "SUCCESS")
        refresh_repository_state(context, include_dependencies=False)


class GITMANAGER_OT_create_github_repository(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.create_github_repository"
    bl_label = "Create GitHub Repository"

    repository_name: StringProperty(name="Repository name")
    description: StringProperty(name="Description")
    owner: StringProperty(name="Owner or organization")
    visibility: EnumProperty(
        name="Visibility",
        items=(("private", "Private", ""), ("public", "Public", "")),
        default="private",
    )
    remote_name: StringProperty(name="Remote name", default="origin")
    push: BoolProperty(name="Push current commits", default=True)

    def invoke(self, context, _event):
        state = context.scene.git_manager
        self.repository_name = state.repository_name or Path(state.repository_path).name
        self.remote_name = get_addon_preferences(context).default_remote
        return context.window_manager.invoke_props_dialog(self, width=540)

    def execute(self, context):
        state = context.scene.git_manager
        if not state.repository_path:
            self.report({"ERROR"}, "Open a local repository first.")
            return {"CANCELLED"}
        _git, _lfs, github, _repository = build_services(context)
        if not github.auth_status().successful:
            self.report({"ERROR"}, "Authenticate with GitHub CLI first.")
            return {"CANCELLED"}
        return self.start_async(
            context,
            "Create GitHub repository",
            lambda: github.create_repository(
                state.repository_path,
                self.repository_name,
                visibility=self.visibility,
                description=self.description,
                owner=self.owner,
                remote_name=self.remote_name,
                push=self.push,
            ),
            process=github.process,
        )

    def on_async_success(self, context, result):
        append_output(context, result.stdout or "GitHub repository created.", "SUCCESS")
        refresh_repository_state(context, include_dependencies=False)

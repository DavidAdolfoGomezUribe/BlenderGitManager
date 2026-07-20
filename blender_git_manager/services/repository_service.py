"""High-level repository workflows."""

from __future__ import annotations

from pathlib import Path

from ..constants import DEFAULT_GITIGNORE
from ..models import InitConfig, InitReport, InitStep, RepositorySnapshot
from ..utils.validation import (
    ValidationError,
    is_probable_blender_temporary_directory,
    validate_branch_name,
    validate_commit_message,
    validate_email,
    validate_repository_name,
    validate_writable_directory,
)
from .git_service import GitCommandError, GitService
from .github_service import GitHubService
from .lfs_service import LFSService


class RepositoryService:
    def __init__(
        self,
        git: GitService | None = None,
        lfs: LFSService | None = None,
        github: GitHubService | None = None,
    ) -> None:
        self.git = git or GitService()
        self.lfs = lfs or LFSService(self.git.executable, self.git.process)
        self.github = github or GitHubService()

    @staticmethod
    def _step(steps: list[InitStep], key: str, label: str) -> InitStep:
        step = InitStep(key=key, label=label, state="running")
        steps.append(step)
        return step

    @staticmethod
    def _complete(step: InitStep, detail: str = "") -> None:
        step.state = "completed"
        step.detail = detail

    @staticmethod
    def _fail(step: InitStep, error: Exception) -> None:
        step.state = "failed"
        step.detail = str(error)

    def validate_initialization(self, config: InitConfig) -> Path:
        validate_repository_name(config.repository_name)
        validate_branch_name(config.initial_branch)
        if config.create_initial_commit:
            validate_commit_message(config.initial_commit_message)
        if not config.author_name.strip():
            raise ValidationError("Git author name is required before the first commit.")
        validate_email(config.author_email)
        root = validate_writable_directory(config.repository_path, create=True)
        if is_probable_blender_temporary_directory(root):
            raise ValidationError("Do not initialize a repository inside Blender or system recovery temporary folders.")
        if (root / ".git").exists():
            raise ValidationError("A .git directory already exists in the selected folder.")
        existing = self.git.detect_root(root)
        if existing:
            raise ValidationError(f"A Git repository already exists at {existing}.")
        return root

    def initialize_repository(self, config: InitConfig) -> InitReport:
        root = self.validate_initialization(config)
        steps: list[InitStep] = []
        report = InitReport(repository_path=root, steps=steps)

        try:
            step = self._step(steps, "git_init", "Initialize Git repository")
            self.git.initialize(root, config.initial_branch)
            self._complete(step, f"Initial branch: {config.initial_branch}")

            step = self._step(steps, "identity", "Configure Git author")
            self.git.config_set("user.name", config.author_name.strip(), root)
            self.git.config_set("user.email", config.author_email.strip(), root)
            if config.apply_identity_globally:
                self.git.config_set("user.name", config.author_name.strip(), global_scope=True)
                self.git.config_set("user.email", config.author_email.strip(), global_scope=True)
            self._complete(step)

            step = self._step(steps, "gitignore", "Create or update .gitignore")
            if config.create_gitignore:
                self.write_gitignore(root, overwrite=config.overwrite_gitignore)
                self._complete(step)
            else:
                step.state = "skipped"

            step = self._step(steps, "lfs", "Configure Git LFS")
            if config.enable_lfs:
                if not self.lfs.version().successful:
                    raise GitCommandError("Git LFS is enabled in the wizard but is not installed.")
                self.lfs.initialize_local(root)
                for pattern in config.lfs_patterns:
                    self.lfs.track(root, pattern)
                self._complete(step, ", ".join(config.lfs_patterns))
            else:
                step.state = "skipped"

            step = self._step(steps, "stage", "Stage initial project files")
            if config.stage_mode == "ALL":
                self.git.add_all(root)
                self._complete(step, "All project files staged")
            elif config.stage_mode == "RECOMMENDED":
                recommended = [name for name in (".gitignore", ".gitattributes") if (root / name).exists()]
                recommended.extend(path.name for path in root.glob("*.blend"))
                if recommended:
                    self.git.add(root, recommended)
                    self._complete(step, f"{len(recommended)} recommended files staged")
                else:
                    step.state = "skipped"
                    step.detail = "No recommended files were found"
            else:
                step.state = "skipped"

            step = self._step(steps, "initial_commit", "Create initial commit")
            if config.create_initial_commit:
                staged = self.git.staged_files(root)
                if not staged:
                    raise GitCommandError("There are no staged files for the initial commit.")
                self.git.commit(root, config.initial_commit_message)
                history = self.git.history(root, max_count=1)
                report.initial_commit_hash = history[0].short_hash if history else ""
                self._complete(step, report.initial_commit_hash)
            else:
                step.state = "skipped"

            step = self._step(steps, "github", "Connect GitHub repository")
            if config.connect_github:
                if not self.github.version().successful:
                    raise GitCommandError("GitHub CLI is not installed.")
                if not self.github.auth_status().successful:
                    raise GitCommandError("GitHub authentication is required before creating the remote repository.")
                self.github.create_repository(
                    root,
                    config.repository_name,
                    visibility=config.github_visibility,
                    description=config.github_description,
                    owner=config.github_owner,
                    remote_name=config.remote_name,
                    push=config.push_initial_branch,
                )
                report.remote_url = self.github.repository_url(root)
                self._complete(step, report.remote_url)
            else:
                step.state = "skipped"

            return report
        except Exception as exc:
            running = next((item for item in reversed(steps) if item.state == "running"), None)
            if running:
                self._fail(running, exc)
            return report

    def write_gitignore(self, root: str | Path, overwrite: bool = False) -> Path:
        path = Path(root) / ".gitignore"
        if path.exists() and not overwrite:
            existing = path.read_text(encoding="utf-8", errors="replace")
            missing_lines = [line for line in DEFAULT_GITIGNORE.splitlines() if line and line not in existing.splitlines()]
            if missing_lines:
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write("\n# Added by Blender Git Manager\n")
                    stream.write("\n".join(missing_lines) + "\n")
            return path
        path.write_text(DEFAULT_GITIGNORE, encoding="utf-8", newline="\n")
        return path

    def clone_repository(
        self,
        repository: str,
        destination: str | Path,
        use_github_cli: bool = False,
    ) -> Path:
        destination_path = Path(destination).expanduser().resolve(strict=False)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if use_github_cli:
            self.github.clone_repository(repository, destination_path)
        else:
            result = self.git.process.run(
                self.git.executable,
                ["clone", repository, str(destination_path)],
                timeout=1800,
            )
            if not result.successful:
                raise GitCommandError(result.stderr or result.stdout or "Clone failed.")
        root = self.git.detect_root(destination_path)
        if not root:
            raise GitCommandError("The cloned folder is not a valid Git repository.")
        if self.lfs.version().successful and (root / ".gitattributes").exists():
            self.lfs.initialize_local(root)
            self.lfs.pull(root)
        return root

    def snapshot(self, root: str | Path, history_limit: int = 50) -> RepositorySnapshot:
        repository_root = self.git.detect_root(root)
        if not repository_root:
            raise GitCommandError("No Git repository was detected.")
        commits = self.git.history(repository_root, history_limit)
        head_commit = self.git.head_commit(repository_root)
        last_commit = next(
            (commit for commit in commits if commit.full_hash == head_commit),
            None,
        )
        if head_commit and last_commit is None:
            last_commit = self.git.commit_info(repository_root, head_commit)
        remotes = self.git.remotes(repository_root)
        return RepositorySnapshot(
            root=repository_root,
            name=repository_root.name,
            active_branch=self.git.head_branch(repository_root),
            head_commit=head_commit,
            remotes=tuple(remotes),
            changes=tuple(self.git.status(repository_root)),
            commits=tuple(commits),
            branches=tuple(self.git.branches(repository_root)),
            sync=self.git.sync_status(repository_root),
            lfs_active=self.lfs.is_active(repository_root),
            last_commit=last_commit,
        )

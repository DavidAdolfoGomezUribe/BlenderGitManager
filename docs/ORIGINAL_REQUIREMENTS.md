# Prompt for developing a Git and Git LFS version-control add-on for Blender

I want to develop a professional Blender add-on that manages Git and GitHub repositories directly from Blender's graphical interface, without requiring users to type manual terminal commands.

The add-on must provide a visual experience similar to source-control tools in Visual Studio Code, Visual Studio, and extensions such as Git Graph.

Its primary goal is to let 3D artists, designers, and developers version `.blend` files, models, textures, animations, and other large assets through Git and Git LFS in an intuitive Blender-integrated interface.

## 1. General objective

Develop a Python add-on for Blender that can:

- Connect Blender to Git.
- Connect Blender to GitHub.
- Use Git LFS for large files.
- Authenticate with GitHub in a browser.
- Create commits without using a console.
- Run common Git operations from buttons and forms.
- Display branches, commits, authors, and changes.
- Display a visual Git-history graph.
- Manage repositories from Blender's interface.
- Visually initialize a new Git repository from the `.blend` file folder or another selected folder, without a terminal.
- Automatically save the `.blend` file before creating a commit.
- Avoid storing passwords or tokens directly in the add-on.

The add-on must not implement Git itself. It must use system-installed executables:

- `git`
- `git-lfs`
- `gh` (GitHub CLI)

Python communication must use `subprocess`, always pass argument lists, and use `shell=False`.

## 2. Provisional name

Add-on name:

```text
Blender Git Manager
```

Other possible names:

```text
Blend Version Control
BlendGit
Git Tools for Blender
Blender Git Graph
```

## 3. Compatibility

The add-on must initially target:

- Blender 4.2 or later.
- Windows 10 and Windows 11.
- Git installed on the system.
- Git LFS installed.
- GitHub CLI installed for browser authentication.

It must later be extensible to:

- Linux.
- macOS.

The architecture should avoid Windows-specific absolute paths where possible.

## 4. Blender UI integration

The add-on must integrate into Blender's main top bar, alongside menus such as:

```text
File
Edit
Render
Window
Help
```

It must add a new menu:

```text
Git
```

Example:

```text
File | Edit | Render | Window | Git | Help
```

The Git menu must provide quick access to:

```text
Git
├── Open Git Manager
├── Initialize Repository
├── Open Existing Repository
├── Clone Repository
├── Repository Status
├── Save and Commit
├── Pull
├── Push
├── Fetch
├── Branches
├── Git LFS
├── GitHub Authentication
└── Settings
```

In addition to the top menu, the add-on must include a main window or wide panel for repository management. It may initially be a 3D View sidebar panel, popup window, custom area, reused editor, or standalone panel accessible from Git. The priority is a wide, clear, organized interface rather than restricting all functionality to a narrow sidebar.

## 5. Git Manager main window

The main window must be divided into sections.

### Repository header

It must display:

- Repository name.
- Local path.
- Remote URL.
- Remote provider, initially GitHub.
- Active branch.
- Synchronization status.
- Latest commit.
- Latest commit author.
- GitHub connection indicator.
- Git LFS indicator.
- Modified-files indicator.

Example:

```text
Repository: TankGameAssets
Branch: main
Remote: github.com/david/TankGameAssets
Status: 3 modified files
Git LFS: Active
GitHub: Authenticated
```

It must include these buttons:

```text
Refresh
Open Repository Folder
Open on GitHub
Settings
```

When the current `.blend` file is not inside a Git repository, the window must not be empty or show only an error. It must show an onboarding screen:

```text
No Git repository detected

[Initialize Repository]
[Open Existing Repository]
[Clone from GitHub]
```

The main action must be **Initialize Repository**, because it is the required entry point for preparing files and creating commits.

## 6. GitHub browser authentication

Authentication must use GitHub CLI.

The add-on must check that `gh` is installed by running:

```bash
gh --version
```

It must check authentication status with:

```bash
gh auth status
```

When the user selects:

```text
Connect to GitHub
```

the add-on must run:

```bash
gh auth login --web
```

The process must:

1. Open the browser.
2. Let the user sign in to GitHub.
3. Authorize GitHub CLI.
4. Return to Blender.
5. Automatically verify authentication status.
6. Show the connected user name.

The add-on must not request or store passwords, personal access tokens, private keys, or plaintext credentials.

It must also include:

```text
Disconnect GitHub
```

which runs:

```bash
gh auth logout
```

A visual confirmation must be shown before logging out.

## 7. Dependency detection

On startup, the add-on must check:

```bash
git --version
git lfs version
gh --version
```

It must display a status section:

```text
Git: Installed
Git LFS: Installed
GitHub CLI: Installed
```

When a dependency is missing, it must explain:

- Which program is missing.
- Why it is required.
- How to install it.
- A button that opens the official installation page.

The add-on must not fail completely when GitHub CLI is missing. Local Git functions must remain available whenever Git and Git LFS are installed.

## 8. Initializing, opening, and cloning repositories

Repository initialization is a primary feature and must be part of the main MVP flow. Users must be able to turn their Blender-project folder into a fully functional Git repository without opening a terminal.

Before version-control actions are displayed, the add-on must detect whether the current `.blend` file already belongs to a repository with:

```bash
git rev-parse --show-toplevel
```

It may also check for a `.git` folder directly, but `git rev-parse` must be the main source for detecting the real repository root.

When no repository is detected, the main window must offer:

```text
Initialize Repository
Open Existing Repository
Clone Repository
```

### 8.1 Initialize a local repository

There must be a primary button:

```text
Initialize Repository
```

It must open a visual wizard rather than immediately running `git init` without options.

The wizard must include at least:

```text
Repository folder:
[Folder selector]

Repository name:
[Project name]

Initial branch:
[main]

Git author name:
[Current Git user or editable value]

Git author email:
[Current Git email or editable value]

Save current .blend inside repository:
[Enabled / Disabled]

Create Blender .gitignore:
[Enabled / Disabled]

Enable Git LFS:
[Enabled / Disabled]

Track .blend files with Git LFS:
[Enabled / Disabled]

Create initial commit:
[Enabled / Disabled]

Initial commit message:
[Initial commit]

Connect to GitHub after initialization:
[Enabled / Disabled]
```

#### Folder selection

By default, if the current file is already saved, the proposed repository root must be:

```python
Path(bpy.data.filepath).parent
```

If the `.blend` file has not been saved yet, the add-on must ask for a folder and offer to save the file there before continuing. Users must also be able to choose another folder through Blender's file selector.

The add-on must validate:

- The path exists or can be created.
- The user has write permission.
- Initialization is not accidentally occurring inside another repository.
- A `.git` folder does not already exist without the user's knowledge.
- The selected folder is not a Blender temporary-recovery path.
- The branch name is valid.
- Author name and email are configured before the first commit.

If a repository already exists, it must show:

```text
A Git repository already exists in this folder.

[Open Repository]
[Refresh Status]
[Cancel]
```

It must not silently initialize again.

#### Initialization command

The preferred command is:

```bash
git init -b main
```

where `main` is the branch name selected by the user. For older Git versions that do not support `-b`, a fallback is required:

```bash
git init
git branch -M main
```

The result must be verified before continuing.

#### Git identity configuration

The wizard must first read:

```bash
git config user.name
git config user.email
git config --global user.name
git config --global user.email
```

If there is no valid local identity, it must allow visual configuration. For the current repository:

```bash
git config user.name "Name"
git config user.email "email@example.com"
```

Global configuration may only be modified after the user explicitly selects:

```text
Apply identity globally
```

#### `.gitignore` creation

The wizard must generate a recommended Blender `.gitignore`.

Suggested base content:

```gitignore
# Blender automatic backups
*.blend1
*.blend2
*.blend3
*.blend@

# Blender temporary files
*.blend.tmp
*.tmp
*.temp

# Python cache
__pycache__/
*.pyc

# Operating system
.DS_Store
Thumbs.db

# Secrets and credentials
.env
*.pem
*.key
credentials.json
```

Users must be able to preview the content, enable or disable rules, add custom patterns, choose whether `.blend1`, `.blend2`, and `.blend3` are ignored or managed through Git LFS, and avoid overwriting an existing `.gitignore` without confirmation.

#### Initial Git LFS setup

When Git LFS is enabled, local initialization must run:

```bash
git lfs install --local
```

It must then apply selected patterns, for example:

```bash
git lfs track "*.blend"
git lfs track "*.fbx"
git lfs track "*.glb"
git lfs track "*.psd"
```

It must verify that `.gitattributes` was created or updated. The wizard must clearly show the files that will be managed by Git LFS before staging the first commit.

#### Saving the Blender file

When enabled, the add-on must save the file before the first commit:

```python
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
```

When the file is not yet inside the repository folder, it must offer:

```text
Save a copy inside repository
Move project file into repository
Cancel
```

No file may be moved or overwritten without explicit confirmation.

#### Initial staging and first commit

After initialization, the wizard must show detected files and let users choose what goes into the first commit.

```text
Stage Selected Files
Stage Recommended Project Files
Stage All
Skip Initial Commit
```

Possible commands:

```bash
git add file
git add .gitignore
git add .gitattributes
git add .
```

Before the first commit, show a summary:

```text
Repository folder: C:/Projects/TankAssets
Initial branch: main
Git LFS: Enabled
Tracked patterns: *.blend, *.fbx, *.glb
Files to commit: 8
Commit message: Initial commit
```

The first commit must run visibly through:

```bash
git commit -m "Initial commit"
```

The message must be editable and an empty commit must not be created accidentally. If no files are staged, warn the user and offer:

```text
Select Files
Create Repository Without Commit
Cancel
```

#### Connecting the local repository to GitHub

Local initialization must work even when the user is not authenticated with GitHub. After creation, users must be able to choose:

```text
Keep Local Only
Connect Existing GitHub Repository
Create New GitHub Repository
```

To connect an existing remote repository:

```bash
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

To create a new repository through GitHub CLI and browser authentication:

```bash
gh repo create REPOSITORY_NAME --source=. --remote=origin --push
```

The creation form must allow:

```text
Repository name
Description
Visibility: Public / Private
Organization or personal account
Remote name: origin
Push initial branch after creation
```

Before `gh repo create`, check:

```bash
gh auth status
```

If the user is not authenticated, show:

```text
Connect to GitHub in Browser
```

which runs:

```bash
gh auth login --web
```

The local repository must remain functional even when authentication or remote creation fails.

#### Complete initialization flow

The wizard must follow this order:

```text
1. Select repository folder
2. Validate folder
3. Configure repository name and initial branch
4. Configure Git author
5. Run git init
6. Create or update .gitignore
7. Initialize Git LFS locally
8. Configure selected LFS patterns
9. Save the current .blend file
10. Detect project files
11. Select and stage files
12. Create the initial commit
13. Optionally connect or create a GitHub repository
14. Optionally push the initial branch
15. Refresh repository status and open Git Manager
```

Each step must show one of these states:

```text
Pending
Running
Completed
Failed
Skipped
```

If a step fails, the wizard must stop dependent actions, preserve the safely created local repository, and offer:

```text
Retry Step
Open Git Output
Continue Without GitHub
Cancel
```

#### Completion result

At the end of initialization, display:

```text
Repository initialized successfully

Repository: TankAssets
Path: C:/Projects/TankAssets
Branch: main
Initial commit: 4d12ab3
Git LFS: Active
Remote: origin
GitHub: Connected

[Open Git Manager]
[Open Repository Folder]
[Open on GitHub]
```

### 8.2 Open an existing repository

Provide:

```text
Open Existing Repository
```

The user may select any folder inside a repository. The add-on must locate the root through:

```bash
git rev-parse --show-toplevel
```

It must validate the repository and display its root path, current branch, remotes, status, latest commit, Git LFS configuration, and whether the current `.blend` file belongs to it. Opening a repository must not silently change the `.blend` file; the association between the selected repository and the Blender session must be visible and editable.

### 8.3 Clone a repository

Provide this form:

```text
Repository URL or owner/repository:
Destination Folder:
Open project after clone:
[Enabled / Disabled]

[Clone]
```

It must support HTTPS URLs, SSH URLs, `owner/repository` when GitHub CLI is available, public repositories, and private repositories with valid authentication.

Commands:

```bash
git clone URL DESTINATION
```

or:

```bash
gh repo clone owner/repository DESTINATION
```

After cloning, it must run or verify:

```bash
git lfs install --local
git lfs pull
```

only when the repository uses Git LFS. Cloning and LFS download must run as controlled tasks so they do not block Blender. After completion, display the found `.blend` files and let the user choose which one to open.

### 8.4 Minimum required operators

The implementation must include at least operators equivalent to:

```text
git_manager.initialize_repository
git_manager.open_repository
git_manager.clone_repository
git_manager.create_initial_commit
git_manager.connect_remote
git_manager.create_github_repository
```

Business logic must not live entirely inside operators. It must delegate to reusable services such as:

```text
RepositoryService
GitService
LFSService
GitHubService
```

## 9. Git LFS

Git LFS must be a core add-on feature.

The add-on must check whether Git LFS is active:

```bash
git lfs version
git lfs env
```

It must initialize it with:

```bash
git lfs install
```

It must provide a UI for choosing extensions managed through LFS. Recommended initial patterns are:

```text
*.blend
*.blend1
*.blend2
*.fbx
*.obj
*.gltf
*.glb
*.abc
*.usd
*.usdc
*.usdz
*.exr
*.hdr
*.psd
*.tif
*.tiff
*.png
*.jpg
*.jpeg
*.wav
*.mp3
*.mp4
*.mov
```

Not all patterns must be enabled. Users must choose which ones to track and may add custom patterns such as:

```text
*.sbsar
*.kra
*.customformat
```

The UI must run:

```bash
git lfs track "*.blend"
git lfs untrack "*.blend"
```

It must show `.gitattributes`, remind users to commit it, and display LFS-managed files with:

```bash
git lfs ls-files
```

For each file show its name, size, LFS pattern, status, and whether it is pending upload.

## 10. Repository status

Provide a Source Control-like section that runs:

```bash
git status --short
```

It must classify files as:

```text
Staged Changes
Changes
Untracked Files
Conflicts
Ignored Files
```

Each file must show name, relative path, status, size, whether it uses Git LFS, and change type. Visual states include:

```text
M = Modified
A = Added
D = Deleted
R = Renamed
?? = Untracked
UU = Conflict
```

Files must be individually selectable.

## 11. Visual Git add

Users must not need to type:

```bash
git add .
```

Provide visual controls:

```text
Stage Selected
Stage File
Stage All
Unstage Selected
Unstage File
Unstage All
Discard Changes
```

Corresponding commands:

```bash
git add file
git add .
git restore --staged file
git reset
git restore file
```

Discarding changes must have a clear confirmation because it is destructive. Include:

```text
Include current .blend file
```

and indicate when the current `.blend` has unsaved changes.

## 12. Intuitive commit creation

Commits must be created through a visual UI:

```text
Commit message:
[Text field]

Extended description:
[Optional text area]

Author:
Name <email>

Staged files:
File list

[Save Blender File Before Commit]
[Commit]
[Commit and Push]
```

Users must never need to manually type:

```bash
git commit -m "message"
```

Internally, the add-on must run:

```bash
git commit -m "message"
```

For extended descriptions it may use:

```bash
git commit -m "Title" -m "Description"
```

Validation must prevent a missing message, warn when there are no staged files or unsaved `.blend` changes, present Git errors clearly, detect when there is nothing to commit, and confirm successful completion.

Before committing it may run:

```python
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
```

There must be a preference to enable or disable automatic saving.

## 13. Push, pull, and fetch

Provide primary buttons:

```text
Fetch
Pull
Push
Sync
```

Commands:

```bash
git fetch
git pull
git push
```

`Sync` must run this safe sequence:

```text
Fetch
Pull
Push
```

Display local branch, remote branch, commits ahead, commits behind, and synchronization state. Example:

```text
main
2 commits ahead
1 commit behind
```

The main interface must avoid `push --force`. An advanced force-push option may only be available in advanced settings with warnings and mandatory confirmation.

## 14. Branch management

Provide a Branches section that runs:

```bash
git branch
git branch --all
git branch --show-current
```

Display current branch, local branches, remote branches, latest commit per branch, author, date, and relationship to the current branch.

Visual actions:

```text
Create Branch
Switch Branch
Rename Branch
Delete Branch
Merge Branch
Publish Branch
Set Upstream
```

Commands:

```bash
git switch name
git switch -c name
git branch -m new_name
git branch -d name
git merge name
git push -u origin name
```

Before switching, check for unsaved changes. When changes exist, offer:

```text
Commit Changes
Stash Changes
Discard Changes
Cancel
```

## 15. History visualization

Provide a Git Graph-inspired visual section. It may use:

```bash
git log --graph --decorate --oneline --all
```

For structured data, prefer a custom format such as:

```bash
git log --all --date=iso --pretty=format:"%H%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%D%x1f%s%x1e"
```

Every commit must show its short and complete hash, message, author name and email, date, branch, tags, parent commits, whether it is a merge commit, and local/remote-branch indicators.

The UI must visually represent commit and branch connections. Conceptual example:

```text
● 4d12ab3 main origin/main Fix tank track animation
│
● a3f7c82 Add Git LFS configuration
│
├─● e1bd422 feature/materials Add metal materials
│/
● 82ac911 Initial commit
```

The visualization must include colored lines per branch, a node for every commit, merge indicators, vertical scrolling, branch filter, message/author/hash search, a refresh button, and commit selection. Selecting a commit must open a details panel.

## 16. Commit details

Selecting a commit must show hash, message, description, author, email, date, parents, associated branches, tags, changed files, change type, and line statistics for text files.

Possible commands:

```bash
git show --stat HASH
git show --name-status HASH
```

For binary files such as `.blend`, show:

```text
Binary file changed
```

Do not attempt to show internal geometry differences inside a `.blend` file.

Actions:

```text
Copy Commit Hash
Checkout Commit
Create Branch from Commit
Create Tag
Revert Commit
Open Commit on GitHub
```

Destructive or state-changing actions must require confirmation.

## 17. Git author and configuration

Show the current Git identity:

```bash
git config user.name
git config user.email
```

Allow configuration of:

```text
User name
User email
```

Options:

```text
Apply to Current Repository
Apply Globally
```

Commands:

```bash
git config user.name "Name"
git config user.email "email@example.com"

git config --global user.name "Name"
git config --global user.email "email@example.com"
```

Clearly indicate whether the configuration is local or global.

## 18. Remote repositories

Show:

```bash
git remote -v
```

The UI must allow:

```text
Add Remote
Edit Remote
Remove Remote
Set Default Remote
Open Remote in Browser
```

Commands:

```bash
git remote add origin URL
git remote set-url origin URL
git remote remove origin
```

Detect GitHub remotes. When the remote is GitHub, allow opening the repository, issues, pull requests, actions, commit, and branch in the browser.

## 19. GitHub repository creation

When authenticated through GitHub CLI, the add-on must create remote repositories.

Form:

```text
Repository Name
Description
Visibility: Public / Private
Initialize with README
Add .gitignore
Add license
Create and Push
```

Use GitHub CLI, for example:

```bash
gh repo create
```

It must connect the local repository and push the first commit. Credentials must not be embedded in the remote URL.

## 20. Stash

Provide a Git Stash section with:

```text
Create Stash
Create Stash with Message
Include Untracked Files
List Stashes
Apply Stash
Pop Stash
Drop Stash
Clear Stashes
```

Commands:

```bash
git stash push -m "message"
git stash push -u -m "message"
git stash list
git stash apply
git stash pop
git stash drop
```

`drop` and `clear` must require confirmation.

## 21. Tags

Allow:

```text
Create Tag
Create Annotated Tag
Delete Tag
Push Tag
Push All Tags
```

Display each tag's name, commit, message, date, and author.

Commands:

```bash
git tag
git tag name
git tag -a name -m "message"
git push origin name
git push origin --tags
```

## 22. Conflicts

Detect conflicted files and show a dedicated section:

```text
Merge Conflicts
```

For text files, it may provide:

```text
Use Ours
Use Theirs
Mark as Resolved
Open Externally
```

For `.blend` files, warn:

```text
.blend files are binary and cannot be merged automatically.
Choose one version or recover content manually.
```

Options:

```text
Keep Local Version
Keep Remote Version
Create Backup of Both
Cancel Merge
```

Before overwriting a `.blend`, create a backup.

## 23. `.blend` files and safety

Detect the open file through:

```python
bpy.data.filepath
```

If it has not been saved, show:

```text
Save the Blender file before using version control.
```

Before important operations, provide timestamped backups:

```text
project_backup_YYYYMMDD_HHMMSS.blend
```

These operations must offer a backup:

- Branch switch.
- Commit checkout.
- Pull with changes.
- Conflict resolution.
- Revert.
- Reset.
- File restoration.

## 24. Operations that must not block Blender

Long-running operations must run in controlled processes or tasks:

- Clone.
- Pull.
- Push.
- Fetch.
- Git LFS upload.
- Git LFS download.
- Checkout of large files.

The UI must show:

```text
Running...
Progress
Cancel
Output
```

The Blender API must not be modified directly from worker threads. Results must reach the main thread through safe mechanisms such as:

```python
bpy.app.timers
```

## 25. Internal console and logging

Provide a panel named:

```text
Git Output
```

It must show executed operations and their results. Example:

```text
[10:31:02] git status --short
[10:31:03] Completed successfully

[10:32:15] git push origin main
[10:32:21] Push completed
```

Credentials, tokens, and sensitive information must not be displayed. Normal mode may show friendly messages such as:

```text
Creating commit...
Uploading large files with Git LFS...
Push completed successfully.
```

Developer mode may show complete arguments while still hiding sensitive information.

## 26. Error handling

Errors must not be shown only in the Python console; they must be converted into understandable messages. Examples:

```text
Git is not installed.
Git LFS is not installed.
GitHub authentication is required.
No remote repository has been configured.
There are no staged files.
The branch has no upstream.
Push was rejected because the remote contains newer commits.
A merge conflict was detected.
The current Blender file has not been saved.
```

Whenever possible, every error must explain what happened, why it happened, how to resolve it, and provide a direct action button.

## 27. Security

Mandatory requirements:

- Use `subprocess.run()` or `subprocess.Popen()`.
- Pass commands as lists.
- Use `shell=False`.
- Validate branch names, tags, and paths.
- Do not concatenate commands.
- Do not execute arbitrary user-entered text.
- Do not store tokens in add-on files.
- Do not store credentials in `.blend` files.
- Do not display tokens in logs.
- Do not automatically upload secret files.
- Warn about files such as `.env`, private keys, and credentials.
- Include a recommended `.gitignore`.

Example `.gitignore`:

```gitignore
# Blender backups
*.blend1
*.blend2
*.blend3

# Temporary files
*.tmp
*.temp
__pycache__/
*.pyc

# Operating system
.DS_Store
Thumbs.db

# Secrets
.env
*.pem
*.key
credentials.json
```

Allow users to decide whether backup files `.blend1` and `.blend2` are tracked through Git LFS or ignored.

## 28. Code architecture

Use a modular architecture:

```text
blender_git_manager/
├── __init__.py
├── blender_manifest.toml
├── preferences.py
├── properties.py
├── constants.py
│
├── operators/
│   ├── authentication.py
│   ├── repository.py
│   ├── staging.py
│   ├── commits.py
│   ├── branches.py
│   ├── remotes.py
│   ├── synchronization.py
│   ├── history.py
│   ├── lfs.py
│   ├── stash.py
│   ├── tags.py
│   └── conflicts.py
│
├── services/
│   ├── process_service.py
│   ├── git_service.py
│   ├── github_service.py
│   ├── lfs_service.py
│   ├── repository_service.py
│   ├── history_parser.py
│   ├── credential_service.py
│   └── background_task_service.py
│
├── ui/
│   ├── top_menu.py
│   ├── main_panel.py
│   ├── repository_panel.py
│   ├── changes_panel.py
│   ├── commit_panel.py
│   ├── graph_panel.py
│   ├── branches_panel.py
│   ├── lfs_panel.py
│   ├── output_panel.py
│   └── dialogs.py
│
├── models/
│   ├── repository.py
│   ├── commit.py
│   ├── branch.py
│   ├── file_change.py
│   └── task.py
│
└── utils/
    ├── paths.py
    ├── validation.py
    ├── formatting.py
    └── backups.py
```

## 29. Central command service

Create a safe central service. Conceptual example:

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass
class CommandResult:
    return_code: int
    stdout: str
    stderr: str

    @property
    def successful(self) -> bool:
        return self.return_code == 0


class ProcessService:

    @staticmethod
    def run(
        executable: str,
        arguments: list[str],
        working_directory: Path | None = None,
        timeout: int | None = None,
    ) -> CommandResult:

        result = subprocess.run(
            [executable, *arguments],
            cwd=str(working_directory) if working_directory else None,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=timeout,
        )

        return CommandResult(
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )
```

All Git, Git LFS, and GitHub CLI commands must go through this service.

## 30. Add-on preferences

Create a preferences section containing:

```text
Git executable path
Git LFS executable path
GitHub CLI executable path

Save .blend before commit
Create backup before checkout
Refresh repository automatically
Refresh interval
Default remote
Default branch name
Enable advanced Git operations
Show developer output
```

Paths must be auto-detected through mechanisms such as:

```python
shutil.which("git")
shutil.which("gh")
```

## 31. Visual design

The UI must resemble a modern Git client. Suggested layout:

```text
┌──────────────────────────────────────────────────────────────────┐
│ Repository: TankAssets        Branch: main        Sync: Up to date │
├─────────────────┬────────────────────────────────────────────────┤
│ Changes         │ Commit Graph                                   │
│                 │                                                │
│ Staged          │ ● main Fix track animation                     │
│  tank.blend     │ │                                              │
│                 │ ● Configure Git LFS                            │
│ Modified        │ │                                              │
│  texture.png    │ ├─● feature/materials Add materials            │
│                 │ │/                                             │
│ Untracked       │ ● Initial commit                               │
│  notes.txt      │                                                │
├─────────────────┴────────────────────────────────────────────────┤
│ Commit message                                                   │
│ [Fix tank track animation                                     ] │
│                                                                  │
│ [Commit] [Commit and Push] [Pull] [Push]                         │
└──────────────────────────────────────────────────────────────────┘
```

Design priorities:

- Intuitive interface.
- Visible actions.
- Clearly differentiated states.
- Confirmations for dangerous actions.
- Technical information available without overwhelming the user.
- Use Blender-native icons where possible.
- Descriptive tooltips.
- Light and dark theme compatibility.

## 32. Known limitations

Clearly communicate that:

- Git LFS stores large files but cannot internally merge two `.blend` files.
- Git cannot show visual geometry, material, or animation differences inside a `.blend`.
- Two users modifying the same `.blend` file can create conflicts.
- Large projects should be split into linked files.
- Git LFS can have quotas depending on the remote provider.
- Authentication depends on GitHub CLI, Git Credential Manager, or system-configured SSH.

## 33. Phased development

### Phase 1: MVP

Implement:

- Git, Git LFS, and GitHub CLI detection.
- Browser-based GitHub authentication.
- Current repository detection.
- Complete visual wizard to initialize a local repository, choose its root folder, create its initial branch, configure Git identity, generate `.gitignore`, enable Git LFS, stage files, and create the first commit.
- Repository cloning.
- Active branch display.
- `git status` display.
- Individual stage, stage all, and unstage.
- Visual commit message field.
- Commit and Commit + Push.
- Pull, Push, and Fetch.
- Basic Git LFS configuration.
- Git top-bar menu.
- Output panel.

### Phase 2

Implement:

- Branch list.
- Create and switch branches.
- Remotes.
- Stash.
- Tags.
- Commit history.
- Commit details.
- Ahead/behind indicators.
- GitHub repository creation.

### Phase 3

Implement:

- Visual commit graph.
- Branch lines.
- Merge.
- Revert.
- Guided conflict resolution.
- Background operations.
- Progress bar.
- Search and filters.

### Phase 4

Implement:

- Full Linux and macOS compatibility.
- GitLab and Bitbucket support.
- Large-file locking.
- Blender-scene metadata comparison.
- Team integration.
- Pull requests.
- Issues.
- Releases.

## 34. MVP acceptance criteria

The MVP is functional when a user can:

1. Open Blender.
2. Access the Git top menu.
3. Initialize a local repository from a selected folder or the `.blend` file folder.
4. Choose the initial branch, configure Git identity, and generate `.gitignore`.
5. Enable Git LFS for `.blend` files during initialization.
6. Select files and create the first commit from the wizard.
7. Authenticate with GitHub in a browser when choosing to connect the remote repository.
8. View modified files.
9. Select files.
10. Stage them for commit.
11. Write a message in a visual field.
12. Create the commit with a button.
13. View the active branch.
14. Run Pull and Push through buttons.
15. Review the basic commit history.
16. See author, date, hash, and message for every commit.
17. Receive clear messages when an operation fails.
18. Complete the full workflow without opening a terminal.

## 35. Expected result

Generate the complete add-on project with:

- Modular code.
- Typing where practical.
- Error handling.
- Correct Blender class registration and unregistration.
- A Git menu in the top bar.
- A working main panel.
- A working visual wizard for repository initialization and first-commit creation.
- Operators to initialize, open, and clone repositories.
- Safe command-execution services.
- Git LFS integration.
- GitHub CLI integration.
- Browser authentication.
- Visual staging and commit UI.
- Commit history.
- Initial branch management.
- `blender_manifest.toml`.
- `README.md`.
- `LICENSE`.
- `.gitignore`.
- Installation instructions.
- Development and debugging instructions.
- Unit tests for functions that do not depend directly on Blender's UI.

Do not generate isolated examples only. Build a real, extensible, organized project foundation.

Begin by developing the MVP. Explain each created file, present the project structure, and provide the complete contents of every file required to run the first version in Blender.

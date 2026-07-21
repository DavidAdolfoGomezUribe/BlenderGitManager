# Blender Git Manager


![BGM](/icon.png)

**Blender Git Manager** is a Blender 4.2+ extension that brings a visual Git, Git LFS, and GitHub CLI workflow directly into Blender. It is designed for 3D artists and teams working with large binary files who want to create versions without manually typing terminal commands.

This release provides an executable foundation for the **MVP** described in the requirements document. The architecture is ready to be extended later with stash support, merges, advanced conflict resolution, GitLab, and Bitbucket.

## MVP features

- A **Git** menu in Blender's top bar.
- A **Git** panel in the 3D View sidebar.
- A large popup window containing the main manager.
- Detection of `git`, `git lfs`, and `gh`.
- GitHub authentication through `gh auth login --web`, with a visible, copyable temporary code.
- Automatic detection of the repository containing the `.blend` file.
- Visible association of another repository with the current session.
- A visual repository-initialization wizard.
- Folder, repository name, initial branch, and Git identity selection.
- Safe creation or extension of `.gitignore`.
- Local Git LFS initialization and common-pattern selection.
- Saving the `.blend` file inside the repository before initialization.
- Stage-all or recommended staging, followed by initial-commit creation.
- Optional GitHub repository creation through `gh repo create`.
- Opening existing repositories.
- Cloning through Git or GitHub CLI.
- Post-clone download of LFS objects when the repository uses `.gitattributes`.
- A visual list of modified, new, staged, and conflicted files.
- Stage and unstage by file, selection, or globally.
- Confirmed discard-changes action.
- Visual commit title and description fields.
- Automatic Blender save before committing.
- Commit and Commit + Push actions.
- Quick Save from the top menu: stages all changes, creates `Quick Save N`, and pushes the active branch.
- Fetch, `--ff-only` Pull, Push, and Sync.
- Limited LFS-push recovery for unavailable locks and transient HTTP 5xx errors.
- Upstream, ahead, and behind detection.
- A structured Git Graph with an initial 200 commits, incremental loading up to 1,000, colored lanes, aligned nodes, forks, and merges.
- Visual identification of HEAD, local and remote branches, and tags, with search and filters.
- Selected-commit details, changed files, statistics, and History actions.
- A **Load Selected Commit** button that materializes the complete tree and reloads the scene in `Detached HEAD`.
- Background loading for History and commit details without accessing the Blender API from worker threads.
- Local and remote branch lists.
- Branch creation and switching with a prior backup and automatic reload of the destination branch's `.blend` file.
- Initial Git LFS pattern management.
- A user-friendly, secret-safe output panel.
- Modal network operations to avoid freezing the interface.
- Local unit and integration tests for modules that do not depend on `bpy`.

## Requirements

- Blender 4.2 or later.
- Windows 10 or Windows 11 for the initial target platform.
- Git installed and available in `PATH`.
- Git LFS installed.
- GitHub CLI for authentication and GitHub-specific operations.

The extension continues to provide local Git functionality when GitHub CLI is not installed. Git LFS is only required when the user enables it.

## Quick installation

1. Download `blender_git_manager-0.1.8.zip`.
2. In Blender, open **Edit > Preferences > Add-ons** or **Extensions**.
3. Select **Install from Disk**.
4. Choose the ZIP without extracting it.
5. Enable **Blender Git Manager**.
6. Open **Git > Open Git Manager** from the top menu.
7. Press **Refresh** to check dependencies.

## Recommended first workflow

1. Save or open your Blender project.
2. Open **Git > Initialize Repository**.
3. Confirm the folder and the `main` branch.
4. Configure your Git name and email address.
5. Keep **Create Blender .gitignore** enabled.
6. Enable Git LFS and select at least `*.blend`.
7. Select **Stage All** or **Stage Recommended**.
8. Create the initial commit.
9. To publish on GitHub, authenticate with **Connect in Browser**.
10. Create the remote through the wizard or **Create on GitHub**.

## Project structure

```text
blender_git_manager/
├── __init__.py                  Main registration and refresh timer
├── blender_manifest.toml        Blender 4.2+ extension manifest
├── constants.py                 Default values and patterns
├── preferences.py               Preferences and executable paths
├── properties.py                RNA state visible to the UI
├── state_sync.py                Service-to-Blender-property synchronization
├── models/
│   ├── __init__.py
│   ├── domain.py                General Blender-independent models
│   └── history.py               Typed Git Graph and detail models
├── operators/
│   ├── __init__.py              Ordered operator registration
│   ├── base.py                  Modal infrastructure for long-running tasks
│   ├── authentication.py        GitHub CLI login and logout
│   ├── repository.py            Initialize, open, clone, remotes, and GitHub repositories
│   ├── staging.py               Stage, unstage, and discard
│   ├── commits.py               Commit, Commit + Push, and Quick Save
│   ├── synchronization.py       Fetch, pull, push, and sync
│   ├── branches.py              Create and switch branches
│   ├── history.py               Commit checkout and safe scene reload
│   ├── history_actions.py       Selected-commit actions
│   ├── history_runtime.py       Asynchronous History-to-main-thread coordinator
│   ├── lfs.py                   LFS pattern track and untrack
│   └── common.py                Refresh, folders, browser, and preferences
├── services/
│   ├── process_service.py       Single external-process execution point
│   ├── git_service.py           Git command facade
│   ├── lfs_service.py           Git LFS facade
│   ├── github_service.py        GitHub CLI facade
│   ├── repository_service.py    Composite business workflows
│   ├── lfs_push_failures.py     Safe LFS failure classification and recovery
│   ├── history_parser.py        Structured Git-history parser
│   ├── history_diff_parser.py   NUL-safe changed-file and statistics parser
│   ├── history_service.py       History queries, filters, and details
│   ├── graph_layout_service.py  Independent lane-layout algorithm
│   ├── status_parser.py         Git status porcelain parser
│   ├── background_task_service.py Reusable task queue
│   └── credential_service.py    Explicit no-secret-storage policy
├── ui/
│   ├── __init__.py
│   ├── top_menu.py              Top Git menu
│   ├── main_panel.py            Sidebar panel
│   ├── dashboard.py             Main manager layout
│   ├── graph_icons.py           RGBA Git Graph connections and nodes
│   └── lists.py                 UILists for changes, commits, branches, and output
└── utils/
    ├── __init__.py
    ├── backups.py               Timestamped Blender-file backup
    ├── checkout.py              Safe Git-tree checkout planning and rollback
    ├── formatting.py            Sizes and argument redaction
    ├── paths.py                 Path normalization and relationships
    └── validation.py            Ref, name, and folder validation
```

## Security

All processes go through `ProcessService` and use:

```python
subprocess.Popen(
    [executable, *arguments],
    shell=False,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
```

Output is consumed incrementally through separate readers to prevent deadlocks, sent to the Blender console, and added to **Git Output** from the main thread. Commands are not concatenated, arbitrary text is not executed, and there is no API for storing tokens. Credentials remain the responsibility of GitHub CLI, Git Credential Manager, or the system SSH agent.

Logging redacts arguments and output related to `token`, `password`, `secret`, `credential`, authorization headers, credentials embedded in URLs, and temporary OAuth codes. The recommended `.gitignore` excludes `.env`, private keys, and `credentials.json`.

## Main commands used

```text
git rev-parse --show-toplevel
git init -b main
git config user.name ...
git config user.email ...
git status --porcelain=v1 --untracked-files=all
git add -- <files>
git add --all
git restore --staged -- <files>
git commit -m <title> -m <description>
git commit -m "Quick Save N"
git fetch origin --prune
git pull --ff-only
git push origin
git push [-u] <remote> <branch>:refs/heads/<remote-branch>
git -c lfs.<url>.locksverify=false push ...
git log --all --pretty=format:<structured-format>
git for-each-ref ...
git lfs install --local
git lfs track <pattern>
git lfs ls-files --long --size
gh auth login --hostname github.com --git-protocol https --web --clipboard
gh auth status --hostname github.com
gh repo create ... --source . --remote origin --push
gh repo clone owner/repository destination
```

## Development and testing

Tests do not require Blender because services and models do not import `bpy`.

```bash
cd blender_git_manager_project
python -m unittest discover -s tests -v
```

To check syntax:

```bash
python -m compileall blender_git_manager
```

To build the ZIP manually from the add-on folder:

```bash
cd blender_git_manager
python ../build_extension.py
```

You can also use Blender's official extension-build command from the folder containing `blender_manifest.toml`.

## Debugging inside Blender

- Enable **Show developer output** in the extension preferences.
- On Windows, open **Window > Toggle System Console** to see commands, stdout, stderr, duration, and exit codes in real time.
- Use the Git panel's **Output** tab to review the same operations, even before opening or initializing a repository.
- To reload during development, disable and re-enable the extension.
- Do not modify Blender data from worker threads. Modal operators apply results from the main thread.

## First-version limitations

- Git Graph uses native Blender components; lanes are distinguished by colored nodes and orthogonal connections adapted to the available width.
- Stash, merge creation, and reset are not yet implemented in the UI.
- `.blend` conflicts are detected, but guided resolution and backup of both variants belong to the next phase.
- Pull uses `--ff-only` to prevent unexpected automatic merges.
- Pressing Escape requests termination of the external process and keeps the task busy until termination is confirmed.
- The wizard provides Stage All, Recommended, and None modes; individual selection is available later in Changes.
- Opening a repository does not silently open another `.blend` file.
- Git and Git LFS cannot merge geometry, materials, or animation inside a binary `.blend` file.

## Next phases

See `docs/ROADMAP.md` for the plans for stash, controlled merges, binary conflicts, file locking, additional providers, and team collaboration.

## License

GPL-3.0-or-later.

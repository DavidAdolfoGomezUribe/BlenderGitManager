# Technical architecture

## Principles

1. **The UI does not execute commands directly.** Operators call services.
2. **Every external process goes through `ProcessService`.** `shell=True` is forbidden.
3. **Domain models do not depend on Blender.** This enables unit tests.
4. **Threads do not modify `bpy`.** `ProcessService` queues incremental output and modal operators apply it on the main thread.
5. **The local repository is independent of GitHub.** A remote failure never invalidates an already-created local repository.
6. **Credentials are not stored.** Authentication is delegated to `gh` and system credential managers.

## Layers

### UI

`ui/dashboard.py` centralizes the layout so it can be reused by both the sidebar panel and the popup window. `UIList` classes do not query Git; they only draw RNA collections.

### Operators

Operators validate Blender context, save the file when appropriate, and delegate the operation. Network tasks use `AsyncModalMixin`.

### State synchronization

`state_sync.py` converts a `RepositorySnapshot` into Blender properties. It is also the only place that populates the changes, commits, and branches collections.

### Services

- `GitService`: atomic commands and parsing.
- `LFSService`: `git lfs` commands.
- `GitHubService`: `gh` commands.
- `RepositoryService`: composite workflows such as initialization and cloning.
- `ProcessService`: safe `Popen`, sanitized incremental output, timeout, and cancellation.

### Models

Dataclasses describe command results, changed files, commits, branches, remotes, synchronization state, and wizard progress.

## Initialization flow

```text
Blender Operator
  ├─ saves .blend on the main thread
  ├─ builds InitConfig
  └─ starts modal task
       └─ RepositoryService.initialize_repository
            ├─ validates folder and identity
            ├─ git init
            ├─ git config
            ├─ .gitignore
            ├─ git lfs install --local
            ├─ git lfs track
            ├─ stage
            ├─ initial commit
            └─ optional gh repo create
```

Each stage produces an `InitStep` with the status `running`, `completed`, `failed`, or `skipped`. The UI records the result of every step.

## Git Graph evolution

The next phase must separate:

1. Structured querying with `git log`.
2. Lane assignment through an active-column algorithm keyed by parent hashes.
3. A visual model of `GraphLane`, `GraphNode`, and `GraphEdge`.
4. Rendering with `gpu`/`blf` in a dedicated editor or region.
5. Commit selection connected to the details panel.

The text output of `git log --graph` must not be parsed; the graph must be built from hashes and parents.

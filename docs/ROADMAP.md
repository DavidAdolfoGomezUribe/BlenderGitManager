# Roadmap

## Delivered in 0.1.8

- Fixed the `UILayout.prop_search` exception that stopped History from drawing.
- Rendered Git Graph lanes and connections with per-lane RGBA colors.
- Centered nodes on the same row as the hash, message, author, date, and references.
- Made the History view compact so the graph remains visible in short windows.
- Added collapsible commit details and a full-width graph with vertical scrolling.
- Added real Blender visual tests for merges and `Detached HEAD`.

## Delivered in 0.1.7

- Visual Git Graph with lanes, forks, merges, and references.
- Search by author, hash, and message; branch filter and incremental loading.
- History with changed files and per-commit statistics.
- Lightweight and annotated tags from commits.
- Branch creation from commits.
- Revert and checkout of commits with confirmation and safe scene reload.

## Phase 2

- Complete remote CRUD.
- Stash with a message and untracked-file inclusion.
- Per-branch upstream indicators.
- Branch and tag publishing.
- Dedicated screen for creating GitHub repositories with README/license.

## Phase 3

- Controlled merge and prior dirty-working-tree detection.
- Text conflicts: ours, theirs, resolved, and external editor.
- `.blend` conflicts: backup of both variants and explicit selection.
- Persistent task center and cancellation of complete process trees.
- LFS progress through stderr parsing and transfer events.

## Phase 4

- Linux and macOS validated in CI.
- GitLab CLI/API and Bitbucket.
- Large-file locking through a compatible provider.
- Extraction and comparison of Blender-scene metadata.
- Pull requests, issues, releases, and actions.
- Team workflows and branch conventions.

## Known MVP technical debt

- Add a porcelain `-z` parser for names containing line breaks or unusual sequences.
- Add English/Spanish localization through Blender translations.
- Persist session preferences in a controlled way without placing paths or secrets in `.blend` files.

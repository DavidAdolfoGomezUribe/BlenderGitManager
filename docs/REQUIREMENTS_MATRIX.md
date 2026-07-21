# Requirements coverage matrix

Legend: **Implemented**, **Partial**, **Planned**.

| Section | Status | Current coverage |
|---|---|---|
| 1. General objective | Implemented | Git, GitHub CLI, LFS, commits, branches, history, and UI without a terminal. |
| 3. Compatibility | Initially implemented | Blender 4.2+, portable design; primary validation targets Windows. |
| 4-5. UI integration | Implemented | Top menu, sidebar panel, wide popup, header, and onboarding. |
| 6. Authentication | Implemented | `gh auth status/login --web/logout`; no secrets are stored. |
| 7. Dependencies | Implemented | Git, LFS, and GH status; manual executable-path configuration. |
| 8. Initialize/Open/Clone | MVP implemented | Wizard, identity, `.gitignore`, LFS, staging mode, initial commit, optional GitHub repository, and clone. |
| 9. Git LFS | Basic implementation | Local install, track/untrack, ls-files, and `.gitattributes` reminder. |
| 10. Status | Basic implementation | Porcelain XY, size, staged, untracked, conflicts, and LFS marker. |
| 11. Visual Git add | Implemented | Stage/unstage by file, selection, and globally; confirmed discard. |
| 12. Commits | Implemented | Title, description, save-before-commit, commit, and commit+push. |
| 13. Push/Pull/Fetch | Implemented | Modal tasks, sync, and ahead/behind. Pull uses `--ff-only`. |
| 14. Branches | Basic implementation | List, create, and switch with dirty-file protection and backup. |
| 15. History | Implemented | Structured Git Graph with colored lanes, merges, references, filters, incremental loading, and commit selection. |
| 16. Commit details | Implemented | Metadata, changed files, statistics, and History actions. |
| 17. Git author | Implemented during initialization | Local/global configuration during initialization; a dedicated panel remains pending. |
| 18. Remotes | Partial | Add/set URL and open GitHub; complete visual CRUD remains pending. |
| 19. Create GitHub repository | Basic implementation | Name, owner, visibility, description, remote, and push. |
| 20. Stash | Planned | Phase 2. |
| 21. Tags | Partial | Lightweight and annotated tag creation from commits; deletion and publishing UI remain pending. |
| 22. Conflicts | Partial | Detection and indication; guided binary/text resolution remains pending. |
| 23. `.blend` safety | Partial | Save and backup on branch switch; backups for all future destructive operations remain pending. |
| 24. Do not block Blender | Mostly implemented | Initialize, clone, authentication, commit/push, and sync use Future + modal timer. Full cancellation remains pending. |
| 25. Git Output | Implemented | Leveled log with a line limit. |
| 26. Errors | Basic implementation | UI messages and output; the specialized catalog can be extended. |
| 27. Security | Implemented | Argument lists, `shell=False`, validation, redaction, and credential policy. |
| 28-29. Architecture | Implemented | UI/operator/service/model/utility layers and central ProcessService. |
| 30. Preferences | Implemented | Executables, save, backup, refresh, remote, branch, and advanced mode. |
| 31. Design | Basic implementation | Dashboard, lists, visible actions, and Blender-theme compatibility. |
| 32. Limitations | Documented | Binaries, merges, quotas, and project partitioning. |
| 33. Phases | Documented in roadmap | Phases 2–4 detailed. |
| 34. MVP criteria | Mostly implemented | Complete terminal-free workflow; individual selection for the initial commit happens after the wizard. |
| 35. Deliverables | Implemented | Code, manifest, README, LICENSE, gitignore, docs, and tests. |

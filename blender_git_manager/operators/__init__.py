from .authentication import GITMANAGER_OT_github_login, GITMANAGER_OT_github_logout
from .branches import GITMANAGER_OT_create_branch, GITMANAGER_OT_switch_branch
from .commits import GITMANAGER_OT_commit
from .common import GITMANAGER_OT_open_folder, GITMANAGER_OT_open_preferences, GITMANAGER_OT_open_remote, GITMANAGER_OT_refresh
from .lfs import GITMANAGER_OT_lfs_track, GITMANAGER_OT_lfs_untrack
from .repository import (
    GITMANAGER_OT_clone_repository,
    GITMANAGER_OT_create_github_repository,
    GITMANAGER_OT_create_initial_commit,
    GITMANAGER_OT_connect_remote,
    GITMANAGER_OT_initialize_repository,
    GITMANAGER_OT_open_manager,
    GITMANAGER_OT_open_repository,
)
from .staging import GITMANAGER_OT_discard_changes, GITMANAGER_OT_stage, GITMANAGER_OT_unstage
from .synchronization import GITMANAGER_OT_synchronize

CLASSES = (
    GITMANAGER_OT_refresh,
    GITMANAGER_OT_open_folder,
    GITMANAGER_OT_open_remote,
    GITMANAGER_OT_open_preferences,
    GITMANAGER_OT_github_login,
    GITMANAGER_OT_github_logout,
    GITMANAGER_OT_open_manager,
    GITMANAGER_OT_open_repository,
    GITMANAGER_OT_initialize_repository,
    GITMANAGER_OT_clone_repository,
    GITMANAGER_OT_create_github_repository,
    GITMANAGER_OT_create_initial_commit,
    GITMANAGER_OT_connect_remote,
    GITMANAGER_OT_stage,
    GITMANAGER_OT_unstage,
    GITMANAGER_OT_discard_changes,
    GITMANAGER_OT_commit,
    GITMANAGER_OT_synchronize,
    GITMANAGER_OT_create_branch,
    GITMANAGER_OT_switch_branch,
    GITMANAGER_OT_lfs_track,
    GITMANAGER_OT_lfs_untrack,
)

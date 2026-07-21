"""Main-thread coordinator for asynchronous History and commit-detail loading."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import bpy

from ..models import (
    CommitDetails,
    CommitReferenceKind,
    HistoryPage,
    HistoryQuery,
)
from ..preferences import get_addon_preferences
from ..services.background_task_service import BackgroundTaskService, TaskCompletion
from ..services.git_service import GitService
from ..services.history_service import HistoryService, filter_history_page
from ..services.process_service import ProcessService
from ..state_sync import append_output


@dataclass(frozen=True, slots=True)
class _SceneRef:
    name: str
    pointer: int


@dataclass(frozen=True, slots=True)
class _HistoryRequest:
    generation: int
    scene: _SceneRef
    scene_epoch: int
    repository_signature: str
    repository: str
    repository_key: str
    git_executable: str
    query: HistoryQuery


@dataclass(frozen=True, slots=True)
class _DetailRequest:
    generation: int
    scene: _SceneRef
    scene_epoch: int
    repository_signature: str
    repository: str
    repository_key: str
    git_executable: str
    commit_hash: str


_GENERATION = count(1)
_TASK_SERVICE: BackgroundTaskService | None = None
_TASK_REQUESTS: dict[str, _HistoryRequest | _DetailRequest] = {}
_TASK_PROCESSES: dict[str, ProcessService] = {}
_ACTIVE_HISTORY_TASK = ""
_ACTIVE_DETAIL_TASK = ""
_PENDING_HISTORY_REQUEST: _HistoryRequest | None = None
_PENDING_DETAIL_REQUEST: _DetailRequest | None = None
_HISTORY_CACHE_LIMIT = 8
_DETAIL_CACHE_LIMIT = 256
_HISTORY_CACHE: OrderedDict[str, HistoryPage] = OrderedDict()
_DETAIL_CACHE: OrderedDict[tuple[str, str], CommitDetails] = OrderedDict()
_SCHEDULED_CALLBACKS: set[object] = set()
_SCENE_EPOCHS: dict[int, int] = {}
_FILTER_TOKENS: dict[int, int] = {}
_REFRESH_TOKENS: dict[int, int] = {}
_DETAIL_TOKENS: dict[int, int] = {}
_DETAIL_GENERATIONS: dict[int, int] = {}
_APPLYING_STATE = False


def _repository_key(repository: str) -> str:
    if not repository:
        return ""
    return os.path.normcase(
        os.path.abspath(os.path.normpath(str(Path(repository).expanduser())))
    )


def _state_from_context(context):
    scene = getattr(context, "scene", None)
    return getattr(scene, "git_manager", None)


def _scene_ref_from_context(context) -> _SceneRef | None:
    scene = getattr(context, "scene", None)
    if scene is None:
        return None
    try:
        pointer = int(scene.as_pointer())
        name = str(scene.name)
    except (AttributeError, ReferenceError, RuntimeError):
        return None
    if pointer <= 0:
        return None
    return _SceneRef(name=name, pointer=pointer)


def _scene_from_ref(reference: _SceneRef):
    """Resolve a Blender Scene without relying on the currently active context."""
    try:
        candidate = bpy.data.scenes.get(reference.name)
        if candidate is not None and int(candidate.as_pointer()) == reference.pointer:
            return candidate
        # A Scene may be renamed while a background read is running. Its RNA
        # pointer remains stable, so fall back to an identity scan.
        for candidate in bpy.data.scenes:
            if int(candidate.as_pointer()) == reference.pointer:
                return candidate
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return None


def _context_for_scene(scene):
    """Build the small context surface used by state/output helpers."""
    try:
        preferences = bpy.context.preferences
    except (AttributeError, ReferenceError, RuntimeError):
        preferences = None
    return SimpleNamespace(scene=scene, preferences=preferences)


def _scene_epoch(reference: _SceneRef) -> int:
    return _SCENE_EPOCHS.get(reference.pointer, 0)


def _bump_scene_epoch(reference: _SceneRef) -> int:
    value = _scene_epoch(reference) + 1
    _SCENE_EPOCHS[reference.pointer] = value
    return value


def _next_scene_token(tokens: dict[int, int], reference: _SceneRef) -> int:
    value = tokens.get(reference.pointer, 0) + 1
    tokens[reference.pointer] = value
    return value


def _history_cache_get(repository_key: str) -> HistoryPage | None:
    cached = _HISTORY_CACHE.pop(repository_key, None)
    if cached is not None:
        _HISTORY_CACHE[repository_key] = cached
    return cached


def _history_cache_put(repository_key: str, page: HistoryPage) -> None:
    _HISTORY_CACHE.pop(repository_key, None)
    _HISTORY_CACHE[repository_key] = page
    while len(_HISTORY_CACHE) > _HISTORY_CACHE_LIMIT:
        _HISTORY_CACHE.popitem(last=False)


def _detail_cache_get(
    repository_key: str,
    commit_hash: str,
) -> CommitDetails | None:
    key = (repository_key, commit_hash)
    cached = _DETAIL_CACHE.pop(key, None)
    if cached is not None:
        _DETAIL_CACHE[key] = cached
    return cached


def _detail_cache_put(
    repository_key: str,
    commit_hash: str,
    details: CommitDetails,
) -> None:
    key = (repository_key, commit_hash)
    _DETAIL_CACHE.pop(key, None)
    _DETAIL_CACHE[key] = details
    while len(_DETAIL_CACHE) > _DETAIL_CACHE_LIMIT:
        _DETAIL_CACHE.popitem(last=False)


def _clear_detail_cache(repository_key: str) -> None:
    for key in tuple(_DETAIL_CACHE):
        if key[0] == repository_key:
            _DETAIL_CACHE.pop(key, None)


def _task_service() -> BackgroundTaskService:
    global _TASK_SERVICE
    if _TASK_SERVICE is None:
        _TASK_SERVICE = BackgroundTaskService(max_workers=2)
    return _TASK_SERVICE


def _cancel_task(task_id: str) -> None:
    """Cancel both the queued Future and an already-running Git process."""
    if not task_id:
        return
    process = _TASK_PROCESSES.get(task_id)
    if process is not None:
        process.cancel()
    service = _TASK_SERVICE
    if service is not None:
        service.cancel(task_id)


def _request_belongs_to_scene(
    request: _HistoryRequest | _DetailRequest | None,
    reference: _SceneRef,
) -> bool:
    return bool(request is not None and request.scene.pointer == reference.pointer)


def _cancel_scene_history_work(reference: _SceneRef) -> None:
    global _PENDING_HISTORY_REQUEST

    if _request_belongs_to_scene(_PENDING_HISTORY_REQUEST, reference):
        _PENDING_HISTORY_REQUEST = None
    active_request = _TASK_REQUESTS.get(_ACTIVE_HISTORY_TASK)
    if _request_belongs_to_scene(active_request, reference):
        _cancel_task(_ACTIVE_HISTORY_TASK)


def _cancel_scene_detail_work(
    reference: _SceneRef,
    *,
    keep_hash: str = "",
) -> None:
    global _PENDING_DETAIL_REQUEST

    pending = _PENDING_DETAIL_REQUEST
    if (
        _request_belongs_to_scene(pending, reference)
        and (not keep_hash or pending.commit_hash != keep_hash)
    ):
        _PENDING_DETAIL_REQUEST = None
    active = _TASK_REQUESTS.get(_ACTIVE_DETAIL_TASK)
    if (
        isinstance(active, _DetailRequest)
        and active.scene.pointer == reference.pointer
        and (not keep_hash or active.commit_hash != keep_hash)
    ):
        _cancel_task(_ACTIVE_DETAIL_TASK)


def _invalidate_scene_work(reference: _SceneRef) -> None:
    """Invalidate every callback/request that captured an older scene state."""
    _bump_scene_epoch(reference)
    _next_scene_token(_FILTER_TOKENS, reference)
    _next_scene_token(_REFRESH_TOKENS, reference)
    _next_scene_token(_DETAIL_TOKENS, reference)
    _DETAIL_GENERATIONS[reference.pointer] = next(_GENERATION)
    _cancel_scene_history_work(reference)
    _cancel_scene_detail_work(reference)


def _query_from_state(state) -> HistoryQuery:
    return HistoryQuery(
        limit=max(100, min(int(state.history_limit), 1000)),
        show_all_branches=bool(state.history_show_all_branches),
        show_remotes=bool(state.history_show_remotes),
        show_tags=bool(state.history_show_tags),
        branch_filter=str(state.history_branch_filter),
    )


def _redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass


def _ensure_poll_timer() -> None:
    try:
        if not bpy.app.timers.is_registered(_poll_history_tasks):
            bpy.app.timers.register(
                _poll_history_tasks,
                first_interval=0.1,
                persistent=True,
            )
    except (AttributeError, RuntimeError):
        pass


def _submit_history(request: _HistoryRequest) -> None:
    global _ACTIVE_HISTORY_TASK

    process = ProcessService(echo_console=False)

    def worker():
        git = GitService(request.git_executable, process=process)
        return HistoryService(git).load(request.repository, request.query)

    task_id = _task_service().submit("Load Git History", worker)
    _TASK_REQUESTS[task_id] = request
    _TASK_PROCESSES[task_id] = process
    _ACTIVE_HISTORY_TASK = task_id
    _ensure_poll_timer()


def _submit_details(request: _DetailRequest) -> None:
    global _ACTIVE_DETAIL_TASK

    process = ProcessService(echo_console=False)

    def worker():
        git = GitService(request.git_executable, process=process)
        return HistoryService(git).load_details(
            request.repository,
            request.commit_hash,
        )

    task_id = _task_service().submit("Load Commit Details", worker)
    _TASK_REQUESTS[task_id] = request
    _TASK_PROCESSES[task_id] = process
    _ACTIVE_DETAIL_TASK = task_id
    _ensure_poll_timer()


def request_history_refresh(context, *, force: bool = False) -> None:
    """Submit a Git read without touching Blender from its worker thread."""
    global _PENDING_HISTORY_REQUEST

    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if state is None or scene_reference is None or not state.repository_path:
        return
    if state.task_running:
        state.history_dirty = True
        schedule_history_refresh(context)
        return

    repository = str(Path(state.repository_path).expanduser().resolve(strict=False))
    key = _repository_key(repository)
    query = _query_from_state(state)
    cached = _history_cache_get(key)
    if (
        not force
        and cached is not None
        and cached.query == query
        and not state.history_dirty
    ):
        _apply_cached_history(context, preferred_hash=_selected_commit_hash(state))
        return

    generation = next(_GENERATION)
    state.history_generation = generation
    state.history_loading = True
    state.history_error = ""
    try:
        preferences = get_addon_preferences(context)
    except Exception as exc:
        state.history_loading = False
        state.history_error = str(exc)
        state.history_dirty = True
        state.history_loaded = bool(state.commits)
        append_output(context, f"Could not start History loading: {exc}", "ERROR")
        _redraw()
        return
    request = _HistoryRequest(
        generation=generation,
        scene=scene_reference,
        scene_epoch=_scene_epoch(scene_reference),
        repository_signature=str(state.history_repository_signature),
        repository=repository,
        repository_key=key,
        git_executable=str(preferences.git_executable),
        query=query,
    )
    if _ACTIVE_HISTORY_TASK:
        _PENDING_HISTORY_REQUEST = request
        _cancel_task(_ACTIVE_HISTORY_TASK)
    else:
        try:
            _submit_history(request)
        except Exception as exc:
            state.history_loading = False
            state.history_error = str(exc)
            state.history_dirty = True
            state.history_loaded = bool(state.commits)
            append_output(context, f"Could not start History loading: {exc}", "ERROR")
    _redraw()


def request_history_details(context) -> None:
    global _PENDING_DETAIL_REQUEST

    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if (
        state is None
        or scene_reference is None
        or not state.repository_path
        or not (0 <= state.commits_index < len(state.commits))
    ):
        if state is not None:
            state.history_detail_loading = False
        if scene_reference is not None:
            _DETAIL_GENERATIONS[scene_reference.pointer] = next(_GENERATION)
            _cancel_scene_detail_work(scene_reference)
        return
    commit_hash = str(state.commits[state.commits_index].full_hash)
    repository = str(Path(state.repository_path).expanduser().resolve(strict=False))
    key = _repository_key(repository)
    generation = next(_GENERATION)
    _DETAIL_GENERATIONS[scene_reference.pointer] = generation
    cached = _detail_cache_get(key, commit_hash)
    if cached is not None:
        _cancel_scene_detail_work(scene_reference)
        _apply_commit_details(state, cached)
        _redraw()
        return

    state.history_detail_hash = commit_hash
    state.history_detail_loading = True
    state.history_detail_error = ""
    try:
        preferences = get_addon_preferences(context)
    except Exception as exc:
        state.history_detail_loading = False
        state.history_detail_error = str(exc)
        append_output(context, f"Could not load commit details: {exc}", "ERROR")
        _redraw()
        return
    request = _DetailRequest(
        generation=generation,
        scene=scene_reference,
        scene_epoch=_scene_epoch(scene_reference),
        repository_signature=str(state.history_repository_signature),
        repository=repository,
        repository_key=key,
        git_executable=str(preferences.git_executable),
        commit_hash=commit_hash,
    )
    if _ACTIVE_DETAIL_TASK:
        _PENDING_DETAIL_REQUEST = request
        _cancel_task(_ACTIVE_DETAIL_TASK)
    else:
        try:
            _submit_details(request)
        except Exception as exc:
            state.history_detail_loading = False
            state.history_detail_error = str(exc)
            append_output(context, f"Could not load commit details: {exc}", "ERROR")
    _redraw()


def _request_scene_state(
    request: _HistoryRequest | _DetailRequest,
):
    """Return the originating scene/state only while request provenance matches."""
    scene = _scene_from_ref(request.scene)
    if scene is None or _scene_epoch(request.scene) != request.scene_epoch:
        return None
    try:
        state = scene.git_manager
        repository_matches = (
            _repository_key(state.repository_path) == request.repository_key
        )
        signature_matches = (
            str(state.history_repository_signature)
            == request.repository_signature
        )
    except (AttributeError, ReferenceError, RuntimeError):
        return None
    if not repository_matches or not signature_matches:
        return None
    return scene, state


def _complete_history(
    completion: TaskCompletion,
    request: _HistoryRequest,
) -> None:
    resolved = _request_scene_state(request)
    if (
        resolved is None
        or resolved[1].history_generation != request.generation
    ):
        return
    scene, state = resolved
    context = _context_for_scene(scene)
    state.history_loading = False
    if completion.error is not None:
        state.history_error = str(completion.error)
        state.history_loaded = bool(state.commits)
        state.history_dirty = True
        append_output(
            context,
            f"Git History could not be loaded: {completion.error}",
            "ERROR",
        )
        return
    if not isinstance(completion.result, HistoryPage):
        state.history_error = "History worker returned an invalid result."
        state.history_loaded = bool(state.commits)
        state.history_dirty = True
        return

    _history_cache_put(request.repository_key, completion.result)
    state.history_error = ""
    try:
        applied = _apply_cached_history(
            context,
            preferred_hash=_selected_commit_hash(state),
        )
    except Exception as exc:
        state.history_error = f"History result could not be applied: {exc}"
        state.history_dirty = True
        state.history_loaded = bool(state.commits)
        append_output(context, state.history_error, "ERROR")
        return
    if not applied:
        state.history_error = "History result no longer matches the repository."
        state.history_dirty = True
        state.history_loaded = bool(state.commits)
        return
    state.history_dirty = False
    append_output(
        context,
        (
            f"Loaded {len(completion.result.commits)} commit(s) for Git Graph"
            + ("; more history is available." if completion.result.has_more else ".")
        ),
        "SUCCESS",
    )


def _complete_details(
    completion: TaskCompletion,
    request: _DetailRequest,
) -> None:
    resolved = _request_scene_state(request)
    if (
        resolved is None
        or _DETAIL_GENERATIONS.get(request.scene.pointer) != request.generation
    ):
        return
    scene, state = resolved
    selected_hash = _selected_commit_hash(state)
    if selected_hash != request.commit_hash:
        return
    state.history_detail_loading = False
    state.history_detail_hash = request.commit_hash
    if completion.error is not None:
        state.history_detail_error = str(completion.error)
        append_output(
            _context_for_scene(scene),
            f"Commit details could not be loaded: {completion.error}",
            "ERROR",
        )
        return
    if not isinstance(completion.result, CommitDetails):
        state.history_detail_error = "Commit details worker returned an invalid result."
        return

    _detail_cache_put(
        request.repository_key,
        request.commit_hash,
        completion.result,
    )
    try:
        _apply_commit_details(state, completion.result)
    except Exception as exc:
        state.history_detail_loading = False
        state.history_detail_error = f"Commit details could not be applied: {exc}"
        append_output(
            _context_for_scene(scene),
            state.history_detail_error,
            "ERROR",
        )


def _poll_history_tasks():
    global _ACTIVE_HISTORY_TASK
    global _ACTIVE_DETAIL_TASK
    global _PENDING_HISTORY_REQUEST
    global _PENDING_DETAIL_REQUEST

    service = _TASK_SERVICE
    if service is None:
        return None

    for completion in service.poll():
        _TASK_PROCESSES.pop(completion.task_id, None)
        request = _TASK_REQUESTS.pop(completion.task_id, None)
        if request is None:
            continue
        if completion.task_id == _ACTIVE_HISTORY_TASK:
            _ACTIVE_HISTORY_TASK = ""
            if isinstance(request, _HistoryRequest):
                _complete_history(completion, request)
        elif completion.task_id == _ACTIVE_DETAIL_TASK:
            _ACTIVE_DETAIL_TASK = ""
            if isinstance(request, _DetailRequest):
                _complete_details(completion, request)

    if not _ACTIVE_HISTORY_TASK and _PENDING_HISTORY_REQUEST is not None:
        request = _PENDING_HISTORY_REQUEST
        _PENDING_HISTORY_REQUEST = None
        resolved = _request_scene_state(request)
        if resolved is not None and resolved[1].history_generation == request.generation:
            try:
                _submit_history(request)
            except Exception as exc:
                scene, state = resolved
                state.history_loading = False
                state.history_error = str(exc)
                state.history_dirty = True
                state.history_loaded = bool(state.commits)
                append_output(
                    _context_for_scene(scene),
                    f"Could not start History loading: {exc}",
                    "ERROR",
                )

    if not _ACTIVE_DETAIL_TASK and _PENDING_DETAIL_REQUEST is not None:
        request = _PENDING_DETAIL_REQUEST
        _PENDING_DETAIL_REQUEST = None
        resolved = _request_scene_state(request)
        if (
            resolved is not None
            and _DETAIL_GENERATIONS.get(request.scene.pointer)
            == request.generation
            and _selected_commit_hash(resolved[1]) == request.commit_hash
        ):
            try:
                _submit_details(request)
            except Exception as exc:
                scene, state = resolved
                state.history_detail_loading = False
                state.history_detail_error = str(exc)
                append_output(
                    _context_for_scene(scene),
                    f"Could not load commit details: {exc}",
                    "ERROR",
                )

    _redraw()
    if (
        _ACTIVE_HISTORY_TASK
        or _ACTIVE_DETAIL_TASK
        or _PENDING_HISTORY_REQUEST is not None
        or _PENDING_DETAIL_REQUEST is not None
        or service.has_running_tasks()
    ):
        return 0.1
    return None


def _selected_commit_hash(state) -> str:
    if 0 <= state.commits_index < len(state.commits):
        return str(state.commits[state.commits_index].full_hash)
    return ""


def _display_date(value: str) -> str:
    return value.replace("T", " ")[:16]


def _reference_names(commit, kind: CommitReferenceKind) -> tuple[str, ...]:
    return tuple(
        reference.name
        for reference in commit.references
        if reference.kind is kind and reference.name != "HEAD"
    )


def _apply_page_to_state(
    state,
    page: HistoryPage,
    *,
    loaded_count: int,
    preferred_hash: str = "",
) -> None:
    global _APPLYING_STATE
    _APPLYING_STATE = True
    try:
        state.commits.clear()
        max_lanes = 1
        head_index = -1
        selected_index = -1
        for index, commit in enumerate(page.commits):
            item = state.commits.add()
            item.full_hash = commit.full_hash
            item.short_hash = commit.short_hash
            item.subject = commit.subject
            item.body = commit.body
            item.author_name = commit.author_name
            item.author_email = commit.author_email
            item.authored_at = commit.authored_at
            item.display_date = _display_date(commit.authored_at)
            item.decorations = commit.decorations
            item.parent_hashes = " ".join(commit.parent_hashes)
            item.lane_index = commit.lane_index
            item.parent_lane_indexes = " ".join(
                str(lane) for lane in commit.parent_lane_indexes
            )
            item.active_lane_indexes = " ".join(
                str(lane)
                for lane, value in enumerate(commit.lanes_before)
                if value is not None
            )
            item.outgoing_lane_indexes = " ".join(
                str(lane)
                for lane, value in enumerate(commit.lanes_after)
                if value is not None
            )
            item.graph_lane_count = max(1, commit.lane_count)
            item.is_merge = commit.is_merge
            item.is_head = any(
                reference.kind is CommitReferenceKind.HEAD
                for reference in commit.references
            )
            item.local_branches = "\n".join(
                _reference_names(commit, CommitReferenceKind.LOCAL_BRANCH)
            )
            item.remote_branches = "\n".join(
                _reference_names(commit, CommitReferenceKind.REMOTE_BRANCH)
            )
            item.tags = "\n".join(
                _reference_names(commit, CommitReferenceKind.TAG)
            )
            max_lanes = max(max_lanes, item.graph_lane_count)
            if item.is_head:
                head_index = index
            if preferred_hash and item.full_hash == preferred_hash:
                selected_index = index

        state.history_graph_lane_count = max_lanes
        state.history_loaded_count = loaded_count
        state.history_visible_count = len(page.commits)
        state.history_has_more = page.has_more
        state.history_loaded = True
        if state.commits:
            state.commits_index = (
                selected_index
                if selected_index >= 0
                else head_index
                if head_index >= 0
                else 0
            )
        else:
            state.commits_index = 0
        try:
            from ..ui.graph_icons import prewarm_graph_icons

            prewarm_graph_icons(state.commits)
        except Exception as exc:
            # The graph still has a text/metadata representation if custom
            # icons cannot be prepared; report diagnostics without rejecting
            # an otherwise valid History page.
            print(
                "[Blender Git Manager][UI][WARNING] "
                f"Could not prepare colored graph icons: {exc}"
            )
    finally:
        _APPLYING_STATE = False


def _apply_cached_history(
    context,
    *,
    preferred_hash: str = "",
    schedule_details: bool = True,
) -> bool:
    state = _state_from_context(context)
    if state is None:
        return False
    cached = _history_cache_get(_repository_key(state.repository_path))
    if cached is None:
        return False
    filtered = filter_history_page(
        cached,
        search=str(state.history_search),
        author=str(state.history_author_filter),
    )
    _apply_page_to_state(
        state,
        filtered,
        loaded_count=len(cached.commits),
        preferred_hash=preferred_hash,
    )
    state.history_has_more = cached.has_more
    if _query_from_state(state) != cached.query:
        state.history_dirty = True
    if schedule_details:
        schedule_history_details(context)
    return True


def _apply_commit_details(state, details: CommitDetails) -> None:
    references = details.references
    state.history_detail_hash = details.full_hash
    state.history_detail_loading = False
    state.history_detail_error = ""
    state.history_detail_message = details.message
    state.history_detail_body = details.description
    state.history_detail_author_name = details.author_name
    state.history_detail_author_email = details.author_email
    state.history_detail_date = details.date
    state.history_detail_parents = " ".join(details.parent_hashes)
    state.history_detail_local_branches = "\n".join(
        reference.name
        for reference in references
        if reference.kind is CommitReferenceKind.LOCAL_BRANCH
    )
    state.history_detail_remote_branches = "\n".join(
        reference.name
        for reference in references
        if reference.kind is CommitReferenceKind.REMOTE_BRANCH
    )
    state.history_detail_tags = "\n".join(
        reference.name
        for reference in references
        if reference.kind is CommitReferenceKind.TAG
    )
    state.history_detail_files.clear()
    for file in details.files:
        item = state.history_detail_files.add()
        item.status = file.status
        item.path = file.path
        item.old_path = file.old_path
        item.binary = file.is_binary
        item.additions = int(file.additions or 0)
        item.deletions = int(file.deletions or 0)
    state.history_detail_file_count = details.changed_files
    state.history_detail_additions = details.total_additions
    state.history_detail_deletions = details.total_deletions
    for commit in state.commits:
        if commit.full_hash == details.full_hash:
            commit.body = details.description
            break


def _schedule(function, *, delay: float) -> None:
    try:
        _SCHEDULED_CALLBACKS.add(function)
        bpy.app.timers.register(function, first_interval=delay)
    except (AttributeError, RuntimeError):
        _SCHEDULED_CALLBACKS.discard(function)


def schedule_history_filter(context) -> None:
    if _APPLYING_STATE:
        return
    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if (
        state is None
        or scene_reference is None
        or state.active_tab != "HISTORY"
    ):
        return
    token = _next_scene_token(_FILTER_TOKENS, scene_reference)

    def apply_filter():
        try:
            if token == _FILTER_TOKENS.get(scene_reference.pointer):
                scene = _scene_from_ref(scene_reference)
                if scene is None:
                    return None
                current = scene.git_manager
                if current.active_tab != "HISTORY":
                    return None
                _apply_cached_history(
                    _context_for_scene(scene),
                    preferred_hash=_selected_commit_hash(current),
                )
        finally:
            _SCHEDULED_CALLBACKS.discard(apply_filter)
        return None

    _schedule(apply_filter, delay=0.15)


def schedule_history_refresh(context) -> None:
    if _APPLYING_STATE:
        return
    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if state is None or scene_reference is None:
        return
    state.history_dirty = True
    # Invalidate a result that could otherwise complete during the debounce
    # interval with the previous query.
    state.history_generation = next(_GENERATION)
    _cancel_scene_history_work(scene_reference)
    state.history_loading = False
    token = _next_scene_token(_REFRESH_TOKENS, scene_reference)
    captured_epoch = _scene_epoch(scene_reference)
    captured_signature = str(state.history_repository_signature)

    def refresh_when_safe():
        repeat = False
        try:
            if token != _REFRESH_TOKENS.get(scene_reference.pointer):
                return None
            scene = _scene_from_ref(scene_reference)
            if scene is None:
                return None
            current = scene.git_manager
            if (
                _scene_epoch(scene_reference) != captured_epoch
                or str(current.history_repository_signature) != captured_signature
                or current.active_tab != "HISTORY"
            ):
                return None
            if current.task_running:
                repeat = True
                return 0.25
            request_history_refresh(_context_for_scene(scene), force=True)
            return None
        finally:
            if not repeat:
                _SCHEDULED_CALLBACKS.discard(refresh_when_safe)

    _schedule(refresh_when_safe, delay=0.2)


def schedule_history_details(context) -> None:
    if _APPLYING_STATE:
        return
    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if (
        state is None
        or scene_reference is None
        or state.active_tab != "HISTORY"
    ):
        return
    selected_hash = _selected_commit_hash(state)
    token = _next_scene_token(_DETAIL_TOKENS, scene_reference)
    _DETAIL_GENERATIONS[scene_reference.pointer] = next(_GENERATION)
    _cancel_scene_detail_work(scene_reference)
    state.history_detail_loading = False
    if not selected_hash:
        return
    if state.history_detail_hash != selected_hash:
        state.history_detail_error = ""
    captured_epoch = _scene_epoch(scene_reference)
    captured_signature = str(state.history_repository_signature)

    def load_details():
        try:
            if token != _DETAIL_TOKENS.get(scene_reference.pointer):
                return None
            scene = _scene_from_ref(scene_reference)
            if scene is None:
                return None
            current = scene.git_manager
            if (
                _scene_epoch(scene_reference) != captured_epoch
                or str(current.history_repository_signature) != captured_signature
                or current.active_tab != "HISTORY"
                or _selected_commit_hash(current) != selected_hash
            ):
                return None
            request_history_details(_context_for_scene(scene))
        finally:
            _SCHEDULED_CALLBACKS.discard(load_details)
        return None

    _schedule(load_details, delay=0.15)


def on_history_tab_changed(context) -> None:
    if _APPLYING_STATE:
        return
    state = _state_from_context(context)
    if state is None or state.active_tab != "HISTORY":
        return
    restored = _apply_cached_history(
        context,
        preferred_hash=_selected_commit_hash(state),
    )
    if not restored or state.history_dirty:
        schedule_history_refresh(context)
    else:
        schedule_history_details(context)


def repository_summary_changed(context, signature: str) -> None:
    """Invalidate graph data after HEAD/ref changes observed by summary refresh."""
    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if state is None or scene_reference is None:
        return
    changed = state.history_repository_signature != signature
    repository_key = _repository_key(state.repository_path)
    state.history_repository_signature = signature
    if changed:
        _invalidate_scene_work(scene_reference)
        state.history_dirty = True
        state.history_loading = False
        state.history_detail_loading = False
        _clear_detail_cache(repository_key)
    if changed or not state.commits:
        _apply_cached_history(
            context,
            preferred_hash=_selected_commit_hash(state),
            schedule_details=not changed,
        )
    if changed and state.active_tab == "HISTORY":
        schedule_history_refresh(context)


def clear_repository_history(context) -> None:
    state = _state_from_context(context)
    scene_reference = _scene_ref_from_context(context)
    if state is None or scene_reference is None:
        return
    repository_key = _repository_key(state.repository_path)
    _invalidate_scene_work(scene_reference)
    _clear_detail_cache(repository_key)
    state.commits.clear()
    state.history_detail_files.clear()
    state.history_loaded = False
    state.history_loading = False
    state.history_dirty = True
    state.history_error = ""
    state.history_repository_signature = ""
    state.history_loaded_count = 0
    state.history_visible_count = 0
    state.history_has_more = False
    state.history_detail_hash = ""
    state.history_detail_loading = False
    state.history_detail_error = ""
    state.history_detail_message = ""
    state.history_detail_body = ""
    state.history_detail_author_name = ""
    state.history_detail_author_email = ""
    state.history_detail_date = ""
    state.history_detail_parents = ""
    state.history_detail_local_branches = ""
    state.history_detail_remote_branches = ""
    state.history_detail_tags = ""
    state.history_detail_file_count = 0
    state.history_detail_additions = 0
    state.history_detail_deletions = 0


class GITMANAGER_OT_history_refresh(bpy.types.Operator):
    bl_idname = "git_manager.history_refresh"
    bl_label = "Refresh Git History"
    bl_description = "Reload structured Git history in the background"

    def execute(self, context):
        request_history_refresh(context, force=True)
        return {"FINISHED"}


class GITMANAGER_OT_history_load_more(bpy.types.Operator):
    bl_idname = "git_manager.history_load_more"
    bl_label = "Load More History"
    bl_description = "Increase the history window and recalculate the complete graph"

    @classmethod
    def poll(cls, context):
        state = _state_from_context(context)
        if state is None or state.history_loading:
            return False
        if state.history_limit >= 1000:
            cls.poll_message_set("The maximum of 1000 loaded commits has been reached.")
            return False
        if state.history_loaded and not state.history_has_more:
            cls.poll_message_set("No additional commits are available.")
            return False
        return bool(state.repository_path)

    def execute(self, context):
        state = context.scene.git_manager
        state.history_limit = min(1000, int(state.history_limit) + 100)
        request_history_refresh(context, force=True)
        return {"FINISHED"}


def cancel_history_runtime() -> None:
    """Cancel queued reads and remove timers during add-on unregister."""
    global _TASK_SERVICE
    global _ACTIVE_HISTORY_TASK
    global _ACTIVE_DETAIL_TASK
    global _PENDING_HISTORY_REQUEST
    global _PENDING_DETAIL_REQUEST

    for process in tuple(_TASK_PROCESSES.values()):
        process.cancel()
    for callback in tuple(_SCHEDULED_CALLBACKS):
        try:
            if bpy.app.timers.is_registered(callback):
                bpy.app.timers.unregister(callback)
        except (AttributeError, RuntimeError):
            pass
    _SCHEDULED_CALLBACKS.clear()
    try:
        if bpy.app.timers.is_registered(_poll_history_tasks):
            bpy.app.timers.unregister(_poll_history_tasks)
    except (AttributeError, RuntimeError):
        pass
    if _TASK_SERVICE is not None:
        _TASK_SERVICE.cancel_all()
        _TASK_SERVICE.shutdown(wait=False)
        _TASK_SERVICE = None
    _TASK_REQUESTS.clear()
    _TASK_PROCESSES.clear()
    _ACTIVE_HISTORY_TASK = ""
    _ACTIVE_DETAIL_TASK = ""
    _PENDING_HISTORY_REQUEST = None
    _PENDING_DETAIL_REQUEST = None
    _HISTORY_CACHE.clear()
    _DETAIL_CACHE.clear()
    _SCENE_EPOCHS.clear()
    _FILTER_TOKENS.clear()
    _REFRESH_TOKENS.clear()
    _DETAIL_TOKENS.clear()
    _DETAIL_GENERATIONS.clear()


CLASSES = (
    GITMANAGER_OT_history_refresh,
    GITMANAGER_OT_history_load_more,
)

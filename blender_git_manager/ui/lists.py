from __future__ import annotations

import bpy

from .graph_icons import fallback_graph_glyph, graph_cell_style, graph_icon_id


_LANE_NODE_ICONS = (
    "KEYTYPE_KEYFRAME_VEC",
    "KEYTYPE_BREAKDOWN_VEC",
    "KEYTYPE_EXTREME_VEC",
    "KEYTYPE_JITTER_VEC",
    "KEYTYPE_MOVING_HOLD_VEC",
)

_GRAPH_CELL_WIDTH = 0.9
_HASH_COLUMN_WIDTH = 5.7
_MESSAGE_COLUMN_WIDTH = 22.0
_AUTHOR_COLUMN_WIDTH = 11.0
_DATE_COLUMN_WIDTH = 10.0
_REFERENCES_COLUMN_WIDTH = 16.0


def _visible_lane_count(context, lane_count: int) -> int:
    region_width = int(getattr(getattr(context, "region", None), "width", 960))
    if region_width >= 1400:
        maximum = 18
    elif region_width >= 900:
        maximum = 12
    else:
        maximum = 6
    return min(max(1, lane_count), maximum)


def _graph_column_width(lane_count: int, visible_lanes: int) -> float:
    overflow = 1.1 if lane_count > visible_lanes else 0.0
    return max(2.8, visible_lanes * _GRAPH_CELL_WIDTH + overflow)


def draw_commit_list_header(context, layout, state) -> None:
    """Draw headers using the same widths as every commit row."""

    lane_count = max(1, int(getattr(state, "history_graph_lane_count", 1)))
    visible_lanes = _visible_lane_count(context, lane_count)
    region_width = int(getattr(getattr(context, "region", None), "width", 960))
    row = layout.row(align=True)

    graph = row.row(align=True)
    graph.ui_units_x = _graph_column_width(lane_count, visible_lanes)
    graph.label(text="Graph")

    object_id = row.row(align=True)
    object_id.ui_units_x = _HASH_COLUMN_WIDTH
    object_id.label(text="Commit")

    message = row.row(align=True)
    message.ui_units_x = _MESSAGE_COLUMN_WIDTH if region_width >= 760 else 15
    message.label(text="Message")

    if region_width < 760:
        return
    author = row.row(align=True)
    author.ui_units_x = _AUTHOR_COLUMN_WIDTH
    author.label(text="Author")
    date = row.row(align=True)
    date.ui_units_x = _DATE_COLUMN_WIDTH
    date.label(text="Date")
    references = row.row(align=True)
    references.ui_units_x = _REFERENCES_COLUMN_WIDTH
    references.label(text="References")


class GITMANAGER_UL_changes(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        status_icon = "ERROR" if item.conflicted else "CHECKMARK" if item.staged else "DOT"
        row.label(text=item.status_code, icon=status_icon)
        row.label(text=item.path)
        if item.uses_lfs:
            row.label(text="LFS", icon="PACKAGE")
        row.label(text=item.size_label)
        if item.staged:
            operator = row.operator("git_manager.unstage", text="", icon="REMOVE")
            operator.path = item.path
        else:
            operator = row.operator("git_manager.stage", text="", icon="ADD")
            operator.path = item.path


class GITMANAGER_UL_commits(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        is_head = bool(getattr(item, "is_head", False))
        node_lane = max(0, int(getattr(item, "lane_index", 0)))
        lane_count = max(
            1,
            int(getattr(data, "history_graph_lane_count", 1)),
            int(getattr(item, "graph_lane_count", 1)),
        )
        region_width = int(getattr(getattr(context, "region", None), "width", 960))
        visible_lanes = _visible_lane_count(context, lane_count)

        graph = row.row(align=True)
        graph.ui_units_x = _graph_column_width(lane_count, visible_lanes)
        for lane in range(visible_lanes):
            cell = graph.row(align=True)
            cell.ui_units_x = _GRAPH_CELL_WIDTH
            style = graph_cell_style(item, lane)
            icon_id = graph_icon_id(style)
            if icon_id:
                cell.label(text="", icon_value=icon_id)
            elif style.node:
                cell.label(
                    text="",
                    icon=_LANE_NODE_ICONS[lane % len(_LANE_NODE_ICONS)],
                )
            else:
                cell.label(text=fallback_graph_glyph(style))
        if lane_count > visible_lanes:
            hidden = lane_count - visible_lanes
            graph.label(
                text=(
                    f"L{node_lane + 1}"
                    if node_lane >= visible_lanes
                    else f"+{hidden}"
                ),
                icon="FORWARD" if node_lane >= visible_lanes else "NONE",
            )

        head = row.row(align=True)
        head.ui_units_x = _HASH_COLUMN_WIDTH
        head.label(
            text=item.short_hash,
            icon="RADIOBUT_ON" if is_head else "BLANK1",
        )

        message = row.row(align=True)
        message.ui_units_x = _MESSAGE_COLUMN_WIDTH if region_width >= 760 else 15
        message.label(
            text=item.subject,
            icon="DECORATE_LINKED" if item.is_merge else "NONE",
        )

        if region_width < 760:
            return

        author = row.row(align=True)
        author.ui_units_x = _AUTHOR_COLUMN_WIDTH
        author.label(text=item.author_name)

        date = row.row(align=True)
        date.ui_units_x = _DATE_COLUMN_WIDTH
        date.label(text=item.display_date or item.authored_at[:16])

        references: list[str] = []
        if item.local_branches:
            references.extend(item.local_branches.splitlines())
        if item.remote_branches:
            references.extend(item.remote_branches.splitlines())
        if item.tags:
            references.extend(f"#{tag}" for tag in item.tags.splitlines())
        refs = row.row(align=True)
        refs.ui_units_x = _REFERENCES_COLUMN_WIDTH
        refs.label(text="  ".join(references)[:80], icon="BOOKMARKS" if references else "BLANK1")


class GITMANAGER_UL_commit_files(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        icon = {
            "A": "ADD",
            "D": "REMOVE",
            "R": "FILE_REFRESH",
            "C": "DUPLICATE",
            "M": "DOT",
        }.get(item.status[:1], "FILE")
        status = row.row(align=True)
        status.ui_units_x = 2.2
        status.label(text=item.status or "M", icon=icon)
        row.label(text=item.path)
        if item.old_path and item.old_path != item.path:
            row.label(text=f"from {item.old_path}")
        stats = row.row(align=True)
        stats.ui_units_x = 7
        if item.binary:
            stats.label(text="binary", icon="PACKAGE")
        else:
            stats.label(text=f"+{item.additions}  -{item.deletions}")


class GITMANAGER_UL_branches(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        icon = "RADIOBUT_ON" if item.current else "OUTLINER_OB_ARMATURE" if item.remote else "DOT"
        row.label(text=item.name, icon=icon)
        if item.upstream:
            row.label(text=item.upstream)
        row.label(text=item.short_hash)
        if not item.current and not item.remote:
            operator = row.operator("git_manager.switch_branch", text="Switch")
            operator.branch_name = (
                item.full_ref.removeprefix("refs/heads/")
                if item.full_ref
                else item.name.removeprefix("heads/")
            )


class GITMANAGER_UL_output(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        icon = {"ERROR": "ERROR", "WARNING": "ERROR", "SUCCESS": "CHECKMARK"}.get(item.level, "INFO")
        row.label(text=item.timestamp)
        row.label(text=item.message, icon=icon)

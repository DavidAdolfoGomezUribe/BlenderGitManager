from __future__ import annotations

import bpy


_LANE_NODE_ICONS = (
    "KEYTYPE_KEYFRAME_VEC",
    "KEYTYPE_BREAKDOWN_VEC",
    "KEYTYPE_EXTREME_VEC",
    "KEYTYPE_JITTER_VEC",
    "KEYTYPE_MOVING_HOLD_VEC",
)


def _index_set(value: str) -> set[int]:
    indexes: set[int] = set()
    for raw in value.split():
        try:
            indexes.add(int(raw))
        except ValueError:
            continue
    return indexes


def _graph_glyph(
    lane: int,
    node_lane: int,
    parent_lanes: set[int],
    active_lanes: set[int],
    outgoing_lanes: set[int],
) -> str:
    horizontal = any(
        min(node_lane, parent_lane) < lane < max(node_lane, parent_lane)
        for parent_lane in parent_lanes
        if parent_lane != node_lane
    )
    endpoint = lane in parent_lanes and lane != node_lane
    vertical = lane in active_lanes or lane in outgoing_lanes
    if horizontal and vertical:
        return "┼"
    if horizontal:
        return "─"
    if endpoint and vertical:
        return "├" if lane < node_lane else "┤"
    if endpoint:
        return "└" if lane < node_lane else "┘"
    if vertical:
        return "│"
    return " "


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
        parent_lanes = _index_set(getattr(item, "parent_lane_indexes", ""))
        active_lanes = _index_set(getattr(item, "active_lane_indexes", ""))
        outgoing_lanes = _index_set(getattr(item, "outgoing_lane_indexes", ""))
        lane_count = max(
            1,
            int(getattr(data, "history_graph_lane_count", 1)),
            int(getattr(item, "graph_lane_count", 1)),
        )
        region_width = int(getattr(getattr(context, "region", None), "width", 960))
        max_visible_lanes = 12 if region_width >= 760 else 6
        visible_lanes = min(lane_count, max_visible_lanes)

        graph = row.row(align=True)
        graph.ui_units_x = max(2.6, visible_lanes * 0.9 + (0.8 if lane_count > visible_lanes else 0.0))
        for lane in range(visible_lanes):
            cell = graph.row(align=True)
            cell.ui_units_x = 0.85
            if lane == node_lane:
                cell.label(text="", icon=_LANE_NODE_ICONS[lane % len(_LANE_NODE_ICONS)])
            else:
                cell.label(
                    text=_graph_glyph(
                        lane,
                        node_lane,
                        parent_lanes,
                        active_lanes,
                        outgoing_lanes,
                    )
                )
        if lane_count > visible_lanes:
            graph.label(text=f"+{lane_count - visible_lanes}")

        head = row.row(align=True)
        head.ui_units_x = 5.7
        head.label(
            text=item.short_hash,
            icon="RADIOBUT_ON" if is_head else "BLANK1",
        )

        message = row.row(align=True)
        message.ui_units_x = 22 if region_width >= 760 else 15
        message.label(
            text=item.subject,
            icon="DECORATE_LINKED" if item.is_merge else "NONE",
        )

        if region_width < 760:
            return

        author = row.row(align=True)
        author.ui_units_x = 11
        author.label(text=item.author_name)

        date = row.row(align=True)
        date.ui_units_x = 10
        date.label(text=item.display_date or item.authored_at[:16])

        references: list[str] = []
        if item.local_branches:
            references.extend(item.local_branches.splitlines())
        if item.remote_branches:
            references.extend(item.remote_branches.splitlines())
        if item.tags:
            references.extend(f"#{tag}" for tag in item.tags.splitlines())
        refs = row.row(align=True)
        refs.ui_units_x = 16
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

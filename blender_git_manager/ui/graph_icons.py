"""Native Blender icons for colored Git graph lanes.

The History backend only calculates graph topology.  This module translates
that topology into small transparent RGBA tiles on Blender's main thread so a
UIList can draw colored connections and a node centered on the matching
commit row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import bpy


_ICON_SIZE = 24
_IMAGE_MARKER = "_blender_git_manager_graph_icon"
_IMAGE_CACHE: dict[tuple[int, int], bpy.types.Image] = {}
_ICON_WARNING_REPORTED = False

# Saturated mid-tone colors remain legible in Blender's light and dark themes.
LANE_COLORS: tuple[tuple[float, float, float, float], ...] = (
    (0.04, 0.62, 0.95, 1.0),
    (0.79, 0.20, 0.93, 1.0),
    (0.93, 0.16, 0.43, 1.0),
    (0.98, 0.36, 0.12, 1.0),
    (0.91, 0.65, 0.04, 1.0),
    (0.18, 0.72, 0.28, 1.0),
    (0.04, 0.68, 0.64, 1.0),
    (0.29, 0.35, 0.94, 1.0),
    (0.91, 0.25, 0.63, 1.0),
    (0.39, 0.62, 0.06, 1.0),
)


@dataclass(frozen=True, slots=True)
class GraphCellStyle:
    lane_index: int
    up: bool = False
    down: bool = False
    left: bool = False
    right: bool = False
    node: bool = False

    @property
    def mask(self) -> int:
        return (
            int(self.up)
            | (int(self.down) << 1)
            | (int(self.left) << 2)
            | (int(self.right) << 3)
            | (int(self.node) << 4)
        )

    @property
    def is_empty(self) -> bool:
        return self.mask == 0


def _index_set(value: str) -> set[int]:
    indexes: set[int] = set()
    for raw in value.split():
        try:
            indexes.add(int(raw))
        except ValueError:
            continue
    return indexes


def graph_cell_style(item, lane_index: int) -> GraphCellStyle:
    """Return the exact connections needed by one lane cell."""

    node_lane = max(0, int(getattr(item, "lane_index", 0)))
    parent_lanes = _index_set(getattr(item, "parent_lane_indexes", ""))
    active_lanes = _index_set(getattr(item, "active_lane_indexes", ""))
    outgoing_lanes = _index_set(getattr(item, "outgoing_lane_indexes", ""))

    left = False
    right = False
    for parent_lane in parent_lanes:
        if parent_lane == node_lane:
            continue
        low = min(node_lane, parent_lane)
        high = max(node_lane, parent_lane)
        if low < lane_index <= high:
            left = True
        if low <= lane_index < high:
            right = True

    return GraphCellStyle(
        lane_index=lane_index,
        up=lane_index in active_lanes,
        down=lane_index in outgoing_lanes,
        left=left,
        right=right,
        node=lane_index == node_lane,
    )


def _paint_rectangle(
    pixels: list[float],
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    color: tuple[float, float, float, float],
) -> None:
    size = _ICON_SIZE
    for y in range(max(0, y_min), min(size, y_max)):
        for x in range(max(0, x_min), min(size, x_max)):
            offset = (y * size + x) * 4
            pixels[offset : offset + 4] = color


def _paint_circle(
    pixels: list[float],
    radius: float,
    color: tuple[float, float, float, float],
) -> None:
    center = (_ICON_SIZE - 1) / 2
    radius_squared = radius * radius
    for y in range(_ICON_SIZE):
        for x in range(_ICON_SIZE):
            if (x - center) ** 2 + (y - center) ** 2 > radius_squared:
                continue
            offset = (y * _ICON_SIZE + x) * 4
            pixels[offset : offset + 4] = color


def _render_pixels(style: GraphCellStyle) -> list[float]:
    pixels = [0.0] * (_ICON_SIZE * _ICON_SIZE * 4)
    center = _ICON_SIZE // 2
    lane_color = LANE_COLORS[style.lane_index % len(LANE_COLORS)]
    outline = (0.015, 0.02, 0.03, 0.82)

    def draw_segments(color, half_width: int) -> None:
        if style.up:
            _paint_rectangle(
                pixels,
                center - half_width,
                center + half_width + 1,
                center,
                _ICON_SIZE,
                color,
            )
        if style.down:
            _paint_rectangle(
                pixels,
                center - half_width,
                center + half_width + 1,
                0,
                center + 1,
                color,
            )
        if style.left:
            _paint_rectangle(
                pixels,
                0,
                center + 1,
                center - half_width,
                center + half_width + 1,
                color,
            )
        if style.right:
            _paint_rectangle(
                pixels,
                center,
                _ICON_SIZE,
                center - half_width,
                center + half_width + 1,
                color,
            )

    # A subtle dark edge keeps bright lines visible with either Blender theme.
    draw_segments(outline, 2)
    draw_segments(lane_color, 1)
    if style.node:
        _paint_circle(pixels, 6.2, outline)
        _paint_circle(pixels, 4.7, lane_color)
        _paint_circle(pixels, 1.35, (0.95, 0.97, 1.0, 1.0))
    return pixels


def _owned_images() -> Iterable[bpy.types.Image]:
    images = getattr(bpy.data, "images", None)
    if images is None:
        return
    for image in tuple(images):
        try:
            if bool(image.get(_IMAGE_MARKER, False)):
                yield image
        except (ReferenceError, RuntimeError):
            continue


def register_graph_icons() -> None:
    # Blender exposes restricted bpy.data during add-on registration.  Actual
    # icons are prepared after History data reaches the main thread.
    global _ICON_WARNING_REPORTED
    _IMAGE_CACHE.clear()
    _ICON_WARNING_REPORTED = False


def unregister_graph_icons() -> None:
    _IMAGE_CACHE.clear()
    images = getattr(bpy.data, "images", None)
    if images is None:
        return
    for image in tuple(_owned_images()):
        try:
            images.remove(image)
        except (ReferenceError, RuntimeError):
            pass


def graph_icon_image_count() -> int:
    return sum(1 for _image in _owned_images())


def _ensure_graph_image(style: GraphCellStyle) -> bpy.types.Image | None:
    if style.is_empty:
        return None
    color_index = style.lane_index % len(LANE_COLORS)
    key = (color_index, style.mask)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        try:
            if cached.as_pointer():
                return cached
        except (ReferenceError, RuntimeError):
            _IMAGE_CACHE.pop(key, None)

    name = f".BGM_GitGraph_{color_index}_{style.mask:02x}"
    existing = bpy.data.images.get(name)
    if existing is not None and bool(existing.get(_IMAGE_MARKER, False)):
        _IMAGE_CACHE[key] = existing
        return existing
    image = bpy.data.images.new(
        name=name,
        width=_ICON_SIZE,
        height=_ICON_SIZE,
        alpha=True,
        float_buffer=False,
        is_data=True,
    )
    image[_IMAGE_MARKER] = True
    image.alpha_mode = "STRAIGHT"
    image.pixels.foreach_set(_render_pixels(style))
    image.update()
    _IMAGE_CACHE[key] = image
    return image


def graph_icon_id(style: GraphCellStyle) -> int:
    global _ICON_WARNING_REPORTED
    try:
        image = _ensure_graph_image(style)
        if image is None:
            return 0
        return int(bpy.types.UILayout.icon(image))
    except Exception as exc:
        if not _ICON_WARNING_REPORTED:
            _ICON_WARNING_REPORTED = True
            print(
                "[Blender Git Manager][UI][WARNING] "
                f"Colored graph icons are unavailable: {exc}"
            )
        return 0


def fallback_graph_glyph(style: GraphCellStyle) -> str:
    """Theme-colored fallback used if an RGBA tile cannot be created."""

    if style.node:
        return "●"
    vertical = style.up or style.down
    horizontal = style.left or style.right
    if vertical and horizontal:
        return "┼"
    if vertical:
        return "│"
    if horizontal:
        return "─"
    return ""


def prewarm_graph_icons(items, *, max_lanes: int = 18) -> None:
    """Create the required image previews before Blender redraws the UIList."""

    for item in items:
        lane_count = max(1, int(getattr(item, "graph_lane_count", 1)))
        for lane_index in range(min(lane_count, max_lanes)):
            _ensure_graph_image(graph_cell_style(item, lane_index))

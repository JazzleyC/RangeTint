"""Range Tint 3 for Foundry Nuke/NukeX.

Shows selected frame ranges in a dedicated lane beside Nuke's timeline and
draws a coloured UI rail immediately outside the displayed image frame.

The image is never modified. A read-only native bridge supplies Nuke's exact
Viewer transform; mouse-transparent Qt rails are then placed outside the frame.
"""

from __future__ import division

import ctypes
import os
import re

import nuke

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


VERSION = "3.2.5"
AUTHOR = "JazzleyVFX"
WEBSITE = "https://jazzley.nl"
PREFIX = "range_tint_"
LEGACY_PROCESS_NODE_NAMES = (
    "RANGE_TINT_INPUT",
    "RANGE_TINT_INPUT_V2",
    "RANGE_TINT_INPUT_V21",
    "RANGE_TINT_INPUT_V22",
    "RANGE_TINT_INPUT_V23",
)

DEFAULTS = {
    "ranges": "1001-1100",
    "inside": "#35C878",
    "outside": "#D64F5C",
    "opacity": 0.78,
    "enabled": True,
    # Fixed screen pixels, always painted outside the image rectangle.
    "border": 5,
    "timeline_height": 4,
    # Saved Viewer-relative position of the draggable toggle button.
    "button_x": 12,
    "button_y": 72,
    "shortcut_settings": "Ctrl+Alt+R",
    "shortcut_toggle": "Ctrl+Alt+T",
    "shortcut_refresh": "",
}

_controller = None
_settings_dialog = None
_native_bridge = None
_native_bridge_error = None


def _load_native_bridge():
    """Load the read-only Nuke Viewer transform bridge once."""
    global _native_bridge, _native_bridge_error
    if _native_bridge is not None:
        return _native_bridge
    if _native_bridge_error is not None:
        return None
    path = os.path.join(os.path.dirname(__file__), "bin", "range_tint_native.dll")
    try:
        bridge = ctypes.CDLL(path)
        bridge.range_tint_viewer_transform.argtypes = (
            ctypes.POINTER(ctypes.c_double), ctypes.c_int
        )
        bridge.range_tint_viewer_transform.restype = ctypes.c_int
        _native_bridge = bridge
    except Exception as error:
        _native_bridge_error = str(error)
        nuke.tprint("Range Tint native bridge could not load: {}".format(error))
    return _native_bridge


def _native_frame_rect(canvas):
    """Return the exact displayed format rectangle in Image_Window coordinates."""
    bridge = _load_native_bridge()
    if bridge is None or canvas is None:
        return None
    values = (ctypes.c_double * 16)()
    try:
        if not bridge.range_tint_viewer_transform(values, len(values)):
            return None
    except Exception:
        return None

    # Nuke gives format coordinates for three known Viewer-window points.
    # Invert that affine transform instead of guessing pan/zoom from mouse input.
    m00 = (values[6] - values[4]) / 100.0
    m10 = (values[7] - values[5]) / 100.0
    m01 = (values[8] - values[4]) / 100.0
    m11 = (values[9] - values[5]) / 100.0
    determinant = (m00 * m11) - (m01 * m10)
    if abs(determinant) < 1.0e-12:
        return None

    def format_to_viewer(format_x, format_y):
        dx = float(format_x) - values[4]
        dy = float(format_y) - values[5]
        viewer_x = (m11 * dx - m01 * dy) / determinant
        viewer_y = (-m10 * dx + m00 * dy) / determinant
        # DDImage/OpenGL uses a bottom-left Viewer origin; Qt uses top-left.
        return viewer_x, float(canvas.height()) - viewer_y

    corners = (
        format_to_viewer(values[0], values[1]),
        format_to_viewer(values[2], values[1]),
        format_to_viewer(values[0], values[3]),
        format_to_viewer(values[2], values[3]),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    width, height = right - left, bottom - top
    if not all(abs(value) < 10000000.0 for value in (left, top, width, height)):
        return None
    if width < 0.5 or height < 0.5:
        return None
    return QtCore.QRectF(left, top, width, height)


def parse_ranges(text):
    """Return sorted, merged inclusive integer ranges."""
    result = []
    text = (text or "").strip()
    if not text:
        return result
    for part in re.split(r"[,;\n]+", text):
        part = part.strip()
        match = re.match(r"^(-?\d+)\s*(?:-|\.\.|\s)\s*(-?\d+)$", part)
        if match:
            first, last = int(match.group(1)), int(match.group(2))
        elif re.match(r"^-?\d+$", part):
            first = last = int(part)
        else:
            raise ValueError("Invalid frame range: {!r}".format(part))
        result.append((min(first, last), max(first, last)))

    result.sort()
    merged = []
    for first, last in result:
        if merged and first <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(last, merged[-1][1]))
        else:
            merged.append((first, last))
    return merged


def format_ranges(ranges):
    return ", ".join(
        str(first) if first == last else "{}-{}".format(first, last)
        for first, last in ranges
    )


def _hidden_knob(name, value):
    if isinstance(value, bool):
        knob = nuke.Boolean_Knob(PREFIX + name, "Range Tint " + name)
    elif isinstance(value, float):
        knob = nuke.Double_Knob(PREFIX + name, "Range Tint " + name)
    elif isinstance(value, int):
        knob = nuke.Int_Knob(PREFIX + name, "Range Tint " + name)
    else:
        knob = nuke.String_Knob(PREFIX + name, "Range Tint " + name)
    knob.setFlag(nuke.INVISIBLE)
    knob.setValue(value)
    return knob


def _read_config():
    config = dict(DEFAULTS)
    root = nuke.root()
    for key in DEFAULTS:
        knob = root.knob(PREFIX + key)
        if knob is not None:
            config[key] = knob.value()
    try:
        config["parsed"] = parse_ranges(config["ranges"])
    except ValueError:
        config["parsed"] = []
    return config


def _write_config(config):
    root = nuke.root()
    for key in DEFAULTS:
        value = config.get(key, DEFAULTS[key])
        knob = root.knob(PREFIX + key)
        if knob is None:
            root.addKnob(_hidden_knob(key, value))
        else:
            knob.setValue(value)


def _qcolour(value, opacity=1.0):
    colour = QtGui.QColor(value)
    colour.setAlphaF(max(0.0, min(1.0, float(opacity))))
    return colour


def _widget_text(widget):
    bits = [widget.metaObject().className(), widget.objectName()]
    for attribute in ("windowTitle", "accessibleName", "toolTip"):
        try:
            bits.append(getattr(widget, attribute)())
        except Exception:
            pass
    return " ".join(str(bit) for bit in bits if bit).lower()


def _main_window():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if "nuke" in _widget_text(widget):
            return widget
    return app.activeWindow()


def _all_root_nodes(node_class=None):
    """Return root-level nodes even when the user is currently inside a Group."""
    root = nuke.root()
    root.begin()
    try:
        return list(nuke.allNodes(node_class) if node_class else nuke.allNodes())
    finally:
        root.end()


def _cleanup_legacy_process_nodes():
    """Detach and remove only the Viewer-process nodes made by old versions."""
    for viewer in _all_root_nodes("Viewer"):
        try:
            name_knob = viewer.knob("input_process_node")
            enabled_knob = viewer.knob("input_process")
            if name_knob is not None and str(name_knob.value() or "") in LEGACY_PROCESS_NODE_NAMES:
                name_knob.setValue("VIEWER_INPUT")
                if enabled_knob is not None:
                    enabled_knob.setValue(False)
        except Exception:
            pass

    root = nuke.root()
    root.begin()
    try:
        for name in LEGACY_PROCESS_NODE_NAMES:
            node = nuke.toNode(name)
            if node is not None and node.Class() == "Group" and node.knob("rt_version"):
                nuke.delete(node)
    finally:
        root.end()


def _frame_is_inside(config, frame=None):
    frame = int(nuke.frame() if frame is None else frame)
    return any(first <= frame <= last for first, last in config.get("parsed", []))


def _shortcut_values(config):
    return tuple(
        str(config.get(name, ""))
        for name in ("shortcut_settings", "shortcut_toggle", "shortcut_refresh")
    )


class _TimelineBar(QtWidgets.QWidget):
    def __init__(self, parent, owner_token=None):
        super(_TimelineBar, self).__init__(parent)
        self.config = _read_config()
        self.setObjectName("RangeTintTimelineBar")
        self.setProperty("rangeTintOverlay", True)
        self.setProperty("rangeTintOwner", owner_token)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.show()

    def set_config(self, config):
        self.config = config
        self.setVisible(bool(config["enabled"]))
        self.update()

    def paintEvent(self, event):
        if not self.config.get("enabled"):
            return
        first = int(nuke.root().firstFrame())
        last = int(nuke.root().lastFrame())
        span = max(1, last - first + 1)
        painter = QtGui.QPainter(self)
        painter.setPen(QtCore.Qt.NoPen)
        painter.fillRect(self.rect(), _qcolour(self.config["outside"], self.config["opacity"]))
        painter.setBrush(_qcolour(self.config["inside"], self.config["opacity"]))
        for start, end in self.config["parsed"]:
            start = max(first, start)
            end = min(last, end)
            if end < start:
                continue
            x1 = (start - first) / span * self.width()
            x2 = (end - first + 1) / span * self.width()
            painter.drawRect(QtCore.QRectF(x1, 0, max(1.0, x2 - x1), self.height()))


class _FrameBorderOverlay(QtCore.QObject):
    """Four small solid sibling widgets; no paint layer over Nuke's GL canvas."""
    def __init__(self, parent, owner_token=None):
        super(_FrameBorderOverlay, self).__init__(parent)
        self.host = parent
        self.config = _read_config()
        self.frame_rect = QtCore.QRectF()
        self.canvas_rect = QtCore.QRectF()
        self.canvas_origin = QtCore.QPointF()
        self.exclusion_rects = []
        self.protect_overlay_status = False
        self.current_frame = int(nuke.frame())
        self.rails = []
        for side in ("Top", "Bottom", "Left", "Right"):
            rail = QtWidgets.QWidget(parent)
            rail.setObjectName("RangeTintFrameRail" + side)
            rail.setProperty("rangeTintOverlay", True)
            rail.setProperty("rangeTintOwner", owner_token)
            rail.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            rail.setAutoFillBackground(True)
            rail.hide()
            self.rails.append(rail)

    def set_canvas_geometry(self, origin, rect):
        self.canvas_origin = QtCore.QPointF(origin)
        self.canvas_rect = QtCore.QRectF(rect)

    def set_exclusions(self, rects, protect_overlay_status=False):
        """Cut host controls out of the rails instead of drawing over them."""
        self.exclusion_rects = [QtCore.QRect(rect) for rect in rects if not rect.isEmpty()]
        self.protect_overlay_status = bool(protect_overlay_status)
        self._layout_rails()

    def set_state(self, config, frame_rect, frame):
        self.config = config
        self.frame_rect = QtCore.QRectF(frame_rect)
        self.current_frame = int(frame)
        self._layout_rails()

    def _layout_rails(self):
        if (not self.config.get("enabled") or self.frame_rect.isEmpty()
                or self.canvas_rect.isEmpty()):
            self.hide()
            return

        width = max(1, int(self.config.get("border", 5)))
        rect = self.frame_rect.translated(self.canvas_origin)
        colour_key = "inside" if _frame_is_inside(self.config, self.current_frame) else "outside"
        colour = QtGui.QColor(self.config[colour_key])
        clip = self.canvas_rect.toAlignedRect()
        clip_left = clip.x()
        clip_top = clip.y()
        clip_right = clip.x() + clip.width()
        clip_bottom = clip.y() + clip.height()

        def clamp(value, minimum, maximum):
            return max(minimum, min(maximum, int(round(value))))

        def clipped_span(start, end, minimum, maximum):
            if end <= minimum:
                return minimum, min(maximum, minimum + width)
            if start >= maximum:
                return max(minimum, maximum - width), maximum
            clipped_start = clamp(start, minimum, maximum)
            clipped_end = clamp(end, minimum, maximum)
            if clipped_end <= clipped_start:
                clipped_end = min(maximum, clipped_start + width)
            return clipped_start, clipped_end

        # When an image edge is outside the visible Viewer, retain a small
        # indicator at the nearest safe canvas edge. When it is visible, the
        # rail remains completely outside the image.
        if rect.left() > clip_left:
            left = clamp(rect.left() - width, clip_left, clip_right - 1)
            left_width = max(1, min(width, int(round(rect.left())) - left))
        else:
            left, left_width = clip_left, width

        if rect.top() > clip_top:
            top = clamp(rect.top() - width, clip_top, clip_bottom - 1)
            top_height = max(1, min(width, int(round(rect.top())) - top))
        else:
            top, top_height = clip_top, width

        if rect.right() < clip_right:
            right = clamp(rect.right(), clip_left, clip_right - 1)
            right_width = max(1, min(width, clip_right - right))
        else:
            right, right_width = clip_right - width, width

        if rect.bottom() < clip_bottom:
            bottom = clamp(rect.bottom(), clip_top, clip_bottom - 1)
            bottom_height = max(1, min(width, clip_bottom - bottom))
        else:
            bottom, bottom_height = clip_bottom - width, width
        horizontal_left, horizontal_right = clipped_span(
            rect.left() - width, rect.right() + width, clip_left, clip_right
        )
        vertical_top, vertical_bottom = clipped_span(
            rect.top(), rect.bottom(), clip_top, clip_bottom
        )
        rail_rects = (
            QtCore.QRect(horizontal_left, top, horizontal_right - horizontal_left, top_height),
            QtCore.QRect(horizontal_left, bottom, horizontal_right - horizontal_left, bottom_height),
            QtCore.QRect(left, vertical_top, left_width, vertical_bottom - vertical_top),
            QtCore.QRect(right, vertical_top, right_width, vertical_bottom - vertical_top),
        )
        exclusions = list(self.exclusion_rects)
        if self.protect_overlay_status:
            # Nuke renders the red "Overlay Off" notice directly into the GL
            # Viewer, so it cannot be discovered as a QWidget. Leave a short
            # gap only in the upper part of the left rail while that notice is
            # present. The top rail remains outside the displayed image.
            status_width = max(96, self.host.fontMetrics().horizontalAdvance("Overlay Off") + 18)
            status_height = max(22, self.host.fontMetrics().height() + 8)
            exclusions.append(
                QtCore.QRect(
                    left - status_width,
                    vertical_top,
                    status_width + left_width + 3,
                    status_height,
                )
            )
        for rail, rail_rect in zip(self.rails, rail_rects):
            visible_rect = rail_rect.intersected(clip)
            if visible_rect.isEmpty():
                rail.hide()
                continue
            palette = rail.palette()
            palette.setColor(QtGui.QPalette.Window, colour)
            rail.setPalette(palette)
            rail.setGeometry(visible_rect)
            mask = QtGui.QRegion(QtCore.QRect(0, 0, visible_rect.width(), visible_rect.height()))
            for exclusion in exclusions:
                overlap = visible_rect.intersected(exclusion)
                if not overlap.isEmpty():
                    local_overlap = overlap.translated(-visible_rect.x(), -visible_rect.y())
                    mask = mask.subtracted(QtGui.QRegion(local_overlap))
            if mask.isEmpty():
                rail.hide()
                continue
            rail.setMask(mask)
            rail.show()
            rail.raise_()

    def show(self):
        self._layout_rails()

    def hide(self):
        for rail in self.rails:
            rail.hide()

    def raise_(self):
        for rail in self.rails:
            if rail.isVisible():
                rail.raise_()

    def deleteLater(self):
        for rail in self.rails:
            rail.hide()
            rail.deleteLater()
        self.rails[:] = []
        super(_FrameBorderOverlay, self).deleteLater()


def _global_mouse_pos(event):
    """Return a QPoint on both PySide2 and PySide6."""
    try:
        return event.globalPosition().toPoint()
    except AttributeError:
        return event.globalPos()


class _MovableToggle(QtWidgets.QPushButton):
    """A normal click button that can also be dragged out of the way."""
    def __init__(self, owner, parent):
        super(_MovableToggle, self).__init__(parent)
        self.owner = owner
        self.is_dragging = False
        self._did_move = False
        self._press_global = QtCore.QPoint()
        self._press_local = QtCore.QPoint()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.is_dragging = True
            self._did_move = False
            self._press_global = _global_mouse_pos(event)
            self._press_local = self.pos()
        super(_MovableToggle, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() & QtCore.Qt.LeftButton:
            delta = _global_mouse_pos(event) - self._press_global
            if delta.manhattanLength() >= 4:
                self._did_move = True
                proposed = self._press_local + delta
                parent = self.parentWidget()
                x = max(4, min(parent.width() - self.width() - 4, proposed.x()))
                y = max(32, min(parent.height() - self.height() - 4, proposed.y()))
                self.move(x, y)
                self.owner.update_border_exclusions()
                event.accept()
                return
        super(_MovableToggle, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        moved = self.is_dragging and self._did_move
        self.is_dragging = False
        if moved and event.button() == QtCore.Qt.LeftButton:
            self.setDown(False)
            self.owner.save_button_position()
            event.accept()
            return
        super(_MovableToggle, self).mouseReleaseEvent(event)


class _ViewerUI(QtCore.QObject):
    """Viewer-local border, movable toggle and non-obscuring timeline lane."""

    def __init__(self, target, owner_token=None):
        super(_ViewerUI, self).__init__(target)
        self.target = target
        self.owner_token = owner_token
        self.config = _read_config()
        self.canvas = None
        self.frame_rect = QtCore.QRectF()
        self._sync_scheduled = False

        self.timeline_host = self._find_timeline_host()
        timeline_parent = self.timeline_host.parentWidget() if self.timeline_host else target
        self.timeline = _TimelineBar(timeline_parent, owner_token)

        initial_canvas = self._find_canvas()
        # Never parent a QWidget into Nuke's OpenGL Image_Window. Nuke 14 can
        # sample child widgets back into its Viewer buffer, producing recursive
        # feedback. The overlay is a Viewer_Window sibling whose geometry is
        # mapped exactly onto the canvas instead.
        self.frame_border = _FrameBorderOverlay(target, owner_token)
        self.frame_border.hide()
        if initial_canvas is not None:
            self._attach_canvas(initial_canvas)

        self.button = _MovableToggle(self, target)
        self.button.setObjectName("RangeTintToggle")
        self.button.setProperty("rangeTintOverlay", True)
        self.button.setProperty("rangeTintOwner", owner_token)
        self.button.setCursor(QtCore.Qt.SizeAllCursor)
        self.button.setToolTip("Drag to move. Click to toggle Range Tint.")
        self.button.clicked.connect(toggle)
        self.button.show()
        self.sync_geometry()

    def _find_canvas(self):
        candidates = []
        for widget in self.target.findChildren(QtWidgets.QWidget):
            try:
                if widget.metaObject().className() == "Image_Window" and widget.width() > 100:
                    candidates.append(widget)
            except RuntimeError:
                pass
        return max(candidates, key=lambda widget: widget.width() * widget.height()) if candidates else None

    def _find_timeline_host(self):
        candidates = []
        for widget in self.target.findChildren(QtWidgets.QWidget):
            try:
                class_name = widget.metaObject().className().lower()
                if "timeslider" in class_name and widget.width() >= 300:
                    candidates.append(widget)
            except RuntimeError:
                pass
        return max(candidates, key=lambda widget: widget.width()) if candidates else None

    def _attach_canvas(self, canvas):
        if self.canvas is canvas:
            return
        if self.canvas is not None:
            try:
                self.canvas.removeEventFilter(self)
            except RuntimeError:
                pass
        self.canvas = canvas
        self.canvas.installEventFilter(self)
        self._position_border_over_canvas()
        self.frame_border.show()
        self.frame_rect = QtCore.QRectF()

    def eventFilter(self, watched, event):
        if watched is not self.canvas:
            return False
        try:
            if event.type() in (
                QtCore.QEvent.MouseMove,
                QtCore.QEvent.MouseButtonPress,
                QtCore.QEvent.MouseButtonRelease,
                QtCore.QEvent.Wheel,
                QtCore.QEvent.KeyPress,
                QtCore.QEvent.Resize,
                QtCore.QEvent.Show,
            ):
                self._schedule_sync()
        except (AttributeError, RuntimeError, TypeError):
            pass
        return False

    def _schedule_sync(self):
        if self._sync_scheduled:
            return
        self._sync_scheduled = True
        QtCore.QTimer.singleShot(0, self._run_scheduled_sync)

    def _run_scheduled_sync(self):
        self._sync_scheduled = False
        try:
            self.sync_geometry()
        except RuntimeError:
            pass

    def _sync_canvas_rect(self):
        if self.canvas is None:
            return
        self._position_border_over_canvas()

    def _position_border_over_canvas(self):
        if self.canvas is None:
            return
        origin = self.canvas.mapTo(self.target, QtCore.QPoint(0, 0))
        left = float(origin.x())
        top = float(origin.y() + max(32, self.target.fontMetrics().height() + 16))
        right = float(origin.x() + self.canvas.width())
        bottom = float(origin.y() + self.canvas.height())

        # Nuke's Viewer tool palette is made of either one narrow container or
        # several small tool buttons. Keep the fallback indicator to its right.
        # Some Nuke layouts already place Image_Window to the right of this
        # palette. Start at the real canvas origin and add an inset only when
        # actual vertically stacked tools overlap that origin.
        palette_right = origin.x()
        small_tools = 0
        tall_tools = 0
        for widget in self.target.findChildren(QtWidgets.QWidget):
            try:
                if widget is self.canvas or widget.property("rangeTintOverlay") or not widget.isVisible():
                    continue
                widget_origin = widget.mapTo(self.target, QtCore.QPoint(0, 0))
                widget_right = widget_origin.x() + widget.width()
                near_left = origin.x() - 4 <= widget_origin.x() <= origin.x() + 48
                overlaps_canvas = (
                    widget_origin.y() < origin.y() + self.canvas.height()
                    and widget_origin.y() + widget.height() > top
                )
                if not near_left or not overlaps_canvas:
                    continue
                if 14 <= widget.width() <= 80 and 14 <= widget.height() <= 80:
                    small_tools += 1
                    palette_right = max(palette_right, widget_right + 4)
                elif widget.width() <= 96 and widget.height() >= 100:
                    tall_tools += 1
                    palette_right = max(palette_right, widget_right + 4)
            except RuntimeError:
                pass
        if small_tools >= 2 or tall_tools:
            left = max(left, float(palette_right))

        # Detect wide native header/ruler rows instead of relying exclusively
        # on a fixed inset. This remains stable across UI scaling and layouts.
        for widget in self.target.findChildren(QtWidgets.QWidget):
            try:
                if widget is self.canvas or widget.property("rangeTintOverlay"):
                    continue
                if not widget.isVisible() or widget.width() < self.canvas.width() * 0.55:
                    continue
                if widget.height() < 4 or widget.height() > 64:
                    continue
                widget_origin = widget.mapTo(self.target, QtCore.QPoint(0, 0))
                if origin.y() <= widget_origin.y() <= origin.y() + 120:
                    top = max(top, float(widget_origin.y() + widget.height()))
            except RuntimeError:
                pass

        # Keep the border above Nuke's status line and TimeSlider when those
        # widgets are part of the same Viewer_Window hierarchy.
        timeline = self._find_timeline_host()
        if timeline is not None:
            timeline_top = timeline.mapTo(self.target, QtCore.QPoint(0, 0)).y()
            status_height = max(18, self.target.fontMetrics().height() + 6)
            bottom = min(bottom, float(timeline_top - status_height))

        if right > left and bottom > top:
            self.frame_border.set_canvas_geometry(
                QtCore.QPointF(float(origin.x()), float(origin.y())),
                QtCore.QRectF(left, top, right - left, bottom - top)
            )
        else:
            self.frame_border.set_canvas_geometry(QtCore.QPointF(), QtCore.QRectF())
        self.update_border_exclusions()

    def update_border_exclusions(self):
        exclusions = []
        if hasattr(self, "button") and self.button.isVisible():
            exclusions.append(self.button.geometry().adjusted(-5, -5, 5, 5))
        protect_overlay_status = False
        try:
            viewer = nuke.activeViewer()
            protect_overlay_status = viewer is not None and not viewer.isOverlayShown()
        except (AttributeError, RuntimeError):
            pass
        self.frame_border.set_exclusions(exclusions, protect_overlay_status)

    def _sync_timeline(self):
        # A narrow strip lives inside the bottom edge of TimeSlider, where it
        # cannot cover tick labels or frame numbers. Lowering it keeps native
        # TimeSlider child widgets (including the playhead) above the strip.
        band_height = max(1, min(4, int(self.config.get("timeline_height", 3))))
        host = self._find_timeline_host()
        if host is None:
            self.timeline.hide()
            return

        if self.timeline.parentWidget() is not host:
            self.timeline.setParent(host)
        self.timeline_host = host
        self.timeline.setGeometry(0, max(0, host.height() - band_height), host.width(), band_height)
        self.timeline.setVisible(bool(self.config.get("enabled")))
        self.timeline.lower()

    def _update_border(self):
        if self.canvas is None:
            return
        self.frame_border.set_state(self.config, self.frame_rect, nuke.frame())
        self.frame_border.raise_()

    def sync_geometry(self):
        canvas = self._find_canvas()
        if canvas is not None and canvas is not self.canvas:
            self._attach_canvas(canvas)
        width, height = self.target.width(), self.target.height()
        if not self.button.is_dragging:
            button_width, button_height = 88, 24
            x = max(4, min(width - button_width - 4, int(self.config.get("button_x", 12))))
            y = max(32, min(height - button_height - 4, int(self.config.get("button_y", 72))))
            self.button.setGeometry(x, y, button_width, button_height)

        self._sync_canvas_rect()
        native_rect = _native_frame_rect(self.canvas)
        self.frame_rect = native_rect if native_rect is not None else QtCore.QRectF()
        self._sync_timeline()
        self._update_border()
        self.button.raise_()

    def save_button_position(self):
        config = _read_config()
        config["button_x"] = int(self.button.x())
        config["button_y"] = int(self.button.y())
        _write_config(config)
        self.config.update(config)

    def set_config(self, config):
        self.config = config
        self.timeline.set_config(config)
        if config["enabled"]:
            self.button.setText("RANGE ON")
            colour, border = "#276B43", "#55D88B"
        else:
            self.button.setText("RANGE OFF")
            colour, border = "#5A3035", "#D64F5C"
        self.button.setStyleSheet(
            "QPushButton { background:%s; color:white; border:1px solid %s; "
            "border-radius:3px; font-weight:bold; padding:2px 6px; }"
            "QPushButton:hover { background:#3C4D55; }" % (colour, border)
        )
        self.button.setVisible(True)
        self.sync_geometry()

    def deleteLater(self):
        if self.canvas is not None:
            try:
                self.canvas.removeEventFilter(self)
            except RuntimeError:
                pass
        for widget in (self.timeline, self.frame_border, self.button):
            try:
                widget.hide()
                widget.deleteLater()
            except RuntimeError:
                pass
        super(_ViewerUI, self).deleteLater()


class _Controller(QtCore.QObject):
    def __init__(self):
        super(_Controller, self).__init__()
        self.owner_token = "{}:{}".format(VERSION, id(self))
        self.config = _read_config()
        self.viewer_uis = []
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(100)
        self.scan_timer = QtCore.QTimer(self)
        self.scan_timer.timeout.connect(self.scan)
        self.scan_timer.start(1500)
        QtCore.QTimer.singleShot(0, self.scan)

    def _scan_viewer_widgets(self):
        existing = set()
        alive = []
        for ui in self.viewer_uis:
            try:
                existing.add(id(ui.target))
                alive.append(ui)
            except RuntimeError:
                pass
        self.viewer_uis = alive

        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        for widget in app.allWidgets():
            try:
                if widget.property("rangeTintOverlay") or not widget.isVisible():
                    continue
                if widget.metaObject().className() != "Viewer_Window":
                    continue
                if widget.width() < 300 or widget.height() < 180 or id(widget) in existing:
                    continue
                ui = _ViewerUI(widget, self.owner_token)
                ui.set_config(self.config)
                self.viewer_uis.append(ui)
                existing.add(id(widget))
            except RuntimeError:
                pass

    def scan(self):
        _remove_old_qt_overlays(self.owner_token)
        self._scan_viewer_widgets()

    def apply_state(self):
        previous_shortcuts = _shortcut_values(self.config)
        self.config = _read_config()
        if _shortcut_values(self.config) != previous_shortcuts:
            register_menu()
        self.scan()
        for ui in list(self.viewer_uis):
            try:
                ui.set_config(self.config)
            except RuntimeError:
                self.viewer_uis.remove(ui)

    def update(self):
        config = _read_config()
        if config != self.config:
            self.apply_state()
            return
        for ui in list(self.viewer_uis):
            try:
                ui.sync_geometry()
                ui.timeline.update()
            except RuntimeError:
                self.viewer_uis.remove(ui)

    def stop(self):
        self.timer.stop()
        self.scan_timer.stop()
        for ui in self.viewer_uis:
            try:
                ui.deleteLater()
            except RuntimeError:
                pass
        self.viewer_uis[:] = []


class _ColourButton(QtWidgets.QPushButton):
    colourChanged = QtCore.Signal()

    def __init__(self, colour, parent=None):
        super(_ColourButton, self).__init__(parent)
        self.colour = QtGui.QColor(colour)
        self.clicked.connect(self.choose)
        self._update_style()

    def _update_style(self):
        self.setText(self.colour.name().upper())
        self.setStyleSheet(
            "QPushButton { background:%s; color:white; font-weight:bold; padding:5px; }"
            % self.colour.name()
        )

    def choose(self):
        colour = QtWidgets.QColorDialog.getColor(self.colour, self, "Choose color")
        if colour.isValid():
            self.colour = colour
            self._update_style()
            self.colourChanged.emit()


class _SingleShortcutEdit(QtWidgets.QKeySequenceEdit):
    """QKeySequenceEdit restricted to exactly one key combination."""

    _NAVIGATION_KEYS = {
        int(QtCore.Qt.Key_Space),
        int(QtCore.Qt.Key_Left),
        int(QtCore.Qt.Key_Right),
        int(QtCore.Qt.Key_Up),
        int(QtCore.Qt.Key_Down),
        int(QtCore.Qt.Key_Home),
        int(QtCore.Qt.Key_End),
        int(QtCore.Qt.Key_PageUp),
        int(QtCore.Qt.Key_PageDown),
        int(QtCore.Qt.Key_Insert),
    }

    def __init__(self, sequence=None, parent=None):
        super(_SingleShortcutEdit, self).__init__(parent)
        sequence = QtGui.QKeySequence(sequence or "")
        if sequence.count():
            sequence = QtGui.QKeySequence(sequence[0])
        if sequence and not self._sequence_is_allowed(sequence):
            sequence = QtGui.QKeySequence()
        self.setKeySequence(sequence)

    @staticmethod
    def _portable_text(sequence):
        try:
            return sequence.toString(QtGui.QKeySequence.PortableText)
        except AttributeError:
            return sequence.toString(
                QtGui.QKeySequence.SequenceFormat.PortableText
            )

    @classmethod
    def _sequence_is_allowed(cls, sequence):
        text = cls._portable_text(sequence)
        if not text:
            return True
        key_name = text.split("+")[-1].strip()
        if re.match(r"^[A-Z0-9]$", key_name, re.IGNORECASE):
            return True
        if re.match(r"^F(?:[1-9]|[12][0-9]|3[0-5])$", key_name, re.IGNORECASE):
            return True
        return key_name.lower() in {
            "space", "left", "right", "up", "down", "home", "end",
            "pgup", "pgdown", "pageup", "pagedown", "ins", "insert",
        }

    @classmethod
    def _physical_key(cls, event):
        # Windows reports Ctrl+Alt as AltGr on some keyboard layouts. Use the
        # native virtual key for letters/digits so R can never become ®.
        native_key = int(event.nativeVirtualKey())
        if 0x41 <= native_key <= 0x5A:
            return int(QtCore.Qt.Key_A) + (native_key - 0x41)
        if 0x30 <= native_key <= 0x39:
            return int(QtCore.Qt.Key_0) + (native_key - 0x30)

        key = int(event.key())
        if int(QtCore.Qt.Key_F1) <= key <= int(QtCore.Qt.Key_F35):
            return key
        if key in cls._NAVIGATION_KEYS:
            return key
        return None

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        modifier_keys = (
            QtCore.Qt.Key_Control,
            QtCore.Qt.Key_Shift,
            QtCore.Qt.Key_Alt,
            QtCore.Qt.Key_Meta,
        )
        if key in modifier_keys:
            event.accept()
            return
        if key in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete) and not modifiers:
            self.clear()
            event.accept()
            return
        if key == QtCore.Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return

        physical_key = self._physical_key(event)
        if physical_key is None:
            QtWidgets.QApplication.beep()
            self.setToolTip(
                "Use one letter, number, function key, or navigation key."
            )
            event.accept()
            return

        modifier_mask = (
            int(QtCore.Qt.ControlModifier)
            | int(QtCore.Qt.ShiftModifier)
            | int(QtCore.Qt.AltModifier)
            | int(QtCore.Qt.MetaModifier)
        )
        sequence = QtGui.QKeySequence(
            (int(modifiers) & modifier_mask) | physical_key
        )
        self.setKeySequence(sequence)
        self.setToolTip(
            "Click the field and press one key combination. "
            "Press Backspace or Delete to clear it."
        )
        event.accept()


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Range Tint {}".format(VERSION))
        self.setMinimumWidth(470)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        config = _read_config()
        self.original_config = {key: config[key] for key in DEFAULTS}

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "The border is placed outside the displayed image using Nuke's native "
            "Viewer transform. It follows pan, zoom, fit and Viewer resizing and "
            "is never included in renders."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QtWidgets.QFormLayout()
        self.ranges = QtWidgets.QLineEdit(config["ranges"])
        self.ranges.setPlaceholderText("1001-1050, 1075-1100")
        form.addRow("Frame ranges", self.ranges)

        range_buttons = QtWidgets.QHBoxLayout()
        project = QtWidgets.QPushButton("Project range")
        project.clicked.connect(self.use_project_range)
        selected = QtWidgets.QPushButton("Selected node")
        selected.clicked.connect(self.use_selected_node)
        range_buttons.addWidget(project)
        range_buttons.addWidget(selected)
        form.addRow("", range_buttons)

        self.inside = _ColourButton(config["inside"])
        self.outside = _ColourButton(config["outside"])
        form.addRow("Inside range", self.inside)
        form.addRow("Outside range", self.outside)

        self.border = QtWidgets.QSpinBox()
        self.border.setRange(1, 30)
        self.border.setSuffix(" px")
        self.border.setValue(int(config["border"]))
        self.border.setToolTip("Screen pixels, always outside the image")
        form.addRow("Border thickness", self.border)

        self.opacity = QtWidgets.QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setValue(int(float(config["opacity"]) * 100))
        form.addRow("Timeline opacity", self.opacity)

        self.timeline_height = QtWidgets.QSpinBox()
        self.timeline_height.setRange(1, 4)
        self.timeline_height.setSuffix(" px")
        self.timeline_height.setValue(int(config["timeline_height"]))
        form.addRow("Timeline band", self.timeline_height)

        shortcut_heading = QtWidgets.QLabel("<b>Keyboard shortcuts</b>")
        form.addRow(shortcut_heading)
        self.shortcut_settings = _SingleShortcutEdit(
            QtGui.QKeySequence(str(config["shortcut_settings"]))
        )
        self.shortcut_toggle = _SingleShortcutEdit(
            QtGui.QKeySequence(str(config["shortcut_toggle"]))
        )
        self.shortcut_refresh = _SingleShortcutEdit(
            QtGui.QKeySequence(str(config["shortcut_refresh"]))
        )
        shortcut_tip = (
            "Press one letter, number, function key, or navigation key, with "
            "optional modifiers. Press Backspace or Delete to clear it."
        )
        for editor in (
            self.shortcut_settings, self.shortcut_toggle, self.shortcut_refresh
        ):
            editor.setToolTip(shortcut_tip)
        form.addRow("Open settings", self.shortcut_settings)
        form.addRow("Toggle overlay", self.shortcut_toggle)
        form.addRow("Refresh Viewers", self.shortcut_refresh)

        self.button_x = int(config.get("button_x", DEFAULTS["button_x"]))
        self.button_y = int(config.get("button_y", DEFAULTS["button_y"]))
        reset_button = QtWidgets.QPushButton("Reset Viewer button position")
        reset_button.setToolTip("The Viewer button can also be dragged directly.")
        reset_button.clicked.connect(self.reset_button_position)
        form.addRow("Viewer button", reset_button)

        self.enabled = QtWidgets.QPushButton()
        self.enabled.setCheckable(True)
        self.enabled.setChecked(bool(config["enabled"]))
        self.enabled.setMinimumHeight(36)
        self.enabled.toggled.connect(self._enabled_toggled)
        self._style_enabled()
        form.addRow("Enabled", self.enabled)
        layout.addLayout(form)

        note = QtWidgets.QLabel(
            "The timeline track is a thin strip at the bottom of Nuke's TimeSlider. "
            "Frame numbers and tick labels remain unobstructed."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#AEB7BD;")
        layout.addWidget(note)

        credits = QtWidgets.QLabel(
            'Created by <a href="{}">{}</a>'.format(WEBSITE, AUTHOR)
        )
        credits.setOpenExternalLinks(True)
        credits.setTextFormat(QtCore.Qt.RichText)
        credits.setStyleSheet("color:#AEB7BD;")
        layout.addWidget(credits)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.ranges.editingFinished.connect(self.preview)
        self.inside.colourChanged.connect(self.preview)
        self.outside.colourChanged.connect(self.preview)
        self.border.valueChanged.connect(self.preview)
        self.opacity.valueChanged.connect(self.preview)
        self.timeline_height.valueChanged.connect(self.preview)

    def _style_enabled(self):
        if self.enabled.isChecked():
            self.enabled.setText("OVERLAY ON - click to disable")
            colour, border = "#276B43", "#55D88B"
        else:
            self.enabled.setText("OVERLAY OFF - click to enable")
            colour, border = "#5A3035", "#D64F5C"
        self.enabled.setStyleSheet(
            "QPushButton { background:%s; color:white; border:1px solid %s; "
            "border-radius:4px; font-weight:bold; padding:7px; }" % (colour, border)
        )

    def _enabled_toggled(self, *args):
        self._style_enabled()
        self.preview()

    def use_project_range(self):
        self.ranges.setText("{}-{}".format(nuke.root().firstFrame(), nuke.root().lastFrame()))
        self.preview()

    def use_selected_node(self):
        try:
            node = nuke.selectedNode()
            self.ranges.setText("{}-{}".format(int(node.firstFrame()), int(node.lastFrame())))
            self.preview()
        except Exception:
            nuke.message("Select a node with a valid frame range first.")

    def reset_button_position(self):
        self.button_x = DEFAULTS["button_x"]
        self.button_y = DEFAULTS["button_y"]
        self.preview()

    def current_config(self, show_error=False):
        try:
            ranges = parse_ranges(self.ranges.text())
        except ValueError as error:
            if show_error:
                nuke.message(str(error))
            return None
        shortcut_settings = self.shortcut_settings.keySequence().toString()
        shortcut_toggle = self.shortcut_toggle.keySequence().toString()
        shortcut_refresh = self.shortcut_refresh.keySequence().toString()
        assigned = [
            shortcut for shortcut in (
                shortcut_settings, shortcut_toggle, shortcut_refresh
            ) if shortcut
        ]
        if len(assigned) != len(set(assigned)):
            if show_error:
                nuke.message("Each Range Tint action must use a different shortcut.")
            return None
        return {
            "ranges": format_ranges(ranges),
            "inside": self.inside.colour.name().upper(),
            "outside": self.outside.colour.name().upper(),
            "opacity": self.opacity.value() / 100.0,
            "enabled": self.enabled.isChecked(),
            "border": self.border.value(),
            "timeline_height": self.timeline_height.value(),
            "button_x": self.button_x,
            "button_y": self.button_y,
            "shortcut_settings": shortcut_settings,
            "shortcut_toggle": shortcut_toggle,
            "shortcut_refresh": shortcut_refresh,
        }

    def preview(self, *args):
        config = self.current_config(False)
        if config is None:
            return
        _write_config(config)
        if _controller is not None:
            _controller.apply_state()

    def save(self):
        config = self.current_config(True)
        if config is None:
            return
        _write_config(config)
        if _controller is not None:
            _controller.apply_state()
        else:
            register_menu()
        self.accept()

    def reject(self):
        _write_config(self.original_config)
        if _controller is not None:
            _controller.apply_state()
        super(SettingsDialog, self).reject()


def show_settings():
    global _settings_dialog
    if _settings_dialog is None:
        _settings_dialog = SettingsDialog(_main_window())
        _settings_dialog.destroyed.connect(_clear_settings_dialog)
    _settings_dialog.show()
    _settings_dialog.raise_()
    _settings_dialog.activateWindow()


def _clear_settings_dialog(*args):
    global _settings_dialog
    _settings_dialog = None


def toggle():
    if _controller is None:
        config = _read_config()
        config["enabled"] = True
        _write_config(config)
        install()
        nuke.tprint("Range Tint: on")
        return
    config = _read_config()
    config["enabled"] = not bool(config["enabled"])
    _write_config(config)
    if _controller is not None:
        _controller.apply_state()
    nuke.tprint("Range Tint: {}".format("on" if config["enabled"] else "off"))


def refresh():
    if _controller is not None:
        _controller.apply_state()


def diagnostics():
    """Print concise native tracking state for troubleshooting."""
    lines = [
        "Range Tint {} diagnostics".format(VERSION),
        "Native bridge: {}".format("loaded" if _load_native_bridge() else _native_bridge_error),
        "Controller: {}".format("running" if _controller is not None else "stopped"),
    ]
    if _controller is not None:
        for index, ui in enumerate(list(_controller.viewer_uis), 1):
            try:
                rect = _native_frame_rect(ui.canvas)
                lines.append(
                    "Viewer {}: canvas={}x{}, frame={}".format(
                        index,
                        ui.canvas.width() if ui.canvas else 0,
                        ui.canvas.height() if ui.canvas else 0,
                        "{:.1f},{:.1f} {:.1f}x{:.1f}".format(
                            rect.x(), rect.y(), rect.width(), rect.height()
                        ) if rect is not None else "unavailable",
                    )
                )
            except RuntimeError:
                lines.append("Viewer {}: closed".format(index))
    message = "\n".join(lines)
    nuke.tprint(message)
    return message


def stop():
    global _controller
    if _controller is not None:
        _controller.stop()
        _controller.deleteLater()
        _controller = None
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app._range_tint_controllers = []
    nuke.tprint("Range Tint stopped; Viewer overlays removed.")


def _remove_old_qt_overlays(keep_owner=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        try:
            if (
                widget.property("rangeTintOverlay")
                and str(widget.property("rangeTintOwner") or "") != str(keep_owner or "")
            ):
                widget.hide()
                widget.deleteLater()
        except RuntimeError:
            pass


def _stop_registered_controllers():
    """Stop controllers kept alive by earlier module reloads."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    controllers = list(getattr(app, "_range_tint_controllers", []))
    for controller in controllers:
        try:
            controller.stop()
            controller.deleteLater()
        except (AttributeError, RuntimeError):
            pass
    app._range_tint_controllers = []


def _add_shortcut_command(menu, label, callback, shortcut):
    shortcut = str(shortcut or "").strip()
    sequence = QtGui.QKeySequence(shortcut)
    if sequence.count():
        sequence = QtGui.QKeySequence(sequence[0])
        shortcut = sequence.toString()
        if not _SingleShortcutEdit._sequence_is_allowed(sequence):
            nuke.tprint(
                "Range Tint cleared unsupported shortcut {!r} for {}.".format(
                    shortcut, label
                )
            )
            shortcut = ""
    try:
        return menu.addCommand(label, callback, shortcut)
    except Exception as error:
        nuke.tprint(
            "Range Tint ignored shortcut {!r} for {}: {}".format(
                shortcut, label, error
            )
        )
        return menu.addCommand(label, callback)


def register_menu():
    config = _read_config()
    main = nuke.menu("Nuke")
    try:
        main.removeItem("Range Tint")
    except Exception:
        pass
    menu = main.addMenu("Range Tint")
    menu.addCommand("Start", install)
    _add_shortcut_command(
        menu, "Settings...", show_settings, config["shortcut_settings"]
    )
    _add_shortcut_command(menu, "Toggle", toggle, config["shortcut_toggle"])
    _add_shortcut_command(
        menu, "Refresh Viewers", refresh, config["shortcut_refresh"]
    )
    menu.addCommand("Diagnostics", diagnostics)
    menu.addSeparator()
    menu.addCommand("Stop", stop)

    viewer_menu = nuke.menu("Viewer")
    try:
        viewer_menu.removeItem("Range Tint")
    except Exception:
        pass
    viewer_menu.addCommand("Range Tint/Start", install)
    viewer_menu.addCommand("Range Tint/Settings...", show_settings)
    viewer_menu.addCommand("Range Tint/Toggle", toggle)
    viewer_menu.addCommand("Range Tint/Diagnostics", diagnostics)
    viewer_menu.addCommand("Range Tint/Stop", stop)


def install():
    global _controller
    if not nuke.GUI:
        return
    register_menu()
    _stop_registered_controllers()
    _remove_old_qt_overlays()
    if _controller is not None:
        _controller.stop()
        _controller.deleteLater()
    _cleanup_legacy_process_nodes()
    _controller = _Controller()
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app._range_tint_controllers = [_controller]
    bridge_status = "native Viewer tracking" if _load_native_bridge() else "timeline only"
    nuke.tprint("Range Tint {} active ({}).".format(VERSION, bridge_status))

# WARNING: automatic patch fallback used
"""
ViaFence - Place via fence along selected tracks
For KiCad 9.0+ (SWIG API for compatibility with wx dialogs)
"""
# Copyright 2026 ozzy_sv https://github.com/ozzysv
#
# original plugin         https://github.com/ozzysv/ViaFence
#
# GPL-3.0 license

import json
import math
import os

import wx
import wx.adv
import pcbnew


# ============================================================================
# Configuration
# ============================================================================

class ViaFenceConfig:
    """Configuration for via fence placement"""
    def __init__(self, spacing_mm=1.0, track_to_via_gap_mm=0.25, 
                 via_diameter_mm=0.6, via_drill_mm=0.3, 
                 staggered=False, net_name="",
                 show_stats=True, units="mm",
                 window_pos_x=None, window_pos_y=None):
        # spacing_mm is kept as the saved/backward-compatible track spacing value.
        self.spacing_mm = spacing_mm
        self.track_to_via_gap_mm = track_to_via_gap_mm
        self.via_diameter_mm = via_diameter_mm
        self.via_drill_mm = via_drill_mm
        self.staggered = staggered
        self.net_name = net_name
        self.show_stats = show_stats
        self.units = units if units in ("mm", "mils") else "mm"
        self.window_pos_x = window_pos_x
        self.window_pos_y = window_pos_y


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "via_fence_cfg.json")
VIA_TIMESTAMP = 55  # Special timestamp to identify vias created by this plugin
PLUGIN_VERSION = "1.1.0"
# Unified placement engine: TRACK, ARC and PAD contours all use the same
# continuous-path / XY-spacing logic.  The former separate pad-ring placement
# and the separate "Via spacing pads" parameter have been removed.
MM_PER_MIL = 0.0254

# ============================================================================
# Debug visualization
# ============================================================================
# Set to False for normal plugin use. When True, ViaFence draws the sampled
# continuous via-centre trajectory and rejected-candidate markers on
# User.Drawings. All debug graphics are added to the same PCB_GROUP as vias.
DEBUG = False
DEBUG_LINE_WIDTH_MM = 0.01
DEBUG_POINT_DIAMETER_MM = 0.05
DEBUG_POINT_STEP_MM = 0.15
DEBUG_REJECTED_DIAMETER_MM = 0.15
DEBUG_REASON_TEXT_WIDTH_MM = 0.08
DEBUG_REASON_TEXT_HEIGHT_MM = 0.08
DEBUG_REASON_TEXT_THICKNESS_MM = 0.003

# Rejected-candidate reason letters used by DEBUG visualization:
#   T = selected TRACK/ARC clearance violation
#   C = collision with other copper TRACK/ARC
#   V = collision/overlap with an existing or generated VIA
#   P = collision/clearance violation with a PAD/contact
#   D = duplicate target position
#   ? = unknown/unclassified rejection


def mm_to_mils(value_mm):
    return value_mm / MM_PER_MIL


def mils_to_mm(value_mils):
    return value_mils * MM_PER_MIL


def format_unit_value(value, decimals=4):
    """Format dialog numbers without unnecessary trailing zeros."""
    try:
        s = f"{float(value):.{decimals}f}"
        return s.rstrip('0').rstrip('.') if '.' in s else s
    except Exception:
        return str(value)


def display_length(value_mm, unit):
    """Return a length formatted for the currently selected display unit."""
    if unit == "mils":
        return f"{format_unit_value(mm_to_mils(value_mm), decimals=3)} mils"
    return f"{format_unit_value(value_mm, decimals=4)} mm"



def load_config():
    defaults = ViaFenceConfig()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return ViaFenceConfig(
                    spacing_mm=data.get("spacing_mm", data.get("track_spacing_mm", 1.0)),
                    track_to_via_gap_mm=data.get("track_to_via_gap_mm", 0.25),
                    via_diameter_mm=data.get("via_diameter_mm", 0.6),
                    via_drill_mm=data.get("via_drill_mm", 0.3),
                    staggered=data.get("staggered", False),
                    net_name=data.get("net_name", ""),
                    show_stats=data.get("show_stats", True),
                    units=data.get("units", "mm"),
                    window_pos_x=data.get("window_pos_x", None),
                    window_pos_y=data.get("window_pos_y", None)
                )
        except:
            pass
    return defaults


def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "spacing_mm": cfg.spacing_mm,
                "track_to_via_gap_mm": cfg.track_to_via_gap_mm,
                "via_diameter_mm": cfg.via_diameter_mm,
                "via_drill_mm": cfg.via_drill_mm,
                "staggered": cfg.staggered,
                "net_name": cfg.net_name,
                "show_stats": cfg.show_stats,
                "units": cfg.units,
                "window_pos_x": cfg.window_pos_x,
                "window_pos_y": cfg.window_pos_y
            }, f, indent=2)
    except Exception:
        pass


def parse_unit_value(ctrl, label, unit="mm", min_value=0.0, allow_zero=False):
    """
    Read a wx.TextCtrl value and return it in millimetres.
    The dialog may display either mm or mils.
    Accepts both 0.7 and 0,7.
    """
    raw = ctrl.GetValue().strip().replace(',', '.')
    try:
        value = float(raw)
    except ValueError:
        example = "0.7" if unit == "mm" else "27.56"
        raise ValueError(f"{label}: enter a valid number, for example {example}")

    if allow_zero:
        if value < min_value:
            raise ValueError(f"{label}: value must be >= {min_value}")
    else:
        if value <= min_value:
            raise ValueError(f"{label}: value must be > {min_value}")

    return mils_to_mm(value) if unit == "mils" else value



class ViaFenceDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(parent, title=f"ViaFence {PLUGIN_VERSION}", size=(500, 590))
        # Use a multi-size icon bundle for the dialog window.
        # wxWidgets/Windows can then select the best-matching size for the
        # current DPI instead of scaling a single bitmap.
        icon_bundle = wx.IconBundle()
        for size in (24, 32, 48, 64):
            icon_path = os.path.join(
                os.path.dirname(__file__),
                f"via_fence_{size}.png"
            )
            if os.path.exists(icon_path):
                icon_bundle.AddIcon(wx.Icon(icon_path, wx.BITMAP_TYPE_PNG))

        if icon_bundle.GetIconCount() > 0:
            self.SetIcons(icon_bundle)
        else:
            # Backward-compatible fallback to the original single icon.
            icon_path = os.path.join(os.path.dirname(__file__), "via_fence_icon.png")
            if os.path.exists(icon_path):
                self.SetIcon(wx.Icon(icon_path, wx.BITMAP_TYPE_PNG))
        
        cfg = load_config()

        # Restore last dialog position if available.
        try:
            if cfg.window_pos_x is not None and cfg.window_pos_y is not None:
                self.SetPosition((int(cfg.window_pos_x), int(cfg.window_pos_y)))
            else:
                self.Centre()
        except Exception:
            self.Centre()

        vbox = wx.BoxSizer(wx.VERTICAL)

        self.unit = cfg.units if cfg.units in ("mm", "mils") else "mm"
        self._unit_controls = []
        
        # Create controls
        # Keep the input column compact so the dialog does not become unnecessarily wide.
        field_size = (120, -1)
        self.spacing = wx.TextCtrl(self, value=format_unit_value(cfg.spacing_mm), size=field_size)
        self.gap = wx.TextCtrl(self, value=format_unit_value(cfg.track_to_via_gap_mm), size=field_size)
        self.via_diam = wx.TextCtrl(self, value=format_unit_value(cfg.via_diameter_mm), size=field_size)
        self.drill = wx.TextCtrl(self, value=format_unit_value(cfg.via_drill_mm), size=field_size)
        self.staggered = wx.CheckBox(self, label="Staggered pattern")
        self.staggered.SetValue(cfg.staggered)
        
        # Show stats checkbox
        self.show_stats = wx.CheckBox(self, label="Show statistics after execution")
        self.show_stats.SetValue(cfg.show_stats)
        
        # Unit selection
        self.unit_mm = wx.RadioButton(self, label="mm", style=wx.RB_GROUP)
        self.unit_mils = wx.RadioButton(self, label="mils")
        self.unit_mm.SetValue(self.unit == "mm")
        self.unit_mils.SetValue(self.unit == "mils")
        self.unit_mm.Bind(wx.EVT_RADIOBUTTON, self.on_unit_changed)
        self.unit_mils.Bind(wx.EVT_RADIOBUTTON, self.on_unit_changed)
        
        # Net selection
        self.net_choice = wx.Choice(self, size=(120, -1))
        self.net_map = {}
        
        nets = board.GetNetsByName()
        net_names = sorted([str(n) for n in nets.keys()])
        
        for name in net_names:
            self.net_choice.Append(name)
            self.net_map[name] = nets[name]
        
        if self.net_choice.GetCount() > 0:
            # Try to select the net from config
            idx = 0
            for i, name in enumerate(net_names):
                if name == cfg.net_name:
                    idx = i
                    break
            self.net_choice.SetSelection(idx)
        
        # Layout
        self.spacing_label = wx.StaticText(self, label="Via spacing track (mm):")
        self.gap_label = wx.StaticText(self, label="Track to via gap (mm):")
        self.via_diam_label = wx.StaticText(self, label="Via diameter (mm):")
        self.drill_label = wx.StaticText(self, label="Via drill (mm):")
        self._unit_label_controls = [
            (self.spacing_label, "Via spacing track"),
            (self.gap_label, "Track to via gap"),
            (self.via_diam_label, "Via diameter"),
            (self.drill_label, "Via drill"),
        ]
        self._unit_controls = [self.spacing, self.gap, self.via_diam, self.drill]

        # Standard wxWidgets tooltips.  No custom timer/delay is used, so the
        # operating system / wxWidgets controls when the tooltip appears and
        # hides it automatically when the pointer leaves the control.
        def set_tip(ctrl, text):
            ctrl.SetToolTip(text)

        set_tip(self.spacing_label,
                "Center-to-center target spacing used along TRACK, ARC, JOIN and PAD-contour routes.")
        set_tip(self.spacing,
                "Center-to-center target spacing used along TRACK, ARC, JOIN and PAD-contour routes.")

        set_tip(self.gap_label,
                "Clearance from the edge of the selected track to the edge of the fence via.")
        set_tip(self.gap,
                "Clearance from the edge of the selected track to the edge of the fence via.")

        set_tip(self.via_diam_label,
                "Overall diameter of each generated via.")
        set_tip(self.via_diam,
                "Overall diameter of each generated via.")

        set_tip(self.drill_label,
                "Drill-hole diameter of each generated via.")
        set_tip(self.drill,
                "Drill-hole diameter of each generated via.")


        set_tip(self.staggered,
                "Use every second target position on the unified copper-boundary trajectory.")

        set_tip(self.net_choice,
                "Electrical net assigned to all generated fence vias.")
        set_tip(self.unit_mm,
                "Display and enter dimensional values in millimetres.")
        set_tip(self.unit_mils,
                "Display and enter dimensional values in mils (1 mil = 0.001 inch).")
        set_tip(self.show_stats,
                "Show a summary of the generated vias and placement settings after execution.")

        self.apply_initial_units()
        self.update_unit_labels()

        fields = [
            (self.spacing_label, self.spacing),
            (self.gap_label, self.gap),
            (self.via_diam_label, self.via_diam),
            (self.drill_label, self.drill),
            (wx.StaticText(self, label="Net:"), self.net_choice),
        ]
        
        for label_ctrl, ctrl in fields:
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.Add(label_ctrl, 0, wx.ALL | wx.CENTER, 5)
            row.Add(ctrl, 1, wx.ALL | wx.EXPAND, 5)
            vbox.Add(row, 0, wx.EXPAND)
        
        unit_row = wx.BoxSizer(wx.HORIZONTAL)
        unit_row.Add(wx.StaticText(self, label="Units:"), 0, wx.ALL | wx.CENTER, 5)
        unit_row.Add(self.unit_mm, 0, wx.ALL | wx.CENTER, 5)
        unit_row.Add(self.unit_mils, 0, wx.ALL | wx.CENTER, 5)
        vbox.Add(unit_row, 0, wx.EXPAND)

        # Separator line
        line = wx.StaticLine(self, style=wx.LI_HORIZONTAL)
        vbox.Add(line, 0, wx.EXPAND | wx.ALL, 10)
        
        vbox.Add(self.staggered, 0, wx.ALL, 5)
        vbox.Add(self.show_stats, 0, wx.ALL, 5)

        # Project link
        project_link = wx.adv.HyperlinkCtrl(
            self,
            label="https://github.com/ozzysv/ViaFence",
            url="https://github.com/ozzysv/ViaFence",
        )
        vbox.Add(project_link, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add(btns, 0, wx.ALL | wx.CENTER, 10)
        
        self.SetSizerAndFit(vbox)
    
    def apply_initial_units(self):
        """Convert initial displayed values if the saved unit is mils."""
        if self.unit != "mils":
            return
        for ctrl in self._unit_controls:
            raw = ctrl.GetValue().strip().replace(',', '.')
            if not raw:
                continue
            try:
                value_mm = float(raw)
            except ValueError:
                continue
            ctrl.SetValue(format_unit_value(mm_to_mils(value_mm), decimals=3))

    def on_unit_changed(self, _event):
        new_unit = "mils" if self.unit_mils.GetValue() else "mm"
        if new_unit == self.unit:
            return

        old_unit = self.unit
        for ctrl in self._unit_controls:
            raw = ctrl.GetValue().strip().replace(',', '.')
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue

            if old_unit == "mm" and new_unit == "mils":
                value = mm_to_mils(value)
                ctrl.SetValue(format_unit_value(value, decimals=3))
            elif old_unit == "mils" and new_unit == "mm":
                value = mils_to_mm(value)
                ctrl.SetValue(format_unit_value(value, decimals=4))

        self.unit = new_unit
        self.update_unit_labels()

    def update_unit_labels(self):
        for label_ctrl, base_label in self._unit_label_controls:
            label_ctrl.SetLabel(f"{base_label} ({self.unit}):")
        self.Layout()

    def on_cancel(self, event):
        self.save_window_position_only()
        self.EndModal(wx.ID_CANCEL)

    def on_close(self, event):
        self.save_window_position_only()
        event.Skip()

    def save_window_position_only(self):
        """Save only the dialog position without changing other settings."""
        try:
            cfg = load_config()
            pos = self.GetPosition()
            cfg.window_pos_x = pos.x
            cfg.window_pos_y = pos.y
            save_config(cfg)
        except Exception:
            pass

    def get_config(self):
        net_name = self.net_choice.GetStringSelection()
        if not net_name:
            raise ValueError("Net: select a valid net")

        spacing_mm = parse_unit_value(self.spacing, "Via spacing track", self.unit, 0.0)
        gap_mm = parse_unit_value(self.gap, "Track to via gap", self.unit, 0.0, allow_zero=True)
        via_diameter_mm = parse_unit_value(self.via_diam, "Via diameter", self.unit, 0.0)
        via_drill_mm = parse_unit_value(self.drill, "Via drill", self.unit, 0.0)
        if via_drill_mm >= via_diameter_mm:
            raise ValueError("Via drill must be smaller than via diameter")

        return ViaFenceConfig(
            spacing_mm=spacing_mm,
            track_to_via_gap_mm=gap_mm,
            via_diameter_mm=via_diameter_mm,
            via_drill_mm=via_drill_mm,
            staggered=self.staggered.GetValue(),
            net_name=net_name,
            show_stats=self.show_stats.GetValue(),
            units=self.unit,
            window_pos_x=self.GetPosition().x,
            window_pos_y=self.GetPosition().y
        )


# ============================================================================
# Geometry utilities
# ============================================================================

def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _as_vec2i(x, y):
    return pcbnew.VECTOR2I(int(round(x)), int(round(y)))


def arc_to_polyline(arc, max_segment_deg=2):
    """
    Return a polyline for PCB_ARC that works across KiCad 8/9 SWIG builds.

    Some KiCad 9 builds return a SHAPE from GetEffectiveShape() that no longer
    exposes ArcToPolyline(), which caused:
        AttributeError: 'SHAPE' object has no attribute 'ArcToPolyline'

    Fallback: reconstruct the arc from start/mid/end points.
    """
    try:
        shape = arc.GetEffectiveShape()
        if hasattr(shape, "ArcToPolyline"):
            poly = list(shape.ArcToPolyline())
            if len(poly) >= 2:
                return poly
    except Exception:
        pass

    try:
        start = arc.GetStart()
        end = arc.GetEnd()
    except Exception:
        return []

    try:
        mid = arc.GetMid()
    except Exception:
        # Last-resort fallback: treat unknown arc API as a straight segment.
        return [start, end]

    x1, y1 = float(start.x), float(start.y)
    x2, y2 = float(mid.x), float(mid.y)
    x3, y3 = float(end.x), float(end.y)

    # Circle through 3 points. If degenerate, use straight approximation.
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [start, end]

    ux = ((x1*x1 + y1*y1) * (y2 - y3) +
          (x2*x2 + y2*y2) * (y3 - y1) +
          (x3*x3 + y3*y3) * (y1 - y2)) / d
    uy = ((x1*x1 + y1*y1) * (x3 - x2) +
          (x2*x2 + y2*y2) * (x1 - x3) +
          (x3*x3 + y3*y3) * (x2 - x1)) / d

    r = math.hypot(x1 - ux, y1 - uy)
    if r < 1e-9:
        return [start, end]

    a1 = math.atan2(y1 - uy, x1 - ux)
    am = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)

    def norm(a):
        while a < 0:
            a += 2 * math.pi
        while a >= 2 * math.pi:
            a -= 2 * math.pi
        return a

    def ccw_delta(a, b):
        return (norm(b) - norm(a)) % (2 * math.pi)

    # Choose direction whose sweep from start to end contains mid.
    sweep_ccw = ccw_delta(a1, a3)
    mid_ccw = ccw_delta(a1, am)
    if mid_ccw <= sweep_ccw:
        sweep = sweep_ccw
    else:
        sweep = -ccw_delta(a3, a1)

    segs = max(2, int(math.ceil(abs(math.degrees(sweep)) / max_segment_deg)))
    pts = []
    for i in range(segs + 1):
        a = a1 + sweep * (i / segs)
        pts.append(_as_vec2i(ux + r * math.cos(a), uy + r * math.sin(a)))
    return pts


def _norm_angle_rad(a):
    """Normalize angle to [0, 2*pi)."""
    while a < 0:
        a += 2 * math.pi
    while a >= 2 * math.pi:
        a -= 2 * math.pi
    return a


def _ccw_delta(a, b):
    return (_norm_angle_rad(b) - _norm_angle_rad(a)) % (2 * math.pi)


def get_arc_geometry(arc):
    """
    Return exact arc geometry as (cx, cy, radius, start_angle, sweep).
    Works from KiCad start/mid/end points, so it is independent of SHAPE API quirks.
    Returns None if the arc is degenerate or the API is unavailable.
    """
    try:
        start = arc.GetStart()
        mid = arc.GetMid()
        end = arc.GetEnd()
    except Exception:
        return None

    x1, y1 = float(start.x), float(start.y)
    x2, y2 = float(mid.x), float(mid.y)
    x3, y3 = float(end.x), float(end.y)

    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None

    cx = ((x1*x1 + y1*y1) * (y2 - y3) +
          (x2*x2 + y2*y2) * (y3 - y1) +
          (x3*x3 + y3*y3) * (y1 - y2)) / d
    cy = ((x1*x1 + y1*y1) * (x3 - x2) +
          (x2*x2 + y2*y2) * (x1 - x3) +
          (x3*x3 + y3*y3) * (x2 - x1)) / d

    r = math.hypot(x1 - cx, y1 - cy)
    if r < 1e-9:
        return None

    a1 = math.atan2(y1 - cy, x1 - cx)
    am = math.atan2(y2 - cy, x2 - cx)
    a3 = math.atan2(y3 - cy, x3 - cx)

    sweep_ccw = _ccw_delta(a1, a3)
    mid_ccw = _ccw_delta(a1, am)
    if mid_ccw <= sweep_ccw:
        sweep = sweep_ccw
    else:
        sweep = -_ccw_delta(a3, a1)

    return (cx, cy, r, a1, sweep)


def _angle_on_arc_sweep(angle, start_angle, sweep, tolerance=1e-9):
    """Return True when angle lies between start_angle and start_angle+sweep."""
    if sweep >= 0:
        return _ccw_delta(start_angle, angle) <= sweep + tolerance
    return _ccw_delta(angle, start_angle) <= -sweep + tolerance


def point_to_arc_distance(px, py, arc):
    """Exact distance from point to the arc centerline, with polyline fallback."""
    geom = get_arc_geometry(arc)
    if geom is not None:
        cx, cy, r, a1, sweep = geom
        a = math.atan2(py - cy, px - cx)
        if _angle_on_arc_sweep(a, a1, sweep):
            return abs(math.hypot(px - cx, py - cy) - r)

        # Projection is outside the arc sweep: nearest point is one of the endpoints.
        try:
            start = arc.GetStart()
            end = arc.GetEnd()
            return min(math.hypot(px - start.x, py - start.y),
                       math.hypot(px - end.x, py - end.y))
        except Exception:
            pass

    poly = arc_to_polyline(arc, max_segment_deg=1)
    if len(poly) < 2:
        return float('inf')
    best = float('inf')
    for i in range(len(poly) - 1):
        d = point_to_segment_distance(
            px, py,
            poly[i].x, poly[i].y,
            poly[i+1].x, poly[i+1].y
        )
        best = min(best, d)
    return best


# ============================================================================
# Path builder
# ============================================================================

def point_key(pt):
    """Use native KiCad integer nanometre coordinates as stable graph keys."""
    return (int(pt.x), int(pt.y))


def key_to_vec(k):
    return pcbnew.VECTOR2I(int(k[0]), int(k[1]))


def add_graph_edge(graph, edges, a, b, source_item):
    if a == b:
        return
    edge_id = len(edges)
    edges.append((a, b, source_item))
    graph.setdefault(a, []).append((b, edge_id))
    graph.setdefault(b, []).append((a, edge_id))


def build_graph_from_selected(selected_items):
    """Build an undirected graph from selected tracks/arcs using exact integer coordinates."""
    graph = {}
    edges = []

    for item in selected_items:
        # Check PCB_ARC before PCB_TRACK because KiCad arc classes may share track ancestry.
        if isinstance(item, pcbnew.PCB_ARC):
            poly = arc_to_polyline(item)
            for i in range(len(poly) - 1):
                add_graph_edge(graph, edges, point_key(poly[i]), point_key(poly[i + 1]), item)

        elif isinstance(item, pcbnew.PCB_TRACK):
            add_graph_edge(graph, edges, point_key(item.GetStart()), point_key(item.GetEnd()), item)

    return graph, edges


def graph_components(graph):
    visited = set()
    components = []

    for start in graph:
        if start in visited:
            continue
        stack = [start]
        nodes = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            nodes.add(node)
            for nxt, _edge_id in graph.get(node, []):
                if nxt not in visited:
                    stack.append(nxt)
        components.append(nodes)

    return components


def trace_branch(graph, start, first_next, first_edge_id, used_edges):
    """
    Trace one branch from a node with degree != 2 until the next endpoint/junction.
    This is what makes T-junctions and multi-branch selections work.
    """
    path = [start, first_next]
    used_edges.add(first_edge_id)
    prev = start
    current = first_next

    while len(graph.get(current, [])) == 2:
        candidates = [(n, e) for n, e in graph[current] if e not in used_edges]
        if not candidates:
            break
        nxt, edge_id = candidates[0]
        used_edges.add(edge_id)
        prev, current = current, nxt
        path.append(current)

    return [key_to_vec(k) for k in path]


def trace_loop(graph, start, used_edges):
    """Trace a closed loop component where every node has degree 2."""
    path = [start]
    current = start

    while True:
        nxt_edge = None
        for nxt, edge_id in graph[current]:
            if edge_id not in used_edges:
                nxt_edge = (nxt, edge_id)
                break

        if nxt_edge is None:
            break

        nxt, edge_id = nxt_edge
        used_edges.add(edge_id)
        current = nxt
        path.append(current)

        if current == start:
            break

    return [key_to_vec(k) for k in path]


def build_paths_from_selected(selected_items):
    """
    Build all independent paths from selected copper.

    Supports:
    - one simple chain
    - multiple disconnected chains
    - T-junctions and junctions with 3+ branches
    - closed loops

    Returns (paths, stats), where paths is a list of VECTOR2I lists.
    """
    graph, edges = build_graph_from_selected(selected_items)
    if not graph:
        return [], {"components": 0, "junctions": 0, "branches": 0, "loops": 0}

    used_edges = set()
    paths = []
    loop_count = 0

    for nodes in graph_components(graph):
        junction_or_end_nodes = [n for n in nodes if len(graph.get(n, [])) != 2]

        if junction_or_end_nodes:
            # Start from every endpoint/junction and trace each unused outgoing edge.
            for node in sorted(junction_or_end_nodes):
                for nxt, edge_id in graph.get(node, []):
                    if edge_id in used_edges:
                        continue
                    path = trace_branch(graph, node, nxt, edge_id, used_edges)
                    if len(path) >= 2:
                        paths.append(path)
        else:
            # Pure closed loop.
            node = next(iter(nodes))
            path = trace_loop(graph, node, used_edges)
            if len(path) >= 2:
                paths.append(path)
                loop_count += 1

    # Safety fallback for any unvisited edges.
    for edge_id, (a, b, _item) in enumerate(edges):
        if edge_id not in used_edges:
            path = trace_branch(graph, a, b, edge_id, used_edges)
            if len(path) >= 2:
                paths.append(path)

    stats = {
        "components": len(graph_components(graph)),
        "junctions": sum(1 for n, adj in graph.items() if len(adj) > 2),
        "branches": len(paths),
        "loops": loop_count,
    }
    return paths, stats


# ============================================================================
# Collision detection
# ============================================================================

def get_board_clearance(board):
    try:
        return board.GetDesignSettings().GetSmallestClearanceValue()
    except Exception:
        return pcbnew.FromMM(0.15)


def segment_bbox(x1, y1, x2, y2, inflate):
    return (min(x1, x2) - inflate, min(y1, y2) - inflate,
            max(x1, x2) + inflate, max(y1, y2) + inflate)


def circle_bbox(x, y, radius):
    return (x - radius, y - radius, x + radius, y + radius)


def _pad_angle_rad(pad):
    """Return pad orientation in radians, compatible with KiCad 8/9 SWIG variants."""
    try:
        angle = pad.GetOrientation()
        if hasattr(angle, "AsRadians"):
            return angle.AsRadians()
        if hasattr(angle, "AsDegrees"):
            return math.radians(angle.AsDegrees())
        # KiCad often stores orientation as deci-degrees in older APIs.
        value = float(angle)
        if abs(value) > 3600:
            return math.radians(value / 10.0)
        if abs(value) > 360:
            return math.radians(value / 10.0)
        return math.radians(value)
    except Exception:
        return 0.0


def _point_in_pad_local(pad, pos):
    """Convert a board point to the pad local coordinate system."""
    pp = pad.GetPosition()
    dx = float(pos.x - pp.x)
    dy = float(pos.y - pp.y)
    a = -_pad_angle_rad(pad)
    ca = math.cos(a)
    sa = math.sin(a)
    return (dx * ca - dy * sa, dx * sa + dy * ca)


def _distance_to_axis_rect(px, py, half_w, half_h):
    """Distance from point to an axis-aligned rectangle. Returns 0 when inside."""
    dx = max(abs(px) - half_w, 0.0)
    dy = max(abs(py) - half_h, 0.0)
    return math.hypot(dx, dy)


def _distance_to_capsule(px, py, half_w, half_h):
    """
    Distance from point to an oval KiCad pad approximated as a capsule.
    Returns 0 when inside the capsule.
    """
    if half_w >= half_h:
        r = half_h
        a = max(half_w - r, 0.0)
        cx = max(-a, min(a, px))
        cy = 0.0
    else:
        r = half_w
        a = max(half_h - r, 0.0)
        cx = 0.0
        cy = max(-a, min(a, py))

    return max(0.0, math.hypot(px - cx, py - cy) - r)


def _distance_to_rounded_rect(px, py, half_w, half_h, radius):
    """
    Distance from point to a rounded rectangle. Returns 0 when inside.
    This is a conservative fallback for KiCad rounded-rect pads.
    """
    radius = max(0.0, min(float(radius), half_w, half_h))
    qx = abs(px) - (half_w - radius)
    qy = abs(py) - (half_h - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    signed = outside + inside - radius
    return max(0.0, signed)


def _pad_roundrect_radius(pad, half_w, half_h):
    """Best-effort rounded-rectangle corner radius in internal KiCad units."""
    try:
        if hasattr(pad, "GetRoundRectCornerRadius"):
            return float(pad.GetRoundRectCornerRadius())
    except Exception:
        pass
    try:
        if hasattr(pad, "GetRoundRectRadiusRatio"):
            return float(pad.GetRoundRectRadiusRatio()) * min(half_w, half_h)
    except Exception:
        pass
    # KiCad default round-rect ratio is commonly 0.25 of the smaller side.
    return 0.25 * min(half_w, half_h)


def pad_clearance_distance_fallback(pad, via_pos):
    """
    Real-shape fallback distance from via center to pad copper edge.
    Handles rotated circle, oval, rectangle and rounded-rectangle pads.
    Returns 0 when the via center is inside the pad copper area.
    """
    px, py = _point_in_pad_local(pad, via_pos)
    half_w = float(pad.GetSizeX()) / 2.0
    half_h = float(pad.GetSizeY()) / 2.0

    shape = None
    try:
        shape = pad.GetShape()
    except Exception:
        pass

    circle_shape = getattr(pcbnew, "PAD_SHAPE_CIRCLE", None)
    oval_shape = getattr(pcbnew, "PAD_SHAPE_OVAL", None)
    rect_shape = getattr(pcbnew, "PAD_SHAPE_RECT", None)
    roundrect_shape = getattr(pcbnew, "PAD_SHAPE_ROUNDRECT", None)

    if shape == circle_shape:
        return max(0.0, math.hypot(px, py) - min(half_w, half_h))

    if shape == oval_shape:
        return _distance_to_capsule(px, py, half_w, half_h)

    if shape == roundrect_shape:
        return _distance_to_rounded_rect(px, py, half_w, half_h,
                                         _pad_roundrect_radius(pad, half_w, half_h))

    if shape == rect_shape:
        return _distance_to_axis_rect(px, py, half_w, half_h)

    # Unknown/custom shapes: use a conservative rectangle instead of the old
    # center-circle approximation, because long connector pads otherwise fail.
    return _distance_to_axis_rect(px, py, half_w, half_h)


def pad_effective_bbox(pad, inflate):
    """Return bbox for the real pad copper shape where possible, with safe fallback."""
    try:
        shape = pad.GetEffectiveShape()
        if hasattr(shape, "BBox"):
            bb = shape.BBox()
        elif hasattr(shape, "GetBoundingBox"):
            bb = shape.GetBoundingBox()
        else:
            bb = None

        if bb is not None:
            try:
                return (
                    bb.GetX() - inflate,
                    bb.GetY() - inflate,
                    bb.GetRight() + inflate,
                    bb.GetBottom() + inflate,
                )
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: old conservative circular bbox around the pad.
    p = pad.GetPosition()
    pad_r = max(pad.GetSizeX(), pad.GetSizeY()) / 2
    return circle_bbox(p.x, p.y, inflate + pad_r)


def pad_collides_with_via(pad, via_pos, via_radius, required_gap):
    """
    Check via-to-pad spacing using the real pad copper shape.

    required_gap is the desired copper-to-copper gap between the via edge and
    the pad edge. For ViaFence this is intentionally the same value as
    "Track to via gap", so pads are treated like copper obstacles with the
    user-selected gap, not only the board DRC clearance.
    """
    required_gap = max(0, int(required_gap))

    # Preferred path: use KiCad shape engine on the pad's effective copper shape.
    try:
        pad_shape = pad.GetEffectiveShape()

        # Inflate the via copper by the requested pad gap. If this inflated
        # circle touches the real pad shape, the via is too close to the pad.
        via_shape = pcbnew.SHAPE_CIRCLE(via_pos, int(via_radius + required_gap))

        try:
            if pad_shape.Collide(via_shape, 0):
                return True
        except TypeError:
            if pad_shape.Collide(via_shape):
                return True
    except Exception:
        pass

    # Fallback: exact-enough geometry in the pad local coordinate system.
    # This is important for long/rounded connector pads: the old center-circle
    # approximation could miss violations near the pad ends.
    return pad_clearance_distance_fallback(pad, via_pos) < (via_radius + required_gap)


class CollisionIndex:
    """Small grid spatial index for fast nearby-copper lookup."""
    def __init__(self, board, ignore_items, via_radius):
        self.board = board
        self.clearance = get_board_clearance(board)
        self.ignore_ids = {id(x) for x in ignore_items}
        self.cell_size = max(int(pcbnew.FromMM(2.0)), int((via_radius + self.clearance) * 4), 1)
        self.grid = {}
        self.objects = []

        self._build(via_radius)

    def _cell_range_for_bbox(self, bbox):
        minx, miny, maxx, maxy = bbox
        return (int(minx // self.cell_size), int(miny // self.cell_size),
                int(maxx // self.cell_size), int(maxy // self.cell_size))

    def _add_object(self, obj):
        idx = len(self.objects)
        self.objects.append(obj)
        cminx, cminy, cmaxx, cmaxy = self._cell_range_for_bbox(obj["bbox"])
        for cx in range(cminx, cmaxx + 1):
            for cy in range(cminy, cmaxy + 1):
                self.grid.setdefault((cx, cy), []).append(idx)

    def _build(self, via_radius):
        inflate = via_radius + self.clearance + pcbnew.FromMM(1.0)

        for item in self.board.GetTracks():
            if id(item) in self.ignore_ids:
                continue

            # Check the more specific classes before PCB_TRACK.
            if isinstance(item, pcbnew.PCB_VIA):
                p = item.GetPosition()
                r = item.GetWidth() / 2
                self._add_object({
                    "kind": "via",
                    "item": item,
                    "bbox": circle_bbox(p.x, p.y, inflate + r),
                })

            elif isinstance(item, pcbnew.PCB_ARC):
                poly = arc_to_polyline(item)
                if len(poly) < 2:
                    continue
                xs = [p.x for p in poly]
                ys = [p.y for p in poly]
                half_w = item.GetWidth() / 2
                self._add_object({
                    "kind": "arc",
                    "item": item,
                    "bbox": (min(xs) - inflate - half_w, min(ys) - inflate - half_w,
                             max(xs) + inflate + half_w, max(ys) + inflate + half_w),
                })

            elif isinstance(item, pcbnew.PCB_TRACK):
                a, b = item.GetStart(), item.GetEnd()
                half_w = item.GetWidth() / 2
                self._add_object({
                    "kind": "track",
                    "item": item,
                    "bbox": segment_bbox(a.x, a.y, b.x, b.y, inflate + half_w),
                })

        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                if id(pad) in self.ignore_ids:
                    continue
                self._add_object({
                    "kind": "pad",
                    "item": pad,
                    "bbox": pad_effective_bbox(pad, inflate),
                })

    def add_created_via(self, via):
        p = via.GetPosition()
        r = via.GetWidth() / 2
        inflate = r + self.clearance + pcbnew.FromMM(1.0)
        self._add_object({
            "kind": "via",
            "item": via,
            "bbox": circle_bbox(p.x, p.y, inflate),
        })

    def nearby(self, pos, search_radius):
        bbox = circle_bbox(pos.x, pos.y, search_radius)
        cminx, cminy, cmaxx, cmaxy = self._cell_range_for_bbox(bbox)
        seen = set()
        for cx in range(cminx, cmaxx + 1):
            for cy in range(cminy, cmaxy + 1):
                for idx in self.grid.get((cx, cy), []):
                    if idx not in seen:
                        seen.add(idx)
                        yield self.objects[idx]




def board_item_identity(item):
    """Return a stable identity key for a KiCad board item.

    SWIG can expose the same C++ PAD through different Python proxy objects, so
    Python ``id(item)`` is not reliable for owner-PAD exclusion.  Prefer the
    item's KiCad UUID and fall back to object id only if UUID access is not
    available in this KiCad build.
    """
    try:
        u = item.GetUuid()
        try:
            return ("uuid", u.AsString())
        except Exception:
            return ("uuid", str(u))
    except Exception:
        pass
    try:
        u = item.m_Uuid
        try:
            return ("uuid", u.AsString())
        except Exception:
            return ("uuid", str(u))
    except Exception:
        pass
    return ("pyid", id(item))


def can_place_via(collision_index, pos, radius, pad_gap=None, ignore_item_ids=None, ignore_pad_ids=None):
    """
    Check only nearby objects instead of scanning the whole board for every candidate.

    pad_gap is the required copper-to-copper gap from via edge to pad edge.
    When omitted, the board clearance is used.
    """
    px, py = pos.x, pos.y
    clearance = collision_index.clearance
    pad_required_gap = clearance if pad_gap is None else max(clearance, int(pad_gap))
    search_radius = radius + max(clearance, pad_required_gap) + pcbnew.FromMM(3.0)
    ignore_item_ids = set() if ignore_item_ids is None else set(ignore_item_ids)
    ignore_pad_ids = set() if ignore_pad_ids is None else set(ignore_pad_ids)

    for obj in collision_index.nearby(pos, search_radius):
        item = obj["item"]
        if id(item) in ignore_item_ids:
            continue
        kind = obj["kind"]

        if kind == "track":
            dist = point_to_segment_distance(
                px, py,
                item.GetStart().x, item.GetStart().y,
                item.GetEnd().x, item.GetEnd().y
            )
            if dist < radius + item.GetWidth() / 2 + clearance:
                return False

        elif kind == "arc":
            dist = point_to_arc_distance(px, py, item)
            if dist < radius + item.GetWidth() / 2 + clearance:
                return False

        elif kind == "via":
            # Via-to-via spacing allows vias to touch edge-to-edge.
            # The dialog field "Track to via gap" is applied only to:
            #   - via to selected track/arc
            #   - via to pad/contact
            # Board DRC clearance is intentionally not added here.
            vp = item.GetPosition()
            vr = item.GetWidth() / 2
            dist = math.hypot(px - vp.x, py - vp.y)
            limit = radius + vr
            if dist < limit:
                return False

        elif kind == "pad":
            # Ignore collision against the SAME selected pad when building
            # long-side pad-ring vias. The candidate was already generated
            # from the real pad boundary + requested offset.
            if board_item_identity(item) in ignore_pad_ids:
                continue

            if pad_collides_with_via(item, pos, radius, pad_required_gap):
                return False

    return True



def selected_copper_rejection_reason(selected_items, pos, via_radius, track_gap, tolerance=None):
    """Return debug reason code if selected reference copper rejects a via.

    T = selected TRACK/ARC clearance violation.
    None = selected reference copper is OK.
    """
    if tolerance is None:
        tolerance = pcbnew.FromMM(0.002)
    required_gap = max(0, int(track_gap))
    px, py = pos.x, pos.y
    for item in selected_items:
        if not hasattr(item, 'GetWidth'):
            continue
        required_center_distance = via_radius + item.GetWidth() / 2 + required_gap
        if isinstance(item, pcbnew.PCB_ARC):
            dist = point_to_arc_distance(px, py, item)
        elif isinstance(item, pcbnew.PCB_TRACK):
            dist = point_to_segment_distance(
                px, py, item.GetStart().x, item.GetStart().y,
                item.GetEnd().x, item.GetEnd().y)
        else:
            continue
        if dist < required_center_distance - tolerance:
            return "T"
    return None


def collision_rejection_reason(collision_index, pos, radius, pad_gap=None,
                               ignore_item_ids=None, ignore_pad_ids=None):
    """Return compact debug code for the first blocking board object.

    C = other copper TRACK/ARC
    V = existing/generated VIA overlap
    P = PAD/contact clearance
    ? = unknown / no collision found
    """
    px, py = pos.x, pos.y
    clearance = collision_index.clearance
    pad_required_gap = clearance if pad_gap is None else max(clearance, int(pad_gap))
    search_radius = radius + max(clearance, pad_required_gap) + pcbnew.FromMM(3.0)
    ignore_item_ids = set() if ignore_item_ids is None else set(ignore_item_ids)
    ignore_pad_ids = set() if ignore_pad_ids is None else set(ignore_pad_ids)

    for obj in collision_index.nearby(pos, search_radius):
        item = obj["item"]
        if id(item) in ignore_item_ids:
            continue
        kind = obj["kind"]
        if kind == "track":
            dist = point_to_segment_distance(
                px, py, item.GetStart().x, item.GetStart().y,
                item.GetEnd().x, item.GetEnd().y)
            if dist < radius + item.GetWidth() / 2 + clearance:
                return "C"
        elif kind == "arc":
            dist = point_to_arc_distance(px, py, item)
            if dist < radius + item.GetWidth() / 2 + clearance:
                return "C"
        elif kind == "via":
            vp = item.GetPosition()
            vr = item.GetWidth() / 2
            if math.hypot(px - vp.x, py - vp.y) < radius + vr:
                return "V"
        elif kind == "pad":
            if board_item_identity(item) in ignore_pad_ids:
                continue
            if pad_collides_with_via(item, pos, radius, pad_required_gap):
                return "P"
    return "?"


# ============================================================================
# Selected pad contour geometry helpers
# ============================================================================

def pad_is_selected(pad):
    """Best-effort pad selection check for KiCad SWIG builds."""
    try:
        if pad.IsSelected():
            return True
    except Exception:
        pass
    try:
        if pad.GetParent() and pad.GetParent().IsSelected():
            return True
    except Exception:
        pass
    return False


def get_selected_pads(board):
    """Return pads selected directly, plus pads of selected footprints if KiCad reports that."""
    pads = []
    seen = set()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad_is_selected(pad) and id(pad) not in seen:
                pads.append(pad)
                seen.add(id(pad))
    return pads




# Pad polygon-offset placement imported/adapted from action_pad_via_stitcher_v005.py.
# This replaces the old radial ring for pads. Rect/roundrect/oval pads are first
# converted to their real copper outline, then offset outward by via radius + gap,
# then sampled along that offset outline. Long straight pad sides therefore stay
# straight instead of becoming an ellipse-like radial path.



# ============================================================================
# Main plugin class
# ============================================================================

class ViaFencePlugin(pcbnew.ActionPlugin):
    """Main plugin for KiCad 9.0"""
    
    def __init__(self):
        super().__init__()
        self.name = "ViaFence"
        self.category = "Modify PCB"
        self.description = "Place via fence along selected tracks for EMI shielding"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "via_fence_icon.png")
    
    def Run(self):
        board = pcbnew.GetBoard()


        selected = [
            x for x in board.GetTracks()
            if x.IsSelected() and isinstance(x, (pcbnew.PCB_TRACK, pcbnew.PCB_ARC))
        ]
        selected_pads = get_selected_pads(board)

        if not selected and not selected_pads:
            wx.MessageBox(
                "No tracks or pads selected.\n\nSelect one or more tracks/arcs and optionally pads to surround.",
                "ViaFence",
                wx.OK | wx.ICON_WARNING
            )
            return

        dlg = ViaFenceDialog(None, board)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return

        try:
            cfg = dlg.get_config()
        except ValueError as e:
            wx.MessageBox(str(e), "ViaFence - Invalid input", wx.OK | wx.ICON_ERROR)
            return
        finally:
            try:
                dlg.Destroy()
            except Exception:
                pass

        save_config(cfg)

        if selected:
            paths, path_stats = build_paths_from_selected(selected)
            if not paths:
                wx.MessageBox(
                    "Failed to build paths from selected tracks.\n\n"
                    "Check that selected items are valid tracks/arcs.",
                    "ViaFence",
                    wx.OK | wx.ICON_ERROR
                )
                return
        else:
            paths = []
            path_stats = {"components": 0, "junctions": 0, "branches": 0, "loops": 0}

        net_name = cfg.net_name
        target_net = None
        nets = board.GetNetsByName()
        for name, net in nets.items():
            if str(name) == net_name:
                target_net = net
                break

        if not target_net:
            wx.MessageBox(
                f"Net '{net_name}' not found on board.",
                "ViaFence",
                wx.OK | wx.ICON_ERROR
            )
            return

        spacing = pcbnew.FromMM(cfg.spacing_mm)
        offset = pcbnew.FromMM(cfg.track_to_via_gap_mm)
        via_diam = pcbnew.FromMM(cfg.via_diameter_mm)
        drill = pcbnew.FromMM(cfg.via_drill_mm)
        radius = via_diam / 2
        pad_gap = offset  # via edge to pad edge must be at least Track-to-via gap

        if spacing <= 0 or via_diam <= 0 or drill <= 0:
            wx.MessageBox(
                "Via spacing track, via diameter and drill must be positive values.",
                "ViaFence - Invalid input",
                wx.OK | wx.ICON_ERROR
            )
            return

        collision_index = CollisionIndex(board, selected, radius)

        created_vias = []
        preview_shapes = []
        placed_positions = set()
        skipped_candidates = 0

        def make_via(pos):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pos)
            via.SetWidth(via_diam)
            via.SetDrill(drill)
            via.SetNet(target_net)
            try:
                via.SetTimeStamp(VIA_TIMESTAMP)
            except Exception:
                pass
            board.Add(via)
            created_vias.append(via)
            collision_index.add_created_via(via)
            return via

        def position_key(x, y):
            # Exact enough to prevent duplicates while allowing normal KiCad nm coordinates.
            return (int(round(x)), int(round(y)))

        # Exact-target placement on the unified copper-boundary route.
        last_rejection_reason = None

        def try_place_regular_via(x, y, ignore_pad_ids=None, skip_selected_clearance=False):
            """Try to place one regular via at an exact target coordinate.

            Debug rejection reason codes:
              T = selected TRACK/ARC clearance violation
              C = collision with other copper TRACK/ARC
              V = collision/overlap with an existing or generated VIA
              P = collision/clearance violation with a PAD/contact
              D = duplicate target position
              ? = unknown/unclassified rejection

            ignore_pad_ids contains stable KiCad item identity keys and is used only while
            walking the offset contour of a PAD.  The owner PAD that generated
            that contour must not reject its own fence candidate; every other PAD
            and every other board object is still checked.
            """
            nonlocal skipped_candidates, last_rejection_reason
            last_rejection_reason = None
            ignore_pad_ids = set() if ignore_pad_ids is None else set(ignore_pad_ids)
            pos_key = position_key(x, y)
            if pos_key in placed_positions:
                last_rejection_reason = "D"  # duplicate target position
                return False

            pos = pcbnew.VECTOR2I(int(round(x)), int(round(y)))
            if not skip_selected_clearance:
                selected_reason = selected_copper_rejection_reason(
                    selected, pos, radius, offset)
                if selected_reason is not None:
                    last_rejection_reason = selected_reason
                    skipped_candidates += 1
                    return False

            if not can_place_via(
                    collision_index, pos, radius, pad_gap,
                    ignore_pad_ids=ignore_pad_ids):
                last_rejection_reason = collision_rejection_reason(
                    collision_index, pos, radius, pad_gap,
                    ignore_pad_ids=ignore_pad_ids)
                skipped_candidates += 1
                return False

            placed_positions.add(pos_key)
            make_via(pos)
            return True


        def _xy_to_vec(xy):
            """Convert an internal XY tuple in KiCad board units to VECTOR2I.

            DEBUG preview helpers use the same floating-point board-unit
            coordinates returned by route primitives. Keep the conversion local
            to Run() so preview geometry cannot depend on legacy helpers.
            """
            return pcbnew.VECTOR2I(int(round(float(xy[0]))), int(round(float(xy[1]))))

        def _add_user_drawing_point(xy, diameter_mm=DEBUG_POINT_DIAMETER_MM):
            """Add one tiny debug point marker to User.Drawings.

            A very short thick PCB_SHAPE segment is used instead of S_CIRCLE for
            reliable KiCad 9/10 SWIG compatibility.  The marker represents one
            sampled point on the actual via-centre trajectory.
            """
            if not DEBUG:
                return
            try:
                x = float(xy[0])
                y = float(xy[1])
                # Keep the point footprint small while using a fixed 0.02 mm
                # debug stroke width.
                half_len = pcbnew.FromMM(max(0.005, diameter_mm * 0.20))
                a = _xy_to_vec((x - half_len, y))
                b = _xy_to_vec((x + half_len, y))

                shape = pcbnew.PCB_SHAPE(board)
                shape.SetShape(pcbnew.S_SEGMENT)
                shape.SetStart(a)
                shape.SetEnd(b)
                try:
                    user_drawings_layer = board.GetLayerID("User.Drawings")
                except Exception:
                    user_drawings_layer = pcbnew.User_Drawings
                shape.SetLayer(user_drawings_layer)
                shape.SetWidth(pcbnew.FromMM(DEBUG_LINE_WIDTH_MM))
                board.Add(shape)
                preview_shapes.append(shape)
            except Exception as e:
                if DEBUG:
                    print(f"ViaFence: route preview point failed: {e}")

        def _add_rejected_candidate_marker(
                xy, reason="?", diameter_mm=DEBUG_REJECTED_DIAMETER_MM,
                line_width_mm=DEBUG_LINE_WIDTH_MM):
            """Draw a hollow circle at a rejected via target coordinate.

            The marker is placed on User.Drawings and added to the same preview
            collection/group as generated vias and trajectory dots.  Its outer
            diameter is 0.10 mm and stroke width is controlled by
            DEBUG_LINE_WIDTH_MM.
            """
            if not DEBUG:
                return
            try:
                x = float(xy[0])
                y = float(xy[1])
                r = float(pcbnew.FromMM(diameter_mm * 0.5))

                shape = pcbnew.PCB_SHAPE(board)
                shape.SetShape(pcbnew.S_CIRCLE)
                center = _xy_to_vec((x, y))
                edge = _xy_to_vec((x + r, y))
                shape.SetCenter(center)
                shape.SetEnd(edge)
                try:
                    user_drawings_layer = board.GetLayerID("User.Drawings")
                except Exception:
                    user_drawings_layer = pcbnew.User_Drawings
                shape.SetLayer(user_drawings_layer)
                shape.SetWidth(pcbnew.FromMM(line_width_mm))
                board.Add(shape)
                preview_shapes.append(shape)

                # Put a tiny one-letter rejection reason exactly at the circle centre.
                # See the DEBUG visualization legend near the constants above.
                try:
                    reason_code = str(reason or "?")[:1]
                    text = pcbnew.PCB_TEXT(board)
                    text.SetText(reason_code)
                    text.SetPosition(center)
                    text.SetLayer(user_drawings_layer)
                    # KiCad 9/10 SWIG builds differ in the PCB_TEXT size API.
                    # Prefer separate width/height setters because they are the
                    # most reliable for board text; fall back to SetTextSize.
                    tw = pcbnew.FromMM(DEBUG_REASON_TEXT_WIDTH_MM)
                    th = pcbnew.FromMM(DEBUG_REASON_TEXT_HEIGHT_MM)
                    if hasattr(text, "SetTextWidth") and hasattr(text, "SetTextHeight"):
                        text.SetTextWidth(tw)
                        text.SetTextHeight(th)
                    elif hasattr(text, "SetTextSize"):
                        text.SetTextSize(pcbnew.VECTOR2I(tw, th))
                    else:
                        raise AttributeError("PCB_TEXT has no supported text-size setter")

                    thickness = pcbnew.FromMM(DEBUG_REASON_TEXT_THICKNESS_MM)
                    if hasattr(text, "SetTextThickness"):
                        text.SetTextThickness(thickness)
                    elif hasattr(text, "SetThickness"):
                        text.SetThickness(thickness)
                    else:
                        pass
                    try:
                        text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
                        text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
                    except Exception:
                        pass
                    try:
                        text.SetVisible(True)
                    except Exception:
                        pass
                    board.Add(text)
                    preview_shapes.append(text)
                except Exception as text_error:
                    if DEBUG:
                        print(f"ViaFence: rejection reason text failed: {text_error}")
            except Exception as e:
                if DEBUG:
                    print(f"ViaFence: rejected-candidate marker failed: {e}")

        def _sample_primitive_points(prim, step_mm=0.15):
            """Sample the exact primitive point_at() trajectory at a fixed pitch."""
            length = float(prim.get("length", 0.0))
            if length <= 1e-6:
                return []
            step = max(float(pcbnew.FromMM(step_mm)), 1.0)
            count = max(1, int(math.ceil(length / step)))
            return [prim["point_at"](length * i / count) for i in range(count + 1)]


        def _closed_primitive_targets(prim):
            """Generate evenly spaced targets around one closed boundary contour.

            The contour perimeter is divided into an integer number of equal
            stations.  Prefer a station pitch within +/-5% of the requested
            spacing and, among those choices, the pitch closest to it.  If the
            tolerance cannot be met, still use the closest integer division so
            the closing gap is identical to every other gap.
            """
            if prim is None or not prim.get("closed", False):
                return []

            perimeter = float(prim.get("length", 0.0))
            requested = float(spacing)
            if perimeter <= 1e-6 or requested <= 0.0:
                return []

            ratio = perimeter / requested
            # The optimum integer N must lie at one of the integers nearest P/S.
            # Include neighbours as a small guard against floating-point ties.
            base = max(1, int(math.floor(ratio)))
            candidates = sorted({max(1, base + delta) for delta in (-1, 0, 1, 2)})

            lo = requested * 0.95
            hi = requested * 1.05
            within_tolerance = [
                n for n in candidates
                if lo <= (perimeter / n) <= hi
            ]
            pool = within_tolerance if within_tolerance else candidates
            via_count = min(
                pool,
                key=lambda n: (abs((perimeter / n) - requested), abs(n - ratio), n)
            )

            actual_spacing = perimeter / via_count
            return [
                (prim, prim["point_at"](actual_spacing * i), actual_spacing * i)
                for i in range(via_count)
            ]


        # ------------------------------------------------------------------
        # Unified copper-boundary placement engine
        # ------------------------------------------------------------------
        # Build ONE geometric copper region from all selected TRACK/ARC/PAD items,
        # then offset that region by (Track-to-via gap + via radius).  The resulting
        # polygon boundary is the real via-centre trajectory.  This naturally
        # handles TRACK<->TRACK corners, T/X junctions, arcs and PAD transitions
        # without special JunctionPrimitive geometry or intersecting branch routes.
        #
        # Both placement and DEBUG preview consume these exact same primitives.
        def _poly_fast_mode():
            try:
                return pcbnew.SHAPE_POLY_SET.PM_FAST
            except Exception:
                return getattr(pcbnew, "PM_FAST", 0)

        def _round_corner_strategy():
            for name in ("CORNER_STRATEGY_ROUND_ALL_CORNERS", "ROUND_ALL_CORNERS"):
                if hasattr(pcbnew, name):
                    return getattr(pcbnew, name)
            # KiCad exposes this enum under different names in some SWIG builds.
            try:
                return pcbnew.CORNER_STRATEGY.ROUND_ALL_CORNERS
            except Exception:
                return 0

        def _error_outside():
            return getattr(pcbnew, "ERROR_OUTSIDE", 1)

        def _poly_simplify(poly):
            try:
                poly.Simplify(_poly_fast_mode())
                return
            except Exception:
                pass
            try:
                poly.Simplify()
            except Exception:
                pass

        def _inflate_poly(poly, amount, max_error):
            if amount <= 0:
                return
            strategy = _round_corner_strategy()
            # API signatures differ slightly between KiCad 9/10 SWIG builds.
            for args in (
                (int(amount), strategy, int(max_error)),
                (int(amount), strategy, int(max_error), True),
            ):
                try:
                    poly.Inflate(*args)
                    return
                except Exception:
                    pass
            # Older wrappers sometimes expose only the segment-count overload.
            try:
                segs = max(16, int(math.ceil(2.0 * math.pi * max(1.0, float(amount)) /
                                              max(1.0, float(max_error)))))
                poly.Inflate(int(amount), segs)
                return
            except Exception as exc:
                raise RuntimeError(f"SHAPE_POLY_SET.Inflate failed: {exc}")

        def _selected_geometry_layer():
            if selected:
                try:
                    return selected[0].GetLayer()
                except Exception:
                    pass
            for pad in selected_pads:
                for lyr_name in ("F_Cu", "B_Cu"):
                    lyr = getattr(pcbnew, lyr_name, None)
                    if lyr is None:
                        continue
                    try:
                        if pad.IsOnLayer(lyr):
                            return lyr
                    except Exception:
                        pass
            return getattr(pcbnew, "F_Cu", 0)

        def _poly_chain_points(chain):
            pts = []
            try:
                count = chain.PointCount()
            except Exception:
                try:
                    count = chain.SegmentCount()
                except Exception:
                    count = 0
            for idx in range(int(count)):
                pt = None
                for getter in ("CPoint", "Point"):
                    if hasattr(chain, getter):
                        try:
                            pt = getattr(chain, getter)(idx)
                            break
                        except Exception:
                            pass
                if pt is not None:
                    pts.append((float(pt.x), float(pt.y)))
            # Remove duplicate closing point and consecutive duplicates.
            clean = []
            for xy in pts:
                if not clean or math.hypot(xy[0]-clean[-1][0], xy[1]-clean[-1][1]) > 0.5:
                    clean.append(xy)
            if len(clean) > 2 and math.hypot(clean[0][0]-clean[-1][0],
                                            clean[0][1]-clean[-1][1]) <= 0.5:
                clean.pop()
            return clean

        def _closed_polyline_primitive(points, kind="unified_boundary"):
            if not points or len(points) < 3:
                return None
            pts = list(points)
            cum = [0.0]
            for i in range(len(pts)):
                a = pts[i]
                b = pts[(i + 1) % len(pts)]
                ln = math.hypot(float(b[0])-float(a[0]), float(b[1])-float(a[1]))
                cum.append(cum[-1] + ln)
            total = float(cum[-1])
            if total <= 1.0:
                return None

            def point_at(d, _pts=pts, _cum=cum, _total=total):
                dd = float(d) % _total if _total > 0 else 0.0
                # Linear scan is inexpensive for the modest polygon sizes produced
                # by KiCad and keeps this compatible with both KiCad 9/10 Python.
                for i in range(len(_pts)):
                    s0, s1 = _cum[i], _cum[i+1]
                    if dd <= s1 or i == len(_pts)-1:
                        a = _pts[i]
                        b = _pts[(i+1) % len(_pts)]
                        ln = s1 - s0
                        t = 0.0 if ln <= 1e-9 else (dd - s0) / ln
                        return (float(a[0]) + (float(b[0])-float(a[0])) * t,
                                float(a[1]) + (float(b[1])-float(a[1])) * t)
                return _pts[0]

            return {
                "length": total,
                "point_at": point_at,
                "item": None,
                "kind": kind,
                "skip_placement": False,
                "is_pad_walk": False,
                "closed": True,
            }

        def _build_unified_copper_boundary_primitives():
            poly = pcbnew.SHAPE_POLY_SET()
            layer = _selected_geometry_layer()
            try:
                max_error = int(board.GetDesignSettings().m_MaxError)
            except Exception:
                max_error = int(pcbnew.FromMM(0.005))
            max_error = max(1, max_error)
            errloc = _error_outside()

            # First union the ACTUAL copper shapes (track widths, arc widths and
            # selected PAD shapes are represented exactly by KiCad itself).
            for item in selected:
                try:
                    item.TransformShapeToPolygon(poly, item.GetLayer(), 0,
                                                 max_error, errloc, False)
                except TypeError:
                    item.TransformShapeToPolygon(poly, item.GetLayer(), 0,
                                                 max_error, errloc)

            for pad in selected_pads:
                try:
                    pad.TransformShapeToPolygon(poly, layer, 0,
                                                max_error, errloc, False)
                except TypeError:
                    pad.TransformShapeToPolygon(poly, layer, 0,
                                                max_error, errloc)

            _poly_simplify(poly)

            # Offset copper edge to VIA CENTRE trajectory. Track width / PAD size
            # is already inside the copper polygon, so only edge gap + via radius
            # is added here.
            _inflate_poly(poly, int(round(offset + radius)), max_error)
            _poly_simplify(poly)

            prims = []
            try:
                outline_count = int(poly.OutlineCount())
            except Exception:
                outline_count = 0

            for oi in range(outline_count):
                outline = None
                for getter in ("COutline", "Outline"):
                    if hasattr(poly, getter):
                        try:
                            outline = getattr(poly, getter)(oi)
                            break
                        except Exception:
                            pass
                if outline is not None:
                    prim = _closed_polyline_primitive(_poly_chain_points(outline),
                                                      "unified_outer_boundary")
                    if prim is not None:
                        prims.append(prim)

                # Holes are also real copper boundaries.  A closed selected track
                # loop has an inner and an outer fence side, so preserve holes as
                # independent closed trajectories.
                try:
                    hole_count = int(poly.HoleCount(oi))
                except Exception:
                    hole_count = 0
                for hi in range(hole_count):
                    try:
                        hole = poly.Hole(oi, hi)
                    except Exception:
                        continue
                    prim = _closed_polyline_primitive(_poly_chain_points(hole),
                                                      "unified_inner_boundary")
                    if prim is not None:
                        prims.append(prim)
            return prims

        def _draw_unified_boundary_preview(prims):
            if not DEBUG:
                return
            for prim in prims:
                for xy in _sample_primitive_points(prim, DEBUG_POINT_STEP_MM):
                    _add_user_drawing_point(xy, DEBUG_POINT_DIAMETER_MM)

        def _place_unified_boundary(prims):
            # Since the route was generated from the union of all selected copper,
            # selected copper itself is the owner geometry, not an obstacle.  The
            # offset construction already enforces Track-to-via gap exactly.
            selected_pad_ids = {board_item_identity(p) for p in selected_pads}
            placed = 0

            for prim in prims:
                targets = _closed_primitive_targets(prim)
                logical_index = 0

                for _p, target_xy, _station in targets:
                    # Unified-boundary staggered mode:
                    # --------------------------------
                    # The unified copper boundary is a single closed physical
                    # via-centre trajectory, so there are no longer independent
                    # LEFT/RIGHT native routes to choose between.  Staggering is
                    # therefore applied to the trajectory stations themselves:
                    # keep one station, skip the next, and repeat.  On the two
                    # long sides of an ordinary track this produces the expected
                    # staggered rows while preserving the exact same geometry,
                    # XY-spacing solver, PAD contours and T/X-junction boundary.
                    #
                    # A skipped/rejected station still advances logical_index so
                    # the pattern phase never shifts after an obstacle.
                    if cfg.staggered and (logical_index % 2 == 1):
                        logical_index += 1
                        continue

                    if try_place_regular_via(
                            target_xy[0], target_xy[1],
                            ignore_pad_ids=selected_pad_ids,
                            skip_selected_clearance=True):
                        placed += 1
                    else:
                        # Keep the same rejected-candidate visualization used by
                        # the continuous engine. The exact target remains a
                        # virtual anchor even when placement is rejected.
                        _add_rejected_candidate_marker(
                            target_xy,
                            reason=last_rejection_reason or "?",
                            diameter_mm=DEBUG_REJECTED_DIAMETER_MM,
                            line_width_mm=DEBUG_LINE_WIDTH_MM,
                        )

                    logical_index += 1

            return placed

        unified_prims = _build_unified_copper_boundary_primitives()
        if not unified_prims:
            wx.MessageBox(
                "Failed to build the unified copper boundary.\n\n"
                "The selected TRACK/ARC/PAD geometry could not be converted to a polygon.",
                "ViaFence",
                wx.OK | wx.ICON_ERROR
            )
            return

        _draw_unified_boundary_preview(unified_prims)
        _place_unified_boundary(unified_prims)

        # Include the configured via spacing in the group name so multiple
        # ViaFence results can be identified directly in the PCB tree.
        group_name = f"ViaFence ({net_name}) {display_length(cfg.spacing_mm, cfg.units)}"

        if created_vias or preview_shapes:
            group = pcbnew.PCB_GROUP(board)
            group.SetName(group_name)
            board.Add(group)

            # Keep both generated vias and their User.Drawings trajectory
            # together, so moving/deleting the ViaFence result acts on all
            # generated objects as one logical unit.
            for item in list(created_vias) + list(preview_shapes):
                try:
                    group.AddItem(item)
                except AttributeError:
                    group.Add(item)

        pcbnew.Refresh()

        if created_vias and cfg.show_stats:
            mode = "Staggered" if cfg.staggered else "Unified boundary"
            wx.MessageBox(
                f"ViaFence - Operation Complete\n\n"
                f"├─ Vias placed: {len(created_vias)}\n"
                f"├─ Mode: {mode}\n"
                f"├─ Net: {net_name}\n"
                f"├─ Selected pads: {len(selected_pads)}\n"
                f"├─ Branches/paths: {path_stats['branches']}\n"
                f"├─ Components: {path_stats['components']}\n"
                f"├─ T/junction nodes: {path_stats['junctions']}\n"
                f"├─ Closed loops: {path_stats['loops']}\n"
                f"├─ Skipped candidates: {skipped_candidates}\n"
                f"├─ Units: {cfg.units}\n"
                f"├─ Via spacing track: {display_length(cfg.spacing_mm, cfg.units)}\n"
                f"├─ Gap: {display_length(cfg.track_to_via_gap_mm, cfg.units)}\n"
                f"├─ Via diameter: {display_length(cfg.via_diameter_mm, cfg.units)}\n"
                f"├─ Via drill: {display_length(cfg.via_drill_mm, cfg.units)}\n"
                f"└─ Group: {group_name}",
                "ViaFence - Statistics",
                wx.OK | wx.ICON_INFORMATION
            )
        elif not created_vias:
            wx.MessageBox(
                "ViaFence - Warning\n\n"
                "No vias were placed.\n\n"
                "Possible reasons:\n"
                "• Collision with existing copper\n"
                "• Path/branches are too short\n"
                "• Clearance constraints prevent placement\n"
                "• Previous vias not removed",
                "ViaFence",
                wx.OK | wx.ICON_WARNING
            )

# Register the plugin
ViaFencePlugin().register()

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
import pcbnew


# ============================================================================
# Configuration
# ============================================================================

class ViaFenceConfig:
    """Configuration for via fence placement"""
    def __init__(self, spacing_mm=1.0, pad_spacing_mm=1.0, track_to_via_gap_mm=0.25, 
                 via_diameter_mm=0.6, via_drill_mm=0.3, 
                 end_margin_mm=0.5, staggered=False, net_name="",
                 show_stats=True, place_at_corners=True, corner_angle_deg=50, units="mm",
                 window_pos_x=None, window_pos_y=None):
        # spacing_mm is kept as the saved/backward-compatible track spacing value.
        self.spacing_mm = spacing_mm
        self.pad_spacing_mm = spacing_mm if pad_spacing_mm is None else pad_spacing_mm
        self.track_to_via_gap_mm = track_to_via_gap_mm
        self.via_diameter_mm = via_diameter_mm
        self.via_drill_mm = via_drill_mm
        self.end_margin_mm = end_margin_mm
        self.staggered = staggered
        self.net_name = net_name
        self.show_stats = show_stats
        self.place_at_corners = place_at_corners
        self.corner_angle_deg = corner_angle_deg
        self.units = units if units in ("mm", "mils") else "mm"
        self.window_pos_x = window_pos_x
        self.window_pos_y = window_pos_y


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "via_fence_cfg.json")
VIA_TIMESTAMP = 55  # Special timestamp to identify vias created by this plugin
PLUGIN_VERSION = "1.0.2"
MM_PER_MIL = 0.0254

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
                    pad_spacing_mm=data.get("pad_spacing_mm", data.get("spacing_mm", 1.0)),
                    track_to_via_gap_mm=data.get("track_to_via_gap_mm", 0.25),
                    via_diameter_mm=data.get("via_diameter_mm", 0.6),
                    via_drill_mm=data.get("via_drill_mm", 0.3),
                    end_margin_mm=data.get("end_margin_mm", 0.5),
                    staggered=data.get("staggered", False),
                    net_name=data.get("net_name", ""),
                    show_stats=data.get("show_stats", True),
                    place_at_corners=data.get("place_at_corners", True),
                    corner_angle_deg=data.get("corner_angle_deg", 50),
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
                "track_spacing_mm": cfg.spacing_mm,
                "pad_spacing_mm": cfg.pad_spacing_mm,
                "track_to_via_gap_mm": cfg.track_to_via_gap_mm,
                "via_diameter_mm": cfg.via_diameter_mm,
                "via_drill_mm": cfg.via_drill_mm,
                "end_margin_mm": cfg.end_margin_mm,
                "staggered": cfg.staggered,
                "net_name": cfg.net_name,
                "show_stats": cfg.show_stats,
                "place_at_corners": cfg.place_at_corners,
                "corner_angle_deg": cfg.corner_angle_deg,
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


def parse_mm_value(ctrl, label, min_value=0.0, allow_zero=False):
    """Backward-compatible helper: read a value as millimetres."""
    return parse_unit_value(ctrl, label, "mm", min_value, allow_zero)



# ============================================================================
# Dialog
# ============================================================================

class ViaFenceDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(parent, title=f"ViaFence {PLUGIN_VERSION}", size=(500, 590))
        icon_path = os.path.join(os.path.dirname(__file__), "via_fence_icon.png")
        if os.path.exists(icon_path):
            icon = wx.Icon(icon_path, wx.BITMAP_TYPE_PNG)
            self.SetIcon(icon)
        
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
        self.spacing = wx.TextCtrl(self, value=format_unit_value(cfg.spacing_mm))
        self.pad_spacing = wx.TextCtrl(self, value=format_unit_value(cfg.pad_spacing_mm))
        self.gap = wx.TextCtrl(self, value=format_unit_value(cfg.track_to_via_gap_mm))
        self.via_diam = wx.TextCtrl(self, value=format_unit_value(cfg.via_diameter_mm))
        self.drill = wx.TextCtrl(self, value=format_unit_value(cfg.via_drill_mm))
        self.margin = wx.TextCtrl(self, value=format_unit_value(cfg.end_margin_mm))
        self.staggered = wx.CheckBox(self, label="Staggered pattern (alternating sides)")
        self.staggered.SetValue(cfg.staggered)
        
        # Corner options
        self.place_corners = wx.CheckBox(self, label="Place vias at corners (outside of bends)")
        self.place_corners.SetValue(cfg.place_at_corners)
        self.corner_angle = wx.TextCtrl(self, value=str(cfg.corner_angle_deg))
        
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
        
        # Help text for staggered pattern
        help_text = wx.StaticText(self, label="  Staggered: places one via per position, alternating left/right")
        help_text.SetForegroundColour(wx.Colour(100, 100, 100))
        help_font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        help_text.SetFont(help_font)
        
        # Net selection
        self.net_choice = wx.Choice(self)
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
        self.pad_spacing_label = wx.StaticText(self, label="Via spacing pads (mm):")
        self.gap_label = wx.StaticText(self, label="Track to via gap (mm):")
        self.via_diam_label = wx.StaticText(self, label="Via diameter (mm):")
        self.drill_label = wx.StaticText(self, label="Via drill (mm):")
        self.margin_label = wx.StaticText(self, label="End margin (mm):")
        self._unit_label_controls = [
            (self.spacing_label, "Via spacing track"),
            (self.pad_spacing_label, "Via spacing pads"),
            (self.gap_label, "Track to via gap"),
            (self.via_diam_label, "Via diameter"),
            (self.drill_label, "Via drill"),
            (self.margin_label, "End margin"),
        ]
        self._unit_controls = [self.spacing, self.pad_spacing, self.gap, self.via_diam, self.drill, self.margin]

        self.apply_initial_units()
        self.update_unit_labels()

        fields = [
            (self.spacing_label, self.spacing),
            (self.pad_spacing_label, self.pad_spacing),
            (self.gap_label, self.gap),
            (self.via_diam_label, self.via_diam),
            (self.drill_label, self.drill),
            (self.margin_label, self.margin),
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
        vbox.Add(help_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Corner options
        corner_box = wx.StaticBoxSizer(wx.StaticBox(self, label="Corner Options"), wx.VERTICAL)
        corner_box.Add(self.place_corners, 0, wx.ALL, 5)
        angle_row = wx.BoxSizer(wx.HORIZONTAL)
        angle_row.Add(wx.StaticText(self, label="  Min corner angle (degrees):"), 0, wx.ALL | wx.CENTER, 5)
        angle_row.Add(self.corner_angle, 0, wx.ALL, 5)
        corner_box.Add(angle_row, 0, wx.EXPAND)
        vbox.Add(corner_box, 0, wx.EXPAND | wx.ALL, 5)
        
        vbox.Add(self.show_stats, 0, wx.ALL, 5)
        
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
        pad_spacing_mm = parse_unit_value(self.pad_spacing, "Via spacing pads", self.unit, 0.0)
        gap_mm = parse_unit_value(self.gap, "Track to via gap", self.unit, 0.0, allow_zero=True)
        via_diameter_mm = parse_unit_value(self.via_diam, "Via diameter", self.unit, 0.0)
        via_drill_mm = parse_unit_value(self.drill, "Via drill", self.unit, 0.0)
        end_margin_mm = parse_unit_value(self.margin, "End margin", self.unit, 0.0, allow_zero=True)
        corner_angle_deg = parse_mm_value(self.corner_angle, "Min corner angle", 0.0)

        if via_drill_mm >= via_diameter_mm:
            raise ValueError("Via drill must be smaller than via diameter")
        if corner_angle_deg >= 180:
            raise ValueError("Min corner angle must be less than 180 degrees")

        return ViaFenceConfig(
            spacing_mm=spacing_mm,
            pad_spacing_mm=pad_spacing_mm,
            track_to_via_gap_mm=gap_mm,
            via_diameter_mm=via_diameter_mm,
            via_drill_mm=via_drill_mm,
            end_margin_mm=end_margin_mm,
            staggered=self.staggered.GetValue(),
            net_name=net_name,
            show_stats=self.show_stats.GetValue(),
            place_at_corners=self.place_corners.GetValue(),
            corner_angle_deg=corner_angle_deg,
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


def get_line_slope(p1, p2):
    """Returns angle of line in radians"""
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])


def get_path_vertices(path, angle_tolerance_deg):
    """
    Find all vertices where the angle between segments exceeds tolerance.
    Returns list of vertex indices (1 to len(path)-2)
    """
    angle_tolerance = math.radians(angle_tolerance_deg)
    vertices = []
    
    for i in range(1, len(path) - 1):
        p_prev = (path[i-1].x, path[i-1].y)
        p_curr = (path[i].x, path[i].y)
        p_next = (path[i+1].x, path[i+1].y)
        
        slope1 = get_line_slope(p_curr, p_prev)
        slope2 = get_line_slope(p_next, p_curr)
        
        deviation = abs(slope1 - slope2)
        # Normalize to [0, pi]
        if deviation > math.pi:
            deviation = 2 * math.pi - deviation
        
        if deviation > angle_tolerance:
            vertices.append(i)
    
    return vertices


def get_outside_normal(p1, p2, p3):
    """
    Calculate the outside normal direction at vertex p2.
    Returns normalized vector (dx, dy) pointing to the outside of the bend.
    
    For a corner, the outside is the side where the via should go.
    For a 90-degree bend, the outside is at 45 degrees bisector outward.
    """
    # Vectors from p2 to p1 and p2 to p3
    v1 = (p1[0] - p2[0], p1[1] - p2[1])  # incoming
    v2 = (p3[0] - p2[0], p3[1] - p2[1])  # outgoing
    
    # Normalize
    len1 = math.hypot(v1[0], v1[1])
    len2 = math.hypot(v2[0], v2[1])
    
    if len1 < 1e-9 or len2 < 1e-9:
        return (0, 0)
    
    u1 = (v1[0] / len1, v1[1] / len1)
    u2 = (v2[0] / len2, v2[1] / len2)
    
    # Determine turn direction (cross product)
    cross = u1[0] * u2[1] - u1[1] * u2[0]
    
    # For a left turn, outside is to the right of incoming edge
    # For a right turn, outside is to the left of incoming edge
    if cross > 0:  # Left turn (CCW)
        outside = (u1[1], -u1[0])
    else:  # Right turn (CW)
        outside = (-u1[1], u1[0])
    
    # Normalize outside vector
    outside_len = math.hypot(outside[0], outside[1])
    if outside_len > 1e-9:
        outside = (outside[0] / outside_len, outside[1] / outside_len)
    
    return outside


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


def selected_copper_gap_ok(selected_items, pos, via_radius, track_gap, tolerance=None, board=None):
    """
    Ensure candidate via keeps the requested Track-to-via gap from the selected
    copper itself. The selected tracks/arcs are intentionally ignored by the
    spatial index, because they are the reference path, so they need this
    explicit check.

    This is especially important on arcs: polyline chord normals can put some
    vias slightly too close to the real curved track, which KiCad DRC then flags.
    """
    if tolerance is None:
        tolerance = pcbnew.FromMM(0.002)  # 2 um numerical tolerance

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
                px, py,
                item.GetStart().x, item.GetStart().y,
                item.GetEnd().x, item.GetEnd().y
            )
        else:
            continue

        if dist < required_center_distance - tolerance:
            return False

    return True


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
            if id(item) in ignore_pad_ids:
                continue

            if pad_collides_with_via(item, pos, radius, pad_required_gap):
                return False

    return True



# ============================================================================
# Selected pad ring placement helpers
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
ROUND_PAD_SEGMENT_MAX_MM = 0.08
ROUND_PAD_MIN_SEGMENTS = 64


def _vf_vec(x, y):
    return pcbnew.VECTOR2I(int(round(x)), int(round(y)))


def _vf_distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def _vf_remove_close_polygon_points(poly, min_dist=2):
    result = []
    for pt in poly:
        if not result or _vf_distance(result[-1], pt) > min_dist:
            result.append(pt)
    if len(result) > 1 and _vf_distance(result[0], result[-1]) <= min_dist:
        result.pop()
    return result


def _vf_polygon_area2(poly):
    area2 = 0
    if len(poly) < 3:
        return 0
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        area2 += a.x * b.y - b.x * a.y
    return area2


def _vf_line_intersection(p1, p2, p3, p4):
    x1, y1, x2, y2 = p1.x, p1.y, p2.x, p2.y
    x3, y3, x4, y4 = p3.x, p3.y, p4.x, p4.y
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return _vf_vec(px, py)


def _vf_arc_points_local(cx, cy, r, a1_deg, a2_deg, steps):
    result = []
    steps = max(1, int(steps))
    for i in range(steps + 1):
        t = i / float(steps)
        a = math.radians(a1_deg + (a2_deg - a1_deg) * t)
        result.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return result


def _vf_round_shape_segments(radius, arc_degrees=360.0):
    max_seg = max(1, int(pcbnew.FromMM(ROUND_PAD_SEGMENT_MAX_MM)))
    arc_len = abs(math.radians(arc_degrees) * max(radius, 1.0))
    return max(3, int(math.ceil(arc_len / float(max_seg))))


def _vf_pad_local_to_board_angle(center, x, y, angle_rad):
    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)
    return _vf_vec(center.x + x * ca - y * sa, center.y + x * sa + y * ca)


def vf_pad_polygon_outline(pad):
    """Approximate pad copper outline as a board-coordinate polygon."""
    center = pad.GetPosition()
    width = float(pad.GetSizeX())
    height = float(pad.GetSizeY())
    half_w = width / 2.0
    half_h = height / 2.0
    angle = _pad_angle_rad(pad)

    shape = None
    try:
        shape = pad.GetShape()
    except Exception:
        pass

    local = []
    segs = 12

    if shape == getattr(pcbnew, "PAD_SHAPE_CIRCLE", None):
        r = min(width, height) / 2.0
        n = max(ROUND_PAD_MIN_SEGMENTS, _vf_round_shape_segments(r, 360.0))
        local = [(math.cos(2 * math.pi * i / n) * r,
                  math.sin(2 * math.pi * i / n) * r) for i in range(n)]

    elif shape == getattr(pcbnew, "PAD_SHAPE_OVAL", None):
        if width >= height:
            r = half_h
            cx = half_w - r
            n = max(8, _vf_round_shape_segments(r, 180.0))
            local.extend(_vf_arc_points_local(cx, 0, r, -90, 90, n))
            local.extend(_vf_arc_points_local(-cx, 0, r, 90, 270, n))
        else:
            r = half_w
            cy = half_h - r
            n = max(8, _vf_round_shape_segments(r, 180.0))
            local.extend(_vf_arc_points_local(0, cy, r, 0, 180, n))
            local.extend(_vf_arc_points_local(0, -cy, r, 180, 360, n))

    elif shape == getattr(pcbnew, "PAD_SHAPE_ROUNDRECT", None):
        try:
            rr = float(pad.GetRoundRectRadiusRatio())
        except Exception:
            rr = 0.25
        r = max(0.0, min(width, height) * rr / 2.0)
        r = min(r, half_w, half_h)
        if r <= 1:
            local = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
        else:
            local.extend(_vf_arc_points_local(half_w - r, -half_h + r, r, -90, 0, segs))
            local.extend(_vf_arc_points_local(half_w - r, half_h - r, r, 0, 90, segs))
            local.extend(_vf_arc_points_local(-half_w + r, half_h - r, r, 90, 180, segs))
            local.extend(_vf_arc_points_local(-half_w + r, -half_h + r, r, 180, 270, segs))

    elif shape == getattr(pcbnew, "PAD_SHAPE_TRAPEZOID", None):
        dx = dy = 0
        try:
            d = pad.GetDelta()
            dx, dy = int(d.x), int(d.y)
        except Exception:
            pass
        local = [
            (-half_w - dx / 2.0, -half_h - dy / 2.0),
            (half_w + dx / 2.0, -half_h + dy / 2.0),
            (half_w - dx / 2.0, half_h - dy / 2.0),
            (-half_w + dx / 2.0, half_h + dy / 2.0),
        ]

    elif shape == getattr(pcbnew, "PAD_SHAPE_CHAMFERED_RECT", None):
        c = min(width, height) * 0.15
        local = [
            (-half_w + c, -half_h), (half_w - c, -half_h), (half_w, -half_h + c),
            (half_w, half_h - c), (half_w - c, half_h), (-half_w + c, half_h),
            (-half_w, half_h - c), (-half_w, -half_h + c),
        ]

    elif shape == getattr(pcbnew, "PAD_SHAPE_CUSTOM", None):
        try:
            poly = pad.GetEffectivePolygon()
            pts = []
            for i in range(poly.OutlineCount()):
                outline = poly.Outline(i)
                for j in range(outline.PointCount()):
                    pts.append(outline.CPoint(j))
            if pts:
                return _vf_remove_close_polygon_points(pts)
        except Exception:
            pass
        bb = pad.GetBoundingBox()
        x1, y1 = int(bb.GetX()), int(bb.GetY())
        x2, y2 = x1 + int(bb.GetWidth()), y1 + int(bb.GetHeight())
        return [_vf_vec(x1, y1), _vf_vec(x2, y1), _vf_vec(x2, y2), _vf_vec(x1, y2)]

    else:
        local = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]

    return _vf_remove_close_polygon_points([_vf_pad_local_to_board_angle(center, x, y, angle) for x, y in local])


def vf_offset_polygon_outward(poly, offset):
    """Offset a mostly-convex KiCad pad polygon outward by offset."""
    poly = _vf_remove_close_polygon_points(poly)
    n = len(poly)
    if n < 3:
        return list(poly)

    ccw = _vf_polygon_area2(poly) > 0
    offset_lines = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % n]
        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy)
        if length <= 1:
            continue
        if ccw:
            nx, ny = dy / length, -dx / length
        else:
            nx, ny = -dy / length, dx / length
        offset_lines.append((_vf_vec(a.x + nx * offset, a.y + ny * offset),
                             _vf_vec(b.x + nx * offset, b.y + ny * offset)))

    if len(offset_lines) < 3:
        return list(poly)

    result = []
    for i in range(len(offset_lines)):
        prev_a, prev_b = offset_lines[(i - 1) % len(offset_lines)]
        cur_a, cur_b = offset_lines[i]
        ip = _vf_line_intersection(prev_a, prev_b, cur_a, cur_b)
        result.append(ip if ip is not None else cur_a)
    return _vf_remove_close_polygon_points(result)


def vf_points_on_polygon(poly, spacing):
    """
    Uniformly sample a closed polygon perimeter.

    v33:
    The previous stitcher-style sampler restarted exactly on polygon vertices and
    could create visually dense via groups near rounded-rectangle/oval transition
    areas. This version samples by accumulated perimeter length with one global
    phase, so distance between neighbouring candidates stays even across corners.
    """
    if len(poly) < 2:
        return []

    spacing = max(1, int(spacing))

    edges = []
    perimeter = 0.0
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        seg_len = _vf_distance(a, b)
        if seg_len <= 1:
            continue
        edges.append((a, b, seg_len, perimeter))
        perimeter += seg_len

    if perimeter <= 1:
        return []

    count = max(1, int(math.floor(perimeter / float(spacing))))
    actual_spacing = perimeter / float(count)

    # Half-step phase avoids forcing candidates exactly onto polygon vertices.
    samples = [(i + 0.5) * actual_spacing for i in range(count)]

    result = []
    edge_idx = 0
    for s in samples:
        s = s % perimeter

        while edge_idx + 1 < len(edges) and s > edges[edge_idx][3] + edges[edge_idx][2]:
            edge_idx += 1

        a, b, seg_len, start_len = edges[edge_idx]
        t = (s - start_len) / seg_len
        t = max(0.0, min(1.0, t))
        result.append(_vf_vec(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t))

    return result


def vf_dedupe_points(points):
    out = []
    seen = set()
    for p in points:
        key = (int(p.x), int(p.y))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def vf_candidate_points_for_pad_polygon(pad, spacing, via_radius, pad_gap):
    outline = vf_pad_polygon_outline(pad)
    offset_outline = vf_offset_polygon_outward(outline, int(via_radius + pad_gap))
    return vf_dedupe_points(vf_points_on_polygon(offset_outline, spacing)), outline, offset_outline

def _pad_local_shape_distance(pad, px, py):
    """Distance from a local pad point to copper edge; 0 means inside."""
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

    return _distance_to_axis_rect(px, py, half_w, half_h)


def _pad_boundary_radius_in_direction(pad, theta):
    """
    Find distance from pad center to real pad outline in a local polar direction.
    Works for circular, oval, rectangular and rounded-rect pads without assuming
    the pad is round.
    """
    ux = math.cos(theta)
    uy = math.sin(theta)
    half_w = float(pad.GetSizeX()) / 2.0
    half_h = float(pad.GetSizeY()) / 2.0
    hi = max(half_w, half_h, 1.0) * 3.0

    # Ensure hi is outside the pad.
    for _ in range(12):
        if _pad_local_shape_distance(pad, ux * hi, uy * hi) > 0:
            break
        hi *= 2.0

    lo = 0.0
    for _ in range(32):
        mid = (lo + hi) * 0.5
        if _pad_local_shape_distance(pad, ux * mid, uy * mid) <= 0:
            lo = mid
        else:
            hi = mid
    return lo


def _pad_local_to_board(pad, lx, ly):
    """Convert local pad coordinates to board coordinates."""
    pp = pad.GetPosition()
    a = _pad_angle_rad(pad)
    ca = math.cos(a)
    sa = math.sin(a)
    return pcbnew.VECTOR2I(
        int(round(pp.x + lx * ca - ly * sa)),
        int(round(pp.y + lx * sa + ly * ca))
    )



def _pad_is_roundish(pad):
    """Return True for circular pads; non-round pads can use straight side rows."""
    try:
        shape = pad.GetShape()
        return shape == getattr(pcbnew, "PAD_SHAPE_CIRCLE", None)
    except Exception:
        return False


def _place_pad_straight_long_side_rows(pad, spacing, radius, offset, position_key,
                                       placed_positions, can_place_cb, make_via_cb):
    """
    Place additional vias along the two long straight sides of a non-circular pad.

    Unlike the radial ring sampler, this builds candidates on straight lines:
        x = from side start to side end
        y = pad edge +/- (via radius + gap)

    The points are generated in the pad local coordinate system and then rotated
    into board coordinates, so it works for rotated rectangular/rounded/oval pads.
    """
    try:
        if _pad_is_roundish(pad):
            return 0

        half_w = float(pad.GetSizeX()) / 2.0
        half_h = float(pad.GetSizeY()) / 2.0
        if half_w <= 0 or half_h <= 0:
            return 0

        # Long side direction in local coordinates.
        if half_w >= half_h:
            long_half = half_w
            short_half = half_h
            horizontal = True
        else:
            long_half = half_h
            short_half = half_w
            horizontal = False

        # Do not try side rows for nearly square pads.
        if long_half < short_half * 1.25:
            return 0

        # Keep endpoints inside the straight part and away from rounded ends/corners.
        # For rounded-rect/oval pads this avoids the curved cap regions.
        end_inset = max(float(radius + offset), float(spacing) * 0.5, short_half * 0.35)
        start = -long_half + end_inset
        end = long_half - end_inset
        usable = end - start
        if usable <= 1.0:
            return 0

        count = max(2, int(math.ceil(usable / max(spacing, 1))) + 1)
        if count <= 1:
            return 0

        placed = 0
        for side in (-1, 1):
            for i in range(count):
                t = i / (count - 1)
                along = start + usable * t
                normal = side * (short_half + float(radius) + float(offset))

                if horizontal:
                    lx, ly = along, normal
                else:
                    lx, ly = normal, along

                pos = _pad_local_to_board(pad, lx, ly)
                pos_key = position_key(pos.x, pos.y)
                if pos_key in placed_positions:
                    continue

                if can_place_cb(pos):
                    placed_positions.add(pos_key)
                    make_via_cb(pos)
                    placed += 1

        return placed
    except Exception:
        return 0


def _estimate_pad_ring_radius(pad, via_radius, pad_gap):
    half_w = float(pad.GetSizeX()) / 2.0
    half_h = float(pad.GetSizeY()) / 2.0
    return max(half_w, half_h) + float(via_radius) + float(pad_gap)


def _pad_long_side_points(pad, via_radius, pad_gap, spacing):
    """
    Return additional local-coordinate candidate points along the two long sides
    of elongated non-round pads.

    The radial pad ring works well for round pads, but on long oval/rect pads
    angular sampling can leave the long straight sides visually under-filled.
    These supplemental points are generated in pad-local coordinates and then
    still pass the normal collision/DRC checks before a via is created.
    """
    half_w = float(pad.GetSizeX()) / 2.0
    half_h = float(pad.GetSizeY()) / 2.0
    if half_w <= 0 or half_h <= 0:
        return []

    # Do not add side-fill for nearly round/square pads.
    long_side = max(half_w, half_h)
    short_side = min(half_w, half_h)
    if short_side <= 0 or (long_side / short_side) < 1.35:
        return []

    spacing = max(float(spacing), 1.0)
    clearance_from_edge = float(via_radius) + float(pad_gap)
    points = []

    def even_axis_positions(start, end):
        length = end - start
        if length <= spacing * 1.25:
            return []
        intervals = max(1, int(math.ceil(length / spacing)))
        pitch = length / intervals
        return [start + pitch * i for i in range(intervals + 1)]

    shape = None
    try:
        shape = pad.GetShape()
    except Exception:
        pass

    oval_shape = getattr(pcbnew, "PAD_SHAPE_OVAL", None)
    roundrect_shape = getattr(pcbnew, "PAD_SHAPE_ROUNDRECT", None)

    if half_w >= half_h:
        # Horizontal elongated pad.  For oval pads the straight side starts after
        # the semicircular end caps, so avoid the rounded ends.  For rect and
        # rounded-rect pads, staying one short-half inside the ends also prevents
        # crowding at the corners where the radial ring already places vias.
        inset = half_h
        if shape == roundrect_shape:
            inset = max(inset, _pad_roundrect_radius(pad, half_w, half_h))
        x_positions = even_axis_positions(-half_w + inset, half_w - inset)
        y = half_h + clearance_from_edge
        for x in x_positions:
            points.append((x, y))
            points.append((x, -y))
    else:
        # Vertical elongated pad.
        inset = half_w
        if shape == roundrect_shape:
            inset = max(inset, _pad_roundrect_radius(pad, half_w, half_h))
        y_positions = even_axis_positions(-half_h + inset, half_h - inset)
        x = half_w + clearance_from_edge
        for y in y_positions:
            points.append((x, y))
            points.append((-x, y))

    return points

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
        pad_spacing = pcbnew.FromMM(cfg.pad_spacing_mm)
        offset = pcbnew.FromMM(cfg.track_to_via_gap_mm)
        via_diam = pcbnew.FromMM(cfg.via_diameter_mm)
        drill = pcbnew.FromMM(cfg.via_drill_mm)
        margin = pcbnew.FromMM(cfg.end_margin_mm)
        radius = via_diam / 2
        pad_gap = offset  # via edge to pad edge must be at least Track-to-via gap

        if spacing <= 0 or pad_spacing <= 0 or via_diam <= 0 or drill <= 0:
            wx.MessageBox(
                "Via spacing track, via spacing pads, via diameter and drill must be positive values.",
                "ViaFence - Invalid input",
                wx.OK | wx.ICON_ERROR
            )
            return

        track_width = pcbnew.FromMM(0.25)
        for item in selected:
            if hasattr(item, 'GetWidth') and item.GetWidth() > 0:
                track_width = item.GetWidth()
                break

        effective_offset = offset + radius + track_width / 2
        collision_index = CollisionIndex(board, selected, radius)

        created_vias = []
        placed_positions = set()
        corner_positions = set()
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

        def place_corner_via(p2, direction, corner_angle_deg):
            nonlocal skipped_candidates

            dx, dy = direction
            norm = math.hypot(dx, dy)
            if norm < 1e-9:
                return False

            dx /= norm
            dy /= norm

            if corner_angle_deg < 60:
                offset_mult = 2.0
            elif corner_angle_deg < 90:
                offset_mult = 1.7
            elif corner_angle_deg < 120:
                offset_mult = 1.4
            else:
                offset_mult = 1.2

            target_x = int(p2.x + dx * effective_offset * offset_mult)
            target_y = int(p2.y + dy * effective_offset * offset_mult)
            pos_key = position_key(target_x, target_y)
            if pos_key in placed_positions:
                return False

            pos = pcbnew.VECTOR2I(target_x, target_y)
            if (selected_copper_gap_ok(selected, pos, radius, offset, board=board) and
                    can_place_via(collision_index, pos, radius, pad_gap)):
                placed_positions.add(pos_key)
                make_via(pos)
                return True

            skipped_candidates += 1
            return False

        def place_selected_pad_ring(pad):
            """
            Place vias around a selected pad.

            CIRCLE pads use the old/legacy radial algorithm only.
            All other supported pad shapes use the Pad Via Stitcher v005
            polygon-offset algorithm:
                real pad outline -> outward offset by gap + via radius -> points on polygon.
            """
            nonlocal skipped_candidates, via_index

            placed = 0

            def try_place_pad_ring_candidate_board(pos):
                nonlocal skipped_candidates, placed
                pos_key = position_key(pos.x, pos.y)
                if pos_key in placed_positions:
                    return False

                if can_place_via(
                        collision_index,
                        pos,
                        radius,
                        pad_gap,
                        ignore_item_ids={id(pad)},
                        ignore_pad_ids={id(pad)}):
                    placed_positions.add(pos_key)
                    make_via(pos)
                    placed += 1
                    return True

                skipped_candidates += 1
                return False

            def try_place_pad_ring_candidate_local(local_x, local_y):
                return try_place_pad_ring_candidate_board(
                    _pad_local_to_board(pad, local_x, local_y)
                )

            # IMPORTANT:
            # Keep circular pads on the old ideal radial sampler only.
            # Do not pass CIRCLE pads through polygon outline / polygon offset,
            # otherwise the circle receives two different candidate sets.
            try:
                is_circle_pad = pad.GetShape() == getattr(pcbnew, "PAD_SHAPE_CIRCLE", None)
            except Exception:
                is_circle_pad = False

            if is_circle_pad:
                ring_r = _estimate_pad_ring_radius(pad, radius, offset)
                count = max(8, int(math.ceil((2.0 * math.pi * ring_r) / max(pad_spacing, 1))))

                # Same phase/jitter style as the old v29 algorithm.
                base_phase = math.pi / max(count, 1)
                local_jitter = [0.0, 0.25, -0.25, 0.5, -0.5]

                for i in range(count):
                    theta0 = base_phase + (2.0 * math.pi * i / count)
                    for j in local_jitter:
                        theta = theta0 + j * (2.0 * math.pi / count)
                        boundary_r = _pad_boundary_radius_in_direction(pad, theta)
                        candidate_r = boundary_r + radius + offset
                        x = candidate_r * math.cos(theta)
                        y = candidate_r * math.sin(theta)
                        if try_place_pad_ring_candidate_local(x, y):
                            break
                    via_index += 1

                return placed

            # Non-circular pads: new Pad Via Stitcher polygon-offset algorithm.
            candidates, outline, offset_outline = vf_candidate_points_for_pad_polygon(
                pad,
                pad_spacing,
                radius,
                offset
            )

            for pos in candidates:
                if try_place_pad_ring_candidate_board(pos):
                    via_index += 1

            return placed

        # 1. Selected-pad vias first.
        #
        # Build via rings around selected pads before any track/arc fence vias.
        # make_via() immediately adds each created pad-ring via to collision_index,
        # so all later corner/regular/transition vias around tracks see these vias
        # as real obstacles and keep proper clearance from them.
        via_index = 0
        pad_ring_vias = 0
        for pad in selected_pads:
            pad_ring_vias += place_selected_pad_ring(pad)

        # 2. Corner vias for every independent branch/path.
        if cfg.place_at_corners:
            for path in paths:
                if len(path) < 3:
                    continue

                corner_indices = get_path_vertices(path, cfg.corner_angle_deg)
                for idx in corner_indices:
                    p1 = path[idx - 1]
                    p2 = path[idx]
                    p3 = path[idx + 1]

                    p1_f = (p1.x, p1.y)
                    p2_f = (p2.x, p2.y)
                    p3_f = (p3.x, p3.y)

                    v1 = (p1_f[0] - p2_f[0], p1_f[1] - p2_f[1])
                    v2 = (p3_f[0] - p2_f[0], p3_f[1] - p2_f[1])
                    len1 = math.hypot(v1[0], v1[1])
                    len2 = math.hypot(v2[0], v2[1])
                    if len1 > 0 and len2 > 0:
                        dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)
                        dot = max(-1, min(1, dot))
                        corner_angle = math.degrees(math.acos(dot))
                    else:
                        corner_angle = 180

                    outside_dir = get_outside_normal(p1_f, p2_f, p3_f)
                    if outside_dir != (0, 0) and place_corner_via(p2, outside_dir, corner_angle):
                        corner_positions.add(position_key(p2.x, p2.y))

        # 3. Regular track/arc vias.
        #
        # v5 change:
        #   Regular placement is now generated from the native selected items, not
        #   from the path polyline.  This is important for PCB_ARC items: the old
        #   polyline approach used chord normals, so on smooth/rounded tracks some
        #   candidates were slightly too close to the real arc and were rejected by
        #   the new DRC-safe selected_copper_gap_ok() check.
        #
        #   For arcs we place directly on concentric offset arcs:
        #       outer radius = arc_radius + effective_offset
        #       inner radius = arc_radius - effective_offset
        #   and we do not use longitudinal shift retries.  This keeps the requested
        #   Track-to-via gap constant along the real curved track and prevents the
        #   "random missing vias" visible on rounded sections.
        def try_place_regular_via(x, y):
            nonlocal skipped_candidates
            pos_key = position_key(x, y)
            if pos_key in placed_positions:
                return False

            pos = pcbnew.VECTOR2I(int(round(x)), int(round(y)))
            if (selected_copper_gap_ok(selected, pos, radius, offset, board=board) and
                    can_place_via(collision_index, pos, radius, pad_gap)):
                placed_positions.add(pos_key)
                make_via(pos)
                return True

            skipped_candidates += 1
            return False

        def even_positions(total_len, requested_spacing, end_margin):
            """
            Return evenly distributed positions along a line/arc length.

            The old algorithm always started at end_margin and then added the
            requested spacing.  That leaves an uneven leftover at the end and is
            very visible near arc-to-straight transitions.  This helper uses the
            whole available length and slightly adjusts the pitch so the first
            and last via rows are balanced.
            """
            if total_len <= 1e-6:
                return [], requested_spacing

            usable = total_len - 2 * end_margin
            if usable <= 1e-6:
                return [total_len / 2.0], total_len

            if requested_spacing <= 1e-6:
                return [end_margin], usable

            # Use ceil so the real pitch is never larger than the requested
            # spacing.  This keeps the fence dense enough while removing the
            # short/long gap at the ends.
            intervals = max(1, int(math.ceil(usable / requested_spacing)))
            pitch = usable / intervals
            return [end_margin + pitch * i for i in range(intervals + 1)], pitch

        def retry_shifts(real_pitch, max_fraction=0.55):
            """
            Candidate shifts around the ideal position.

            v9: the previous arc-native placement only retried up to about
            0.30-0.36 pitch.  At straight-to-arc junctions, the first arc
            candidate can collide with the last straight candidate.  Allowing
            retries up to about half a pitch lets the via move to the nearest
            free, DRC-safe point instead of being skipped, while still keeping
            the row visually even.
            """
            if real_pitch <= 0:
                return [0]
            fractions = [0, 0.08, -0.08, 0.16, -0.16, 0.24, -0.24,
                         0.32, -0.32, 0.40, -0.40, 0.48, -0.48,
                         max_fraction, -max_fraction]
            seen = set()
            out = []
            for f in fractions:
                val = real_pitch * f
                key = int(round(val))
                if key not in seen:
                    seen.add(key)
                    out.append(val)
            return out

        def place_on_track_segment(track, local_via_index):
            nonlocal skipped_candidates
            p1, p2 = track.GetStart(), track.GetEnd()
            dx, dy = p2.x - p1.x, p2.y - p1.y
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-6:
                return local_via_index

            ux, uy = dx / seg_len, dy / seg_len
            px_vec, py_vec = -uy, ux

            positions, real_pitch = even_positions(seg_len, spacing, margin)
            if not positions:
                return local_via_index

            # Straight tracks may retry a little along the segment when a pad or
            # existing via blocks the exact balanced position.  The retry range
            # is based on the real balanced pitch, not the original spacing.
            shifts = retry_shifts(real_pitch, 0.55)

            edge_margin = min(margin, real_pitch * 0.35)

            for next_pos in positions:
                base_x = p1.x + ux * next_pos
                base_y = p1.y + uy * next_pos

                if cfg.staggered:
                    sides_to_try = [-1 if (local_via_index % 2 == 0) else 1]
                else:
                    sides_to_try = [-1, 1]

                for side in sides_to_try:
                    placed_this_side = False
                    for shift in shifts:
                        shifted_pos = next_pos + shift
                        if shifted_pos < edge_margin or shifted_pos > seg_len - edge_margin:
                            continue
                        x = p1.x + ux * shifted_pos + px_vec * effective_offset * side
                        y = p1.y + uy * shifted_pos + py_vec * effective_offset * side
                        if try_place_regular_via(x, y):
                            placed_this_side = True
                            break
                    if not placed_this_side:
                        skipped_candidates += 1

                local_via_index += 1

            return local_via_index

        def place_on_arc_native(arc, local_via_index):
            nonlocal skipped_candidates
            geom = get_arc_geometry(arc)
            if geom is None:
                # Fallback for unusual KiCad builds: treat the arc as a set of
                # short straight sections, but this path should rarely be used.
                poly = arc_to_polyline(arc, max_segment_deg=1)
                for i in range(len(poly) - 1):
                    tmp = type('TmpTrack', (), {})()
                    tmp.GetStart = lambda p=poly[i]: p
                    tmp.GetEnd = lambda p=poly[i + 1]: p
                    local_via_index = place_on_track_segment(tmp, local_via_index)
                return local_via_index

            cx, cy, arc_radius, start_angle, sweep = geom
            if abs(sweep) < 1e-9 or arc_radius <= 1e-6:
                return local_via_index

            # v8:
            #   Distribute vias evenly on the real offset curves, not on the
            #   centreline.  The outside row and inside row have different radii,
            #   therefore they also have different arc lengths and need their own
            #   balanced pitch.  This gives a visually uniform fence on rounded
            #   tracks while preserving the DRC-safe selected_copper_gap_ok() and
            #   pad-shape clearance checks.
            sweep_sign = 1 if sweep >= 0 else -1

            if cfg.staggered:
                # In staggered mode there is only one row at each centreline
                # station.  Keep the centreline distribution, but compute the
                # actual point on the chosen offset radius.
                center_len = abs(sweep) * arc_radius
                positions, real_pitch = even_positions(center_len, spacing, margin)
                shifts = retry_shifts(real_pitch, 0.55)
                edge_margin = min(margin, real_pitch * 0.35)

                for center_pos in positions:
                    side = -1 if (local_via_index % 2 == 0) else 1
                    candidate_radius = arc_radius + effective_offset * side
                    if candidate_radius <= radius:
                        skipped_candidates += 1
                        local_via_index += 1
                        continue

                    placed = False
                    for arc_shift in shifts:
                        shifted_center_pos = center_pos + arc_shift
                        if shifted_center_pos < edge_margin or shifted_center_pos > center_len - edge_margin:
                            continue
                        angle = start_angle + sweep_sign * (shifted_center_pos / arc_radius)
                        x = cx + math.cos(angle) * candidate_radius
                        y = cy + math.sin(angle) * candidate_radius
                        if try_place_regular_via(x, y):
                            placed = True
                            break
                    if not placed:
                        skipped_candidates += 1
                    local_via_index += 1

                return local_via_index

            # Dual-side mode: each side is its own real offset arc with balanced
            # pitch.  This avoids the visual compression on the inner radius and
            # stretching on the outer radius.
            for side in (-1, 1):
                candidate_radius = arc_radius + effective_offset * side
                if candidate_radius <= radius:
                    skipped_candidates += 1
                    continue

                offset_len = abs(sweep) * candidate_radius
                positions, real_pitch = even_positions(offset_len, spacing, margin)
                if not positions:
                    continue

                shifts = retry_shifts(real_pitch, 0.55)
                edge_margin = min(margin, real_pitch * 0.35)

                for offset_pos in positions:
                    placed = False
                    for arc_shift in shifts:
                        shifted_offset_pos = offset_pos + arc_shift
                        if shifted_offset_pos < edge_margin or shifted_offset_pos > offset_len - edge_margin:
                            continue

                        angle = start_angle + sweep_sign * (shifted_offset_pos / candidate_radius)
                        x = cx + math.cos(angle) * candidate_radius
                        y = cy + math.sin(angle) * candidate_radius
                        if try_place_regular_via(x, y):
                            placed = True
                            break

                    if not placed:
                        skipped_candidates += 1

            # Keep the global index roughly in sync for the next selected item.
            # Exact value is only important for staggered mode, which returned
            # above after incrementing per logical position.
            local_via_index += max(1, int(math.ceil((abs(sweep) * arc_radius) / spacing)))
            return local_via_index


        def endpoint_normal_candidates(item, endpoint_key):
            """Return candidate outward normals at one endpoint of a selected item.

            This is used only to fill small visual gaps at smooth transitions
            between two selected items, for example straight -> arc.  Regular
            placement still handles the main rows.
            """
            try:
                if isinstance(item, pcbnew.PCB_ARC):
                    geom = get_arc_geometry(item)
                    if geom is None:
                        return []
                    cx, cy, arc_radius, _start_angle, _sweep = geom
                    if endpoint_key == point_key(item.GetStart()):
                        p = item.GetStart()
                    elif endpoint_key == point_key(item.GetEnd()):
                        p = item.GetEnd()
                    else:
                        return []

                    rx = float(p.x) - cx
                    ry = float(p.y) - cy
                    rl = math.hypot(rx, ry)
                    if rl < 1e-9:
                        return []
                    nx = rx / rl
                    ny = ry / rl
                    # side +1 = outside radial, side -1 = inside radial
                    return [(nx, ny), (-nx, -ny)]

                if isinstance(item, pcbnew.PCB_TRACK):
                    a = item.GetStart()
                    b = item.GetEnd()
                    if endpoint_key == point_key(a):
                        dx = float(b.x - a.x)
                        dy = float(b.y - a.y)
                    elif endpoint_key == point_key(b):
                        dx = float(a.x - b.x)
                        dy = float(a.y - b.y)
                    else:
                        return []
                    dl = math.hypot(dx, dy)
                    if dl < 1e-9:
                        return []
                    ux = dx / dl
                    uy = dy / dl
                    return [(-uy, ux), (uy, -ux)]
            except Exception:
                return []
            return []

        def endpoint_offset_points(item, endpoint_key, distance_along):
            """Candidate via points near a selected-item endpoint.

            v11: the visible hole is often not exactly at the mathematical
            straight/arc endpoint.  It is usually half a pitch before or after
            the transition because the straight segment and the arc each balance
            their own spacing independently.  This helper returns DRC-checked
            candidate points a short distance *inside* each connected item on
            both offset rows.
            """
            out = []
            try:
                if isinstance(item, pcbnew.PCB_ARC):
                    geom = get_arc_geometry(item)
                    if geom is None:
                        return out
                    cx, cy, arc_radius, start_angle, sweep = geom
                    if abs(sweep) < 1e-9 or arc_radius <= 1e-6:
                        return out
                    sweep_sign = 1 if sweep >= 0 else -1

                    if endpoint_key == point_key(item.GetStart()):
                        base_angle = start_angle
                        dir_sign = sweep_sign       # move from start into arc
                    elif endpoint_key == point_key(item.GetEnd()):
                        base_angle = start_angle + sweep
                        dir_sign = -sweep_sign      # move from end back into arc
                    else:
                        return out

                    for side in (-1, 1):
                        rr = arc_radius + effective_offset * side
                        if rr <= radius:
                            continue
                        angle = base_angle + dir_sign * (distance_along / rr)
                        out.append((cx + math.cos(angle) * rr,
                                    cy + math.sin(angle) * rr))

                elif isinstance(item, pcbnew.PCB_TRACK):
                    a = item.GetStart()
                    b = item.GetEnd()
                    if endpoint_key == point_key(a):
                        tx = float(b.x - a.x)
                        ty = float(b.y - a.y)
                        ex, ey = float(a.x), float(a.y)
                    elif endpoint_key == point_key(b):
                        tx = float(a.x - b.x)
                        ty = float(a.y - b.y)
                        ex, ey = float(b.x), float(b.y)
                    else:
                        return out
                    tl = math.hypot(tx, ty)
                    if tl < 1e-9:
                        return out
                    ux = tx / tl
                    uy = ty / tl
                    nx1, ny1 = -uy, ux
                    nx2, ny2 = uy, -ux
                    bx = ex + ux * distance_along
                    by = ey + uy * distance_along
                    out.append((bx + nx1 * effective_offset, by + ny1 * effective_offset))
                    out.append((bx + nx2 * effective_offset, by + ny2 * effective_offset))
            except Exception:
                return []
            return out

        def fill_transition_gaps():
            """Fill visual holes at smooth selected-item junctions.

            v10 tried only the exact shared endpoint.  v11 additionally probes
            several distances into both connected items (roughly 0.25...0.75 of
            the pitch).  This fills the common straight->arc gap while preserving
            DRC safety because every point still goes through try_place_regular_via().
            """
            endpoint_map = {}
            for it in selected:
                try:
                    endpoint_map.setdefault(point_key(it.GetStart()), []).append(it)
                    endpoint_map.setdefault(point_key(it.GetEnd()), []).append(it)
                except Exception:
                    pass

            # v12:
            #   Transition holes can be smaller than the requested Via spacing.
            #   The requested spacing is therefore treated as the normal pitch,
            #   not as a hard minimum near straight/arc transitions.
            #
            #   We scan many local positions around the shared endpoint.  A via
            #   is still placed only if KiCad-clearance checks pass, so this may
            #   create a locally smaller pitch than "Via spacing", but it will
            #   not violate DRC copper/via clearance.
            probe_fractions = [
                0.00,
                0.12, 0.18, 0.24, 0.30,
                0.36, 0.42, 0.48, 0.54, 0.60,
                0.66, 0.72, 0.78, 0.84, 0.90,
                1.00, 1.10, 1.20,
            ]
            probe_distances = [spacing * f for f in probe_fractions]

            for ep_key, items_at_ep in endpoint_map.items():
                unique_items = []
                seen_ids = set()
                for it in items_at_ep:
                    if id(it) not in seen_ids:
                        seen_ids.add(id(it))
                        unique_items.append(it)
                if len(unique_items) < 2:
                    continue

                ex, ey = ep_key

                # 1) Original endpoint bridge using averaged normals.
                candidates = []
                for i in range(len(unique_items)):
                    for j in range(i + 1, len(unique_items)):
                        normals_a = endpoint_normal_candidates(unique_items[i], ep_key)
                        normals_b = endpoint_normal_candidates(unique_items[j], ep_key)
                        for na in normals_a:
                            for nb in normals_b:
                                dot = na[0] * nb[0] + na[1] * nb[1]
                                if dot < 0.35:
                                    continue
                                ax = na[0] + nb[0]
                                ay = na[1] + nb[1]
                                al = math.hypot(ax, ay)
                                if al < 1e-9:
                                    continue
                                candidates.append((ax / al, ay / al, dot))

                candidates.sort(key=lambda v: v[2], reverse=True)
                tried_normals = set()
                for nx, ny, _dot in candidates:
                    nkey = (int(round(nx * 1000)), int(round(ny * 1000)))
                    if nkey in tried_normals:
                        continue
                    tried_normals.add(nkey)
                    for scale in (1.0, 1.08, 1.16, 1.25):
                        if try_place_regular_via(ex + nx * effective_offset * scale,
                                                 ey + ny * effective_offset * scale):
                            break

                # 2) New v11 local probes around the transition.  These do not
                # force placement; they only add a via where the spacing to
                # existing vias and copper clearances allow it.
                tried_points = set()
                for d in probe_distances[1:]:
                    for it in unique_items:
                        for x, y in endpoint_offset_points(it, ep_key, d):
                            pkey = (int(round(x / pcbnew.FromMM(0.05))),
                                    int(round(y / pcbnew.FromMM(0.05))))
                            if pkey in tried_points:
                                continue
                            tried_points.add(pkey)

                            # Try the exact candidate first.  If it is blocked by
                            # an already-created via, try small local nudges along
                            # both connected items.  This keeps the fill local and
                            # can intentionally make the local pitch smaller than
                            # the requested Via spacing, but never smaller than
                            # the real DRC clearance because try_place_regular_via()
                            # still calls can_place_via().
                            if try_place_regular_via(x, y):
                                continue

                            for extra in (spacing * 0.05, -spacing * 0.05,
                                          spacing * 0.10, -spacing * 0.10):
                                for xx, yy in endpoint_offset_points(it, ep_key, max(0, d + extra)):
                                    ppkey = (int(round(xx / pcbnew.FromMM(0.05))),
                                             int(round(yy / pcbnew.FromMM(0.05))))
                                    if ppkey in tried_points:
                                        continue
                                    tried_points.add(ppkey)
                                    if try_place_regular_via(xx, yy):
                                        break



        def fill_large_local_gaps():
            """Add optional extra vias only where the visual row gap is too large.

            v13:
              Normal Via spacing is still used for the main distribution.
              This pass samples half-pitch positions on the selected tracks/arcs.
              A via is added only if the full DRC-safe checks pass, so local pitch
              may become smaller than the requested Via spacing, but never smaller
              than the real copper/via clearance.

              This is mainly for the inside row of bends where the balanced arc row
              can leave a 1.3...1.5x visual gap near the straight/arc transition.
            """
            if spacing <= 0:
                return

            sample_step = max(spacing * 0.50, radius * 0.75)
            if sample_step <= 1:
                return

            def try_dense_candidate(x, y):
                # Same DRC-safe placement path as normal vias.
                return try_place_regular_via(x, y)

            for it in selected:
                try:
                    if isinstance(it, pcbnew.PCB_ARC):
                        geom = get_arc_geometry(it)
                        if geom is None:
                            continue
                        cx, cy, arc_radius, start_angle, sweep = geom
                        if abs(sweep) < 1e-9 or arc_radius <= 1e-6:
                            continue

                        for side in (-1, 1):
                            rr = arc_radius + effective_offset * side
                            if rr <= radius:
                                continue
                            total_len = abs(sweep) * rr
                            if total_len <= sample_step:
                                continue

                            # Do not force endpoints; those are handled by transition fill.
                            d = sample_step * 0.5
                            while d < total_len - sample_step * 0.5:
                                a = start_angle + (sweep / abs(sweep)) * (d / rr)
                                x = cx + math.cos(a) * rr
                                y = cy + math.sin(a) * rr
                                if try_dense_candidate(x, y):
                                    # Once inserted, the collision index is updated by make_via().
                                    pass
                                d += sample_step

                    elif isinstance(it, pcbnew.PCB_TRACK):
                        p1, p2 = it.GetStart(), it.GetEnd()
                        dx, dy = p2.x - p1.x, p2.y - p1.y
                        seg_len = math.hypot(dx, dy)
                        if seg_len <= sample_step:
                            continue
                        ux, uy = dx / seg_len, dy / seg_len
                        nx, ny = -uy, ux

                        d = sample_step * 0.5
                        while d < seg_len - sample_step * 0.5:
                            bx = p1.x + ux * d
                            by = p1.y + uy * d
                            for side in (-1, 1):
                                x = bx + nx * effective_offset * side
                                y = by + ny * effective_offset * side
                                if try_dense_candidate(x, y):
                                    pass
                            d += sample_step
                except Exception:
                    continue



        def fill_largest_row_gaps():
            """Targeted final pass: split only visibly-too-large gaps in each via row.

            v14:
              The v13 half-pitch sampler can miss a gap if the sample grid is not
              aligned with the actual placed row.  This pass looks at the vias that
              were really created, projects them onto each selected track/arc offset
              row, finds neighbouring vias whose row-distance is too large, and
              tries to place one new via at the midpoint of that exact gap.

              This is especially useful on the inner side of a bend.  It can create
              a local pitch smaller than the requested Via spacing, but every
              candidate still goes through try_place_regular_via(), so via-via,
              via-track and via-pad clearances remain protected.
            """
            if spacing <= 0:
                return

            max_allowed_gap = spacing * 1.18
            row_tolerance = max(radius * 1.75, spacing * 0.28)
            endpoint_ignore = max(margin * 0.25, spacing * 0.10)

            def norm_angle(a):
                while a < 0:
                    a += 2 * math.pi
                while a >= 2 * math.pi:
                    a -= 2 * math.pi
                return a

            def angular_delta(start, angle, sweep_sign):
                if sweep_sign >= 0:
                    return (norm_angle(angle) - norm_angle(start)) % (2 * math.pi)
                return (norm_angle(start) - norm_angle(angle)) % (2 * math.pi)

            def try_split_gap_at(param_to_xy, a, b):
                gap = b - a
                if gap <= max_allowed_gap:
                    return False

                # Try midpoint first; if blocked, try slight offsets around it.
                # For a 1.4 mm gap and 1.0 mm requested spacing, midpoint gives
                # about 0.7 mm to neighbours, which is often DRC-safe with 0.4 mm
                # vias and 0.2 mm clearance.
                for frac in (0.50, 0.44, 0.56, 0.38, 0.62, 0.32, 0.68):
                    d = a + gap * frac
                    x, y = param_to_xy(d)
                    if try_place_regular_via(x, y):
                        return True
                return False

            for it in selected:
                try:
                    if isinstance(it, pcbnew.PCB_ARC):
                        geom = get_arc_geometry(it)
                        if geom is None:
                            continue
                        cx, cy, arc_radius, start_angle, sweep = geom
                        if abs(sweep) < 1e-9 or arc_radius <= 1e-6:
                            continue
                        sweep_sign = 1 if sweep >= 0 else -1

                        for side in (-1, 1):
                            rr = arc_radius + effective_offset * side
                            if rr <= radius:
                                continue
                            total_len = abs(sweep) * rr
                            row_params = []
                            for via in created_vias:
                                vp = via.GetPosition()
                                vx = float(vp.x) - cx
                                vy = float(vp.y) - cy
                                vr = math.hypot(vx, vy)
                                if abs(vr - rr) > row_tolerance:
                                    continue
                                a = math.atan2(vy, vx)
                                delta = angular_delta(start_angle, a, sweep_sign)
                                if delta < -1e-9 or delta > abs(sweep) + 0.06:
                                    continue
                                d = delta * rr
                                if endpoint_ignore <= d <= total_len - endpoint_ignore:
                                    row_params.append(d)

                            if len(row_params) < 2:
                                continue
                            row_params = sorted(set(int(round(v)) for v in row_params))

                            def arc_xy(d, rr=rr):
                                a = start_angle + sweep_sign * (d / rr)
                                return (cx + math.cos(a) * rr,
                                        cy + math.sin(a) * rr)

                            # Iterate a few times because inserting one midpoint
                            # can reveal/fix the next largest local gap.
                            for _ in range(3):
                                changed = False
                                for a, b in zip(row_params, row_params[1:]):
                                    if try_split_gap_at(arc_xy, float(a), float(b)):
                                        changed = True
                                        break
                                if not changed:
                                    break
                                # Rebuild row list after insertion.
                                row_params = []
                                for via in created_vias:
                                    vp = via.GetPosition()
                                    vx = float(vp.x) - cx
                                    vy = float(vp.y) - cy
                                    vr = math.hypot(vx, vy)
                                    if abs(vr - rr) > row_tolerance:
                                        continue
                                    a = math.atan2(vy, vx)
                                    delta = angular_delta(start_angle, a, sweep_sign)
                                    if delta > abs(sweep) + 0.06:
                                        continue
                                    d = delta * rr
                                    if endpoint_ignore <= d <= total_len - endpoint_ignore:
                                        row_params.append(d)
                                row_params = sorted(set(int(round(v)) for v in row_params))

                    elif isinstance(it, pcbnew.PCB_TRACK):
                        p1, p2 = it.GetStart(), it.GetEnd()
                        dx, dy = p2.x - p1.x, p2.y - p1.y
                        seg_len = math.hypot(dx, dy)
                        if seg_len <= spacing:
                            continue
                        ux, uy = dx / seg_len, dy / seg_len
                        nx, ny = -uy, ux

                        for side in (-1, 1):
                            row_params = []
                            for via in created_vias:
                                vp = via.GetPosition()
                                vx = float(vp.x) - p1.x
                                vy = float(vp.y) - p1.y
                                along = vx * ux + vy * uy
                                if along < endpoint_ignore or along > seg_len - endpoint_ignore:
                                    continue
                                dist_to_center = abs(vx * nx + vy * ny - effective_offset * side)
                                if dist_to_center <= row_tolerance:
                                    row_params.append(along)

                            if len(row_params) < 2:
                                continue
                            row_params = sorted(set(int(round(v)) for v in row_params))

                            def track_xy(d, side=side):
                                bx = p1.x + ux * d
                                by = p1.y + uy * d
                                return (bx + nx * effective_offset * side,
                                        by + ny * effective_offset * side)

                            for _ in range(3):
                                changed = False
                                for a, b in zip(row_params, row_params[1:]):
                                    if try_split_gap_at(track_xy, float(a), float(b)):
                                        changed = True
                                        break
                                if not changed:
                                    break
                                row_params = []
                                for via in created_vias:
                                    vp = via.GetPosition()
                                    vx = float(vp.x) - p1.x
                                    vy = float(vp.y) - p1.y
                                    along = vx * ux + vy * uy
                                    if along < endpoint_ignore or along > seg_len - endpoint_ignore:
                                        continue
                                    dist_to_center = abs(vx * nx + vy * ny - effective_offset * side)
                                    if dist_to_center <= row_tolerance:
                                        row_params.append(along)
                                row_params = sorted(set(int(round(v)) for v in row_params))
                except Exception:
                    continue

        for item in selected:
            # Important: PCB_ARC must be checked before PCB_TRACK because some
            # KiCad SWIG builds expose arcs as track-derived classes.
            if isinstance(item, pcbnew.PCB_ARC):
                via_index = place_on_arc_native(item, via_index)
            elif isinstance(item, pcbnew.PCB_TRACK):
                via_index = place_on_track_segment(item, via_index)

        # Fill small visual holes at smooth selected-item junctions.
        fill_transition_gaps()
        fill_large_local_gaps()
        fill_largest_row_gaps()

        if created_vias:
            group = pcbnew.PCB_GROUP(board)
            group.SetName(f"ViaFence ({net_name})")
            board.Add(group)
            for via in created_vias:
                try:
                    group.AddItem(via)
                except AttributeError:
                    group.Add(via)

        pcbnew.Refresh()

        if created_vias and cfg.show_stats:
            mode = "Staggered" if cfg.staggered else "Dual-side"
            corners_placed = len(corner_positions)
            wx.MessageBox(
                f"ViaFence - Operation Complete\n\n"
                f"├─ Vias placed: {len(created_vias)}\n"
                f"├─ Corner vias: {corners_placed}\n"
                f"├─ Mode: {mode}\n"
                f"├─ Net: {net_name}\n"
                f"├─ Selected pads: {len(selected_pads)}\n"
                f"├─ Pad-ring vias: {pad_ring_vias if 'pad_ring_vias' in locals() else 0}\n"
                f"├─ Branches/paths: {path_stats['branches']}\n"
                f"├─ Components: {path_stats['components']}\n"
                f"├─ T/junction nodes: {path_stats['junctions']}\n"
                f"├─ Closed loops: {path_stats['loops']}\n"
                f"├─ Skipped candidates: {skipped_candidates}\n"
                f"├─ Units: {cfg.units}\n"
                f"├─ Via spacing track: {display_length(cfg.spacing_mm, cfg.units)}\n"
                f"├─ Via spacing pads: {display_length(cfg.pad_spacing_mm, cfg.units)}\n"
                f"├─ Gap: {display_length(cfg.track_to_via_gap_mm, cfg.units)}\n"
                f"├─ Via diameter: {display_length(cfg.via_diameter_mm, cfg.units)}\n"
                f"├─ Via drill: {display_length(cfg.via_drill_mm, cfg.units)}\n"
                f"└─ Group: ViaFence ({net_name})",
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

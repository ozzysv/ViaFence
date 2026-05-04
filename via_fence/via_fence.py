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
    def __init__(self, spacing_mm=2.0, track_to_via_gap_mm=0.2, 
                 via_diameter_mm=0.6, via_drill_mm=0.3, 
                 end_margin_mm=1.0, staggered=False, net_name="",
                 show_stats=True, place_at_corners=True, corner_angle_deg=30):
        self.spacing_mm = spacing_mm
        self.track_to_via_gap_mm = track_to_via_gap_mm
        self.via_diameter_mm = via_diameter_mm
        self.via_drill_mm = via_drill_mm
        self.end_margin_mm = end_margin_mm
        self.staggered = staggered
        self.net_name = net_name
        self.show_stats = show_stats
        self.place_at_corners = place_at_corners
        self.corner_angle_deg = corner_angle_deg


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "via_fence_cfg.json")
VIA_TIMESTAMP = 55  # Special timestamp to identify vias created by this plugin


def load_config():
    defaults = ViaFenceConfig()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return ViaFenceConfig(
                    spacing_mm=data.get("spacing_mm", 2.0),
                    track_to_via_gap_mm=data.get("track_to_via_gap_mm", 0.2),
                    via_diameter_mm=data.get("via_diameter_mm", 0.6),
                    via_drill_mm=data.get("via_drill_mm", 0.3),
                    end_margin_mm=data.get("end_margin_mm", 1.0),
                    staggered=data.get("staggered", False),
                    net_name=data.get("net_name", ""),
                    show_stats=data.get("show_stats", True),
                    place_at_corners=data.get("place_at_corners", True),
                    corner_angle_deg=data.get("corner_angle_deg", 30)
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
                "end_margin_mm": cfg.end_margin_mm,
                "staggered": cfg.staggered,
                "net_name": cfg.net_name,
                "show_stats": cfg.show_stats,
                "place_at_corners": cfg.place_at_corners,
                "corner_angle_deg": cfg.corner_angle_deg
            }, f, indent=2)
    except Exception:
        pass


def parse_mm_value(ctrl, label, min_value=0.0, allow_zero=False):
    """Read a wx.TextCtrl value as a positive mm float. Accepts both 0.7 and 0,7."""
    raw = ctrl.GetValue().strip().replace(',', '.')
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{label}: enter a valid number, for example 0.7")

    if allow_zero:
        if value < min_value:
            raise ValueError(f"{label}: value must be >= {min_value}")
    else:
        if value <= min_value:
            raise ValueError(f"{label}: value must be > {min_value}")
    return value


# ============================================================================
# Dialog
# ============================================================================

class ViaFenceDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(parent, title="ViaFence", size=(460, 560))
        icon_path = os.path.join(os.path.dirname(__file__), "via_fence_icon.png")
        if os.path.exists(icon_path):
            icon = wx.Icon(icon_path, wx.BITMAP_TYPE_PNG)
            self.SetIcon(icon)
        
        cfg = load_config()
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Create controls
        self.spacing = wx.TextCtrl(self, value=str(cfg.spacing_mm))
        self.gap = wx.TextCtrl(self, value=str(cfg.track_to_via_gap_mm))
        self.via_diam = wx.TextCtrl(self, value=str(cfg.via_diameter_mm))
        self.drill = wx.TextCtrl(self, value=str(cfg.via_drill_mm))
        self.margin = wx.TextCtrl(self, value=str(cfg.end_margin_mm))
        self.staggered = wx.CheckBox(self, label="Staggered pattern (alternating sides)")
        self.staggered.SetValue(cfg.staggered)
        
        # Corner options
        self.place_corners = wx.CheckBox(self, label="Place vias at corners (outside of bends)")
        self.place_corners.SetValue(cfg.place_at_corners)
        self.corner_angle = wx.TextCtrl(self, value=str(cfg.corner_angle_deg))
        
        # Show stats checkbox
        self.show_stats = wx.CheckBox(self, label="Show statistics after execution")
        self.show_stats.SetValue(cfg.show_stats)
        
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
        fields = [
            ("Via spacing (mm):", self.spacing),
            ("Track to via gap (mm):", self.gap),
            ("Via diameter (mm):", self.via_diam),
            ("Via drill (mm):", self.drill),
            ("End margin (mm):", self.margin),
            ("Net:", self.net_choice),
        ]
        
        for label, ctrl in fields:
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.Add(wx.StaticText(self, label=label), 0, wx.ALL | wx.CENTER, 5)
            row.Add(ctrl, 1, wx.ALL | wx.EXPAND, 5)
            vbox.Add(row, 0, wx.EXPAND)
        
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
    
    def get_config(self):
        net_name = self.net_choice.GetStringSelection()
        if not net_name:
            raise ValueError("Net: select a valid net")

        spacing_mm = parse_mm_value(self.spacing, "Via spacing", 0.0)
        gap_mm = parse_mm_value(self.gap, "Track to via gap", 0.0, allow_zero=True)
        via_diameter_mm = parse_mm_value(self.via_diam, "Via diameter", 0.0)
        via_drill_mm = parse_mm_value(self.drill, "Via drill", 0.0)
        end_margin_mm = parse_mm_value(self.margin, "End margin", 0.0, allow_zero=True)
        corner_angle_deg = parse_mm_value(self.corner_angle, "Min corner angle", 0.0)

        if via_drill_mm >= via_diameter_mm:
            raise ValueError("Via drill must be smaller than via diameter")
        if corner_angle_deg >= 180:
            raise ValueError("Min corner angle must be less than 180 degrees")

        return ViaFenceConfig(
            spacing_mm=spacing_mm,
            track_to_via_gap_mm=gap_mm,
            via_diameter_mm=via_diameter_mm,
            via_drill_mm=via_drill_mm,
            end_margin_mm=end_margin_mm,
            staggered=self.staggered.GetValue(),
            net_name=net_name,
            show_stats=self.show_stats.GetValue(),
            place_at_corners=self.place_corners.GetValue(),
            corner_angle_deg=corner_angle_deg
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


def arc_to_polyline(arc, max_segment_deg=10):
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


def point_to_arc_distance(px, py, arc):
    """Approximate arc distance by sampling / fallback reconstruction."""
    poly = arc_to_polyline(arc)
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
                p = pad.GetPosition()
                pad_r = max(pad.GetSizeX(), pad.GetSizeY()) / 2
                self._add_object({
                    "kind": "pad",
                    "item": pad,
                    "bbox": circle_bbox(p.x, p.y, inflate + pad_r),
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


def can_place_via(collision_index, pos, radius):
    """Check only nearby objects instead of scanning the whole board for every candidate."""
    px, py = pos.x, pos.y
    clearance = collision_index.clearance
    search_radius = radius + clearance + pcbnew.FromMM(3.0)

    for obj in collision_index.nearby(pos, search_radius):
        item = obj["item"]
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
            vp = item.GetPosition()
            vr = item.GetWidth() / 2
            if math.hypot(px - vp.x, py - vp.y) < radius + vr + clearance:
                return False

        elif kind == "pad":
            pp = item.GetPosition()
            pad_r = max(item.GetSizeX(), item.GetSizeY()) / 2
            if math.hypot(px - pp.x, py - pp.y) < radius + pad_r + clearance:
                return False

    return True


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

        if not selected:
            wx.MessageBox(
                "No tracks selected.\n\nSelect one or more connected track/arc segments first.",
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

        paths, path_stats = build_paths_from_selected(selected)
        if not paths:
            wx.MessageBox(
                "Failed to build paths from selected tracks.\n\n"
                "Check that selected items are valid tracks/arcs.",
                "ViaFence",
                wx.OK | wx.ICON_ERROR
            )
            return

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
        margin = pcbnew.FromMM(cfg.end_margin_mm)
        radius = via_diam / 2

        if spacing <= 0 or via_diam <= 0 or drill <= 0:
            wx.MessageBox(
                "Spacing, via diameter and drill must be positive values.",
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
            if can_place_via(collision_index, pos, radius):
                placed_positions.add(pos_key)
                make_via(pos)
                return True

            skipped_candidates += 1
            return False

        # 1. Corner vias for every independent branch/path.
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

        # 2. Regular vias along every path/branch.
        via_index = 0
        for path in paths:
            accumulated = 0
            next_pos = margin

            for i in range(len(path) - 1):
                p1, p2 = path[i], path[i + 1]
                dx, dy = p2.x - p1.x, p2.y - p1.y
                seg_len = math.hypot(dx, dy)
                if seg_len < 1e-6:
                    continue

                ux, uy = dx / seg_len, dy / seg_len
                px_vec, py_vec = -uy, ux

                while accumulated + seg_len >= next_pos:
                    t = next_pos - accumulated
                    base_x = p1.x + ux * t
                    base_y = p1.y + uy * t

                    if position_key(base_x, base_y) in corner_positions:
                        next_pos += spacing
                        continue

                    if cfg.staggered:
                        sides_to_try = [-1 if (via_index % 2 == 0) else 1]
                    else:
                        sides_to_try = [-1, 1]

                    via_placed_this_position = False
                    shifts = [0, spacing * 0.25, -spacing * 0.25,
                              spacing * 0.5, -spacing * 0.5]

                    for side in sides_to_try:
                        if via_placed_this_position and cfg.staggered:
                            break

                        for shift in shifts:
                            x = int(base_x + ux * shift + px_vec * effective_offset * side)
                            y = int(base_y + uy * shift + py_vec * effective_offset * side)
                            pos_key = position_key(x, y)
                            if pos_key in placed_positions:
                                continue

                            pos = pcbnew.VECTOR2I(x, y)
                            if can_place_via(collision_index, pos, radius):
                                placed_positions.add(pos_key)
                                make_via(pos)
                                via_placed_this_position = True
                                break
                            skipped_candidates += 1

                    via_index += 1
                    next_pos += spacing

                accumulated += seg_len

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
                f"├─ Branches/paths: {path_stats['branches']}\n"
                f"├─ Components: {path_stats['components']}\n"
                f"├─ T/junction nodes: {path_stats['junctions']}\n"
                f"├─ Closed loops: {path_stats['loops']}\n"
                f"├─ Skipped candidates: {skipped_candidates}\n"
                f"├─ Spacing: {cfg.spacing_mm} mm\n"
                f"├─ Gap: {cfg.track_to_via_gap_mm} mm\n"
                f"├─ Via diameter: {cfg.via_diameter_mm} mm\n"
                f"├─ Via drill: {cfg.via_drill_mm} mm\n"
                f"└─ Group: ViaFence ({net_name})",
                "ViaFence - Statistics",
                wx.OK | wx.ICON_INFORMATION
            )
        elif not created_vias and cfg.show_stats:
            wx.MessageBox(
                "ViaFence - Warning\n\n"
                "No vias were placed.\n\n"
                "Possible reasons:\n"
                "• Collision with existing copper\n"
                "• Path/branches are too short\n"
                "• Clearance constraints prevent placement",
                "ViaFence",
                wx.OK | wx.ICON_WARNING
            )

# Register the plugin
ViaFencePlugin().register()
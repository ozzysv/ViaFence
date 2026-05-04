# ViaFence for KiCad 9

**ViaFence** is a KiCad 9 Action Plugin that places via fences along selected tracks and arcs for EMI shielding, RF grounding, and improved return-current control.

The plugin can follow complex selected copper geometry, including continuous tracks, arcs, T-junctions, multiple branches, and closed loops.

---

## Features

- Places via fences along selected PCB tracks and arcs
- Supports KiCad 9 Python/SWIG API
- Works with:
  - straight tracks
  - arcs
  - T-junctions
  - multiple branches
  - closed loops
- Dual-side or staggered via placement
- Optional corner-via placement outside bends
- Selectable target net, usually `GND`
- Configurable:
  - via spacing
  - track-to-via gap
  - via diameter
  - drill size
  - end margin
  - corner angle threshold
- Collision checking against:
  - existing tracks
  - arcs
  - vias
  - footprint pads
- Grid-based collision index for better performance on larger boards
- Stores settings in `via_fence_cfg.json`
- Groups generated vias as `ViaFence (<net>)`

---

## Requirements

- KiCad 9.0 or newer
- Python 3.9 or newer
- wxPython, included with KiCad's Python environment

---

## Installation
Download the latest release from the Releases section (do not use "Download ZIP")
Copy the via_fence folder from the archive into your KiCad 9 third-party plugins directory

Typical Windows path:

```text
C:\Users\<User>\Documents\KiCad\9.0\3rdparty\plugins
```

The folder should contain:

```text
via_fence/
├── __init__.py
├── plugin.json
├── via_fence.py
├── via_fence_cfg.json
└── via_fence_icon.png        # optional
```

Then restart KiCad or reload plugins from PCB Editor.

---

## Usage

1. Open your PCB in KiCad PCB Editor.
2. Select one or more connected tracks/arcs.
3. Run **ViaFence** from the plugin toolbar or the Action Plugins menu.
4. Configure the parameters.
5. Select the target net, usually `GND`.
6. Press **OK**.

The plugin will place vias along the selected copper geometry and group them into a KiCad group named:

```text
ViaFence (<net>)
```

---

## Parameters

| Parameter | Description |
|---|---|
| Via spacing | Distance between regular via positions along the selected path |
| Track to via gap | Clearance from the track edge to the via edge before adding via radius and track width compensation |
| Via diameter | Outer diameter of the generated via |
| Via drill | Drill size of the generated via |
| End margin | Distance from the beginning of each path before placing the first via |
| Net | Electrical net assigned to generated vias |
| Staggered pattern | Places one via per position, alternating left/right |
| Place vias at corners | Adds extra vias outside detected bends when possible |
| Min corner angle | Minimum bend/deviation angle used to detect corners |
| Show statistics | Shows a result summary after placement |

---

## Notes About Corner Vias

The corner option does not change the main via fence pattern. It only tries to add extra vias outside bends.

A corner via may not appear if:

- a regular via is already close to the corner
- the area near the corner violates clearance rules
- another via, track, arc, or pad blocks placement
- the detected bend does not exceed the configured minimum corner angle
- the spacing is small enough that the difference is visually hard to notice

For a visible corner-via test, use a simple 90° track bend with larger spacing, for example 2–3 mm.

---

## T-Junctions and Multiple Branches

ViaFence reconstructs selected copper as a graph. Junction nodes and branch endpoints are used to split the selection into independent paths. This allows the plugin to process shapes such as:

```text
     |
-----+-----
     |
```

Each branch is processed separately while still sharing the same generated via group and collision index.

---

## Collision Handling

Before placing a via, the plugin checks nearby board objects using a spatial grid index. This avoids scanning the whole board for every candidate via and improves performance on larger PCBs.

Objects checked include:

- tracks
- arcs
- existing vias
- newly created vias
- footprint pads

If placement would violate clearance, the candidate via is skipped.

---

## Configuration File

The plugin saves the last used settings in:

```text
via_fence_cfg.json
```

Example:

```json
{
  "spacing_mm": 0.7,
  "track_to_via_gap_mm": 0.3,
  "via_diameter_mm": 0.6,
  "via_drill_mm": 0.3,
  "end_margin_mm": 1.0,
  "staggered": false,
  "net_name": "GND",
  "show_stats": true,
  "place_at_corners": true,
  "corner_angle_deg": 50.0
}
```

---

## Recommended Starting Values

For general GND stitching around signal traces:

```text
Via spacing:        0.7–2.0 mm
Track to via gap:   0.2–0.4 mm
Via diameter:       0.5–0.7 mm
Via drill:          0.25–0.35 mm
End margin:         0.5–1.0 mm
Net:                GND
```

For RF/high-speed layouts, choose spacing based on the highest relevant frequency and your PCB stackup rules.

---

## Limitations

- The plugin does not automatically verify RF design correctness.
- Generated vias still need to comply with your manufacturer’s DRC and fabrication limits.
- Very dense layouts may skip many candidate vias due to clearance conflicts.
- The plugin works on selected tracks/arcs only; it does not automatically detect entire nets.

---

## Troubleshooting

### No vias were placed

Possible causes:

- selected path is too short
- via spacing is too large
- clearance rules block placement
- wrong net was selected
- selected geometry is not valid track/arc geometry

### Corner option seems to make no difference

This is usually normal. Corner vias are additional candidates only. If a normal via is already close to the bend, or if clearance prevents placement, the visual result may look identical.

### Plugin does not appear in KiCad

Check that the plugin folder contains `__init__.py`, `plugin.json`, and `via_fence.py`, then restart KiCad.

# SectionLab

Desktop tool for drawing a single closed cross-section and computing its geometric
properties. Free, non-commercial, Windows-native; distributed as a self-contained ZIP.

The complete v1 specification and task breakdown live in
[`odd/tasks/sectionlab-v1.md`](odd/tasks/sectionlab-v1.md). That document is the source of
truth for scope, behavior and conventions.

## v1 scope

- Custom geometry: line segments, one closed contour, single section per document.
- Eleven parametric templates (rectangle, rectangular hollow, circle, pipe, triangle,
  regular polygon, I, H, U, L, T) with editable parameters and defaults; no profile catalogs.
- Exact input: typed vertex list plus an editable vertex table; snaps for endpoint,
  intersection, midpoint, arc/circle centre and perpendicular, plus ortho mode.
- Editing: move/insert/delete vertex, undo/redo.
- Active unit `mm`, `cm`, `m` or `in` for input and output; internal model always in mm.
- Outputs about centroidal axes: A, perimeter, centroid, Ix, Iy, Ixy, principal I1/I2 with
  angle, radii of gyration, elastic moduli Sx/Sy, bounding box.
- Validation blocks calculation (not saving) on open contour, fewer than three vertices,
  self-intersection, duplicate points or zero area.
- Projects saved as `.sectionlab` JSON (schema-versioned); results copied to clipboard or
  exported as full-precision CSV.
- UI in Spanish; code, comments, commits and internal docs in English.

## Deferred to v2

Torsion constant J, warping constant, shear centre, shear areas, plastic section moduli,
plastic centroid, shape factor, composite/material properties, stress visualisation,
reference-axis tool, user-created holes, hatch, multi-section documents,
template→free-geometry conversion, cut/paste/trim, numeric length/angle drawing entry,
PDF/PNG reports, **DXF import/export**.

## Stack

- **UI**: PySide6 + Qt Widgets + QGraphicsView/QGraphicsScene (custom canvas)
- **Geometry**: shapely
- **Solver**: sectionproperties (unit-agnostic; returns plain floats)
- **Packaging**: PyInstaller `--onedir` → ZIP; Inno Setup installer later

## Development

Target platform is Windows; the repository is also developed on Linux.

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
tools/dev.sh uv run pytest      # Linux: loads the vendored Qt libEGL, runs headless
tools/dev.sh uv run sectionlab
```

`tools/dev.sh` exists only because the Linux dev host lacks the system `libEGL` that Qt 6
requires; on Windows call `uv run` directly. The vendored copy lives in `.devlibs/`, which is
not committed.

## Status

Project scaffold in place; application code under construction.

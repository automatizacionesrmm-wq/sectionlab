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

## Usage

1. Pick a template on the right, type its parameters in the active unit and press
   **Aplicar**, or press **Nueva geometría libre** and draw with the mouse: click to add a vertex,
   `Enter` to close the contour, `Esc` to cancel. `F8` toggles ortho mode; snaps appear for
   endpoints, intersections, midpoints, centres and perpendicular feet.
2. **Calcular** (`Ctrl+Enter`) validates and fills the results table. Validation messages are
   Spanish and name the offending geometry; saving an invalid drawing is still allowed.
3. The vertex table mirrors the drawing in the active unit and accepts typed coordinates;
   edits are undoable with `Ctrl+Z`.
4. **Configuración → Preferencias** changes the active unit and the displayed decimals.
   Changing the unit only converts the display; the geometry is never recomputed.
5. **Guardar** writes one `.sectionlab` JSON file. **Exportar CSV** writes every value at full
   precision (`repr`), independent of the visible decimals.

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

## Windows packaging

```powershell
tools\build_windows.ps1
```

The script installs the `build` extra, runs PyInstaller with
[`packaging/sectionlab.spec`](packaging/sectionlab.spec) and zips the onedir output into
`dist/SectionLab-<version>-windows.zip`. `dist/SectionLab/SectionLab.exe` runs without a
console window and needs no Python on the target machine. GitHub Releases is the intended
distribution channel; there is no code signing.

PyInstaller cannot cross-compile, so the Windows ZIP must be built on Windows. The same spec
builds on Linux, and the frozen binary accepts two flags useful for smoke testing:

```bash
dist/SectionLab/SectionLab --version     # SectionLab 0.1.0
dist/SectionLab/SectionLab --self-test   # runs one rectangle calculation, prints area and Ix
```

The bundle is large (about 370 MB unpacked) because it ships Qt, numpy/scipy and the
matplotlib that `sectionproperties` imports; the plotting extras and notebook dependencies
are excluded in the spec.

## Status

v1 feature complete and tested (`tools/dev.sh uv run pytest`), packaged with PyInstaller.

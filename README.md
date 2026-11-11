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
- Interface: dark and light drafting themes sharing one colour-token table, an icon toolbar
  with a primary **Calcular** button, and a canvas that draws a grid with labelled axes, a
  live crosshair, contour fill and vertex handles. Icons are drawn in code, so they recolour
  with the theme and stay sharp on high-density screens.
- The drawing is the central widget and the three inspectors (plantilla, vértices, resultados)
  are docks: drag a title bar to move one, drag it out of the window to float it, drag the
  separators to resize, or press `F9` to hide them all and give the drawing the whole window.
- UI in Spanish; code, comments, commits and internal docs in English.

## Deferred to v2

Torsion constant J, warping constant, shear centre, shear areas, plastic section moduli,
plastic centroid, shape factor, composite/material properties, stress visualisation,
reference-axis tool, user-created holes, hatch, multi-section documents,
template→free-geometry conversion, cut/paste/trim, numeric length/angle drawing entry,
PDF/PNG reports, **DXF import/export**.

## Usage

1. Pick a template on the right and type its parameters in the active unit: the section is
   drawn as soon as the template or a parameter changes, so **Aplicar** is only a convenience.
   Or press **Nueva geometría libre** and draw with the mouse: click to add a vertex; the first
   vertex turns green as the closing target, so clicking it (or the right button, or `Enter`)
   closes the contour, and `Esc` cancels. `F8` toggles ortho mode; snaps appear for endpoints,
   intersections, midpoints, centres and perpendicular feet.
   A template section belongs to its parameters, so its vertices stay locked. When you want to
   adjust it by hand, **Convertir a geometría libre** keeps the contour exactly as drawn and
   hands you the vertices; **Deshacer** puts the template back.
2. Every segment carries its own dimension, written outside the contour in the active unit:
   widths and heights for straight edges, a length for slanted ones. **Ver → Cotas**
   (`Ctrl+D`) shows and hides them. Double-click an editable dimension, type the new value and
   press `Enter`: the section moves so that segment measures that value, in one undo step. The
   closing edge stays read-only because its length follows from the others, and a refused
   value explains itself in the status bar.
3. Move around the drawing like in a CAD program: the wheel zooms towards the cursor, the
   middle button drags the view, and a middle double click fits the section on screen. The
   view has no scrollbars; **Acercar**, **Alejar** and **Ajustar** are on the toolbar.
   The inspectors are docks, so you can drag them by their title bar to either side or out of
   the window, double-click a title bar to float it, or right-click it for the same moves by
   name. `F9` (**Ver → Paneles → Mostrar todos los paneles**) hides them all and brings back
   any that is closed, and **Ver → Paneles** lists each inspector so a panel closed with its
   own `×` can be reopened by name. While none of them is on screen the status bar says so.
4. **Calcular** (`Ctrl+Enter`) validates and fills the results table, then marks the centroid
   with a dot and the principal axes `1` and `2`. The reference axes through the origin are
   labelled `X` and `Y`. Validation messages are
   Spanish and name the offending geometry; saving an invalid drawing is still allowed.
5. The vertex table mirrors the drawing in the active unit and accepts typed coordinates;
   selecting a row marks that vertex on the drawing, and clicking a vertex selects its row.
   Edits are undoable with `Ctrl+Z`.
6. **Configuración → Preferencias** changes the active unit and the displayed decimals.
   Changing the unit only converts the display; the geometry is never recomputed. The same
   unit is used for input and output: dimensions, vertex table and results always agree.
7. **Ver → Tema** (`Ctrl+Shift+T`) switches between the dark and light themes; the choice is
   remembered in the saved preferences.
8. **Guardar** writes one `.sectionlab` JSON file. **Exportar CSV** writes every value at full
   precision (`repr`), independent of the visible decimals.

## Stack

- **UI**: PySide6 + Qt Widgets + QGraphicsView/QGraphicsScene (custom canvas)
- **Geometry**: shapely
- **Solver**: sectionproperties (unit-agnostic; returns plain floats)
- **Packaging**: PyInstaller `--onedir` for the runtime, Inno Setup for the installer, and a
  separate code archive so updates are kilobytes instead of megabytes

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

A release is three files, because the runtime and the application change at different speeds:

| Artifact | Size | Changes when |
| --- | --- | --- |
| `SectionLab-<version>-setup.exe` | 75 MB | a dependency or Python itself changes |
| `SectionLab-<version>-windows.zip` | 114 MB | never useful on its own: the portable copy of the same folder |
| `SectionLab-<version>-code.zip` | 43 kB | the application code changes, which is almost always |

The setup installs under the user profile (no administrator rights), and running a newer setup
upgrades the previous installation in place: there is no folder to decompress and the saved
preferences survive.

### Updating without downloading the bundle again

The frozen runtime — CPython, Qt, scipy, numpy, shapely — lives in `_internal/` and is
untouched by a code change. The application package is deliberately **not** frozen:
`SectionLab.exe` puts `app\` at the front of `sys.path` and imports `sectionlab` from there
([`packaging/launcher.py`](packaging/launcher.py); the spec excludes `"sectionlab"`).

So the quick loop after a change is:

1. Download `SectionLab-<version>-code.zip` from the newest green run (~60 kB).
2. Extract it into `app\` of the installation, replacing the `sectionlab` folder.
3. Start `SectionLab.exe`.

The installer is only needed when the runtime changes (a new dependency, a new Python version).
[`tools/assemble_app.py`](tools/assemble_app.py) is what copies the package beside the frozen
executable and writes that archive, locally and in CI.

### Updates from inside the application

From 0.2.0 onward SectionLab updates itself: it asks GitHub for the newest release once per
launch (and whenever you pick **Ayuda → Buscar actualizaciones**), and when there is one, a
banner above the drawing offers it. **Actualizar** downloads the code archive (about 50 kB),
checks its SHA-256 when GitHub publishes one, and replaces `app\sectionlab`, keeping the
previous folder as `sectionlab.bak`. Nothing restarts on its own: the window asks first.

The running version is visible in the title bar, in **Configuración → Preferencias** and in
**Ayuda → Acerca de SectionLab**.

A release that changes the runtime rather than the code carries no code archive; the banner
offers the full installer instead, and the window closes so it can run.

**The updater cannot update a build that lacks it.** 0.2.0 has to be installed once with the
setup from [Releases](https://github.com/automatizacionesrmm-wq/sectionlab/releases/latest);
after that, every new release can be applied from inside the window.

### Install or update (no toolchain needed)

The current build is published in
[Releases](https://github.com/automatizacionesrmm-wq/sectionlab/releases/latest), where the
files download directly:

1. **`SectionLab-<version>-setup.exe`** — run it once (or let the application update itself). It installs under your user profile
   without administrator rights, adds a Start-menu entry and an uninstaller, and a newer setup
   upgrades the previous installation in place, keeping your preferences.
2. **`SectionLab-<version>-code.zip`** — the update. Extract the `sectionlab` folder it holds
   into `app\` of the installation; the next start runs the new code. It is 43 kB, so a change
   to the program never downloads the runtime again. Run the setup only when the runtime itself
   changes (a new dependency or Python version).
3. **`SectionLab-<version>-windows.zip`** — portable copy for a machine where nothing may be
   installed: unzip and run `SectionLab.exe`.

Every push to `main` also builds these files on a Windows runner:
[`.github/workflows/windows-build.yml`](.github/workflows/windows-build.yml). Open the
**Actions** tab, pick the newest `windows-build` run and download the artifact you need:
`SectionLab-installer` (75 MB), `SectionLab-code` (43 kB) or `SectionLab-portable` (114 MB).
The run fails if the frozen bundle does not pass `--self-test`, so a green artifact is a working
build.

### Build it yourself

```powershell
tools\build_windows.ps1
```

The script installs the `build` extra, runs PyInstaller with
[`packaging/sectionlab.spec`](packaging/sectionlab.spec), calls `tools/assemble_app.py`, zips
the folder and — when Inno Setup 6 is installed — compiles
[`packaging/sectionlab.iss`](packaging/sectionlab.iss). Without Inno Setup it warns and skips
the installer. `dist/SectionLab/SectionLab.exe` runs without a console window and needs no
Python on the target machine. GitHub Releases is the intended distribution channel; there is no
code signing, so Windows shows the SmartScreen warning until you choose "More info → Run
anyway".

PyInstaller cannot cross-compile, so the Windows artifacts must be built on Windows. The same
spec builds on Linux, and the frozen binary accepts two flags useful for smoke testing:

```bash
dist/SectionLab/SectionLab --version     # SectionLab 0.2.3
dist/SectionLab/SectionLab --self-test   # runs one rectangle calculation, prints area and Ix
```

The Windows executable has no console, so `--self-test` shows its result in a dialog instead of
printing it. That is the quickest way to confirm a downloaded bundle actually works on a machine
without Python. The bundle is large (about 370 MB unpacked) because it ships Qt, numpy/scipy and
the matplotlib that `sectionproperties` imports; the plotting extras and the notebook
dependencies are excluded in the spec.

## Status

v1 feature complete and tested (`tools/dev.sh uv run pytest`), packaged with PyInstaller.

# SectionLab v1 — complete first Windows-buildable delivery

Free, non-commercial Windows desktop tool: draw one closed cross-section (free geometry or
parametric template) and compute its geometric properties, shipped as a self-contained ZIP.
v1 scope is frozen by the 13 interview decisions recorded in Engram project `sectionlab`,
observations 3024–3036 (session `manual-save-sectionlab`).

## Specs

- **S1 Stack.** Python 3.12 + PySide6 (Qt Widgets) + QGraphicsView/QGraphicsScene, single
  process. No web, Tauri, Electron, Docker or server. `shapely` handles 2D geometry
  operations. `sectionproperties` is the calculation engine; it is unit-agnostic, returns
  plain floats from its getters and never converts or attaches units.
- **S2 Units.** The internal geometry model is always millimetres. One global active unit
  selector (`mm`, `cm`, `m`, `in`) controls input *and* output. User input is converted to
  mm on entry; displayed results are converted from mm with the same factor. Changing the
  active unit converts values only — it never recomputes or mutates geometry.
- **S3 Display precision.** Settings exposes visible decimals `0..6`, default `2`. It affects
  on-screen presentation only. All internal computation uses full floating-point precision
  with no intermediate rounding.
- **S4 CSV precision.** CSV export always writes full available precision, independent of the
  visible-decimals setting.
- **S5 Custom geometry.** v1 supports line segments only, a single closed contour, no
  user-created holes, no materials, no hatch. A hollow parametric shape is still one section
  with an outer and an inner contour.
- **S6 Numeric input.** A section can be created from a typed vertex list, for example
  `(0,0), (120,0), (120,80), (0,80)`, expressed in the active display unit. An editable
  vertex table shows every vertex x/y, allows editing, and updates the drawing.
- **S7 Snaps and aids.** v1 snaps: endpoint, intersection, midpoint, circle/arc centre,
  perpendicular, plus ortho mode. "Centre" means circle/arc centre, never the section
  centroid. Not in v1: parallel, extension, polar tracking, grid snap, tangent, quadrant,
  nearest, node/insertion, apparent intersection, object-snap tracking.
- **S8 Editing.** v1: move a vertex by drag or through the vertex table; insert a vertex on a
  segment; delete a vertex while keeping the contour closed when at least three vertices
  remain; undo/redo. Cut, paste and trim are not v1.
- **S9 Axes.** x positive to the right, y positive upward, origin free/user-controlled.
- **S10 Parametric templates.** Edited only through their parameter fields; changing a
  parameter rebuilds the shape. Sharp corners only — no fillets or root radii. There is no
  conversion from a template to free geometry: parametric and free-geometry modes are
  separate. All parameter values use the active display unit and are stored in mm.

  | Template | Parameters | Defaults (mm) |
  | --- | --- | --- |
  | Rectangle | b, h | 100, 200 |
  | Rectangular hollow | b, h, t | 100, 200, 6 |
  | Solid circle | D | 100 |
  | Hollow circle / pipe | D, t | 100, 10 |
  | Triangle | b, h, apex offset from base centre | 100, 100, 0 |
  | Regular polygon | n sides, circumradius R | n=6, R=50 |
  | I | h, b, tw, tf | 200, 100, 6, 10 |
  | H | h, b, tw, tf | 200, 200, 8, 12 |
  | U (channel) | h, b, tw, tf | 200, 80, 6, 10 |
  | L (angle) | b (horizontal leg), h (vertical leg), t | 100, 100, 10 |
  | T | h, b, tw, tf | 150, 100, 8, 12 |

- **S11 Outputs.** Area, perimeter, centroid (x, y), centroidal Ix, Iy, Ixy, principal
  centroidal I1/I2 with principal angle, radii of gyration rx, ry, r1, r2, elastic section
  moduli Sx, Sy, and bounding box. Global/origin moments of inertia are not shown.
- **S12 Deferred to v2.** Torsion constant J, warping constant, shear centre, shear areas,
  plastic section moduli, plastic centroid, shape factor, composite/material properties,
  stress visualisation, explicit reference-axis tool, user-created holes, hatch,
  multi-section documents, template→free-geometry conversion, cut/paste/trim, numeric
  length/angle drawing entry, PDF/PNG reports, DXF import/export.
- **S13 Validation.** `Calcular` is always enabled and validates instead of being disabled.
  It blocks and explains, in Spanish, an open contour, fewer than three vertices,
  self-intersection, duplicate points, or zero area, and highlights the offending geometry in
  the drawing. Saving an invalid contour is allowed; only calculation is blocked.
- **S14 Persistence.** Save and open project files: one section per `.sectionlab` file, JSON,
  holding geometry, active display unit, template parameters and a schema/version field.
  No multi-section tabs or documents.
- **S15 Results UX.** Results table shown in the app; copy the table to the clipboard; export
  the table as CSV. PDF/PNG reports are not v1. The CSV carries results, not the project.
- **S16 Language.** User-facing labels, buttons, messages and help: Spanish. Source code,
  identifiers, comments, commit messages and internal documentation: English. Error codes and
  logs stay English. Application name: `SectionLab`.
- **S17 Interaction speed.** Drawing and editing must feel fast: direct coordinate entry,
  minimal modal dialogs, keyboard-friendly where practical.
- **S18 Windows package.** PyInstaller `--onedir` producing a ZIP; Inno Setup installer later;
  distribution through GitHub Releases; no code signing; free non-commercial distribution.
  The first Windows-testable ZIP covers the complete v1 scope above, not a stripped slice.
- **S19 Numeric conventions.** Chosen by the orchestrator, pending user confirmation:
  `Ixy = ∫xy dA` with the S9 axes; principal angle `θp = 0.5·atan2(-2·Ixy, Ix - Iy)` in
  degrees, positive counter-clockwise from +x; contours normalized to counter-clockwise
  winding before calculation; closure and duplicate-point tolerance `1e-6 mm` absolute.

## Derived implementation decisions (architect, not user requirements)

- **D1 Curved templates are exact.** `circle` and `pipe` are calculated from closed-form
  formulas (`A = πD²/4`, `I = πD⁴/64`, `S = I/(D/2)`, `J` unused in v1) so textbook
  verification is exact. Their on-screen representation is a 360-segment polygon; the polygon
  is presentation only and never feeds the calculation. Every other section, free geometry
  included, is meshed and calculated by `sectionproperties`.
- **D2 Angular shapes are polygonal.** Every other template is an exact straight-line polygon
  built from its parameters, with sharp corners per S10.
- **D3 Contour winding.** Free-geometry contours are normalized to counter-clockwise winding
  before calculation; a clockwise input is accepted, never rejected.
- **D4 Elastic section moduli** use the greatest centroidal fibre distance:
  `Sx = Ix / max(y_max - cy, cy - y_min)`, `Sy = Iy / max(x_max - cx, cx - x_min)`.
- **D5 Full-precision export** means the shortest round-trip decimal representation of the
  float (`repr`), never a fixed format, so CSV re-imports to the identical value.
- **D6 Messages are localized in the UI layer.** Core validation returns stable English codes;
  the Spanish text for each code lives in the UI strings module (T12).
- **D7 Mesh density.** `sectionproperties` meshes a section with `mesh_size = max(extent/10,
  0.5 mm)`, where `extent` is the longest bounding-box side. Verified on solid, hollow and
  triangular sections: relative error at machine precision (`< 1e-12`) and about 0.5 s per
  calculation. Denser meshes only cost time; the default keeps `Calcular` responsive.
- **D8 Reported sign conventions.** `Ixy = ∫xy dA`, so an L angle in the first quadrant reports
  a negative product of inertia. The principal angle is the solver's principal-axis angle
  folded into `(-90°, 90°]`, counter-clockwise from `+x`.
- **D9 Packaging.** One spec file (`packaging/sectionlab.spec`) drives the onedir build and
  `tools/build_windows.ps1` wraps it for Windows (install build extra, build, zip into
  `dist/SectionLab-<version>-windows.zip`). sectionproperties' analysis modules resolve
  statically, so the spec declares no hidden imports and excludes the plotting extras
  (matplotlib, PIL, IPython, pandas) to keep the ZIP small. The frozen bundle is smoke tested
  by `SectionLab.exe --self-test`, which runs one rectangle calculation and prints its area
  without opening a window.

## Core API contract

`sectionlab.core` never imports Qt. All internal values are millimetres, all angles degrees.

```python
# sectionlab.core.units
class Unit(str, Enum): MM = "mm"; CM = "cm"; M = "m"; IN = "in"
FACTOR_TO_MM: dict[Unit, float]                  # 1.0, 10.0, 1000.0, 25.4
def to_mm(value: float, unit: Unit) -> float
def from_mm(value: float, unit: Unit) -> float
def to_mm2(value: float, unit: Unit) -> float    # areas
def from_mm2(value: float, unit: Unit) -> float
def to_mm3(value: float, unit: Unit) -> float    # section moduli
def from_mm3(value: float, unit: Unit) -> float
def to_mm4(value: float, unit: Unit) -> float    # inertias
def from_mm4(value: float, unit: Unit) -> float

# sectionlab.core.precision
DEFAULT_DECIMALS = 2; MIN_DECIMALS = 0; MAX_DECIMALS = 6
def format_value(value: float, decimals: int) -> str      # display only
def format_full(value: float) -> str                      # round-trip exact
def results_to_csv(rows: Sequence[Mapping[str, float]]) -> str

# sectionlab.core.model
@dataclass(frozen=True)
class Point: x: float; y: float
@dataclass
class Contour:
    points: list[Point]
    closed: bool = True                                   # False == drawn path leaves a gap
@dataclass
class Section:
    outer: Contour
    inner: Contour | None = None
    template: TemplateSpec | None = None

def signed_area(contour: Contour) -> float                # mm², sign = winding
def normalize_ccw(contour: Contour) -> Contour

# sectionlab.core.validation
class IssueCode(str, Enum): OPEN_CONTOUR; TOO_FEW_VERTICES; DUPLICATE_POINTS;
    SELF_INTERSECTION; ZERO_AREA
@dataclass(frozen=True)
class ValidationIssue: code: IssueCode; points: tuple[Point, ...]
CLOSURE_TOLERANCE_MM = 1e-6
# Rules, applied to outer and inner contour alike:
#   closed is False            -> OPEN_CONTOUR, reported at the missing closing edge
#   fewer than 3 points        -> TOO_FEW_VERTICES
#   two points within tolerance-> DUPLICATE_POINTS
#   non-simple ring (shapely)  -> SELF_INTERSECTION
#   |signed area| negligible at the contour's own scale (tol * largest extent) -> ZERO_AREA
# A self-intersecting ring has no meaningful signed area, so ZERO_AREA is not reported for it.
# A typed vertex list is treated as closed; only canvas drawing can produce an open path.
def validate_section(section: Section) -> list[ValidationIssue]   # empty == valid

# sectionlab.core.engine
@dataclass(frozen=True)
class SectionProperties:   # area mm², lengths mm, inertias mm⁴, moduli mm³, angle deg
    area: float; perimeter: float; cx: float; cy: float
    ix: float; iy: float; ixy: float
    i1: float; i2: float; principal_angle_deg: float
    rx: float; ry: float; r1: float; r2: float
    sx: float; sy: float
    x_min: float; x_max: float; y_min: float; y_max: float
MESH_DIVISOR = 10; MIN_MESH_SIZE_MM = 0.5                        # see D7
class InvalidSectionError(ValueError): issues: list[ValidationIssue]
def calculate(section: Section) -> SectionProperties             # raises InvalidSectionError

# sectionlab.core.templates
class TemplateKind(str, Enum): RECTANGLE; RECT_HOLLOW; CIRCLE; PIPE; TRIANGLE; POLYGON;
    I_PROFILE; H_PROFILE; U_CHANNEL; L_ANGLE; T_PROFILE
@dataclass(frozen=True)
class TemplateParam: key: str; default: float; minimum: float
def parameters(kind: TemplateKind) -> tuple[TemplateParam, ...]
def default_params(kind: TemplateKind) -> dict[str, float]
class TemplateParameterError(ValueError): code: str              # stable English code
class TemplateParam(key: str; default: float; minimum: float)
def build_section(kind: TemplateKind, params: Mapping[str, float] | None = None) -> Section

# Fixed parameter keys and defaults, per template (defaults in mm):
#   RECTANGLE  b=100  h=200
#   RECT_HOLLOW b=100 h=200 t=6
#   CIRCLE     d=100
#   PIPE       d=100  t=10
#   TRIANGLE   b=100  h=100 offset=0        (offset = apex offset from base centre)
#   POLYGON    n=6    r=50                 (n = sides, r = circumradius)
#   I_PROFILE  h=200  b=100 tw=6  tf=10
#   H_PROFILE  h=200  b=200 tw=8  tf=12
#   U_CHANNEL  h=200  b=80  tw=6  tf=10
#   L_ANGLE    b=100  h=100 t=10
#   T_PROFILE  h=150  b=100 tw=8  tf=12
# `n` is a dimensionless count (minimum 3); every other parameter is a length in mm.

# sectionlab.core.document
SCHEMA_VERSION = 1
def to_payload(section: Section, unit: Unit) -> dict[str, object]
def from_payload(payload: Mapping[str, object]) -> tuple[Section, Unit]
def save(path: str | Path, section: Section, unit: Unit) -> None
def load(path: str | Path) -> tuple[Section, Unit]
```

## Tasks

| ID | Specs | Route | Work | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1, S18 | inline | Repo scaffold: git, uv project, src layout, pytest config, .gitignore, README realignment | a7f37db |
| T2 | S2, S3, S4, S19 | inline | Units + precision core (mm internal, conversions, formatting, CSV precision) with tests | d3d972d |
| T3 | S5, S9, S13, S19 | inline | Section model + contour validation (closure, <3 vertices, duplicates, self-intersection, zero area) | d3d972d |
| T4 | S1, S11, S19 | inline | sectionproperties integration returning every S11 property about centroidal axes, verified against analytical values | 20a8b82 |
| T5 | S10 | inline | Eleven parametric template generators with defaults and parameter rebuild | 20a8b82 |
| T6 | S14 | inline | `.sectionlab` JSON persistence with schema version | 35ade55 |
| T7 | S15, S3, S4 | inline | Results table: display, clipboard copy, full-precision CSV | c93506f |
| T8 | S5, S7, S8, S17 | inline | Canvas: segment drawing, six snaps, vertex move/insert/delete, undo/redo | a0a64a1 |
| T9 | S6, S17 | inline | Vertex table + typed vertex-list entry | f55b800 |
| T10 | S13, S16 | inline | Calcular flow: always enabled, Spanish blocking messages, offending geometry highlighted | 282136b |
| T11 | S2, S3, S16 | inline | Settings dialog: active unit and visible decimals | 282136b |
| T12 | S16 | inline | Centralized Spanish UI strings; English code and logs | c93506f |
| T13 | S18 | inline | PyInstaller onedir spec, build script, ZIP smoke test | see Log |

## Log

- **L1** (verbatim, user): "estavamos inicializando el proyecto verifica que todo este al dia
  y que sepas todas las decisiones que tomamos si algo no esta claro preguntame"
- **L2** (verbatim, user answers to the verification report): first slice/milestone answer
  "necesito que quede lo mas completo posible"; next-step answer "Documentar + esqueleto del
  proyecto"; DXF answer "Es v2".
- **L3** Prior requirements interview record: Engram observations 3024–3036, project
  `sectionlab`, session `manual-save-sectionlab`. Specs S1–S18 consolidate them; nothing was
  added or removed.
- **L4** Repo audit before this work: directory `/home/ragnar_15/proyectos/sectionlab` was not
  a git repository; only `README.md`, `.atl/skill-registry.md`, `.atl/.gitignore`,
  `.atl/.skill-registry.cache.json` and an empty `.pi/` existed. The README advertised DXF
  in/out and v2 properties as current scope; both were corrected under L2.
- **L5** Delegation unavailable: the configured subagent model `C1-Pro/gemini-3.8-flash-high`
  does not resolve in the active profile, so T2–T13 run inline with test-first discipline.
- **L6** Implementation record (all verified with `tools/dev.sh uv run pytest tests/ -q`, 271
  tests green; 276 at close): T2 `core/units.py`, `core/precision.py`; T3 `core/model.py`,
  `core/validation.py`; T4 `core/engine.py`; T5 `core/templates.py`; T6 `core/document.py`;
  T7 `ui/results.py`; T8 `core/snap.py`, `ui/canvas.py`; T9 `ui/vertex_table.py`; T10/T11
  `ui/app.py`, `ui/settings.py`, `ui/template_panel.py`; T12 `ui/strings.py`.
- **L9** Packaging evidence (T13): `uv run pyinstaller --noconfirm --clean packaging/sectionlab.spec`
  builds a working onedir bundle on Linux (`dist/SectionLab`, 370 MB, 211 MB zipped), and the
  frozen binary passes `--self-test` (`area=20000.000000`, `ix=66666666.666668`). The GUI in
  the bundle also starts offscreen once the host `libEGL` is injected, the same host limitation
  `tools/dev.sh` works around. PyInstaller cannot cross-compile, so the actual Windows ZIP has
  to be produced on Windows by `tools\build_windows.ps1`.
- **L7** Template parameter form keeps the millimetre value it was built from, so switching
  mm → cm → in → mm on the form never accumulates rounding drift; typed values still convert
  on apply. Guarded by `tests/test_settings_ui.py`.
- **L8** `tools/dev.sh` exists because this Linux host lacks `libEGL.so.1`; it vendors the
  runtime into `.devlibs/` (gitignored) and forces `QT_QPA_PLATFORM=offscreen` for tests.

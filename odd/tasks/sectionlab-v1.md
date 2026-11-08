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
  verification is exact. Their on-screen representation is a 512-segment polygon; the polygon
  is presentation only and never feeds the calculation.
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
def calculate(section: Section) -> SectionProperties             # raises on invalid section

# sectionlab.core.templates
class TemplateKind(str, Enum): RECTANGLE; RECT_HOLLOW; CIRCLE; PIPE; TRIANGLE; POLYGON;
    I_PROFILE; H_PROFILE; U_CHANNEL; L_ANGLE; T_PROFILE
@dataclass(frozen=True)
class TemplateParam: key: str; default: float; minimum: float
def parameters(kind: TemplateKind) -> tuple[TemplateParam, ...]
def default_params(kind: TemplateKind) -> dict[str, float]
def build_section(kind: TemplateKind, params: Mapping[str, float]) -> Section

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
| T1 | S1, S18 | inline | Repo scaffold: git, uv project, src layout, pytest config, .gitignore, README realignment | pending |
| T2 | S2, S3, S4, S19 | worker | Units + precision core (mm internal, conversions, formatting, CSV precision) with tests | pending |
| T3 | S5, S9, S13, S19 | worker | Section model + contour validation (closure, <3 vertices, duplicates, self-intersection, zero area) | pending |
| T4 | S1, S11, S19 | worker | sectionproperties integration returning every S11 property about centroidal axes, verified against analytical values | pending |
| T5 | S10 | worker | Eleven parametric template generators with defaults and parameter rebuild | pending |
| T6 | S14 | worker | `.sectionlab` JSON persistence with schema version | pending |
| T7 | S15, S3, S4 | worker | Results table: display, clipboard copy, full-precision CSV | pending |
| T8 | S5, S7, S8, S17 | worker | Canvas: segment drawing, six snaps, vertex move/insert/delete, undo/redo | pending |
| T9 | S6, S17 | worker | Vertex table + typed vertex-list entry | pending |
| T10 | S13, S16 | worker | Calcular flow: always enabled, Spanish blocking messages, offending geometry highlighted | pending |
| T11 | S2, S3, S16 | worker | Settings dialog: active unit and visible decimals | pending |
| T12 | S16 | worker | Centralized Spanish UI strings; English code and logs | pending |
| T13 | S18 | worker | PyInstaller onedir spec, build script, ZIP smoke test | pending |

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

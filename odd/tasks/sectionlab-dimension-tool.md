# SectionLab — CAD dimension tool (v0.3)

Feature: replace derived per-segment dimensions with user-placed dimensions that drive the
geometry. Dimensioning stops being something the application does to every edge and becomes a
tool the user wields, like in a CAD program.

## Specs

- **S1 Only the dimensions the user placed exist.** No dimension is drawn for a segment
  because the segment exists. The canvas starts with no dimensions; `Ver → Cotas` (`Ctrl+D`)
  keeps toggling visibility, but now over the dimensions the user created. Quoted requirement:
  «no se que se le ponga cota a todo solo lo que yo acoto».
- **S2 Dimension tool.** A toolbar action (with its shortcut) arms a dimension mode: the first
  click fixes the first reference, the second click fixes the second reference — or a single
  click on a segment measures that segment's length — and the dimension line follows the
  cursor until the third click places it. `Esc` cancels the mode. Reference points are
  acquired with the existing snaps: the point a snap or an alignment guide locks is the point
  the reference is taken from, so a click near a vertex takes that vertex, a click on an edge
  midpoint takes that midpoint, and a click anywhere else on an edge takes the perpendicular
  foot there; the status bar names the snap that is being used. Anchors are durable (a vertex
  or a point at parameter `t` along an edge), so a locked point that is neither — a contour
  centre — is not available as a reference in this delivery. Quoted requirement: «debemos
  tener una herramienta de acotado como las de CAD».
- **S3 Three kinds of dimension in this delivery.** Segment length (axis-aligned segment),
  horizontal distance between two points, vertical distance between two points. A horizontal
  or vertical dimension measures the projection of the two references on that axis. Quoted
  decision: «Segmento + horizontal + vertical».
- **S4 Any distance inside the section.** The two references may be any two vertices, a vertex
  and an edge midpoint, or the midpoints of two edges; they need not be consecutive vertices.
  Two edge midpoints are reached by clicking each edge on its midpoint snap, while a click on
  the body of an edge keeps measuring that whole edge. Quoted requirement: «la forma de acotar cualquier distancia dentro de la sección».
- **S5 A dimension drives the geometry.** A double click on an editable dimension opens the
  one-line editor in the active unit; confirming makes the geometry measure the typed value in
  a single undo step. The displayed number is always measured from the geometry, never stored,
  so the drawing and its dimensions cannot disagree. Impossible or ambiguous values are
  refused with a Spanish message in the status bar. Quoted requirement: «parametrizarla, cosa
  que la modifico, se pueda modificar».
- **S6 A dimension on a template moves a template parameter.** Editing a dimension of a
  template section changes the template parameter that measure controls (each template
  declares its own mapping), the parameter form shows the new value and the section is redrawn;
  the section is never converted to free geometry behind the user's back. Quoted decision:
  «Cada plantilla declara qué parámetro mueve».
- **S7 Reference dimensions.** A dimension whose measure no single rule can satisfy
  unambiguously — the closing edge is the standing example — is created as a reference: it is
  drawn, it is not editable, and a double click explains why in the status bar.
- **S8 The user chooses where the dimension sits.** Every dimension stores its own separation
  from the measured entity; dragging its text changes that separation without touching the
  geometry. Quoted requirement: «como las de CAD».
- **S9 Deleting a dimension.** A selected dimension is deleted with `Supr` or from its context
  menu, undoably.
- **S10 Persistence and reference stability.** Dimensions are saved in the `.sectionlab` file as
  an optional key, so files written before this feature still open (with no dimensions) and
  dimensions survive a save/reopen round trip. References are remapped when vertices are
  inserted, deleted, or when the contour winding is normalized; a dimension whose anchor vertex
  disappears is removed and the status bar says so.
- **S11 Nothing else changes.** Units, precision, validation, section calculation, snapping,
  undo/redo, templates and the update flow keep their current semantics.
- **S12 Alignment guides.** While the cursor moves over the drawing — free geometry drawing,
  dimension placement and vertex dragging alike — the canvas shows dashed reference lines from
  the drawing's reference points (vertices, edge midpoints and each contour's centre) whenever
  the cursor shares their x or their y within a screen tolerance. The cursor locks to that
  coordinate, so the point that gets placed is exactly aligned, the active guide names the
  reference it belongs to in the status bar, and `Ver → Líneas de referencia` switches the
  guides off. This holds for the dimension line as well as for its references. While ortho is
  on, the coordinate ortho already fixed is not aligned again — the guides align the free axis
  only, because a guide on the fixed axis would contradict ortho. Guides are decoration over
  the geometry: they never move a vertex and never take part in undo. Quoted requirement: «otra cosa que quiero tener es lo de los cad que haga como
  las lineas de referencia con respecto a los puntos como para saber que estoy alineado».

## Tasks

| ID | Task | Specs | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | Dimension model: anchors, kinds, measure, remapping | S3, S4, S10 | core, test-first | `fa48fb5` |
| T2 | Generalized measure solver: one move rule per kind | S5, S7 | core, test-first | `fa48fb5` |
| T3 | Template parameter mapping per template kind | S6 | core, test-first | `567ea83` |
| T4 | Persistence of dimensions in `.sectionlab` | S10 | core, test-first | `567ea83` |
| T5 | Canvas draws, selects, drags and edits stored dimensions | S1, S5, S8, S9 | ui | `adbfe68` |
| T6 | Dimension tool mode with snaps and preview | S2 | ui | `adbfe68` |
| T7 | App wiring, strings, docs, auto-dimension removal | S1, S11 | ui + docs | `adbfe68` |
| T8 | Alignment guides: pure guide computation and cursor lock | S12 | core/snap, test-first | `91a1849` |
| T9 | Canvas paints the guides, locks the cursor, View toggle | S12 | ui | `adbfe68` |

## Log

- **L1** (user, verbatim):
  «que tal quiero seguir trabajando en la app
  /tmp/herdr-clipboard-images-1000/client-232-clipboard-1794443358107768934-0.png observa como
  se ve actualmente las cotas la idea que yo tengo es tener lla forma de acotar cualquier
  ditancia dentro del la seccion y parametrizarla cosa que la la modifico se pueda modificar
  como podemos logar eso, y no se que se le ponga cota a todo solo lo que yo acoto debemos
  tener una herramienta de acotado como las de CAD»
- **L2** (decisions taken in the design conversation):
  - Template: «Cada plantilla declara qué parámetro mueve».
  - Kinds in the first delivery: «Segmento + horizontal + vertical».
  - Automatic per-segment dimensions: «Se eliminan: solo las que yo cree».
- **L4** (user, verbatim):
  «otra cosa que quiero tener es lo de los cad que haga como las lineas de referencia con
  respecto a los puntos como para saber que estoy alineado.»
  Split as S12, T8 (pure computation, no Qt) and T9 (canvas and menu), because it does not
  depend on the dimension model and can be built beside it.
- **L3** (design consequence accepted by the parent): the reference is stored as an anchor
  (`vertex i` or `edge i at t`), the value is measured and never persisted, and one move rule —
  translate every vertex on the far side of a reference plane along a direction — serves the
  three kinds, which keeps the solver deterministic and testable without Qt.
- **L5** (independent verification round over T1-T9): one read-only verifier reproduced the
  feature headlessly and signed off S1, S3, S5-S8, S10-S12 with evidence. It failed three
  points and the parent corrected them, keeping the specs above in step:
  - Deleting a dimension announced «cotas eliminadas» because the dropped count compared the
    previous list with the kept one; it now counts what the incoming snapshot could not keep.
  - A wholesale section replacement (a different template, a new drawing) silently re-anchored
    the old dimensions to unrelated vertices and persisted them; such a shape change now drops
    them and says so, while rebuilding the same template keeps them.
  - A dimension coming from a file that no longer fits was dropped without a word; it is
    reported now.
  Reference acquisition and the alignment guides had two gaps against S2/S4/S12: an edge
  midpoint could not start a dimension, so no two midpoints could be measured, and the
  dimension line ignored the guides and lost them under ortho. Anchors now come from the point
  the snaps and guides lock, and the dimension line is locked the same way.

## Slices

Review boundaries, in commit order. Slice 1 already landed; it is kept apart because the
alignment guides touch neither the dimension model nor the canvas.

| Slice | Commits | Contents |
| --- | --- | --- |
| 1 | `34c3267`, `91a1849`, `fa48fb5`, `4f84e60` | specs; alignment guides (T8); dimension model and solver (T1, T2); lock sync |
| 2 | `567ea83` | template parameter mapping and persistence (T3, T4) |
| 3 | `adbfe68` | canvas and window: placed dimensions, selection, drag, delete, the Acotar tool, alignment guides, commands, strings, automatic dimensions removed, README (T5, T6, T7, T9) |
| 4 | `d0a3f0c` | what the verification round corrected: honest drop reporting, no silent carry-over across a shape change, midpoint references, guide-locked dimension lines |

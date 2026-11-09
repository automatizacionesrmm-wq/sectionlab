# SectionLab canvas refinement

Make the drawing readable and dimensionable: visible snap targets, reference axes, a marked
centroid with its own axes, one dimension per segment with a switch, parametric dimension
editing, a table that highlights what it selects, and inspectors that can actually move.

Conventions unchanged: geometry in millimetres, Spanish UI strings, English code and commits,
`core/` never imports Qt.

## Specs

S1. Vertex handles are smaller than in 0.1.1 and never hide the geometry. The selected vertex
    is unmistakable: larger mark, ring, and its index beside it. The click radius stays
    forgiving (9 px), so smaller handles never make a vertex harder to grab.

S2. Every segment of the outer contour shows its dimension while the dimensions are switched
    on: horizontal segments their width, vertical segments their height, slanted segments
    their length, drawn with extension lines, a dimension line and the value in the active
    unit with the display decimals. `Ver → Cotas` (checkable, on by default) turns them all on
    and off.

S3. «que cada linea tenga para acotar y que cuando acoto eso sea parametrico»: an orthogonal
    dimension is editable in place. Double-clicking its value opens an editor in the active
    unit; confirming the value moves every vertex on the far side of that segment by the same
    delta, so a rectangle stays a rectangle and the contour stays closed, and the change is
    one undo step. Slanted segments and the closing segment (last vertex back to the first)
    stay read-only, because their length is a consequence of the others. A rejected value (not
    a number, zero or less, an unchanged value, a template section) leaves the geometry
    untouched and says why in the status bar.

S4. «la parte de los osnad no la veo»: a snap target is visibly marked the moment the cursor
    picks it, with a glyph per family (endpoint square, midpoint triangle, centre circle,
    intersection cross, perpendicular right angle) and its Spanish name next to the cursor.

S5. The reference axes are explicit: the x and y axes through the origin are drawn stronger
    than the grid and labelled `X` and `Y`, so the origin the coordinates come from is
    obvious. The centroid is marked with a dot and `C`, and its own axes are drawn through it
    as dashed lines labelled `1` and `2`, rotated by the principal angle. Nothing is drawn
    before a calculation exists.

S6. «la parte de plantilla solo debe estar activa si yo escojo plantilla»: the template
    inspector is only on screen while the section comes from a template. In free geometry it
    disappears, its entry in `Ver → Paneles` is disabled, and the drawing gets the space.
    Loading a template brings it back.

S7. Selecting a vertex in the table marks that same vertex on the drawing, and clicking a
    vertex on the drawing selects its row. The two views never disagree.

S8. «todos los cuadros estan de un solo lado… yo quiero poder moverlos»: dragging an
    inspector by its header really moves it — to the left column, the right column, or out as
    its own window — and right-clicking the header offers the same moves as explicit entries,
    so it works even when dragging is awkward. The bottom edge is deliberately not a target:
    it would take height away from the drawing. Double-clicking the header floats or
    docks it. The default arrangement spreads the information: `Plantilla` above `Vértices` on
    the left, `Resultados` on the right, drawing in the middle.

S10. «verificar que la unidad de los datos de entrada sean los mismos para la salida»: the unit
    is one, for input and for output. A dimension, a vertex coordinate and a result are all
    written in the active unit, and the unit symbol next to a value is the unit that value was
    converted to — `20000 mm²` never shows as `200` next to `mm²`. A value typed in centimetres
    reads back as the same number in centimetres, without drift.

S11. «los valores que vienen de una plantilla no se pueden editar»: a template section belongs
    to its parameters, so its vertices cannot be nudged. The template inspector offers
    **Convertir a geometría libre**: the contour is kept exactly as drawn, the template is
    dropped, the vertices and dimensions become editable, and it is one undoable step that
    walks back into template mode. While a template field has the keyboard, the dimensions
    that measure it are highlighted with the field's own name, so it is clear which value is
    being edited.

S9. Every change respects the existing contract: millimetre geometry, contour wound CCW, one
    undo step per user action, `Calcular` still validating before it reports, no Qt import
    below `ui/`.

## Tasks

T1. Viewport readability — smaller handles, selected-vertex marker, snap glyphs with names,
    labelled reference axes, centroid with its principal axes — and the segment dimensions
    with the `Ver → Cotas` switch. commit: `feat: dimension every segment` (includes T2, which
    the same painter and the same unit plumbing made inseparable).
T2. Segment dimensions with the `Ver → Cotas` switch. Landed with T1.
T3. Parametric dimension editing through a pure geometry operation plus an in-place editor.
    commit: `feat: let a dimension drive the geometry`
T4. Template sections become free geometry, the focused parameter names its dimension, and the
    template inspector leaves with the template. commit: `feat: convert a template into
    editable geometry`
T5. Table and drawing selection sync, movable inspectors with real drag and a header menu, new
    default arrangement. commit: `ui: arrange and move the inspectors`
T6. Documentation, README, full verification and the 0.1.2 build. commit: `docs: describe the
    dimensioned canvas`

## Log

L1. User, verbatim: «lo puntos de los vertices estan demaciado grande
    /tmp/herdr-clipboard-images-1000/client-224-clipboard-1794238035948202066-0.png   la cotas
    de cada segmento deben poder verse encender y apagar o acotar asi uno sabe si el dibujo
    esta de acuero a lo que se queria, la parte de los osnad no la veo. deberia marcarse el eje
    de refderencia desde donde se estan midiendo los centroide y marcarse el centroide con sus
    ejes. la parte de plantilla solo debe estar activa si yo escojo plantilla sino deb esta en
    lienzo limpio sin ocupar espacio. cuando toco uno de los vertices de la tabla  deberia
    marcarce el que selecione en pantalla.  todos los cuadros estan de un solo lado no deberia
    ser asi yo quiero poder moverlos. porque se miran demaciadas cosas en un solo lado. que
    cada linea tenga para acotar y que cuando acoto eso sea parametrico entiendes?  .»

L2. Decisions taken with the user before writing code: the dimension is editable and moves the
    geometry (no constraint solver, no read-only phase); the template inspector hides itself in
    free geometry; the default arrangement is `Plantilla` + `Vértices` left, `Resultados`
    right. The attached screenshot could not be opened on this host, so the specs rely on the
    words above.

L3. User, verbatim: «hay dos problemas primero los valores que vienen de una plantilla no se
    pueden editar no se pueden ajustar a mi gusto y en la pantalla no esta claro que valor se
    esta editando» (reported in Spanish, reproduced here as the request it was). Decision
    taken with the user before writing code: **convert to free geometry and edit**, keeping
    the contour exactly as it is, over a hybrid mode or editing through the template only.

L4. User, verbatim: «continua acuerdate tambie de verificar que la unidad de los datos de
    entrada sean los mismos para la salida.» This uncovered a real defect: the results table
    converted values to the active unit but kept the millimetre symbol, so `20000 mm²` showed
    as `200` next to `mm²`. Fixed in T1's commit and pinned by
    `test_the_unit_column_follows_the_active_unit`.

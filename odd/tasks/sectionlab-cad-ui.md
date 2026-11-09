# SectionLab — CAD-grade interface (v1.1)

Feature: rebuild the SectionLab interface so it reads as a professional cross-section tool
instead of generic Qt widgets, and so the drawing behaves like CAD.

## Specs

- **S1 Professional shell.** The window looks like an engineering application: dark chrome,
  an icon toolbar grouped by intent, a drawing area that dominates the window, and panels that
  read as docked inspectors, not form stacks. Quoted requirement: «no se parece nada
  profesional a una app de secciones», «los iconos de CAD».
- **S2 Icons on every action.** Every tool, command and panel header carries a line icon; no
  action is identifiable only by its text. The calculate command is a primary button with an
  icon and its shortcut. Quoted requirement: «no veo botones con sus iconos de calcular».
- **S3 CAD drawing area.** The canvas renders a drafting surface: adaptive grid with a major
  and minor step, labelled axes, contour fill plus outline, fixed-size vertex handles,
  centroid marker with dashed centroidal axes, crosshair cursor, snap marker with its name,
  live delta readout, dimensions, and a scale bar or zoom controls. Quoted requirement: «el
  dibujo de lineas y demas no se siente como un CAD».
- **S4 Template changes are immediate.** Selecting a template kind draws it at once with its
  default parameters, and editing a parameter redraws the shape without pressing anything.
  Quoted requirement: «si yo cambio de perfil tengo que darle aplicar para poder que se
  dibuje porque?». Spec S10 of `sectionlab-v1.md` already requires that a parameter change
  rebuilds the shape; the current implementation only rebuilds on `Aplicar`.
- **S5 Readable results.** Results are grouped (geometry, centroidal inertia, radii and
  moduli), right-aligned in a monospace column, with the unit as a quiet suffix, and are
  readable at a glance in the unit and decimals the user chose. Quoted requirement: «no veo
  botones … y demas».
- **S6 Unchanged semantics.** Units, precision, validation messages, persistence,
  sectionproperties calculation, snapping geometry and undo behaviour keep their current
  contracts; this feature changes how the tool looks and how templates commit, not what it
  computes.

## Tasks

| ID | Specs | Route | Commit | State |
| --- | --- | --- | --- | --- |
| T1 | S1-S3 | Design directions under `design/sectionlab-cad/` | — | done |
| T2 | S1, S2 | Inline: theme tokens (`ui/theme.py`), icon factory (`ui/icons.py`), toolbar/rail regrouping | `f53d574`, `25bb460`, `853b71d` | done |
| T3 | S3 | Inline: canvas drafting surface (grid, axes, crosshair, snap marker, scale) | `a51c4c4` | done |
| T4 | S4 | Inline: live template rebuild (kind change draws, parameter edit redraws) | `f30d9a9` | done |
| T5 | S5 | Inline: grouped results inspector and vertex inspector styling | `853b71d` | done |
| T6 | S1-S6 | Inline: verification, screenshots offscreen, README update | `cf9873b` | done |

## Log

- **L1** User, verbatim: «esto es lo que me sale … no se parece nada profesional a una app de
  secciones no veo botones con sus iconos de calcular y demas los iconos de CAD como podemos
  mejorarlo ademas de que el dibujo de lineas y demas no se siente como un CAD».
- **L2** User, verbatim: «ahorita si yo cambio de perfil tengo que darle aplicar para poder
  que se dibuje porque?». Diagnosed as a UX defect against S10 of `sectionlab-v1.md`:
  `TemplatePanel` only emits `applied` from the `Aplicar` button, and `set_kind` rebuilds the
  parameter form alone, so a kind change never redraws the section.
- **L3** Three design directions written to `design/sectionlab-cad/`: `01-estacion-oscura.html`
  (dark CAD workstation), `02-plano-claro.html` (light drafting sheet with a results strip),
  `03-estudio-compacto.html` (floating palettes plus a command line). Alternatives: the one
  handed off gets implemented, the others stay as references.
- **L4** Scope decision by the user: implement **both** themes (dark and light) in a single
  shell rather than one of the three artboards, so the drawing takes its colours from one
  token table per theme (`ui/theme.py`) and the stylesheet and canvas pens cannot drift.
  Vector icons only, drawn in code (`ui/icons.py`): no image assets to ship, and they recolour
  with the theme while staying crisp on high-density screens. Commits `f53d574`, `25bb460`.
- **L5** Live template rebuild fixed per L2: `TemplatePanel` emits `applied` immediately on a
  kind change and after a 120 ms pause on a parameter edit; `set_kind`/`set_params` stay silent
  so opening a document does not repaint. `Aplicar` remains only as an explicit affordance.
  Commit `f30d9a9`; tests `tests/test_template_panel.py`.
- **L6** Shell rebuilt as one window with an icon toolbar grouped by intent, `Calcular` as the
  primary button, and three docked panel cards (Plantilla, Vértices, Resultados) inside a
  scroll area. Theme switch lives in `Ver → Tema` (`Ctrl+Shift+T`) and is persisted with the
  other preferences in `AppSettings.theme`; the canvas receives the theme palette through
  `CanvasView.apply_palette`. Commit `853b71d`.
- **L7** Canvas drafting surface: adaptive minor grid whose step is picked from
  `GRID_STEPS` so no line falls below 7 px, major lines every five minor steps with labels in
  model millimetres, x/y axes, live crosshair with an `X, Y` readout, snap marker, inner
  contour drawn dashed, closed outer contour filled, pixel-based vertex hit testing so handles
  stay clickable at any zoom, and `reset_view` as the fit fallback for an empty scene. Commit
  `a51c4c4`.
- **L8** Verification: `tools/dev.sh uv run pytest tests/` → **306 passed** (28 new tests in
  `test_theme.py`, `test_icons.py`, `test_template_panel.py` and additions to `test_app.py`,
  `test_canvas.py`, `test_settings_ui.py`). Offscreen screenshots inspected at 1440x900 for
  dark, light and free-geometry modes; the Qt stylesheet sub-controls (spin arrows, combo
  chevron) had to be painted into cached PNGs because Qt rejects colour fragments there.
- **L9** Windows bundle rebuilt from the redesign by GitHub Actions: run `42627713014` on
  `windows-latest` finished `success` for `85083d0`, artifact `SectionLab-windows`
  108.59 MB (the frozen `--self-test` gate inside the workflow re-checked the reference
  numbers, so the packaged build computes the same section as the tests).
- **L10** User, verbatim: «el zoon no quiero scroll quiero porde navegar dentro del canvas como
  lo hago en autocad acercarme alejarme cnetra asi como lo hago en autocad o los CAD». The view
  now has no scrollbars: the wheel scales about the cursor, the middle button drags the
  drawing, a middle double click fits the section, and toolbar Acercar/Alejar zoom about the
  viewport centre. A fixed large world rect keeps panning free of the content bounds, and
  `S3` stays satisfied because the navigation is part of the drafting surface.
- **L11** User, verbatim: «cuando quiero cerrar la figura aqui no puedo … toco el vertice y se
  abren las propiedades pero no se pone la linea la idea es que sea como en autocad que yo
  pueda unir las lineas para eso eran los osnap». Two causes: the Windows ZIP the user had was
  built *before* `efaf29c` (the closing fix), and even with it the only closing spot was a
  9 px halo on the first vertex with no visual cue. Repair: the first vertex is painted with
  the `ok` token as the closing target while drawing, a click within `CLOSE_HIT_PX` (14 px) of
  it closes (drawn anyway at snap tolerance 8 px), the right button closes when there are
  three or more vertices and cancels below that, and the status hint names every way to close.
  Tests: `test_a_click_near_the_first_vertex_closes_the_contour`,
  `test_the_context_button_closes_the_contour`,
  `test_the_context_button_cancels_a_short_polyline`,
  `test_the_first_vertex_is_highlighted_as_the_closing_target`.
- **L12** Clicking the starting point must never leave a duplicate vertex behind, because that
  is what the old build did and it produced «Hay vértices en la misma posición». `add_vertex`
  now closes the polyline when the appended point coincides with the first one and there are
  three or more vertices; anything else is appended as before.
- **L13** User, verbatim: «la pantalla de dibujo sea tan chica deberia ser la mas grande y
  tener la barra de propiedades y de editar en un lugar y que se pueda mover y ajustar donde
  quiera agrandar y achicar». The fixed `QSplitter` plus scrolling side column became three
  `QDockWidget`s (movable, floatable, closable) with the canvas as the central widget, and
  `Ver → Paneles` (`F9`) hides them all. While capturing the result the icon sheet showed a
  second defect: `icon()` scaled its 24-unit drawing by `size * ratio / _GRID` on a pixmap
  that already carried the device pixel ratio, so every icon was drawn at twice its size and
  clipped to its top-left fragment. Fixed to `size / _GRID`, with
  `test_every_icon_fills_its_box_without_being_clipped` pinning it (RED before, GREEN after).
- **L14** User, verbatim: «me gusta visualmente pero hice algo quite la barra lateral ahora
  donde la encuentro?» — the docks could be closed with their own `×` and the only way back
  was `F9`, which nothing announced. S3/S4 now require: a `Ver → Paneles` submenu built from
  each dock's `toggleViewAction()` (so a single panel is reopened by name, in sync with Qt),
  a master entry that is checked only when **every** inspector is up, so one press adds back
  what is missing instead of finishing the hiding, and a status-bar hint
  («Paneles ocultos · F9 o Ver → Paneles los recupera») that is visible only while none of
  them is on screen. Tests: `test_one_shortcut_press_restores_the_panels_it_found_missing`,
  `test_the_panels_menu_can_reopen_the_one_that_was_closed`,
  `test_the_status_bar_explains_how_to_bring_the_panels_back`; the older
  `test_hiding_one_panel_unchecks_the_toggle` now pins the all-visible semantics.
  Verified: 334 tests green, offscreen captures of the submenu and of the status hint, CI run
  42644791067 on `86dff1a` green, and Release `v0.1.1` published with setup 71.81 MB,
  portable 108.99 MB and code 44 625 B. The version was bumped because a code archive that
  keeps the `0.1.0` name would be indistinguishable from the one already installed, and
  `tests/test_package.py` now derives the expected version from `pyproject.toml` instead of
  hard-coding it, which is what failed first.

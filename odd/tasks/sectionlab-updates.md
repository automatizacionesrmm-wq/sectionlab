# SectionLab in-app updates

The application tells the user that a newer release exists, shows the version it is running,
and updates itself from inside the window: download, apply, ask before restarting. The split
delivery makes this cheap — the application code is plain `.py` files under `app\`, outside the
frozen executable, so a new version costs about 50 kB and never needs the installer.

Conventions unchanged: geometry in millimetres, Spanish UI strings, English code and commits,
`core/` never imports Qt.

## Specs

S1. The running version is visible without opening a file: the window title reads
    `SectionLab <version>`, `Configuración → Preferencias` shows it, and a new
    `Ayuda → Acerca de SectionLab` shows the version, the licence line and the repository link.

S2. «la idea es que en pantalla me indique nueva actulizacion entonces como ahorita estoy
    probando necesito que cada nueva release necesito probarlo»: the check runs once per launch,
    in the background, and never blocks the drawing or the calculation. `Ayuda → Buscar
    actualizaciones` repeats it on demand. No time-based cache: while releases are being tested,
    every launch must see the newest one.

S3. When a newer version exists, a dismissible banner appears above the drawing, without a modal
    dialog: `Hay una versión nueva <version>`, with `Actualizar` and `Más tarde`. `Más tarde`
    hides it for this session only; the next launch offers it again. Nothing is downloaded until
    the user asks for it.

S4. `Actualizar` downloads the code archive of that release into the user's application-data
    folder, verifies its SHA-256 when GitHub publishes one, and only then replaces
    `app\sectionlab\`, keeping the previous folder as `sectionlab.bak` until the new code starts
    successfully. A download that fails partway leaves the installation untouched.

S5. After applying, the application asks before restarting, as chosen by the user. With unsaved
    changes it says so instead of discarding them; restarting re-launches the same executable and
    the window closes only after the new process starts.

S6. A release that needs a new runtime (a dependency, Python or Qt) is not solved by a code
    archive. When the release carries no `-code.zip`, the banner offers the full installer, which
    runs after the application closes; the per-user installer needs no administrator rights.

S7. Failure never blocks and never nags: an automatic check that fails (offline, DNS, rate limit,
    unexpected JSON) changes nothing on screen. A manual check reports the reason in the status
    bar, in Spanish. The update path is never a prerequisite for drawing or calculating.

S8. Comparison is numeric, not alphabetical: `0.10.0` is newer than `0.9.9`. A release whose
    version cannot be parsed is ignored rather than offered.

S9. Every network and archive operation lives behind a seam that tests replace, so the suite runs
    offline and deterministically: the release fetch, the archive download and the restart are
    injected, never performed.

S10. The frozen runtime must be able to do it: `packaging/launcher.py` declares every module the
    excluded application package needs at runtime that the analyser can no longer see, including
    the HTTPS and archive modules, and a test fails if that list drifts.

## Tasks

T1. Pure update logic and archive installation, free of Qt. commit: `feat: know when a release is
    newer`
T2. Version on screen, background check, manual check and the update banner. commit: `feat: say
    when an update is waiting`
T3. Download, verify and apply, then ask before restarting; installer fallback. commit: `feat:
    update from inside the window`
T4. Launcher drift for the network modules, README and version 0.2.0. commit: `build: freeze the
    modules the updater needs`
T5. Verification, Windows build and release 0.2.0 — the first release that can update itself.

## Log

L1. User, verbatim: «osea yo prefiero que ya desde dentro desde mi misma app me salga hay
    actulizaciones y que actulice y muestre la version»

L2. Decisions taken with the user before writing code: **make the repository public** so the
    check needs no credentials (his choice, after the three options were explained); **check on
    every launch plus a manual entry**, because releases are being tested right now and a daily
    cache would hide the new one; **ask before restarting**.

L3. Repository made public after a bounded audit of everything ever committed: 62 files, all
    source, tests, documentation and design artboards; no environment files, no keys, no
    binaries. The commit author email becomes public with the history.

L4. The updater cannot update the build that lacks it: 0.2.0 has to be installed once with the
    setup, and from 0.2.0 onward every release can be applied from inside the window.

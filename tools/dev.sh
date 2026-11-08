#!/usr/bin/env bash
# Linux development wrapper.
#
# The Ubuntu dev host lacks the system libEGL that Qt 6 dlopen()s; PySide6 needs it before
# any Qt import. This wrapper points the loader at the vendored copy under .devlibs/ (not
# committed) and then runs whatever command it was given.
#
# Usage: tools/dev.sh uv run pytest
#        tools/dev.sh uv run sectionlab
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
vendor_lib="$repo_root/.devlibs/root/usr/lib/x86_64-linux-gnu"

if [[ -d "$vendor_lib" ]]; then
  export LD_LIBRARY_PATH="$vendor_lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

cd "$repo_root"
exec "$@"

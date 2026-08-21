#!/usr/bin/env bash
# Runtime PR/release baseline. It validates the locked FineWine patch bytes and
# applies them to a clean CodeWeavers Wine source tree; it does not build Wine.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESET_SOURCE=false

case "${1:-}" in
  "") ;;
  --reset-source) RESET_SOURCE=true ;;
  --help|-h)
    echo "Usage: ./script/runtime-preflight.sh [--reset-source]"
    exit 0
    ;;
  *)
    echo "Unknown option: $1" >&2
    exit 2
    ;;
esac

cd "$ROOT_DIR"

for command_name in git jq shasum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

# FineWine carries upstream trailing whitespace in two original patch files.
# .gitattributes intentionally exempts that imported text from the check.
git diff --check
bash -n script/build-runtime.sh script/sync-wine-source.sh

# shellcheck source=/dev/null
source runtime.env
# shellcheck source=/dev/null
source sources/WINE_SOURCE.lock
# shellcheck source=/dev/null
source sources/FINEWINE_PATCHSET.lock

[[ "$RUNTIME_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || {
  echo "RUNTIME_VERSION is not SemVer: $RUNTIME_VERSION" >&2
  exit 1
}
[[ "$RUNTIME_PATCHSET" == finewine-endfield-* ]] || {
  echo "RUNTIME_PATCHSET must identify the FineWine build: $RUNTIME_PATCHSET" >&2
  exit 1
}
[[ "$WINE_VERSION" == "11.0" ]] || {
  echo "FineWine integration has only been verified against Wine 11.0." >&2
  exit 1
}

patch_root="patches/finewine"
test -f "$patch_root/PATCH_ORDER"
test -f "$patch_root/PATCHES.sha256"
(
  cd "$patch_root"
  shasum -a 256 -c PATCHES.sha256
)

actual_patch_count="$(grep -cve '^[[:space:]]*$' "$patch_root/PATCH_ORDER")"
[[ "$actual_patch_count" == "$FINEWINE_PATCHSET_PATCH_COUNT" ]] || {
  echo "FineWine PATCH_ORDER count mismatch: expected $FINEWINE_PATCHSET_PATCH_COUNT, got $actual_patch_count" >&2
  exit 1
}

jq -e \
  --arg version "$RUNTIME_VERSION" \
  --arg revision "$FINEWINE_PATCHSET_REVISION" \
  --argjson patch_count "$FINEWINE_PATCHSET_PATCH_COUNT" \
  '.schemaVersion == 1
    and .version == $version
    and .runtimeABI >= 1
    and .prefixABI == "arclume-jx3-prefix-1"
    and .capabilities.fineWinePatchSet.revision == $revision
    and .capabilities.fineWinePatchSet.patchCount == $patch_count' \
  manifests/runtime-definition.json >/dev/null

if [[ "$RESET_SOURCE" == true ]]; then
  ./script/sync-wine-source.sh --reset
else
  ./script/sync-wine-source.sh
fi

source_marker="work/wine/.arclume-patchset"
[[ -f "$source_marker" && "$(<"$source_marker")" == "$FINEWINE_PATCHSET_REVISION" ]] || {
  echo "FineWine patch marker was not written to the source worktree." >&2
  exit 1
}

grep -q 'PsGetProcessImageFileName' work/wine/dlls/ntoskrnl.exe/ntoskrnl.c
grep -q 'is_privileged_instr' work/wine/dlls/ntdll/unix/signal_x86_64.c
grep -q 'KiUserApcDispatcher' work/wine/dlls/kernel32/module.c

echo "Runtime preflight passed: Arclume Wine $RUNTIME_VERSION, FineWine $FINEWINE_PATCHSET_REVISION."

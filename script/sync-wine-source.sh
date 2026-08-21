#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/sources/WINE_SOURCE.lock"
SOURCE_DIR="$ROOT_DIR/work/wine"
CACHE_DIR="$ROOT_DIR/cache"
PATCH_DIR="$ROOT_DIR/patches"
FINEWINE_PATCH_DIR="$PATCH_DIR/finewine"
FINEWINE_LOCK_FILE="$ROOT_DIR/sources/FINEWINE_PATCHSET.lock"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "Missing source lock file: $LOCK_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$LOCK_FILE"

if [[ ! -f "$FINEWINE_LOCK_FILE" ]]; then
  echo "Missing FineWine patchset lock file: $FINEWINE_LOCK_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$FINEWINE_LOCK_FILE"
PATCHSET_MARKER_FILE="$SOURCE_DIR/.arclume-patchset"

reset_source=false
case "${1:-}" in
  "") ;;
  --reset) reset_source=true ;;
  --help|-h)
    cat <<'USAGE'
Usage: ./script/sync-wine-source.sh [--reset]

Downloads the locked public CodeWeavers source package when necessary, verifies
its SHA-256, extracts sources/wine into work/wine, and applies tracked patches
in lexical order.

  --reset  Safely discard the local extracted Wine worktree before re-extracting.
USAGE
    exit 0
    ;;
  *)
    echo "Unknown option: $1" >&2
    exit 2
    ;;
esac

if [[ -f "$SOURCE_DIR/VERSION" && "$reset_source" == false ]]; then
  actual_version="$(<"$SOURCE_DIR/VERSION")"
  if [[ "$actual_version" == "Wine version $WINE_VERSION" \
      && -f "$PATCHSET_MARKER_FILE" \
      && "$(<"$PATCHSET_MARKER_FILE")" == "$FINEWINE_PATCHSET_REVISION" ]]; then
    echo "Wine source is ready: $SOURCE_DIR ($actual_version)"
    exit 0
  fi
  echo "Existing source tree does not match the locked FineWine patchset." >&2
  echo "Run with --reset after saving any local work." >&2
  exit 1
fi

if [[ "$reset_source" == true && -e "$SOURCE_DIR" ]]; then
  case "$SOURCE_DIR" in
    "$ROOT_DIR"/work/wine) ;;
    *)
      echo "Refusing to reset unexpected source path: $SOURCE_DIR" >&2
      exit 1
      ;;
  esac
  /usr/bin/find "$SOURCE_DIR" -depth -delete
fi

/bin/mkdir -p "$CACHE_DIR" "$SOURCE_DIR"
ARCHIVE_PATH="$CACHE_DIR/$SOURCE_ARCHIVE"

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  partial_path="$ARCHIVE_PATH.partial"
  /usr/bin/curl --fail --location --progress-bar --output "$partial_path" "$SOURCE_URL"
  /bin/mv "$partial_path" "$ARCHIVE_PATH"
fi

actual_sha="$(/usr/bin/shasum -a 256 "$ARCHIVE_PATH" | /usr/bin/awk '{print $1}')"
if [[ "$actual_sha" != "$SOURCE_SHA256" ]]; then
  echo "Source SHA-256 mismatch for $ARCHIVE_PATH" >&2
  echo "Expected: $SOURCE_SHA256" >&2
  echo "Actual:   $actual_sha" >&2
  exit 1
fi

/usr/bin/tar -xzf "$ARCHIVE_PATH" -C "$SOURCE_DIR" --strip-components=2 "$SOURCE_MEMBER"

actual_version="$(<"$SOURCE_DIR/VERSION")"
if [[ "$actual_version" != "Wine version $WINE_VERSION" ]]; then
  echo "Extracted Wine version is unexpected: $actual_version" >&2
  exit 1
fi

apply_patch_file() {
  local patch_file="$1"
  if [[ ! -f "$patch_file" ]]; then
    echo "Tracked patch is missing: $patch_file" >&2
    exit 1
  fi
  echo "Applying ${patch_file#"$ROOT_DIR"/}"
  # Wine is an extracted worktree beneath this repository. Apply from the
  # Runtime root and explicitly prefix every patch path so Git cannot mistake
  # the source directory for the repository-relative path.
  /usr/bin/git -c core.attributesFile=/dev/null -C "$ROOT_DIR" apply \
    --check --whitespace=nowarn --directory=work/wine "$patch_file" \
    2> >(/usr/bin/grep -vF '[attr]generated gitlab-generated linguist-generated=true not allowed: work/wine/.gitattributes:1' >&2)
  /usr/bin/git -c core.attributesFile=/dev/null -C "$ROOT_DIR" apply \
    --whitespace=nowarn --directory=work/wine "$patch_file" \
    2> >(/usr/bin/grep -vF '[attr]generated gitlab-generated linguist-generated=true not allowed: work/wine/.gitattributes:1' >&2)
}

shopt -s nullglob
patches=()
patches=("$PATCH_DIR"/*.patch)
for patch_file in "${patches[@]-}"; do
  [[ -n "$patch_file" ]] || continue
  apply_patch_file "$patch_file"
done

if [[ ! -f "$FINEWINE_PATCH_DIR/PATCH_ORDER" \
    || ! -f "$FINEWINE_PATCH_DIR/PATCHES.sha256" ]]; then
  echo "FineWine patchset manifest is incomplete." >&2
  exit 1
fi

(
  cd "$FINEWINE_PATCH_DIR"
  /usr/bin/shasum -a 256 -c PATCHES.sha256
)

finewine_patch_count=0
while IFS= read -r patch_relative; do
  if [[ -z "$patch_relative" || "$patch_relative" == /* || "$patch_relative" == *".."* ]]; then
    echo "Unsafe FineWine patch path: $patch_relative" >&2
    exit 1
  fi
  apply_patch_file "$FINEWINE_PATCH_DIR/$patch_relative"
  finewine_patch_count=$((finewine_patch_count + 1))
done < "$FINEWINE_PATCH_DIR/PATCH_ORDER"

if [[ "$finewine_patch_count" != "$FINEWINE_PATCHSET_PATCH_COUNT" ]]; then
  echo "FineWine patch count mismatch: expected $FINEWINE_PATCHSET_PATCH_COUNT, applied $finewine_patch_count" >&2
  exit 1
fi

/usr/bin/printf '%s\n' "$FINEWINE_PATCHSET_REVISION" > "$PATCHSET_MARKER_FILE"

echo "Wine source is ready: $SOURCE_DIR ($actual_version)"

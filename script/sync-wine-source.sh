#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/sources/WINE_SOURCE.lock"
SOURCE_DIR="$ROOT_DIR/work/wine"
CACHE_DIR="$ROOT_DIR/cache"
PATCH_DIR="$ROOT_DIR/patches"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "Missing source lock file: $LOCK_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$LOCK_FILE"

reset_source=false
case "${1:-}" in
  "") ;;
  --reset) reset_source=true ;;
  --help|-h)
    cat <<'USAGE'
Usage: ./script/sync_crossover_wine_source.sh [--reset]

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
  if [[ "$actual_version" == "Wine version $WINE_VERSION" ]]; then
    echo "Wine source is ready: $SOURCE_DIR ($actual_version)"
    exit 0
  fi
  echo "Existing source version is unexpected: $actual_version" >&2
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

shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
for patch_file in "${patches[@]}"; do
  echo "Applying $(basename "$patch_file")"
  /usr/bin/patch -d "$SOURCE_DIR" -p1 --forward --batch < "$patch_file"
done

echo "Wine source is ready: $SOURCE_DIR ($actual_version)"

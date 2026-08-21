#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/sources/WINE_SOURCE.lock"
RUNTIME_DEFINITION="$ROOT_DIR/runtime.env"
SOURCE_DIR="$ROOT_DIR/work/wine"
BUILD_DIR="$ROOT_DIR/work/build/wine-x86_64"
DIST_DIR="$ROOT_DIR/dist"
RUNTIME_MARKER_FILE=".arclume-runtime-version"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "Missing source lock file: $LOCK_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$LOCK_FILE"

if [[ ! -f "$RUNTIME_DEFINITION" ]]; then
  echo "Missing runtime definition: $RUNTIME_DEFINITION" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$RUNTIME_DEFINITION"

if [[ -z "${RUNTIME_PATCHSET:-}" ]]; then
  echo "runtime.env must define RUNTIME_PATCHSET." >&2
  exit 1
fi

RUNTIME_ROOT="arclume-wine-runtime-${RUNTIME_ARCHITECTURE}"
DEFAULT_OUTPUT="$DIST_DIR/arclume-wine-${RUNTIME_VERSION}-${RUNTIME_ARCHITECTURE}.tar.xz"

clean_build=false
repackage_only=false
output_path="$DEFAULT_OUTPUT"
base_archive=""
runtime_channel="$RUNTIME_CHANNEL"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)
      clean_build=true
      ;;
    --repackage)
      repackage_only=true
      ;;
    --base-archive)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--base-archive requires a path" >&2
        exit 2
      fi
      base_archive="$1"
      ;;
    --output)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--output requires a path" >&2
        exit 2
      fi
      output_path="$1"
      ;;
    --channel)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--channel requires stable or prerelease" >&2
        exit 2
      fi
      runtime_channel="$1"
      ;;
    --help|-h)
      cat <<'USAGE'
Usage: ./script/build-runtime.sh --base-archive PATH [--clean] [--repackage] [--channel CHANNEL] [--output PATH]

Builds the locked x86_64 Wine source, overlays its install output onto a fresh
copy of an explicit baseline runtime archive, and writes a candidate .tar.xz
plus a SHA-256-bound release manifest.

  --base-archive PATH  A known-good runtime archive used only as a packaging
                       baseline. It is never read from an App checkout.
  --clean        Remove only work/build/wine-x86_64 before configuring.
  --repackage    Preserve the existing native Wine binaries and only create a
                 new, version-marked candidate archive. Use for App-side
                 runtime integration releases that do not change Wine source.
  --channel      Release channel written to the candidate manifest: stable
                 (default from runtime.env) or prerelease.
  --output PATH  Candidate archive destination (must not already exist).

The input archive is never overwritten. The script does not access or modify
game prefixes under ~/Library/Application Support.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -z "$base_archive" ]]; then
  echo "--base-archive is required." >&2
  exit 2
fi

if [[ "$base_archive" != /* ]]; then
  base_archive="$ROOT_DIR/$base_archive"
fi

if [[ "$output_path" != /* ]]; then
  output_path="$ROOT_DIR/$output_path"
fi

for tool in /usr/bin/tar /usr/bin/shasum; do
  if [[ ! -x "$tool" ]]; then
    echo "Required build tool is unavailable: $tool" >&2
    exit 1
  fi
done

if [[ "$repackage_only" == false ]]; then
  for tool in /usr/bin/xcrun /usr/bin/make; do
    if [[ ! -x "$tool" ]]; then
      echo "Required build tool is unavailable: $tool" >&2
      exit 1
    fi
  done
  if [[ ! -x "$SOURCE_DIR/configure" || ! -f "$SOURCE_DIR/VERSION" ]]; then
    echo "Wine source is not ready. Run ./script/sync-wine-source.sh first." >&2
    exit 1
  fi
  if [[ "$(<"$SOURCE_DIR/VERSION")" != "Wine version $WINE_VERSION" ]]; then
    echo "Wine source version does not match the lock file." >&2
    exit 1
  fi
fi

if [[ ! -f "$base_archive" ]]; then
  echo "Missing baseline runtime archive: $base_archive" >&2
  exit 1
fi

baseline_root="$(/usr/bin/tar -tJf "$base_archive" | /usr/bin/awk -F/ 'NF { print $1; exit }')"
if [[ -z "$baseline_root" || "$baseline_root" == "." || "$baseline_root" == ".." ]]; then
  echo "Unable to determine a safe runtime root from: $base_archive" >&2
  exit 1
fi

if [[ -e "$output_path" ]]; then
  echo "Refusing to overwrite existing candidate: $output_path" >&2
  exit 1
fi

if [[ "$repackage_only" == true && "$clean_build" == true ]]; then
  echo "--clean cannot be used with --repackage." >&2
  exit 2
fi

case "$runtime_channel" in
  stable|prerelease) ;;
  *)
    echo "Unsupported runtime channel: $runtime_channel" >&2
    exit 2
    ;;
esac

write_runtime_metadata() {
  local runtime_directory="$1"
  /usr/bin/printf '%s\n' "$RUNTIME_VERSION" > "$runtime_directory/$RUNTIME_MARKER_FILE"
  /usr/bin/printf '{\n  "schemaVersion": 1,\n  "id": "%s",\n  "displayName": "%s",\n  "version": "%s",\n  "channel": "%s",\n  "patchSet": "%s",\n  "runtimeABI": %s,\n  "prefixABI": "%s",\n  "architecture": "%s",\n  "minimumMacOS": "%s",\n  "legacyInstallRoots": ["%s"],\n  "legacyInstallMarkers": ["%s"],\n  "engine": {\n    "wineVersion": "%s",\n    "crossOverSourceVersion": "%s"\n  }\n}\n' \
    "$RUNTIME_ID" "$RUNTIME_DISPLAY_NAME" "$RUNTIME_VERSION" "$runtime_channel" "$RUNTIME_PATCHSET" \
    "$RUNTIME_ABI" "$PREFIX_ABI" "$RUNTIME_ARCHITECTURE" "$RUNTIME_MINIMUM_MACOS" \
    "$LEGACY_INSTALL_ROOT" "$LEGACY_INSTALL_MARKER" "$WINE_VERSION" "$CROSSOVER_VERSION" > "$runtime_directory/.arclume-runtime.json"
}

write_release_manifest() {
  local archive_path="$1"
  local archive_sha="$2"
  local manifest_path="${archive_path%.tar.xz}.runtime.json"
  local archive_name
  archive_name="$(/usr/bin/basename "$archive_path")"
  /usr/bin/printf '{\n  "schemaVersion": 1,\n  "id": "%s",\n  "displayName": "%s",\n  "version": "%s",\n  "channel": "%s",\n  "patchSet": "%s",\n  "runtimeABI": %s,\n  "prefixABI": "%s",\n  "architecture": "%s",\n  "minimumMacOS": "%s",\n  "legacyInstallRoots": ["%s"],\n  "legacyInstallMarkers": ["%s"],\n  "archive": {\n    "name": "%s",\n    "sha256": "%s",\n    "rootDirectory": "%s"\n  },\n  "engine": {\n    "wineVersion": "%s",\n    "crossOverSourceVersion": "%s"\n  }\n}\n' \
    "$RUNTIME_ID" "$RUNTIME_DISPLAY_NAME" "$RUNTIME_VERSION" "$runtime_channel" "$RUNTIME_PATCHSET" \
    "$RUNTIME_ABI" "$PREFIX_ABI" "$RUNTIME_ARCHITECTURE" "$RUNTIME_MINIMUM_MACOS" \
    "$LEGACY_INSTALL_ROOT" "$LEGACY_INSTALL_MARKER" "$archive_name" "$archive_sha" "$RUNTIME_ROOT" "$WINE_VERSION" "$CROSSOVER_VERSION" \
    > "$manifest_path"
  echo "Manifest: $manifest_path"
}

if [[ "$repackage_only" == true ]]; then
  /bin/mkdir -p "$ROOT_DIR/work/build" "$(dirname "$output_path")"
  staging_parent="$(/usr/bin/mktemp -d "$ROOT_DIR/work/build/runtime-repackage.XXXXXX")"
  staging_runtime="$staging_parent/$RUNTIME_ROOT"
  cleanup_repackage() {
    if [[ -d "$staging_parent" ]]; then
      /usr/bin/find "$staging_parent" -depth -delete
    fi
  }
  trap cleanup_repackage EXIT

  /usr/bin/tar -xJf "$base_archive" -C "$staging_parent"
  extracted_runtime="$staging_parent/$baseline_root"
  if [[ ! -d "$extracted_runtime" ]]; then
    echo "Baseline archive does not contain expected root: $baseline_root" >&2
    exit 1
  fi
  if [[ "$extracted_runtime" != "$staging_runtime" ]]; then
    /bin/mv "$extracted_runtime" "$staging_runtime"
  fi
  for required_path in \
    "$staging_runtime/lib/wine/x86_64-unix/wine" \
    "$staging_runtime/bin/wineserver" \
    "$staging_runtime/lib/wine/x86_64-unix/ntdll.so" \
    "$staging_runtime/dxvk/x64/dxgi.dll"; do
    if [[ ! -e "$required_path" ]]; then
      echo "Baseline archive is missing required runtime file: $required_path" >&2
      exit 1
    fi
  done

  write_runtime_metadata "$staging_runtime"
  echo "Creating re-versioned runtime candidate: $output_path"
  /usr/bin/tar -cJf "$output_path" -C "$staging_parent" "$RUNTIME_ROOT"
  candidate_sha="$(/usr/bin/shasum -a 256 "$output_path" | /usr/bin/awk '{print $1}')"
  echo "Candidate ready: $output_path"
  echo "SHA-256: $candidate_sha"
  write_release_manifest "$output_path" "$candidate_sha"
  exit 0
fi

run_x86() {
  if [[ "$(/usr/bin/uname -m)" == "arm64" ]]; then
    /usr/bin/arch -x86_64 "$@"
  else
    "$@"
  fi
}

if [[ "$(/usr/bin/uname -m)" == "arm64" ]] && ! /usr/bin/arch -x86_64 /usr/bin/true; then
  echo "Rosetta is required to build the x86_64 Wine runtime." >&2
  exit 1
fi

if [[ "$clean_build" == true && -e "$BUILD_DIR" ]]; then
  case "$BUILD_DIR" in
    "$ROOT_DIR"/work/build/wine-x86_64) ;;
    *)
      echo "Refusing to clean unexpected build path: $BUILD_DIR" >&2
      exit 1
      ;;
  esac
  /usr/bin/find "$BUILD_DIR" -depth -delete
fi

/bin/mkdir -p "$BUILD_DIR" "$(dirname "$output_path")"
sdk_root="$(/usr/bin/xcrun --sdk macosx --show-sdk-path)"
# The app can require a newer macOS release, but the translated x86_64 Wine
# loader needs CrossOver's legacy deployment target to avoid a macOS 26 loader
# crash while creating Wine's first server thread. Passing this only to
# configure is insufficient: clang is invoked later by make, where Xcode
# otherwise defaults the Mach-O minimum version to its SDK.
deployment_target="${MACOSX_DEPLOYMENT_TARGET:-10.15}"
# Xcode 27's SDK advertises pipe2(), but macOS 26 does not provide its weak
# runtime symbol. Autoconf otherwise enables HAVE_PIPE2 from the SDK headers;
# Wine then calls the unresolved symbol while creating the first server pipe
# and Rosetta jumps to address 0. Keep the portable pipe()+fcntl() path for
# every bundled macOS runtime.
configure_pipe2_cache="ac_cv_func_pipe2=no"
# Xcode signs the app bundle, but this runtime is intentionally expanded into
# Application Support on first use. Preserve a signature on its native Mach-O
# files as well when producing a distributable build. This is particularly
# important for Rosetta on newer macOS releases.
runtime_codesign_identity="${RUNTIME_CODESIGN_IDENTITY:-}"
jobs="${JOBS:-$(/usr/sbin/sysctl -n hw.ncpu)}"
host_cc="/usr/bin/gcc -arch x86_64"
host_cxx="/usr/bin/g++ -arch x86_64"
build_path="$PATH"
if [[ -x /opt/homebrew/opt/bison/bin/bison ]]; then
  build_path="/opt/homebrew/opt/bison/bin:$build_path"
elif [[ -x /usr/local/opt/bison/bin/bison ]]; then
  build_path="/usr/local/opt/bison/bin:$build_path"
fi

# Apple Silicon Homebrew libraries are arm64-only. When building the x86_64
# Wine host tools, reuse the x86_64 FreeType dylib already carried by the
# baseline runtime and pair it with Homebrew's architecture-neutral headers.
# The rebuilt runtime continues to ship that same dylib under lib64.
freetype_cflags="${FREETYPE_CFLAGS:-}"
freetype_libs="${FREETYPE_LIBS:-}"
build_dyld_fallback="${DYLD_FALLBACK_LIBRARY_PATH:-}"
build_ldflags="${LDFLAGS:-}"
compat_lib_dir="$BUILD_DIR/.arclume-x86_64-libs"
if [[ -f "$base_archive" ]]; then
  /bin/mkdir -p "$compat_lib_dir"
  /usr/bin/tar -xJf "$base_archive" -C "$compat_lib_dir" \
    --strip-components=2 \
    "$baseline_root/lib64/libMoltenVK.dylib" \
    "$baseline_root/lib64/libfreetype.6.20.2.dylib" \
    "$baseline_root/lib64/libfreetype.6.dylib"
  /bin/ln -sf libfreetype.6.dylib "$compat_lib_dir/libfreetype.dylib"
  build_ldflags="-L$compat_lib_dir${build_ldflags:+ $build_ldflags}"
  build_dyld_fallback="$compat_lib_dir${build_dyld_fallback:+:$build_dyld_fallback}"
fi
if [[ -z "$freetype_cflags" && -z "$freetype_libs" \
  && -f /opt/homebrew/opt/freetype/include/freetype2/ft2build.h ]]; then
  freetype_cflags="-I/opt/homebrew/opt/freetype/include/freetype2"
  freetype_libs="-L$compat_lib_dir -lfreetype"
fi

if [[ ! -f "$BUILD_DIR/Makefile" ]]; then
  echo "Configuring Wine $WINE_VERSION for x86_64..."
  (
    cd "$BUILD_DIR"
    run_x86 /usr/bin/env \
      PATH="/usr/local/bin:$build_path" \
      SDKROOT="$sdk_root" \
      MACOSX_DEPLOYMENT_TARGET="$deployment_target" \
      CC="$host_cc" \
      CXX="$host_cxx" \
      LDFLAGS="$build_ldflags" \
      FREETYPE_CFLAGS="$freetype_cflags" \
      FREETYPE_LIBS="$freetype_libs" \
      "$configure_pipe2_cache" \
      /bin/bash "$SOURCE_DIR/configure" \
      --enable-win64 \
      --disable-tests \
      --prefix=/
  )
fi

if /usr/bin/grep -q '^#define HAVE_PIPE2 1' "$BUILD_DIR/include/config.h"; then
  echo "Wine configuration unexpectedly enabled pipe2; refusing an incompatible macOS runtime." >&2
  exit 1
fi

echo "Building Wine $WINE_VERSION with $jobs jobs..."
(
  cd "$BUILD_DIR"
  run_x86 /usr/bin/env \
    PATH="/usr/local/bin:$build_path" \
    SDKROOT="$sdk_root" \
    MACOSX_DEPLOYMENT_TARGET="$deployment_target" \
    DYLD_FALLBACK_LIBRARY_PATH="$build_dyld_fallback" \
    /usr/bin/make -j "$jobs"
)

staging_parent="$(/usr/bin/mktemp -d "$ROOT_DIR/work/build/runtime-staging.XXXXXX")"
staging_runtime="$staging_parent/$RUNTIME_ROOT"
cleanup_staging() {
  if [[ -d "$staging_parent" ]]; then
    /usr/bin/find "$staging_parent" -depth -delete
  fi
}
trap cleanup_staging EXIT

/usr/bin/tar -xJf "$base_archive" -C "$staging_parent"
extracted_runtime="$staging_parent/$baseline_root"
if [[ ! -d "$extracted_runtime" ]]; then
  echo "Baseline archive does not contain expected root: $baseline_root" >&2
  exit 1
fi
if [[ "$extracted_runtime" != "$staging_runtime" ]]; then
  /bin/mv "$extracted_runtime" "$staging_runtime"
fi

write_runtime_metadata "$staging_runtime"

echo "Installing Wine core into a fresh runtime staging directory..."
(
  cd "$BUILD_DIR"
  run_x86 /usr/bin/env \
    PATH="/usr/local/bin:$build_path" \
    SDKROOT="$sdk_root" \
    MACOSX_DEPLOYMENT_TARGET="$deployment_target" \
    DYLD_FALLBACK_LIBRARY_PATH="$build_dyld_fallback" \
    /usr/bin/make install "DESTDIR=$staging_runtime"
)

# `make install` includes Wine's SDK, developer tools, and unstripped PE
# modules. None are used by Arclume at runtime. Strip the PE builtins and
# retain only the Wine launch/server utilities, keeping the shipped archive
# close to the baseline runtime instead of adding several hundred MB.
strip_tool="$(command -v x86_64-w64-mingw32-strip || true)"
if [[ -z "$strip_tool" ]]; then
  echo "x86_64-w64-mingw32-strip is required to package the runtime." >&2
  exit 1
fi
echo "Stripping Windows modules and removing build-only Wine files..."
/usr/bin/find "$staging_runtime/lib/wine" -type f \
  \( -name '*.dll' -o -name '*.exe' -o -name '*.ocx' -o -name '*.cpl' \
     -o -name '*.drv' -o -name '*.ax' -o -name '*.acm' -o -name '*.vxd' \
     -o -name '*.sys' \) \
  -exec "$strip_tool" --strip-unneeded {} +
if [[ -d "$staging_runtime/include" ]]; then
  /usr/bin/find "$staging_runtime/include" -depth -delete
fi
if [[ -d "$staging_runtime/share/man" ]]; then
  /usr/bin/find "$staging_runtime/share/man" -depth -delete
fi
for build_tool in function_grep.pl winebuild winecpp wineg++ winegcc widl \
  winedump winemaker wmc wrc; do
  if [[ -e "$staging_runtime/bin/$build_tool" ]]; then
    /usr/bin/find "$staging_runtime/bin/$build_tool" -depth -delete
  fi
done

wine_loader="$staging_runtime/lib/wine/x86_64-unix/wine"
wineserver="$staging_runtime/bin/wineserver"
if [[ ! -x "$wine_loader" || ! -x "$wineserver" ]]; then
  echo "Wine install layout is incomplete; expected:" >&2
  echo "  $wine_loader" >&2
  echo "  $wineserver" >&2
  exit 1
fi

if ! /usr/bin/xcrun vtool -show-build "$wine_loader" \
  | /usr/bin/grep -q "minos $deployment_target"; then
  echo "Wine loader deployment target does not match $deployment_target." >&2
  /usr/bin/xcrun vtool -show-build "$wine_loader" >&2
  exit 1
fi

if [[ -n "$runtime_codesign_identity" ]]; then
  echo "Signing native Wine runtime files..."
  while IFS= read -r -d '' native_binary; do
    if /usr/bin/file -b "$native_binary" | /usr/bin/grep -q '^Mach-O'; then
      /usr/bin/codesign --force --sign "$runtime_codesign_identity" \
        --timestamp=none "$native_binary"
    fi
  done < <(/usr/bin/find "$staging_runtime" -type f -print0)

fi

echo "Creating candidate archive: $output_path"
/usr/bin/tar -cJf "$output_path" -C "$staging_parent" "$RUNTIME_ROOT"
candidate_sha="$(/usr/bin/shasum -a 256 "$output_path" | /usr/bin/awk '{print $1}')"
echo "Candidate ready: $output_path"
echo "SHA-256: $candidate_sha"
write_release_manifest "$output_path" "$candidate_sha"

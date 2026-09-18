#!/bin/bash
# Uses only a fresh disposable prefix; never opens a user's application prefix.
set -euo pipefail
runtime="${1:?usage: test-builtin-loader-lock.sh RUNTIME FIXTURE_DIRECTORY}"
fixtures="${2:?missing fixture directory}"
test -x "$runtime/lib/wine/x86_64-unix/wine"
test -x "$runtime/bin/wineserver"
test -f "$fixtures/builtin-loader-lock32.exe"
test -f "$fixtures/builtin-loader-lock64.exe"
test_dir="$(mktemp -d /tmp/arclume-builtin-lock-test.XXXXXX)"
chmod 700 "$test_dir"
export WINEPREFIX="$test_dir/prefix" WINEARCH=win64
export WINESERVER="$runtime/bin/wineserver" WINEDATADIR="$runtime/share/wine"
export WINEDLLPATH="$runtime/lib/wine/x86_64-windows:$runtime/lib/wine/i386-windows:$runtime/lib/wine"
export DYLD_FALLBACK_LIBRARY_PATH="$runtime/lib64" WINEMSYNC=1
export WINEDEBUG=-all,err+all
unset WINEDLLOVERRIDES PROCYON_DLL_PATH CX_APPLEGPTK_LIBD3DSHARED_PATH D3DMETAL_FRAMEWORK_PATH
unset CX_GRAPHICS_BACKEND CX_ACTIVE_GRAPHICS_BACKEND
wine="$runtime/lib/wine/x86_64-unix/wine"
active_watchdog=''
cleanup() {
    if [[ -n "$active_watchdog" ]]; then kill "$active_watchdog" 2>/dev/null || true; fi
    "$WINESERVER" -k 2>/dev/null || true
    "$WINESERVER" -w 2>/dev/null || true
}
trap cleanup EXIT
run_bounded() {
    local limit="$1" label="$2" status=0
    shift 2
    "$@" > "$test_dir/$label.log" 2>&1 &
    local child=$!
    (
        sleep "$limit"
        if kill -0 "$child" 2>/dev/null; then
            printf 'LOCKTEST TIMEOUT %s\n' "$label" >> "$test_dir/$label.log"
            "$WINESERVER" -k 2>/dev/null || true
            kill "$child" 2>/dev/null || true
        fi
    ) &
    active_watchdog=$!
    wait "$child" || status=$?
    kill "$active_watchdog" 2>/dev/null || true
    wait "$active_watchdog" 2>/dev/null || true
    active_watchdog=''
    printf '%s exit=%s\n' "$label" "$status"
    return "$status"
}
printf 'Isolated test output: %s\n' "$test_dir"
run_bounded 90 wineboot "$wine" wineboot.exe -u
for bits in 32 64; do
    run_bounded 15 "lock$bits" "$wine" "$fixtures/builtin-loader-lock$bits.exe" || true
    sed -n '/^LOCKTEST/p' "$test_dir/lock$bits.log"
    if ! grep -q "LOCKTEST PASS $bits-bit" "$test_dir/lock$bits.log"; then exit 1; fi
done

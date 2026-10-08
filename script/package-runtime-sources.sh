#!/usr/bin/env bash
# Publish the committed recipe and its authenticated, unmodified inputs.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
if [[ $# != 2 || "$1" != --output ]]; then
  echo 'Usage: bash script/package-runtime-sources.sh --output PATH.tar.gz' >&2
  exit 2
fi
output="$2"
[[ "$output" == /* ]] || output="$root/$output"
[[ "$output" == *.tar.gz && ! -e "$output" && ! -L "$output" ]]
source runtime.env
source sources/WINE_SOURCE.lock
jq -e '.dependencies | type == "array" and length > 0' sources/MEDIA_SOURCES.json >/dev/null
# Never combine a working-tree recipe with a different source commit.
git show HEAD:runtime.env | cmp - runtime.env
git diff --quiet HEAD -- sources script patches runtime.env manifests LICENSES THIRD-PARTY-NOTICES.md
temporary=$(mktemp -d "$root/work/source-release.XXXXXX")
trap 'find "$temporary" -depth -delete' EXIT
bundle="arclume-wine-$RUNTIME_VERSION-sources"
git archive HEAD --prefix="$bundle/" | tar -xf - -C "$temporary"
upstream="$temporary/$bundle/sources/upstream"
mkdir -p "$upstream"
while IFS=$'\t' read -r archive sha; do
  [[ "$archive" != */* && "$archive" != .* && "$sha" =~ ^[a-f0-9]{64}$ ]]
  if [[ "$archive" == "$SOURCE_ARCHIVE" ]]; then
    input="$root/cache/$archive"
  else
    input="$root/cache/media/$archive"
  fi
  test -f "$input"
  actual=$(shasum -a 256 "$input" | awk '{print $1}')
  test "$actual" = "$sha"
  cp "$input" "$upstream/$archive"
done < <(
  printf '%s\t%s\n' "$SOURCE_ARCHIVE" "$SOURCE_SHA256"
  jq -r '.dependencies[] | [.archive, .sha256] | @tsv' sources/MEDIA_SOURCES.json
)
git rev-parse HEAD > "$temporary/$bundle/SOURCE_COMMIT"
tar -czf "$temporary/sources.tar.gz" -C "$temporary" "$bundle"
# A concurrent publisher must not be overwritten.
ln "$temporary/sources.tar.gz" "$output"
echo "Source bundle: $output"

# Arclume Runtime

The public build-source repository for the Arclume Wine runtime. It is
intentionally separate from the Arclume macOS app repository.

## Ownership boundary

| Repository | Owns |
| --- | --- |
| `PigeonMuyz/Arclume` | App UI, Runtime Manager, runtime selection, prefixes, game integration, and the runtime selected for an App release. |
| `PigeonMuyz/Arclume-Runtime` | Wine source lock, patches, reproducible build scripts, product runtime identity, generated manifest, and candidate runtime artifacts. |

The App never builds Wine. It consumes a verified runtime archive and its
generated manifest. Public Runtime Releases pair every binary archive with its
exact source tag, source lock, patches, notices and SHA-256-bound manifest.

## Versions

`runtime.env` is the release source of truth:

- `RUNTIME_VERSION` is the public SemVer (`1.0.0`, `1.0.1`, `1.1.0`).
- `RUNTIME_ABI` is the App-to-runtime contract.
- `PREFIX_ABI` decides whether an existing Games container can be retained.
- Wine and CrossOver source revisions are implementation details in
  `sources/WINE_SOURCE.lock`.
- `RUNTIME_PATCHSET` records the Wine behavior included in the Runtime.
  Arclume Wine 1.1.0 vendors the reviewed FineWine / Endfield compatibility
  patch set; see `patches/finewine/` and `sources/FINEWINE_PATCHSET.lock`.

## Build a candidate

The base archive is an explicit input. This prevents the Runtime repository
from reading an App checkout and makes the dependency auditable.

```bash
./script/sync-wine-source.sh
./script/build-runtime.sh \
  --base-archive /absolute/path/to/known-good-runtime.tar.xz
```

For an App-side integration release that does not rebuild Wine:

```bash
./script/build-runtime.sh --repackage \
  --base-archive /absolute/path/to/known-good-runtime.tar.xz
```

Both commands produce an archive and a SHA-256-bound manifest in `dist/`.
Candidate artifacts are ignored by Git. Promote a tested artifact to the
matching public GitHub Release only after launch and game validation, and keep
the source tag and third-party notices linked beside the binary.

## GitHub Actions

- **Runtime 前置审核** runs on pull requests. It validates the patch hashes,
  extracts the locked CodeWeavers source and confirms every tracked Wine patch
  applies cleanly; it intentionally does not build Wine.
- **构建并发布 Arclume Wine Runtime** runs only when a `main` commit contains
  `release: <version>` / `release: github actions`, `pre-release: <version>` /
  `pre-release: github actions`, or when dispatched manually. It validates that
  the requested version matches `runtime.env`, downloads the declared baseline
  Runtime, rebuilds Wine, checks the archive and manifest, then publishes the
  archive, manifest and SHA-256 file to the matching Stable or Pre-Release.
  A Pre-Release uses the `prerelease` manifest channel and
  `arclume-wine-pre-<version>` tag; after publication the workflow removes only
  older Arclume Wine Pre-Releases, never a Stable Release.

The build is not a compatibility claim. Publish only after the target games
have been validated on real hardware.

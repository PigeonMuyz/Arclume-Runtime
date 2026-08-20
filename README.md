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

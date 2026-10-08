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
  Arclume Wine 1.1.1 vendors the reviewed FineWine / Endfield compatibility
  patch set; see `patches/finewine/` and `sources/FINEWINE_PATCHSET.lock`.
  Version 1.1.2 adds proportional Dock icon margins and paired user32/win32u
  loader-lock ordering changes. The native host remains x86_64 (AMD64); WoW64
  includes both i386 and x86_64 Windows modules because YY is a 32-bit app.
  **YY may still become unresponsive in microphone-queue mode.** This release
  is not a claim that all channel modes or long voice sessions are stable.

## Build a candidate

The base archive is an explicit input. This prevents the Runtime repository
from reading an App checkout and makes the dependency auditable.

```bash
./script/sync-wine-source.sh
./script/build-runtime.sh \
  --base-archive /absolute/path/to/known-good-runtime.tar.xz
```

Version 1.1.3 also builds pinned x86_64 GStreamer, FFmpeg
and dav1d dependencies. `--repackage` is disabled for this runtime so an old
Wine core without multimedia bridges cannot be relabelled as the new version.
See [multimedia build and headless validation](docs/media-runtime.md) for tools,
low-priority builds, isolation, compatibility and rollback instructions.

The build produces an archive and a SHA-256-bound manifest in `dist/`.
Candidate artifacts are ignored by Git. Release notes distinguish headless
decode validation from real-game and target-OS validation. Keep the source tag
and third-party notices linked beside the binary. After committing the release
sources, `bash script/package-runtime-sources.sh --output dist/arclume-wine-1.1.3-sources.tar.gz`
packages that exact commit plus the SHA-256-verified Wine/media input archives.
It excludes build trees, signing material and user data.

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
  Runtime 发布还需要 `MACOS_APP_CERTIFICATE_P12_BASE64`、
  `MACOS_APP_CERTIFICATE_PASSWORD`、`MACOS_DEVELOPER_TEAM_ID` 与
  `RUNTIME_CODESIGN_IDENTITY`（也可复用 `MACOS_SIGNING_IDENTITY`）。这不是 DMG
  签名要求：Wine loader 需携带 macOS 麦克风输入 entitlement；缺少证书时 workflow
  会停止，避免发布功能倒退的 Runtime。
  A Pre-Release uses the `prerelease` manifest channel and
  `arclume-wine-pre-<version>` tag; after publication the workflow removes only
  older Arclume Wine Pre-Releases, never a Stable Release.

The build is not a compatibility claim. Publish only after the target games
have been validated on real hardware.

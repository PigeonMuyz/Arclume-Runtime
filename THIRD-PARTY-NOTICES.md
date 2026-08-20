# Third-party and distribution boundary

This repository contains Arclume-owned build metadata, scripts, and patches.
Wine source is downloaded from the locked public CodeWeavers FOSS source input;
do not commit an extracted Wine worktree or a prebuilt runtime archive here.

`runtime.env` is Arclume's product release identity. It is deliberately
separate from the Wine and CrossOver source versions in
`sources/WINE_SOURCE.lock`.

Every public Runtime Release must link its exact source tag, source lock,
patches, SHA-256-bound manifest and the notices required by Wine and every
bundled component. A Runtime archive must not be published by itself without
that release record.

Apple Game Porting Toolkit/D3DMetal components, when used by an App release,
retain Apple’s applicable terms. They are not licensed under this repository’s
GPL and are not represented as Arclume open source. DXVK, DXMT, Wine Mono,
fonts and optional NVIDIA payloads retain their respective upstream terms.

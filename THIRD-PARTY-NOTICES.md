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

## FineWine / Endfield compatibility patches

Arclume Wine 1.1.0 vendors 23 patches from
[stoicswe/Endfield_FineWine](https://github.com/stoicswe/Endfield_FineWine) at
revision `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`. The upstream project
states that its Wine patches are LGPL-2.1-or-later; the stage-two set originates
from dw-proton and retains the rights of its original contributors, including
Etaash Mathamsetty, Ziia Shi / mkrsym1, NelloKudo and others. Arclume preserves
the exact patch files, deterministic application order and SHA-256 checksums
under `patches/finewine/`. The LGPL-2.1 text is included at
`LICENSES/Wine-LGPL-2.1-or-later.txt`.

The patches are compatibility work for protected Windows software. They do not
provide game content, accounts, service access or a guarantee of compatibility;
users remain responsible for the relevant game and online-service terms.

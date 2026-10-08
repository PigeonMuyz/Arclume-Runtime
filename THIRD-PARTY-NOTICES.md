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

Arclume Wine 1.1.1 vendors 23 patches from
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

## Multimedia runtime (1.1.3)

`sources/MEDIA_SOURCES.json` records exact upstream archives and SHA-256 values
for GStreamer, its selected plugin sets, FFmpeg, dav1d and their build/runtime
dependencies. These components retain their own upstream licenses; they do not
inherit this repository's license. The candidate archive includes their
available COPYING/LICENSE/AUTHORS/NOTICE files in `share/arclume-media/licenses`.
The GLib macOS pipe fallback and gst-libav software-dav1d registration patches
are shipped alongside those notices.

FFmpeg's JPEG routines include work by the Independent JPEG Group. This
software is based in part on the work of the Independent JPEG Group. Arclume
has not modified FFmpeg's `jfdctfst.c`, `jfdctint_template.c` or `jrevdct.c`.

FFmpeg is configured with GPL and nonfree options disabled. This is a build
configuration, not a claim that every codec is free of patent or distribution
restrictions. Before public distribution, review the complete component license
set and provide the corresponding source archives, build recipes and patches,
including material needed to relink any statically included LGPL dependencies.
The Release includes a corresponding-source bundle containing the locked Wine
and media input archives together with this repository's exact release commit,
patches and build recipes. NASM's macOS archive is a build-host tool, not a
library shipped in the Runtime. Sources for pre-existing baseline components
remain identified by the baseline release; see `RUNTIME_BASELINE_VERSION`.

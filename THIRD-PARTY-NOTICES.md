# Third-party and distribution boundary

This repository contains Arclume-owned build metadata, scripts, and patches.
Wine source is downloaded from the locked public CodeWeavers FOSS source input;
do not commit an extracted Wine worktree or a prebuilt runtime archive here.

`runtime.env` is Arclume's product release identity. It is deliberately
separate from the Wine and CrossOver source versions in
`sources/WINE_SOURCE.lock`.

A private GitHub repository is an internal development and CI boundary only.
If a runtime or an App containing it is distributed to another person, ship the
corresponding source and license notices required by Wine and every bundled
component. In particular, verify redistribution rights for Apple Game Porting
Toolkit/D3DMetal, DXVK/DXMT, Wine Mono, fonts, and optional NVIDIA payloads
before publishing a binary release.

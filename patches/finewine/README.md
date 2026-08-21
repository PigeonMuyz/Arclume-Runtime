# FineWine / Endfield compatibility patch set

This directory vendors the 23 Wine patches from
[stoicswe/Endfield_FineWine](https://github.com/stoicswe/Endfield_FineWine)
at commit `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`.

The upstream project authored its two macOS/Rosetta signal fixes and ports the
remaining ACE compatibility patches from dw-proton. The patches target Wine
and are therefore **LGPL-2.1-or-later**. They remain attributed to their
upstream authors, including Etaash Mathamsetty, Ziia Shi / mkrsym1,
NelloKudo and other dw-proton contributors.

## What is included

- Rosetta 2 recovery for VMProtect/TenProtect multi-byte NOP and privileged
  instruction faults.
- `ntoskrnl.exe` exports and compatibility backports required by ACE.
- Endfield-gated `KiUser*Dispatcher` handling and a timing compatibility fix.

The patch set is used by Arclume Wine 1.1.0 and later. It was checked against
the locked CrossOver 26.3.0 / Wine 11.0 source on 2026-08-21: all 23 patches
apply in the order listed in `PATCH_ORDER`.

`PATCHES.sha256` preserves the exact imported patch bytes. The source-sync
script verifies it before applying anything. Keep both this attribution and
the corresponding entry in `THIRD-PARTY-NOTICES.md` when redistributing a
runtime built from this source tree.

This is a compatibility patch set, not a guarantee that a particular game,
anti-cheat service, account or online service will operate. Users remain
responsible for complying with the applicable game and service terms.

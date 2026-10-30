# asteroid-embedded licence review

Research only, 2026-10-30. Not legal advice; points where the answer is a judgement call are marked **[uncertain]**.

Repo: `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded` (135 commits, single author Darrel Griët, first commit 2026-10-25). Current outbound licence: `LICENSE` = GPL-3.0 text, README says "GPL-3.0-or-later", `ui/Cargo.toml` says `license = "GPL-3.0-or-later"`, both `dts/*.dts` carry `SPDX-License-Identifier: GPL-3.0-or-later`. No other file in `src/`, `ui/`, `ld/`, `tools/`, `tests/` has a licence or copyright header (90 of 93 files in `src/` have none; the three that do are the derived files listed below).

## 1. Component inventory

What ends up in `build/asteroid.img` (Android boot image = firmware binary + DTB + ramdisk of blobs), plus references used while writing it.

| # | Component | Where | Licence (evidence) | Constraint on the combined image |
|---|---|---|---|---|
| 1 | Own C firmware, linker script, tools, tests | `src/`, `ld/`, `tools/`, `tests/` | Currently GPL-3.0-or-later (README, `LICENSE`); no per-file headers | Free to choose: sole author, can relicense at will |
| 2 | Own Rust UI crate + `.slint` files | `ui/src`, `ui/ui`, `ui/build.rs` | GPL-3.0-or-later (`ui/Cargo.toml:5`) | Same |
| 3 | Own DTS | `dts/sturgeon.dts`, `dts/sparrow.dts` | GPL-3.0-or-later (SPDX line 1) | Same. Mainline equivalents (`qcom-apq8026-huawei-sturgeon.dts`, `qcom-msm8226.dtsi`) are **BSD-3-Clause** (headers checked on torvalds/linux master), so even verbatim reuse would not force GPL |
| 4 | **Slint** 1.18.1 framework: `slint`, `slint-macros`, `i-slint-core`, `i-slint-core-macros`, `i-slint-common`, `i-slint-compiler`, `i-slint-renderer-software`, `i-slint-backend-selector`, `slint-build` (last three build-time) | crates.io + vendored copies in `third_party/slint/` (commit 365e00e, "unmodified from crates.io", patches to follow) | `GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0` (each `Cargo.toml`; 801 SPDX headers in the vendored files) | **The only no-cost option usable here is GPL-3.0-only** (see §2.1). This single dependency decides the licence of the combined work. GPL-3.0-*only*: the combined image cannot be "or-later" |
| 5 | Rust dependency tree actually linked for `armv7a-none-eabihf` (243 crates, `cargo tree -e normal --target armv7a-none-eabihf`) | `ui/Cargo.lock` | 11 Slint crates (above); 34 `Unicode-3.0` (icu4x: `icu_*`, `zerovec`, `yoke`, `tinystr`, `litemap`, `writeable`, `potential_utf`, `zerofrom`, `zerotrie`, `fixed_decimal`); `tiny-skia`, `tiny-skia-path` BSD-3-Clause; `arrayref` BSD-2-Clause; `foldhash`, `slotmap`, `zlib-rs` Zlib; `libloading` ISC; `winit`, `codespan-reporting`, `unicode-linebreak`, `spirv` Apache-2.0 only; rest MIT and/or Apache-2.0 (some with Zlib/0BSD/Unlicense/CC0 options) | All permissive and GPLv3-compatible (FSF list: Apache-2.0 "compatible with version 3 of the GNU GPL", Unicode License v3 "compatible with all versions of the GNU GPL"). Apache-2.0-only crates rule out **GPL-2.0-only** as an outbound licence. Attribution notices required in binary distributions (MIT/BSD/Unicode-3.0 all say so) |
| 6 | **NimBLE** 1.10.0 host | `third_party/nimble` (host, GAP/GATT services, transport, porting pieces per `Makefile:34-37`) | Apache-2.0 + bundled BSD-3 (`queue.h`, `os_mbuf.c`), Gary S. Brown CRC32 (`LICENSE` lines 203-220); `NOTICE` file present | GPLv3-compatible, **not GPLv2-compatible** (Apache: "Apache 2 software can therefore be included in GPLv3 projects"; FSF has "never considered the Apache License to be compatible with GPL version 2"). Apache §4(d): the `NOTICE` text must be reproduced when redistributing |
| 7 | **Mbed TLS** 3.6.7 (aes, bignum, cmac, cipher, ... per `Makefile:38`) | `third_party/mbedtls` | `Apache-2.0 OR GPL-2.0-or-later` (`LICENSE` line 1, `README.md:317`); `3rdparty/p256-m` same dual, `3rdparty/everest` Apache-2.0 | Either branch is GPLv3-compatible. Choose and record **Apache-2.0** so the code stays usable if the own code goes permissive |
| 8 | **TinyUSB** + its ChipIdea port | `third_party/tinyusb`, `src/usb/dcd_ci_hs_msm.c` (header: MIT, Copyright 2019 Ha Thach) | MIT | Keep header |
| 9 | 5x12 console font | `src/display/font5x12.h` | BSD-2-Clause, Copyright 2008 The Android Open Source Project (header) | Keep header; binary distributions must reproduce the notice "in the documentation and/or other materials" |
| 10 | FlatMesh geometry | `src/display/flatmesh_geometry.h` | BSD-3-Clause, Copyright 2016 Florent Revest (from `qml-asteroid/src/controls/src/flatmesh.{h,cpp}`) | Header currently a one-line attribution, not the BSD text; add the full notice or SPDX tag |
| 11 | Ionicons (38 SVGs, resized) | `ui/icons/`, `third_party/asteroid-icons-ion` | MIT (Ionic) per `third_party/asteroid-icons-ion/LICENSE`; `md-mastodon.svg` is OFL-1.1 (README) but not among the 38 | Keep LICENSE |
| 12 | Fonts: Noto Sans Light, Raleway Light | `ui/fonts/` + `OFL.txt`, `Raleway-OFL.txt` | SIL OFL-1.1 (Raleway with Reserved Font Name) | OFL explicitly allows fonts to be "bundled, embedded, redistributed and/or sold with any software" (`OFL.txt` preamble); font data compiled into the image. The OFL is not itself GPL-compatible as a software licence (FSF), but fonts embedded in a program are generally treated as a separate work **[uncertain, low risk; Debian/Fedora ship this combination routinely]**. Keep the OFL texts, do not rename the fonts |
| 13 | Font: Roboto Light/Medium | `ui/fonts/Roboto-LICENSE.txt` | Apache-2.0 (Google 2015) | Same as Apache above; no NOTICE file exists for Roboto |
| 14 | Inter variable font inside vendored `i-slint-common/sharedfontique/` | `third_party/slint/i-slint-common` | OFL-1.1-RFN (`.license` file) | Only compiled when the `fontique` feature is on (not for this `no_std` build) — present in the repo, not in the image |
| 15 | **GPU microcode** `a330_pm4.fw`, `a330_pfp.fw` | `firmware/`, loaded from the ramdisk, never linked | Qualcomm `LICENSE.qcom`; verified **identical** (modulo whitespace) to linux-firmware `LICENSES/LICENSE.qcom`; linux-firmware `WHENCE` entry for `qcom/a330_*`: "Redistributable. See LICENSE.qcom and NOTICE.qcom for details", `SPDX-License-Identifier: LicenseRef-LICENSE.qcom` | §1.2: binary-only, only with Qualcomm chipsets, must ship the licence text, no trademarks. §1.3: "You shall not subject the Materials to any third party license terms (e.g., open source license terms)" → must be clearly **outside** the GPL grant (GPLv3 §5 "aggregate"). WHENCE also names `NOTICE.qcom` (24 KB third-party notices) — not in the repo |
| 16 | **Bluetooth patchram** `4343A0.hcd` (BCM43430A0) | `firmware/` | **No licence found.** Not in linux-firmware (`WHENCE` has no `BCM43430A0`/`4343A0` entry; the Cypress `LICENCE.cypress` only covers the files Cypress contributed). AsteroidOS gets it from the stock Huawei `/vendor/firmware` (meta-sturgeon `android_sturgeon-mm.bb`: `LICENSE = "CLOSED"`, Dropbox tarball of the system partition; `bcm4343.conf: fw_patch = /vendor/firmware/4343A0.hcd`) | **Weakest link.** No known right to redistribute. Options in §4 |
| 17 | Toolchain runtime: `arm-none-eabi-gcc` libgcc, Rust `core`/`alloc`/`compiler_builtins` | linked | GCC Runtime Library Exception; Rust MIT OR Apache-2.0 | "System Libraries" / permissive; no effect |
| 18 | *Reference only:* lk2nd | `~/Downloads/AsteroidOS/lk2nd` | MIT (Travis Geiselbrecht) + BSD-3-Clause-with-NON-INFRINGEMENT (Linux Foundation/Qualcomm) + libfdt BSD-2 + libufdt Apache-2.0 (`LICENSE`) | Copying allowed under any outbound licence **if the file's notice is kept**. Line-overlap check `src/` vs lk2nd: 0 verbatim lines except 3 trivial `#define`s in `scm.c` → nothing currently copied, no missing notices |
| 19 | *Reference only:* vendor kernel (CAF 3.10, GPL-2.0-only), mainline Linux drivers (`a3xx_gpu.c`: `GPL-2.0-only`, Red Hat / Linux Foundation; `btbcm.c`, `hci_bcm.c` GPL-2.0) | notes | GPL-2.0-only | **Incompatible with GPLv3** (FSF: "GPLv3 is not compatible with GPLv2 by itself") and with any permissive licence → reimplement, never copy (as done for BMS). Exceptions: mainline DTS (BSD-3-Clause) and envytools-generated register headers (`a3xx.xml.h`, MIT-style) are copyable |
| 20 | *Reference only:* AsteroidOS userland | `qml-asteroid`: `COPYING` = LGPL-2.1, headers 13× LGPL-2.1-or-later, 5× BSD-3-Clause, 2× GPL-3.0-or-later; `asteroid-launcher`: `COPYING.BSD`, `COPYING.MIT`, 34 files with BSD text, 1 GPL-3.0-or-later QML | See §2.5 for both directions |

## 2. Analysis

### 2.1 Slint fixes the licence of the image

Slint's own `LICENSE.md` (github.com/slint-ui/slint, read 2026-10-30):

> 1. Royalty-free License – Permits use in **proprietary** desktop, mobile, and web applications **at no cost**. Use in embedded systems is excluded.
> 2. GNU GPLv3 – Permits use in **open source software** under GPL-compatible terms, **at no cost**, for desktop, mobile, and web applications, as well as for embedded systems.
> 3. Commercial license – ... including desktop, mobile, web, and embedded systems.
> ... A Commercial license is required for embedded systems, regardless of disclosure.

Royalty-free 2.0 text (`third_party/slint/i-slint-core/LICENSES/LicenseRef-Slint-Royalty-free-2.0.md`):

- §1 grants use only "as part of a Desktop, Mobile, or Web Application". A Mobile Application is one "designed to run on a general-purpose mobile computer (mobile phone or tablet), typically installed and executed locally on the computer's operating system."
- §3: "The License does not permit the use of the Software within Embedded Systems. An Embedded System is a computer system designed to perform a specific task within a larger mechanical or electrical system."
- §2 (attribution: `AboutSlint` widget in an About screen, or the badge on the download page) only matters if §1/§3 are satisfied.

A bare-metal watch firmware is not "installed ... on the computer's operating system" (it *is* the OS), the watch is not a phone or tablet, and Slint's FAQ gives appliance controllers and car dashboards as embedded examples. So the Royalty-free licence is **not available** **[reasonably certain]**; the attribution questions (AboutSlint, badge) are moot. The commercial licence's embedded royalty is waived "for non-commercial, personal, and open source projects" (slint.dev/license.html) but it is still a paid plan and gives nothing the GPL option does not already give an open-source project.

Consequence: as long as Slint is in the image, **the combined work must be distributed under GPL-3.0** (Slint's choice is GPL-3.0-*only*). Slint says explicitly that this does not constrain the rest: "Use Slint for free under the GPLv3 on any platform; your own files can stay MIT or Apache-2.0" (`LICENSE.md`), FAQ: "While your software modules can remain under the MIT-license, the work as a whole must be licensed under the GPL."

### 2.2 Is GPL-3.0 consistent with everything else?

Yes. Every other linked component is MIT / BSD / Apache-2.0 / Zlib / ISC / 0BSD / Unicode-3.0 / OFL (fonts) and all are GPLv3-compatible per the FSF list. The GPU blob is kept outside the covered work (separate files in the ramdisk, loaded by name; GPLv3 §5: "inclusion of a covered work in an aggregate does not cause this License to apply to the other parts of the aggregate").

What GPL-3.0 is **not** consistent with: GPL-2.0-only code (vendor kernel, mainline `drivers/gpu/drm/msm`, `drivers/bluetooth`). That is a property of Apache-2.0 + GPL-3.0 and holds for every option below, so the "reimplement, don't copy" rule stays.

Note on versions: our files say "or-later", Slint is "3.0-only"; the image as a whole is therefore effectively GPL-3.0-only. Keeping own files "or-later" is harmless and matches AsteroidOS's own GPL files; the README should say the *image* is GPL-3.0-only.

### 2.3 What GPLv3 obliges when `asteroid.img` is published

- §4/§5: keep notices, mark modified Slint files ("carry prominent notices stating that you modified it, and giving a relevant date") — relevant for the planned run-time-font patches in `third_party/slint`.
- §6: Corresponding Source for every published image: the tagged repo (Makefile, `Cargo.lock`, `ld/`, vendored crates reachable) satisfies §6(d). "System Libraries" (libgcc, Rust `core`) are excluded by §1.
- §6 Installation Information ("anti-tivoisation"): applies only "If you convey an object code work ... in, or with, or specifically for use in, a User Product, and the conveying occurs as part of a transaction in which the right of possession and use of the User Product is transferred to the recipient". Publishing a free download for watches people already own is not such a transaction **[reasonably certain]**, so no obligation arises. Even for someone selling pre-flashed watches it is met trivially: lk2nd's fastboot (`fastboot boot asteroid.img`) is the documented install path, nothing is signed or locked.
- §5(d) "Appropriate Legal Notices" in interactive interfaces: not required because "if the Program has interactive interfaces that do not display Appropriate Legal Notices, your work need not make them do so" — Slint's library has none. **No licence in use requires an About/licences screen.** (AboutSlint is a Royalty-free-only condition.)
- Apache §4(d): reproduce NimBLE's `NOTICE` (and Roboto's licence text) with distributions.
- MIT/BSD/Unicode-3.0: reproduce copyright notices in binary distributions "in the documentation and/or other materials". For 243 crates this is best generated (`cargo about`/`cargo-license`) into a `THIRD_PARTY_NOTICES` file at release time rather than curated by hand.

### 2.4 Apache-2.0 vs GPL-2.0

NimBLE (Apache-2.0 only) and most Rust crates make GPL-2.0-only impossible as an outbound licence. Mbed TLS's dual licence is irrelevant to that: both branches work with GPLv3; picking Apache-2.0 is the natural choice (NimBLE's own `porting/nimble/Makefile.mbedtls` pairs them, BLUETOOTH.md §6 decision already says "Mbed TLS under Apache-2.0"). Record the choice in the third-party notice so nobody later assumes the GPL branch.

### 2.5 Sharing with AsteroidOS in both directions

- AsteroidOS → embedded: BSD-3 files (launcher, FlatMesh) and LGPL-2.1-or-later files (qml-asteroid) can be used in a GPLv3 image (LGPL-2.1 §3 allows conversion to GPL "version 2 ... or any later version"). Under permissive own-code (§3 option B) LGPL code may still be used, but as separate files that keep their LGPL header, not pasted into MIT files.
- Embedded → AsteroidOS: `asteroid-launcher` is BSD-3/MIT, `qml-asteroid` LGPL-2.1+. GPL-3.0 code cannot go into either without relicensing. Today Darrel can relicense his own lines at will (sole author); that stops being true for anything that absorbed Slint-derived code or outside contributions. If drivers, the BLE profile code or UI ideas are ever to flow back (or to lk2nd, which is MIT), permissive own files remove the friction entirely.

### 2.6 Vendored Slint crates

Vendoring is fine under GPL-3.0-only: keep every SPDX header, the `LICENSES/` folders, add a `third_party/slint/README` with the upstream version, the licence option taken ("used under GPL-3.0-only") and a dated list of modified files (§5a). Patched crates must not be published to crates.io under the Slint name. If the font patches are upstreamed, Slint's `CONTRIBUTING` takes contributions under MIT-0 — Darrel keeps copyright, no CLA.

## 3. Options

| Option | What it means | Pros | Cons |
|---|---|---|---|
| **A. Status quo** — everything GPL-3.0-or-later, Slint GPL-3.0-only | One licence for the repo | Simplest story; own code stays copyleft even if someone swaps Slint for a commercial licence; can absorb LGPL-2.1+/GPL-3 snippets directly into own files | Sharing back to AsteroidOS (BSD/LGPL) or lk2nd (MIT) needs relicensing every time; contributions come in as GPL; dual-licence bookkeeping grows with contributors. Does **not** buy the ability to copy Linux (GPL-2.0-only) code |
| **B. Own code MIT (or BSD-3-Clause), image GPL-3.0-only via Slint** | File-level permissive, work-as-a-whole GPL. Exactly the pattern Slint's `LICENSE.md` describes | Zero-friction code sharing to AsteroidOS/lk2nd/anyone; same inbound rules as today (MIT/BSD/Apache/Zlib copy, GPL-2 reimplement); if Slint is ever replaced the whole image becomes permissive without relicensing | Two-layer explanation needed in `LICENSE`; LGPL/GPL snippets can only enter as separate files; own drivers could be used in proprietary firmware by someone who buys a Slint commercial licence (only matters if copyleft on the drivers is a goal) |
| C. Slint Royalty-free | — | — | **Not available**: Embedded System exclusion (§2.1) |
| D. Slint commercial | Paid plan, royalties waived for OSS | Would allow a non-GPL image | Pointless for an open-source project; cost and paperwork for nothing |
| E. Own code LGPL-2.1-or-later (match qml-asteroid) | — | Flows into qml-asteroid | Flows nowhere else without relicensing; LGPL on bare-metal code with no linking boundary is meaningless; more complex than B for less |
| F. Dual "MIT OR GPL-3.0-or-later" | — | — | Redundant: MIT already permits GPL use |
| G. Replace Slint | Whole image permissive | — | Throws away the chosen toolkit; only a lever if the GPL ever blocks something |

## 4. Recommendation

**Option B**: own files under **MIT** (`SPDX-License-Identifier: MIT`), combined image distributed under **GPL-3.0-only** because of Slint. MIT rather than BSD-3-Clause because lk2nd, TinyUSB and Ionicons are MIT and the Rust ecosystem is MIT/Apache; BSD-3-Clause would be equally workable and matches `asteroid-launcher`'s headers — pick one, do not mix.

If copyleft on the firmware itself is a goal in its own right, stay with A: it is fully consistent today and the only cost is relicensing on each share-back. Nothing in the inventory forces the change; it is a values decision.

Either way, three things need fixing independently of A vs B: the `.hcd` blob (no redistribution right found), the missing notices (`NOTICE.qcom`, NimBLE `NOTICE`, BSD text for FlatMesh), and the README's licence paragraph (lists Noto only, calls the image "or-later").

**`4343A0.hcd`:** recommended handling is to stop shipping it in the repo and have `make`/`tools/run.py` obtain it (`adb pull /vendor/firmware/4343A0.hcd` from a watch running AsteroidOS, or from the stock `system.img` per meta-sturgeon's `README-system-dir.md`) into a git-ignored `firmware/` file, with the Makefile failing clearly when it is absent. Alternative: keep shipping it as AsteroidOS effectively does (its `android` recipe is `LICENSE = "CLOSED"` and redistributes the stock partition from Dropbox) and document the provenance — that is the status quo risk, not a new one. Asking Infineon/Cypress for a redistributable BCM43430A0 patch is the clean long-term fix **[uncertain which they'd grant]**.

## 5. Working rule under the recommendation

| Source | Licence | Can copy into own (MIT) files? | Notes |
|---|---|---|---|
| lk2nd core, TinyUSB, Ionicons, Mesa ir3 output | MIT | Yes | Keep the original header on copied files |
| lk2nd Qualcomm parts, mainline DTS, FlatMesh, asteroid-launcher | BSD-2/3-Clause | Yes | Keep header; BSD-3 "no endorsement" clause is passive |
| NimBLE, Mbed TLS (Apache branch), Roboto, Apache-2.0 crates | Apache-2.0 | Yes, as `third_party` or with header | Reproduce `NOTICE`; §4(b) mark changed files |
| Zlib / ISC / 0BSD / Unicode-3.0 / CC0 / Unlicense crates | permissive | Yes | Notices in `THIRD_PARTY_NOTICES` |
| OFL fonts | OFL-1.1 | Embed, do not modify or rename | Keep OFL texts |
| qml-asteroid LGPL-2.1+ files, AsteroidOS GPL-3.0+ QML | LGPL/GPL | **Not into MIT files**; as separate files keeping their licence, which then are part of the GPL image | Under option A they could be merged into own GPL files |
| Slint | GPL-3.0-only | **Not into MIT files**; stays in `third_party/slint` | Patches there are GPL-3.0-only |
| Vendor kernel 3.10, mainline `drm/msm`, `drivers/bluetooth`, any GPL-2.0-only code | GPL-2.0-only | **No, under every option** | Reimplement from register-level facts (as done for BMS). Register maps, sequences of writes and protocol constants are facts; whole functions, comments and structure are expression **[the boundary is a judgement call]** |
| BTstack | BSD + non-commercial clause | No | Already ruled out (BLUETOOTH.md §6) |
| Firmware blobs | LICENSE.qcom / none | Never "code"; ship separately in the ramdisk, outside the GPL grant | `.hcd` see §4 |

So the rule "third-party code must be MIT/BSD/Apache/zlib; OFL fonts OK; GPL code gets reimplemented" stays exactly as it is, with one addition: LGPL/GPL *files* may be included whole (keeping their licence) because the image is GPL anyway, but never merged into own files.

## 6. To-do list (when the decision is made)

1. `LICENSE` / `LICENSES/`: either keep `LICENSE` (GPL-3.0 text) and add a short `LICENSE.md` explaining the layers, or go REUSE-style: `LICENSES/MIT.txt`, `LICENSES/GPL-3.0-only.txt`, `LICENSES/Apache-2.0.txt`, `LICENSES/BSD-3-Clause.txt`, `LICENSES/OFL-1.1.txt`, `LICENSES/LicenseRef-LICENSE.qcom.txt` + a `REUSE.toml`. Statement to make: "Own files: MIT. The firmware image links Slint under GPL-3.0-only, so the image as a whole is GPL-3.0-only. `firmware/` is not part of the licensed work."
2. Per-file tagging: either two SPDX lines (`SPDX-FileCopyrightText: 2026 Darrel Griët`, `SPDX-License-Identifier: MIT`) at the top of every own file in `src/`, `ui/`, `ld/`, `dts/`, `tools/`, `tests/`, or — consistent with the no-comments rule — a `REUSE.toml` with `[[annotations]] path = ["src/**", "ui/src/**", ...]` so no file needs a header. `reuse lint` then checks the whole tree, including `third_party/`.
3. `ui/Cargo.toml`: `license = "MIT"` (or leave GPL under option A); `dts/*.dts` SPDX line to match.
4. `third_party/slint/README.md`: upstream version 1.18.1 from crates.io, "used under GPL-3.0-only", dated list of modified files and why; keep every `LICENSES/` folder and SPDX header untouched.
5. Record the Mbed TLS choice ("used under Apache-2.0") and keep `third_party/mbedtls/LICENSE`.
6. `NOTICE` at repo root collecting: NimBLE `NOTICE` text, Roboto Apache-2.0 attribution, Android 5x12 font BSD notice, FlatMesh BSD-3 notice (Florent Revest 2016), Ionicons MIT, OFL font copyrights, Unicode-3.0 (icu4x). Fix `src/display/flatmesh_geometry.h` to carry the real BSD-3 notice or an SPDX tag.
7. Release artefacts: generate `THIRD_PARTY_NOTICES.md` for the Rust tree (`cargo about generate` or `cargo license`) and ship it next to `asteroid.img`; make sure every published image is built from a tag so §6(d) Corresponding Source is the tag.
8. `firmware/`: add linux-firmware's `NOTICE.qcom` next to `LICENSE.qcom` (WHENCE names both), a `firmware/README` stating the files are not covered by the project licence and quoting the Qualcomm redistribution conditions; decide on `4343A0.hcd` (§4).
9. README licence paragraph: list all three font families, say "image: GPL-3.0-only (Slint), own files: MIT", keep the ramdisk/blob sentence.
10. No About/licences screen is required by any licence in use; optional later as a settings page (GPLv3 §5(d) does not apply, Slint attribution only applies to the Royalty-free licence).
11. Update the project memory / EMBEDDED.md decision line: "own code MIT, image GPL-3.0-only via Slint; LGPL/GPL files may be included whole, never merged".

## 7. Open questions for Darrel

1. Copyleft on own code wanted (A) or frictionless sharing (B)?
2. `4343A0.hcd`: pull-from-watch at build time, keep shipping with a provenance note, or ask Infineon?
3. MIT or BSD-3-Clause for own files (house style vs lk2nd/TinyUSB)?
4. SPDX headers in files or a `REUSE.toml` (no headers)?

## Sources

- Slint `LICENSE.md`: https://github.com/slint-ui/slint/blob/master/LICENSE.md; FAQ: https://github.com/slint-ui/slint/blob/master/FAQ.md; pricing/licence page: https://slint.dev/license.html; Royalty-free 2.0 text: `third_party/slint/i-slint-core/LICENSES/LicenseRef-Slint-Royalty-free-2.0.md`
- GPLv3 text: https://www.gnu.org/licenses/gpl-3.0.html (§1 System Libraries / Corresponding Source, §5 aggregate and 5(d), §6 User Product / Installation Information)
- FSF licence list: https://www.gnu.org/licenses/license-list.html (Apache-2.0, Unicode v3, GPLv2/GPLv3)
- Apache GPL compatibility: https://www.apache.org/licenses/GPL-compatibility.html
- linux-firmware `WHENCE` (adreno block, `qcom/a330_*`, "See LICENSE.qcom and NOTICE.qcom"; no BCM43430A0 entry) and `LICENSES/LICENSE.qcom`, `LICENSES/NOTICE.qcom`: https://gitlab.com/kernel-firmware/linux-firmware
- Mainline DTS headers: `arch/arm/boot/dts/qcom/qcom-apq8026-huawei-sturgeon.dts` (BSD-3-Clause, Luca Weiss 2022), `qcom-msm8226.dtsi` (BSD-3-Clause, Linux Foundation 2020); `drivers/gpu/drm/msm/adreno/a3xx_gpu.c` (GPL-2.0-only)
- Local: `third_party/*/LICENSE`, `third_party/nimble/NOTICE`, `third_party/mbedtls/README.md`, `ui/fonts/*.txt`, `ui/Cargo.toml`, `ui/Cargo.lock` (crate licences via `cargo tree --target armv7a-none-eabihf`), `~/Downloads/AsteroidOS/lk2nd/LICENSE`, `qml-asteroid/COPYING`, `asteroid-launcher/COPYING.*`, `meta-smartwatch/meta-sturgeon/recipes-android/android/android_sturgeon-mm.bb`, `asteroid-embedded-notes/EMBEDDED.md` (lines 19-23, 395-396, 423-424), `BLUETOOTH.md` §6

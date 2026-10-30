# Run-time font rasterisation for the Slint UI (asteroid-embedded)

Research notes and implementation plan, 2026-10-30. Research only: nothing in the repo was
modified, nothing was flashed. All experiments live in
`/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS/a46dd4d0-5ddc-4e73-b24d-ef856df96f8a/scratchpad/fontplan/`
(referred to as `$S` below).

## 1. Recommendation in one paragraph

Patch Slint 1.18.1 so the software renderer's `systemfonts` path (parley + fontique + swash +
skrifa) builds without `std` (option 2). It is proven: a 149+/79- line patch over 16 files makes
`i-slint-renderer-software` with `systemfonts` compile for `armv7a-none-eabihf` on stable Rust,
links into a bootable-shaped `asteroid.img`, and with pre-rendered glyphs dropped and the fonts
subset to Latin/Greek/Cyrillic the image goes from 11.32 MB to about 5.2 MB (see section 3 for
the measured numbers). Text is rasterised at the exact size requested, cached by glyph, and
drawn through the same texture blit as today's bitmap glyphs, so the steady-state repaint cost
does not change. `SLINT_FONT_SIZES` and the embedded character set go away. Option 1 (Rust
`std` on bare metal) is dead on the current nightly: `std`'s platform layer no longer has an
"unsupported OS" fallback for `os = none` targets. Option 3 (SDF) gets the image to 3.97 MB
but keeps the quality, speed and hand-listed-sizes problems. The main risks are a Slint fork to
carry until it is upstreamed, +1.2 MB of shaping code, and first-draw ordering (fonts must be
registered before the first text layout).

## 2. Baseline (measured)

Scratch copy of the repo (`$S/repo`, `make -j8`, 47 s):

```
build/asteroid.img  11,323,392 B
.text 11,259,644  .data 2,560  .bss 984,320   (arm-none-eabi-size build/asteroid.elf)
```

Given numbers from earlier work: 7.8 MB of that is pre-rendered glyphs (4 fonts x 22 sizes),
the rest (~3.5 MB) is code, icon textures and the ring segments; watchface repaint 13.1 ms
(`uibench 0 0 10`); SDF build at 24 px: 3.4 MB image, 18.6 ms, 144 px digits wobbly.

## 3. Findings per option

### 3.1 Option 1: `std` on bare metal (nightly + `-Zbuild-std`) -- rejected

Experiment: `$S/ui-std` (copy of `ui/`, `slint` feature `std`, `i-slint-renderer-software`
feature `systemfonts`, `#![feature(restricted_std)]`, `#[panic_handler]` replaced by a hook),
built with `rustup toolchain install nightly --profile minimal -c rust-src`
(rustc 1.101.0-nightly 2026-10-29) and

```
RUSTC_WRAPPER=$S/rustc-wrap.sh cargo +nightly build --release \
    -Zbuild-std=std,panic_abort --target armv7a-none-eabihf
```

Three attempts (`$S/std-build{1,2,3}.log`):

1. `-Zcrate-attr=feature(restricted_std)` in RUSTFLAGS: `core` itself fails with
   `E0635 unknown feature restricted_std` (the attribute reaches the sysroot crates).
2. Wrapper that skips sysroot crates: every `no_std` dependency (`zerotrie`, `zerovec`, ...)
   and every host build script fails with the same E0635, because the feature only exists in
   a std that was built with `cfg(restricted_std)`.
3. Wrapper that retries without the attribute on E0635: the attribute problem is solved, but
   **std itself does not compile for `armv7a-none-eabihf`** (`$S/std-build3.log`):
   - `library/std/src/sys/alloc/mod.rs:66`, `sys/io/error/mod.rs:1`: `cfg_select!` with no
     fallback arm for an unknown `target_os` ("none of the predicates evaluated to true");
   - `sys/sync/{condvar,mutex,once,rwlock}/no_threads.rs`: `compile_error!("Using no_threads
     implementation on a target with threads")` because the built-in target sets
     `target_has_threads`;
   - unresolved `sys::io::{decode_error_kind, errno, ...}`, `sys::thread_local::key::*`,
     `sys::fill_bytes`.

   The "unsupported PAL" that older write-ups rely on is gone: std's `build.rs` now only sets
   `restricted_std` for a hard-coded list of known-but-unsupported OSes, and each `sys` module
   selects an implementation by `target_os` with no `_ =>` arm. Making this work would mean a
   custom target JSON *and* patching `rust-src` in the toolchain (or a `[patch]` of the sysroot
   source), pinned to one nightly. Not a proven method, high maintenance; dropped. Even if it
   compiled, `Instant::now`, `env`, `fs` and thread-locals would be stubs that panic or return
   errors at run time, and Slint's std paths use all of them (`sharedfontique.rs` reads
   `SLINT_FONT_PATH`, `renderer-software/lib.rs` reads `SLINT_SOFTWARE_RENDERER_PARLEY_DISABLED`
   through `OnceLock`, `i-slint-core/window.rs` uses `std::env::args_os()`).

### 3.2 Option 2: patch Slint so `systemfonts` works with `no_std` + `alloc` -- recommended, proven

**What the stack needs.** The whole font stack is already `no_std`-capable with a `libm`
feature: parley 0.11.1, fontique 0.11.1, parlance, skrifa 0.44, read-fonts 0.41, font-types,
swash 0.2.10 (`scale`, `render`), zeno, yazi, harfrust 0.12, icu_normalizer/properties/
segmenter 2.x (`#![no_std]`), hashbrown, core_maths. Only Slint's glue uses `std`:
`i-slint-common/sharedfontique.rs` (env/fs scanning of `SLINT_FONT_PATH`, `HashSet`,
`PathBuf`), `i-slint-core/textlayout/sharedparley*` (`std::cell`, `HashSet`, `Arc`,
`std::thread_local!`), `i-slint-core/item_rendering.rs` (`ItemCache` gated on `std` and using
`std::collections::HashMap`), `i-slint-core/renderer.rs` (`register_font_from_memory` gated on
`std`), `i-slint-renderer-software/fonts/{systemfonts,vectorfont}.rs` (`HashMap`, the `clru`
glyph cache with `RandomState`, `DefaultHasher`), `lib.rs` (`OnceLock`+env, `std::pin::pin!`,
`std::num::NonZero`). The feature definitions also force it: `systemfonts = [..., "std",
"dep:clru"]` and parley is pulled with default features (`system` -> `std` -> fontconfig).

**The patch.** Fork of the registry crates in `$S/fork` (git: `pristine 1.18.1` -> `PR 12367`
-> `no_std systemfonts` -> `parley complex-scripts behind a feature`). The no_std part
(`$S/slint-nostd-systemfonts.patch`, 747 lines of diff, 16 files, +149/-79):

| file | change |
|---|---|
| `i-slint-renderer-software/Cargo.toml` | `systemfonts` no longer implies `std`/`clru`; `skrifa` default-features off; `libm`/`std` forward to skrifa; hashbrown dep |
| `i-slint-core/Cargo.toml` | parley/skrifa/swash default-features off, `libm`/`std` forward to them and to `i-slint-common`; hashbrown dep; new `parley-complex-scripts` feature, on under `std` |
| `i-slint-common/Cargo.toml`, `lib.rs` | `std`/`libm` features; `no_std` unless `std`/`color-parsing`/test; fontique default-features off |
| `i-slint-common/sharedfontique.rs` | env/fs font-path scanning and `new_shared()` under `cfg(std)`; `alloc::sync::Arc`; `FontPath` alias (`PathBuf` with std, `String` without) |
| `i-slint-compiler/Cargo.toml` | its (host) `i-slint-common` gets `std` |
| `i-slint-core/textlayout/sharedparley.rs`, `cache.rs`, `shaping.rs`, `layout.rs`, `selection.rs` | `core::cell`, `hashbrown::HashSet`, `alloc::{sync::Arc, borrow::Cow, string::String}`, `crate::thread_local!` + `with`/`borrow_mut`, `num_traits::Float` for `floor/ceil/round`, `link_under_cursor` un-gated |
| `i-slint-core/item_rendering.rs` | `ItemCache` available without `std`, on `hashbrown::HashMap` |
| `i-slint-core/renderer.rs` | `register_font_from_memory` under `shared-parley` only, `Box<dyn core::error::Error>` |
| `i-slint-renderer-software/fonts/systemfonts.rs` | `hashbrown::HashMap`; `register_font_from_path` under `std` |
| `i-slint-renderer-software/fonts/vectorfont.rs` | `clru` replaced by a 40-line LRU on `hashbrown` bounded by alpha-map bytes (1 MiB as upstream); `DefaultHashBuilder::hash_one` for the variation-coords hash |
| `i-slint-renderer-software/lib.rs` | `parley_disabled()` is `false` without `std`; `core::pin::pin!`, `core::num::NonZero`; `register_font_from_path` under `std` |

Plus upstream PR #12367 (badicsalex / Foundation Devices, open since 2026-07-05, 43 lines) which
adds `EmbedResourcesKind::EmbedForSoftwareRendererNoFonts` (`slint-build`) /
`EmbedTexturesOnly` (`i-slint-compiler`): images are still pre-rendered to textures, no glyphs
are embedded; and `FontContext::set_default_font_family`. It applied to 1.18.1 with `patch -p1`
without fuzz. (PR #12815, "Bring software renderer text quality on par with Skia", gamma and
hinting, is a draft and not needed.)

**Build evidence.** `$S/ui-nostd` = `ui/` + `[patch.crates-io]` to the fork,
`i-slint-renderer-software` features `["experimental", "systemfonts"]`, stable Rust,
`cargo build --release` -> exit 0, one warning (`$S/nostd-build7.log`, `nostd-build8.log`).
The generated `watchface.rs` contains 0 `BitmapFont` and 1994 `StaticTextures` (icons and ring
untouched). `build.rs` uses `EmbedForSoftwareRendererNoFonts` and no `SLINT_FONT_SIZES`;
`watch.rs` registers the four TTFs via `include_bytes!` in `Platform::create_window_adapter`
through `i_slint_core::renderer::RendererSealed::register_font_from_memory` (the window adapter
is created lazily on the first `Screen::new()`, after `set_platform`, so the SlintContext exists).

Linked images (`make -j8` in repo copies, `$S/*-make.log`):

| variant | asteroid.img | .text |
|---|---|---|
| baseline (bitmap glyphs, 22 sizes) | 11,323,392 | 11,259,644 |
| no_std vector fonts, full TTFs, parley `complex-scripts` (icu dictionaries) | 9,539,584 | 9,474,704 |
| same, no TTF data linked (isolates the font files) | 7,796,736 | 7,732,768 |
| same as row 2 but `complex-scripts` off | 6,483,968 | 6,419,392 |
| **candidate**: `complex-scripts` off + Latin/Greek/Cyrillic subset TTFs (431 KB) | **5,173,248** | 5,108,304 |
| SDF at 96 px (option 3, sizes >= 16 only) | 3,966,976 | 3,904,084 |

Attribution from a linker map of row 2 (`$S/nostd.map`): the four TTFs are 1,741,648 B
(607 KB Noto Sans Light, 519/512 KB Roboto Light/Medium, 104 KB Raleway Light); five anonymous
rodata blobs of 2.01 + 0.47 + 0.26 + 0.17 + 0.13 MB = 3.04 MB are the icu_segmenter
dictionaries/LSTM data that parley's `complex-scripts` feature (`LineSegmenter::new_dictionary`,
`WordSegmenter::new_dictionary`) pulls in; i-slint-core enables that feature unconditionally for
non-wasm targets. Without it parley uses `new_for_non_complex_scripts` (UAX#14 without
dictionary breaking for Thai/Lao/Khmer/Burmese; CJK still breaks between ideographs). The
remaining ~1.2 MB over the 3.5 MB base is parley/harfrust/swash/skrifa/fontique code and the
icu properties/normalizer tables.

Font subsets (`$S/subset/`, fontTools 4.x `pyftsubset --layout-features=kern,liga --no-hinting`):

| font | full | Latin (U+0000-024F + punctuation/arrows/symbols) | Latin+Greek+Cyrillic+Latin Ext Add. |
|---|---|---|---|
| NotoSans-Light | 607,136 | 48,864 | 155,472 |
| Roboto-Light | 518,580 | 44,640 | 112,728 |
| Roboto-Medium | 511,592 | 44,000 | 111,384 |
| Raleway-Light | 104,340 | 48,632 | 50,968 |

**CPU cost.** Host micro-benchmark `$S/bench` (swash 0.2.10 `Render` with `Source::Outline`,
`Format::Alpha`, no hinting; parley 0.11.1 shape + `break_all_lines` + `align`; Apple M-series,
idle CPU, release build):

```
NotoSans-Light  20px  1.1 us/glyph  (alpha map ~108 B)      Raleway-Light  20px  1.0 us
NotoSans-Light  36px  1.0 us/glyph  (~326 B)                Raleway-Light  36px  1.4 us
NotoSans-Light  72px  1.6 us/glyph  (~1.2 KB)               Raleway-Light  72px  2.3 us
NotoSans-Light 144px  2.9 us/glyph  (~4.9 KB)               Raleway-Light 144px  4.1 us
parley shape+layout: "12:34" 7.8 us; 64-char notification line 7.1 us
```

Cortex-A7 at ~1 GHz, in-order, VFPv4, float `floor/sqrt` through the `libm` crate: assume
30-50x slower than the host core. Estimates: 144 px glyph 0.1-0.2 ms, 20-36 px glyph
30-70 us, a 64-character paragraph layout 0.2-0.4 ms. These are **cache-miss costs only**:
Slint caches rendered glyphs (`GLYPH_CACHE`, keyed by font, size, glyph, 4 sub-pixel bins) and
laid-out paragraphs (`TextLayoutCache`, invalidated by property change). The steady-state
watchface repaint therefore does the same work as today: `draw_glyph_run` hands the cached
`alpha_map` to `DrawTextureArgs` exactly like a bitmap glyph (`lib.rs:3327`). First paint of a
screen rasterises its glyphs once: watchface ~10 glyphs at 144 px + ~30 small ones ~ 2-5 ms;
launcher with ~100 glyphs at 20 px ~ 3-10 ms; a new notification ~1-3 ms. Compared with the
SDF path, which costs per *pixel* every frame (13.1 -> 18.6 ms), this costs per *new glyph*.

**RAM.** Fonts are `&'static [u8]` in the image, no copy (`fontique::Blob` wraps the slice).
Glyph cache: upstream limit 1 MiB of alpha bytes; the watchface's 10 digits x 4 sub-pixel
bins x 5-7 KB = 0.2-0.3 MB per family, so 1 MiB covers one family with headroom; with four
selectable families raise the limit to 4-8 MiB (constant in `vectorfont.rs`; `UI_HEAP_SIZE` is
64 MB). Per-item layout cache: a few KB per text item. swash `ScaleContext` and parley
`LayoutContext` scratch: tens of KB. Expect < 2 MB extra heap in practice; measure.

**Licences.** parley, fontique, parlance, skrifa, read-fonts, font-types, swash, zeno, yazi,
linebender_resource_handle, hashbrown: Apache-2.0 OR MIT; harfrust, core_maths: MIT; foldhash:
Zlib; icu_*: Unicode-3.0 (permissive). Nothing GPL beyond Slint itself, which `ui/` already
uses under GPL-3.0-or-later. Fonts stay OFL / Apache (Roboto).

**Upstreamability.** The patch only relaxes gates and swaps std-only containers; desktop
behaviour is unchanged (`std` still implies everything it did, `complex-scripts` stays on under
`std`). Slint merged no_std fixes for the software renderer's `Path` in 1.19 (#13565, #13629) and
there is a second embedded user wanting non-bundled vector fonts (#12367). File an issue
("software renderer: vector fonts without std") and a PR of the patch rebased on master; master's
`i-slint-renderer-software/Cargo.toml` still has `systemfonts = [..., "std", "dep:clru"]`, so
the patch applies conceptually unchanged (parley 0.12 there).

### 3.3 Option 3: better SDF -- measured, not recommended

The SDF target size is `(max*2/3).max(16).min(6*min)` in
`i-slint-compiler/passes/embed_glyphs.rs:535`; with sizes 4..144 that is `min(96, 24) = 24` px,
hence the wobbly 144 px digits. Dropping the 4/7/8/12/13 px sizes (`SLINT_FONT_SIZES` min 16)
gives a 96 px field: `$S/repo-sdf`, `slint-build` feature `sdf-fonts`, `.with_sdf_fonts(true)`:
image **3,966,976 B** (vs 3.4 MB at 24 px, 11.3 MB baseline). Quality at 144 px would be fine
(1.5x upscale, range 6 px); the small sizes (turbo list 4-13 px) are then sampled 8-24x down
from the field and look poor, the 18.6 ms per-pixel sampling cost stays, SDF-or-alpha is a
per-font flag so mixing needs a compiler patch, and every computed size still has to be listed
and the character set is still fixed at build time. msdf (multi-channel) would fix corners but
needs renderer work and 3x the data. Keep as the documented fallback: it is a two-line
`build.rs` change away.

### 3.4 Other routes considered

- **Newer Slint.** crates.io has 1.18.1 as latest (`cargo info slint`); master is `1.19.0 -
  Unreleased`. Nothing there provides no_std vector fonts. Master adds an
  `owned-pre-rendered-resources` feature ("bitmap fonts built at run time, as the interpreter
  does") which makes `BitmapFont` with owned storage possible, i.e. route 4b below without
  leaking.
- **4b: build `BitmapFont` tables at boot with an own rasteriser** (no Slint patch; swash or
  fontdue, both permissive). Keeps Slint's bitmap path, but every size still has to be listed,
  all glyphs of every size are rasterised eagerly at boot (~1000 glyphs x ~20 sizes x 50-100 us
  on the A7 = 1-2 s of boot time, or a reduced charset), and `BitmapFont`/`BitmapGlyphs` are
  doc-hidden internal structs with `'static` slices (leak until 1.19's owned storage). Inferior
  to option 2, which gets lazy rendering and exact sizes from code Slint already ships.
- **Fonts on eMMC.** `src/storage/ext4.c` can read a file from userdata (`ext4_lookup` +
  `ext4_read`); `register_font_from_memory` takes `&'static [u8]`, so a `Box::leak` of the read
  buffer works. This removes the font data from the image entirely (-0.43 MB with subsets, or
  ships full fonts / CJK fallbacks at zero image cost). Optional later step.

## 4. Implementation plan (option 2)

Each step produces a bootable image and is measured with: `ls -l build/asteroid.img` +
`arm-none-eabi-size build/asteroid.elf`; `uibench <panel> 0 10` for panels 0-6 run twice in a
row (first = cold glyph cache, second = warm); heap use (step 1 adds it to `status`); a
screenshot of each panel (`shot`) for side-by-side comparison with the current image.

**Step 0 - carry the fork.** Create a git fork of slint-ui/slint with branch
`nostd-systemfonts` on tag `v1.18.1`: cherry-pick PR #12367, then the patch from
`$S/fork` (`git -C $S/fork format-patch pristine..HEAD` gives three commits; the fork tree is
registry layout, so re-apply by file into the slint workspace: `internal/common`,
`internal/core`, `internal/renderers/software`, `internal/compiler`, `api/rs/build`). Reference
it from `ui/Cargo.toml`:

```toml
[patch.crates-io]
slint = { git = "https://github.com/<fork>/slint", rev = "<sha>" }
slint-build = { git = ..., rev = "<sha>" }
i-slint-core = { git = ..., rev = "<sha>" }
i-slint-common = { git = ..., rev = "<sha>" }
i-slint-compiler = { git = ..., rev = "<sha>" }
i-slint-renderer-software = { git = ..., rev = "<sha>" }
```

(All six because `[patch]` entries must share the version; `slint`/`slint-build` are unchanged
but must come from the same source to keep `=1.18.1` path deps consistent. Cargo.lock pins the
rev. If network-free builds matter, vendor the six crate directories under `third_party/slint/`
with `path =` instead, as the scratch experiment does.) Makefile: `UI_SRCS` only watches `ui/`;
either add the vendored path to the `find` or drop the dependency list and always run cargo
(it is a no-op when up to date). Observed in the experiment: `make` did not rebuild the Rust
lib after a fork change.

**Step 1 - fork in, behaviour unchanged.** `ui/Cargo.toml`: `i-slint-renderer-software`
features `["experimental", "systemfonts"]`, add `i-slint-core = { version = "=1.18.1",
default-features = false }`. `ui/src/watch.rs`: `static FONTS: [&[u8]; 4]` with
`include_bytes!` of the four TTFs and, in `create_window_adapter`, after
`MinimalSoftwareWindow::new`:

```rust
use i_slint_core::renderer::RendererSealed;
for font in FONTS { window.renderer().register_font_from_memory(font)?; }
```

Keep `EmbedForSoftwareRenderer` and `SLINT_FONT_SIZES` for now: bitmap fonts are still embedded
and `fonts::match_font` prefers them, so rendering is identical. Test: boots, screens identical,
`uibench` identical, image ~ +1.2 MB code + 1.7 MB TTF (expect ~14.3 MB; this step only proves
the fork links and `register_font_from_memory` does not fail -- if it returns
"slint platform not initialized", move the registration to `open()` before `component.show()`,
or register through `i_slint_core::context::with_global_context(|ctx|
ctx.font_context().borrow_mut().register_static_font(..))`). Add a `ui_heap_used()` export
(`HEAP.used()`) and print it in `status`.

**Step 2 - run-time fonts.** `ui/build.rs`: `EmbedForSoftwareRendererNoFonts`, delete the
`SLINT_FONT_SIZES` block and its comment. Test on all 7 panels: digital watchface at full and
nightstand size (86 %, now rendered at the exact fractional size instead of the nearest listed
one -- check vertical placement and the hour preview at 160 px), launcher labels, notification
with long body (wrapping now done by parley/UAX#14), turbo list names at 4-13 px. Measure image
(expect ~6.5 MB with full TTFs), cold/warm `uibench`, heap. Compare screenshots; small metric
differences are expected (skrifa metrics vs the compiler's, 4 sub-pixel bins).

**Step 3 - subset the fonts.** Add `tools/subset-fonts.sh` with the `pyftsubset` command
(Latin+Greek+Cyrillic set above, keep `--layout-features=kern,liga`), keep the full TTFs out of
the image (`ui/fonts/full/` or regenerate from upstream), update `ui/fonts/*.txt` licence notes
(OFL permits subsetting with the reserved-name rule; Roboto Apache). Expect ~5.2 MB (Latin-only
~4.95 MB). Verify notification text with Cyrillic/Greek and that missing glyphs show `.notdef`
rather than panicking.

**Step 4 - tune.** Raise the glyph-cache limit (`vectorfont.rs`, 1 MiB -> 4-8 MiB) if the warm
`uibench` of the watchface with all four families exceeds the cold one by more than noise; try
`.hint(true)` on the swash scaler for 20-26 px UI text if it looks soft (hinting changes
advances; measure); decide `SUBPIXEL_BIN_COUNT` (4 upstream; 1 halves cache size and makes the
digits pixel-identical frame to frame). Each of these is one line in the fork.

**Step 5 - optional, fonts from eMMC.** Read `userdata:/fonts/*.ttf` with the ext4 reader into
the UI heap and register them in addition to (or instead of) the embedded subsets; lets the
device carry full Noto / CJK fallbacks. fontique's fallback chain (`append_fallbacks` per
script) can be set from `register_fonts`' returned family ids.

**Step 6 - upstream.** Open the Slint issue + PR (no_std `systemfonts`), rebased on master,
with #12367 as the companion. Once merged, `[patch.crates-io]` goes away at the next Slint
bump.

**Fallbacks.** If step 2 shows an unfixable rendering or performance problem: (a) keep the fork
only for `EmbedForSoftwareRendererNoFonts` + bitmap fonts for the 144/124 px digits and vector
fonts for everything else (`match_font` already prefers an embedded family when one is
registered under that name, so embedding only the digit fonts at the two large sizes is a
`SLINT_FONT_SIZES`/import split in the `.slint` files); or (b) SDF at 96 px from section 3.3
(3.97 MB, no fork).

## 5. Risks

1. **Fork maintenance** until upstream merges; the patch is small and mechanical, but each
   Slint upgrade needs a rebase. Mitigated by pinning `rev` and by the upstream PR.
2. **Font registration order.** `systemfonts::fallbackfont` does
   `query_fontique(..).unwrap()`: with no font registered, the first text layout panics. The
   plan registers in `create_window_adapter`; step 1 verifies this before anything else changes.
3. **Rendering differences**: exact sizes, sub-pixel bins, skrifa metrics, parley line breaking
   (no `TextWrap` quirks of the old simple line breaker). Visual check per panel; the `.slint`
   layouts were tuned for rounded sizes.
4. **Code size** +1.2 MB and `complex-scripts` off (no dictionary breaking for Thai-family
   scripts). If 1.2 MB matters, the next candidates are the icu_properties tables and harfrust's
   complex shapers; attribute with `-Wl,-Map` as in `$S/nostd.map`.
5. **Performance**: per-frame overhead of `TextLayoutCache` lookups and `text_size` queries
   through parley for ~10 text items -- expected negligible against 13 ms, to be measured; cold
   first paint of a screen a few ms.
6. **Panics inside the font stack** on malformed data (`expect("fatal: swash is unable to
   parse truetype font")`): only our own TTFs are registered; eMMC fonts (step 5) should be
   validated with `skrifa::FontRef::new` before registration.
7. **Hash iteration / LRU**: the replacement glyph cache evicts by linear scan; fine for a few
   thousand entries, swap for the `lru` crate if it ever shows up in profiles.
8. **Toolchain**: stays on stable Rust (MSRV 1.92 from Slint 1.18); no nightly.

## 6. Artefacts and commands

- `$S/ui-std`, `$S/rustc-wrap.sh`, `$S/std-build{1,2,3}.log` - option 1 attempts.
- `$S/fork` (git), `$S/slint-nostd-systemfonts.patch`, `$S/pr12367.diff` - option 2 patch.
- `$S/ui-nostd`, `$S/nostd-build{1..8}.log` - the no_std crate; `$S/repo-nostd*` - linked
  images (`repo-nostd`: complex-scripts off, full TTFs; `repo-nostd-nofontdata`;
  `repo-nostd-final`: subset fonts); `$S/nostd.map` - linker map.
- `$S/repo-sdf` - SDF 96 px variant; `$S/subset/`, `$S/venv` - fontTools subsets.
- `$S/bench` - host swash/parley micro-benchmark (`./target/release/fontbench ../ui/fonts`).
- Upstream references: slint-ui/slint PR #12367 (non-bundled vector fonts, open), PR #12815
  (text quality draft), 1.19 changelog (no_std `Path` fixes #13565/#13629,
  `owned-pre-rendered-resources`), `i-slint-compiler/passes/embed_glyphs.rs:535` (SDF size).

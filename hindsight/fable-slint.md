# Hindsight: was Slint the right UI choice for asteroid-embedded?

Research only (2026-10-30). Code read: `ui/`, `src/ui/`, `src/gpu/`, `src/display/`,
`asteroid-embedded-notes/EMBEDDED.md` and `GPU-UI.md`, git history of both repos, plus web
sources listed at the end. Note: the context file says "today only composition is on the GPU";
that is out of date. Since `9dddb19`/`d36168e` (2026-10-30 14:36) the `TargetPixelBuffer` hook
in `ui/src/paint.rs` hands rectangles, rounded rectangles, glyphs and images to `src/gpu/paint.c`;
only gradients, rotations and the scene walk stay on the CPU.

## Verdict: keep, but change

Slint was the right call and remains the right call. The honest accounting:

### What Slint bought (evidence)

1. **Speed of the QML port.** The entire AsteroidOS-like UI (watchface + classic face, seven
   launcher layouts, settings with live previews, alarm/timer/stopwatch, quick panel,
   notifications, Today, music, overlay) was written between `4ad450c` (10-26 22:19) and
   `e2fee26` (10-30), i.e. 4 days, 38 ui/Slint commits, 3,889 lines of `.slint` added. The six
   extra launcher layouts incl. flick physics were one commit (`0a1e6fe`, +579 lines of
   `launcher.slint`) in one evening, transcribed from the QML in `aos/src/applauncher/`.
   Declarative bindings/animations map 1:1 onto Qt Quick (`animate`, `TouchArea`, `for`/`if`,
   models), which is why `EMBEDDED.md` ("AsteroidOS layout match") could be done from QML
   sources alone without reference screenshots for six of the layouts.
2. **The GPU path exists and works, via a supported hook.** `TargetPixelBuffer` (experimental
   feature, `i-slint-renderer-software` 1.18.1) was built for exactly this ("DMA2D/PXP"
   delegation). `GPU-UI.md §10`: full repaint face 1.76 ms GPU vs 4.4 ms CPU, list 2.94 vs
   7.4 ms, 2 draws per screen, PSNR 50–55 dB vs the software path; per-screen layers + partial
   repaint keep idle CPU at ~1 µs/frame (§8) and GPU at 1.4 ms/frame (§9). The adapter is
   small: `paint.rs` 233 lines + `paint.c` 431 lines. The glyph atlas comes for free from the
   `AlphaMap` textures Slint hands over; no text engine had to be written.
3. **Fallback for free.** When the GPU is suspended (AOD), `paint_begin` returns false and
   every hook declines, so the same scene renders on the CPU (`GPU-UI.md §10`, `ui_render` in
   `watch.rs`). No second code path.
4. **Licence fits.** GPL-3.0-only is compatible with the project's GPL-3.0-or-later
   (`GPU-UI.md §7`); nothing else in the stack is copyleft-constrained by it.
5. **Preview on the host.** `make preview` (`Makefile`, `preview.slint`, slint-viewer with
   `--auto-reload`) gives a desktop iteration loop without the watch.

### What it cost (evidence)

1. **Image size: 9.6 MB of the 11.2 MB image is embedded glyph bitmaps** (nm: 11,133
   `SLINT_EMBEDDED_RESOURCE_*` symbols = 9,585,897 bytes of 11,976,400). Root cause:
   `EmbedForSoftwareRenderer` pre-rasterises every font at every size, and sizes computed at
   run time (previews, nightstand 86 %, turbo list in 4 px steps) must be enumerated by hand
   (`SLINT_FONT_SIZES` in `ui/build.rs`: 22 sizes). The image grew 0.9 → 4.5 → 11.3 MB in two
   days (`EMBEDDED.md` "layout match", "Indicators"). The fix in progress (vendor 5 crates,
   `365e00e`, `9b3c992` = upstream PR 12367, `a25005f` no_std systemfonts, uncommitted
   `watch.rs` `register_font_from_memory`) should bring it to ~1.7 MB of TTFs + swash/parley
   code. PR 12367 is still open upstream (maintainers agree with the use case, want a rename).
2. **Software-renderer limits force workarounds in the UI source:**
   - No rounded clip (documented limitation; issue #4176 open since 2024; PR #9098 closed
     2026-03 as "outdated", maintainer wants a generic rounded-clip command). Consequences:
     `launcher.slint` speed dial draws the wheel in three clipped rectangles plus
     `2*strips` 4-px strips with per-strip opacity to emulate a QML ShaderEffect fade; round
     previews use a `Preview.fits()` heuristic to hide items that don't fit the circle.
   - No `Path` without std in 1.18 → the nightstand ring is 50 SVG segments generated in
     `build.rs`. Slint 1.16 added `software-renderer-path` for no_std and 1.19 (unreleased)
     "fixed building the software renderer's path support for no_std (#13565, #13629)", so this
     is a version lag, not a permanent wall.
   - No shaders/opacity layers: opacity is an alpha multiply, no `rotation`/`scale` in the
     software renderer (`GPU-UI.md §2`). QML `ShaderEffect`s (masks, fades) are either strips
     in `.slint` or moved to C/GPU (`stack.c`: app round window as a 64-gon mesh clip, edge
     indicators, dim, mesh colours).
   - `#RRGGBBAA` literal order and `row`/`col` name clashes (`EMBEDDED.md`, one evening lost on
     a fully transparent speed-dial band).
3. **CPU scene walk stays.** ~0.75 ms per list repaint even with every draw discarded
   (`§10`); the seconds tick costs 0.77 ms either way. On the A7 this is fine, but it caps
   what the GPU path can remove.
4. **Rust/no_std friction (toolkit-independent, but Slint pulled it in):** compiler_builtins'
   weak `__aeabi_uldivmod` ~2000x slower than libgcc caused random watchdog boots
   (`EMBEDDED.md` "UI toolkit"); a second Rust toolchain in the build; 494 crates in
   `Cargo.lock`; 33 MB `.a`.
5. **Version risk now owned by the project.** With the vendoring, the project carries patches
   to `i-slint-core`/`-compiler`/`-renderer-software` and uses the `experimental`
   `TargetPixelBuffer` (its signature changed once already: `fill_rectangle` → `draw_rectangle`
   per the C++ docs mismatch). Upgrading to 1.19 means rebasing those patches.

### Alternatives, then and now

| Option | GPU on a3xx | Fonts | Round clip / shader effects | QML fidelity | Licence | Size | Iteration | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Slint SW renderer + TargetPixelBuffer (current)** | rects/rounded/glyphs/images on GPU; gradients, rotation, scene walk CPU | bitmap-embedded today; runtime vector in progress | none in renderer; strips or C-side GPU effects | high (declarative, bindings, animations) | GPL-3 ok | 11 MB → ~3 MB after fonts | `.slint` edit + cargo + `make run`; host preview | keep |
| **Slint with own `ItemRenderer` on vendored `i-slint-core`** (option (a) in `GPU-UI.md`) | everything incl. gradients, rotation, opacity layers, rounded clip via stencil/mask | now feasible: text layout lives in `i-slint-core/textlayout/sharedparley` (shared-parley feature), which the project already patches, and swash rasterises glyphs; `GPU-UI.md §2`'s "text is the problem" is weaker since 1.14–1.16 | yes, you own the renderer | same `.slint` files | same | ~same | same | 3–5 weeks; only if TargetPixelBuffer hits a wall. The `Renderer` trait is sealed but vendoring removes that barrier at the price of tracking internals each release |
| **LVGL 9.5 (C, MIT)** | formal custom draw-unit API (`lv_draw_create_unit`, evaluate/dispatch per task: fill, border, shadow, letter/label, image, layer, line, arc, triangle, mask_rect, vector); an a3xx unit would be the same ~500 lines as `paint.c` but covers every task; shipped units are VG-Lite, NemaGFX, Dave2D, OpenGL ES/NanoVG (need GL, so not usable bare metal) | Tiny TTF (stb_truetype) / FreeType at run time; no size enumeration | rounded clip via mask tasks; NEON asm software fallback | **low**: imperative C widgets + `lv_anim`; the XML UI (9.3+) has components and subject bindings but no expression language, so each QML layout is a hand-written C state machine | MIT (permissive, Darrel's stated preference) | ~300–500 KB | C only, no Rust toolchain; no host preview comparable to slint-viewer without the simulator | credible then; migrating now = rewrite 3.9k lines of `.slint` + `watch.rs`, ~4–6 weeks, with fidelity loss |
| **Custom immediate-mode renderer on a3xx (C)** | total control: single shader fades/masks, SDF rounded rects (52-instr shader already measured, `GPU-UI.md §3`) | own: stb_truetype/fontdue glyphs into the existing atlas; own line-breaking/elide/alignment | trivial | lowest: every binding, animation, list model, flick, preview is hand code | any | smallest | fastest build, but every screen is C | `paint.c` is already ~60 % of such a backend; the missing 40 % (text layout, layout/animation/model framework) is 2–3 months to reach today's fidelity. Not worth it |
| **QML-subset interpreter/compiler** | would need its own renderer anyway (above) | own | own | highest in principle (copy QML verbatim) | — | large | — | a language runtime (JS expressions, binding graph, anchors, Flickable/ListView, ShaderEffect): months to a year. Slint *is* the pragmatic version of this (a QML-like compiled to Rust); not credible |
| **Slint FemtoVG/Skia/Vello** | need std + GL/Vulkan/WGPU; Vello needs compute | — | — | — | — | — | — | not bare-metal (`GPU-UI.md §4(b)`) |
| **egui/epaint** | epaint 0.37 rasterises via `vello_cpu`, no `std`/no_std feature; immediate mode redraws every frame | runtime | yes | low | MIT/Apache | — | — | not no_std, wrong power profile for a watch |
| **Qt for MCUs (Qt Quick Ultralite)** | GPU backends only for vendor 2D cores | — | — | real QML subset | commercial only | — | — | excluded by licence |
| **embedded-graphics / embedded-gui** | none | bitmap | no | none (primitives only) | MIT | tiny | — | too low-level |

### Recommendation (keep-but-change)

1. **Finish and upstream the run-time font work** (in flight: `365e00e`..`a25005f` + uncommitted
   `watch.rs`). It removes the 9.6 MB glyph payload, `SLINT_FONT_SIZES`, and the bold-as-Light
   compromise. Upstream PR 12367 is open and wanted; the no_std systemfonts patch is the kind
   of contribution Slint merges. Keep the vendored diff as a patch series over pristine 1.18.1
   so 1.19 is a rebase, not a re-port. Cost: days.
2. **Take Slint 1.19 when released** (`no_std` `Path` fix #13565/#13629, bitmap fonts registered
   once #14033, opaque-element skipping #12366 in 1.18, dithered gradients). Expect to drop the
   50-segment SVG ring hack. Cost: a day plus patch rebase.
3. **Rounded clip: patch the vendored software renderer**, not the UI. The maintainers'
   stated design (PR #9098 review: a rounded-clip command wrapping N following commands) is
   small, and a fork (`listary/slint` "software: clip children to rounded corners", merged
   2026-10-03) has a working implementation to study. With the GPU hook, the clip can arrive
   as an extra `PhysicalRegion`-plus-radius and map onto `paint_rounded`'s corner masks (or a
   stencil). Cost: ~1 week; removes the speed-dial strips and the `Preview.fits()` heuristic.
4. **Keep QML `ShaderEffect` emulation on the C/GPU side** (as `stack.c` already does for the
   app window, dims, indicators) rather than inside `.slint`. Add one generic hook: a
   per-screen post-pass (mask texture or fade band) in `stack_compose`. The speed-dial fade is
   one tinted quad there. Cost: 2–3 days.
5. **Do not pursue option (a) or LVGL now.** The remaining CPU cost (0.75 ms walk, ~1–2 ms
   `gpu_draw_end` spin, no async paint, `§10` "Not done") is better spent on async submission
   than on a renderer rewrite. Revisit (a) only if a required effect (per-item rotation,
   gradient-heavy screens, real opacity groups) cannot be composed in C.

Net: Slint delivered the AsteroidOS look in four days with a supported GPU path; its costs
(fonts, rounded clip, no_std Path) are all version-lag or patchable issues the project is already
fixing, and every alternative trades the declarative QML mapping, the project's main lever, for
a permissive licence or a cleaner GPU story that `paint.c` already mostly provides.

## Sources

- Slint changelog (1.10–1.19 unreleased): https://raw.githubusercontent.com/slint-ui/slint/master/CHANGELOG.md
- Slint 1.18 release post (2026-09-16, Vello experimental): https://slint.dev/blog/slint-1.18-released
- Slint renderers and software-renderer limitations: https://docs.slint.dev/latest/docs/slint/guide/backends-and-renderers/backends_and_renderers
- `TargetPixelBuffer` (experimental, 1.18.1): https://docs.rs/i-slint-renderer-software/latest/i_slint_renderer_software/trait.TargetPixelBuffer.html
- `Renderer` sealed, `RendererSealed` methods: https://docs.rs/i-slint-core/latest/src/i_slint_core/renderer.rs.html
- PR 12367 (fonts not bundled, open): https://github.com/slint-ui/slint/pull/12367
- PR 9098 (rounded clip, closed; issue #4176; fork listary/slint #3): https://github.com/slint-ui/slint/pull/9098
- Issue 5274 (software renderer does not clip rounded border): https://github.com/slint-ui/slint/issues/5274
- LVGL draw units: https://lvgl.io/docs/open/main-modules/draw/draw_units
- LVGL draw pipeline / custom unit API: https://lvgl.io/docs/open/9.5/main-modules/draw/draw_pipeline
- LVGL 9.5 changelog (2026-02-18): https://lvgl.io/docs/open/9.5/CHANGELOG
- LVGL XML runtime loading: https://lvgl.io/docs/open/9.5/xml/integration/xml.html
- epaint 0.37 features (vello_cpu, no std feature): https://docs.rs/crate/epaint/latest/features

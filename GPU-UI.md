# Rendering the Slint UI on the GPU (sturgeon, Adreno 305B)

Plan written 2026-10-29 from the state of `asteroid-embedded` main (c9f07f3)
plus the uncommitted m7 UI (screen stack, notifications, weather, music).
Stage 0 is prototyped on the `gpu-ui` branch (worktree
`../asteroid-embedded-gpu-ui`, uncommitted). Companion notes: EMBEDDED.md
(M4 GPU, M5 UI), IR3.md (shader toolchain).

## 1. Where we are

- Slint 1.18.1, software renderer (`MinimalSoftwareWindow`,
  `RepaintBufferType::ReusedBuffer`) paints into one persistent
  premultiplied RGBA layer at 0x0a000000 (WB-cached DRAM, 416-pixel rows);
  only the dirty region is repainted (`ui/src/watch.rs`).
- Our A3xx driver (`src/gpu/`) draws the FlatMesh (516 vertices, 1.1 ms)
  and blends the layer over it as one textured quad (shader d);
  mesh + full-screen quad = 3.0 ms GPU per frame, idle UI ~1 µs CPU.
- A full-layer software repaint costs ~6.4 ms CPU. The m7 UI slides its
  four screens inside one Slint window by animating `face.x/y`, which
  forces a full repaint every frame for 400 ms (`NewBuffer` in
  `ui_update`) and still leaves stale remnants when the partial
  repainter's dirty region (at most 3 rectangles, bounding boxes of
  moved items) misses something.

## 2. What Slint 1.18.1 exposes (checked in the crate sources)

Paths are under `~/.cargo/registry/src/index.crates.io-*/`.

- Public, stable: `slint::platform::{Platform, WindowAdapter}`,
  `software_renderer::{SoftwareRenderer, MinimalSoftwareWindow,
  TargetPixel, LineBufferProvider, PhysicalRegion, RepaintBufferType,
  RenderingRotation}` (`i-slint-renderer-software-1.18.1/lib.rs`,
  docs: https://docs.rs/slint/1.18.1/slint/platform/software_renderer/).
  `Platform::create_window_adapter` is called once per component
  instantiated, so several windows, each with its own `SoftwareRenderer`
  and partial-repaint state, are supported out of the box. That is what
  stage 0 uses.
- The `Renderer` trait is sealed (`i-slint-core-1.18.1/renderer.rs:42-52`:
  "you are not expected to implement this trait yourself"). A renderer of
  our own has to implement `RendererSealed` and
  `item_rendering::ItemRenderer` (`i-slint-core-1.18.1/item_rendering.rs:564`:
  draw_rectangle, draw_border_rectangle, draw_window_background,
  draw_image, draw_text, draw_text_input, draw_path, draw_box_shadow,
  visit_opacity/layer/clip, combine_clip, translate/rotate/scale,
  apply_opacity, save/restore_state, draw_cached_pixmap, ...) from
  `i-slint-core`, which crates.io describes as "Internal Slint Runtime
  Library" with no compatibility promise. `PartialRenderer`
  (`partial_renderer.rs`) is reusable for dirty tracking. Text is the
  problem: the embedded glyph bitmaps are registered into the software
  renderer's private `fonts` module (`lib.rs:20 mod fonts;`,
  `fonts.rs:234 register_bitmap_font`), its layout code is private, and
  `RenderText` only hands a renderer the string and style. A custom
  `ItemRenderer` has to bring its own text layout (wrap, elide, align)
  and glyph source.
- The intended hardware hook: `TargetPixelBuffer`
  (`target_pixel_buffer.rs:208-235`), the "DMA2D/PXP" path:
  `fill_background(brush, region)`, `draw_rectangle(DrawRectangleArgs,
  clip)` (rect, four radii, border width, background and border `Brush`,
  alpha, rotation) and `draw_texture(DrawTextureArgs, clip)` (`TextureData`
  in Rgb/Rgba/RgbaPremultiplied/AlphaMap, `colorize`, alpha, destination
  rect, rotation, tiling); each returns false to fall back to the CPU.
  Reached through `SoftwareRenderer::render_into_buffer`, behind the
  `experimental` feature of `i-slint-renderer-software` (`lib.rs:554`),
  which we can turn on by adding that crate as a direct dependency with
  the feature (cargo unifies features). What arrives there, in painter's
  order while the item tree is walked (`lib.rs:1905-1960`, `RenderToBuffer`):
  images (`lib.rs:2368`, `2430`), plain/rounded/border rectangles and the
  window background (`2680`, `2729`, `2961`, `3319`, `674`), and the
  pre-rasterised glyphs as `AlphaMap` textures with `colorize`
  (`2601`). Not routed: SDF glyphs (`2557`, CPU only; we embed bitmap
  glyphs, not SDF) and gradient fills declined by `draw_rectangle`. The
  software renderer's own limits apply to the scene it builds: opacity is
  an alpha multiply, no layers (`3104`), clip is rectangular with the
  radius a TODO (`3068`), rotate/scale TODO (`3094`), box shadow TODO
  (`3059`).
- `Window::set_rendering_rotation` exists but is not needed: the 180°
  panel orientation is handled by the MDP pipe flip.

## 3. A3xx facts that shape a UI renderer

- Textures: linear only for anything the CPU writes (32-byte base,
  128-byte pitch, `TEX_CONST_1 PITCHALIGN`); `TILE_4X4` exists for GPU-
  owned textures (`fd3_resource.c:101`) but buys nothing here. Formats
  (`fd3_format.c`): `8_UNORM` (A8/R8 alpha maps with a swizzle),
  `8_8_UNORM`, `8_8_8_8_UNORM` with WZYX/WXYZ/XYZW swaps, 5_6_5.
  Sampler: nearest/linear/aniso, clamp/repeat/mirror. Render targets:
  `RB_R8G8B8A8_UNORM` (what we use, alpha ignored by the MDP), 5_6_5, A8.
- Blending: full factor/opcode set per MRT (`fd3_blend.c`); we have
  premultiplied source-over. Clipping: `GRAS_SC_WINDOW_SCISSOR` per draw
  gives rectangular clips for free; rounded clips need a shader mask or
  stencil (no stencil buffer set up yet).
- Shaders: no hand-written IR3 needed. `tools/ir3c` (IR3.md) compiles
  GLSL ES on pc; measured today: textured quad × uniform tint = 10
  instructions (shader e, now in `shaders.h`); a rounded rectangle with
  border and 1-px anti-aliasing as a signed-distance fragment shader =
  52 instructions, instrlen 9, 4 vec4 constants (fits the 128-unit
  instruction buffer with room). The error-prone part is transcribing the
  compiler's metadata (regids, inloc, constlen, pixlod) into
  `struct gpu_shader`; past five shaders a generator from `ir3c -C` output
  is worth writing.
- Draw cost: every state change after a draw inserts `CP_WAIT_FOR_IDLE`
  (`draw.c sync_state`), so a UI of N items costs N drains unless draws
  are batched per (program, texture, blend). Not measured yet; stage 1
  measures it.
- Memory and coherency (`src/soc/mmu.c`): the GPU reads physical DDR
  without an IOMMU. Layers and heap are WB-cached, so CPU-written texels
  are cleaned (`dcache_clean_range`) before `gpu_draw_end` submits
  (per-row cleans of the dirty box today), GPU-written targets are
  invalidated before the CPU reads them, and `gpu_draw_begin` invalidates
  the UCHE once per frame. GPU-only data (shaders, vertex quads) lives in
  the uncached window at 0x1e000000 (15 MB). A glyph atlas would be
  write-once per glyph (clean the touched rows once). Layer addresses:
  0x0a000000 + n × 1 MiB, below m7's screenshot buffer at 0x0b000000.

## 4. Options

(a) Full Slint item renderer on the A3xx driver (`ItemRenderer` +
`RendererSealed` against pinned `i-slint-core`). Everything on the GPU:
rectangles as quads with the SDF shader, images as textures, text from a
glyph atlas, scissor clips, alpha-multiplied opacity like the software
renderer. Effort: large (weeks): a Rust→C draw-command interface, the
shaders, image embedding of our own, and above all a text layout engine
plus glyph source, because Slint's are private. Risk: high: internal API
that moves between releases (pin 1.18.1, re-port on upgrades), parity bugs
in text. Payoff: no pixel work on the CPU at all.

(b) femtovg (or any GL vector renderer) over a GLES shim: femtovg and
`i-slint-renderer-femtovg` need `std`, a `glow` GL context and runtime GLSL
compilation; a GLES2 implementation on our command stream is a driver
project of freedreno's size. Not practical bare metal. Skia likewise.

(b') The supported accelerator path: implement `TargetPixelBuffer` and
route it to the GPU. Rectangles (plain, rounded, bordered) → SDF shader;
images → RGBA textures keyed by data pointer; glyphs → one R8 atlas built
lazily from the `AlphaMap` textures Slint hands us (keyed by their static
data pointer), drawn tinted with `colorize`; clip = scissor on the dirty
region ∩ item clip (≤ 3 rectangles). The GPU draws into the layer (it must
stay CPU-readable for the fallback and the partial repainter) and the
compositor of stage 0 puts the layer on screen. Ordering trap: any item
the hook declines is drawn by the CPU into the same buffer in painter's
order, so before the first CPU fallback of a frame the pending GPU work
has to be submitted, waited for and the layer rows invalidated; accept
everything we actually use (gradients are the only likely decline) and
that path stays rare. Effort: medium (2–3 weeks): Rust command list,
C atlas + rect shader + batching of consecutive same-texture draws into
one triangle list. Risk: medium: `experimental` feature (the trait has
been reworked since it appeared and may change again), unknown draw-call
overhead. Payoff: CPU per repaint drops from pixel work to a scene walk;
text stays pixel-identical to today (same glyph bitmaps).

(c) Hybrid, pixels on the CPU, composition on the GPU: one Slint window
and layer per screen (watchface, notifications, weather, music); the GPU
places the layers, slides and darkens them, fades popups. A screen's
content never moves inside its layer, so Slint's partial repaint stays
small during slides (no `NewBuffer` forcing) and the remnants after slides
cannot occur. Effort: small (done, ~400 lines). Risk: low: public API
only. Payoff: slides and dims cost nothing on the CPU; the per-item
repaint cost of the software renderer remains for content that animates
inside a screen (the clock, a flickable).

(d) Order of attack: (c) now, (b') next, (a) only if (b') hits a wall
(rounded clips, rotations, gradients). (b') is what Slint built the hook
for; (a) consumes internals that Slint does not promise to keep.

## 5. Recommendation and stages

Every stage ships on its own and is checked on the watch with the frame
logs (`tick … fps`, `gpu: N frames, X us submit to idle, Y us vertices`,
`ui: N of M frames repainted, update X us avg, Y us per repaint`) and
`shot` / `shot layer` screenshots (m7 console).

Stage 0 — screen layers composed on the GPU (prototyped, see §6).
Watch for: 59 fps while idle and during slides; `ui:` repaints during a
slide stay at the watchface's own rate (seconds, animations) instead of
every frame; `gpu:` per-frame time with two layers + dim during a slide
(expect ~3.5–4 ms, down to ~3 ms at rest); no remnants after any slide;
tap on the clock still toggles seconds; a drag past 40 px cancels the
Slint press.

Stage 1 — measure and tune the draw path. Count draws per frame and the
cost of each `CP_WAIT_FOR_IDLE`; drop the WFI between draws that only
change the texture/constants if the GPU tolerates it (check freedreno's
fd3 state emission: it does not WFI between draws). Give the mesh the
parallax m7 does on the CPU (`flatmesh_view` from `stack_offset`). Use
`gpu_draw_layer_at(..., alpha)` to fade the notification popup and pairing
code in and out by making them their own `Screen` kinds. Exit: numbers in
EMBEDDED.md, no visible change.

Stage 2 — `TargetPixelBuffer` on the GPU (b'). 2a: enable the
`experimental` feature, implement the three hooks for solid/rounded
rectangles and alpha-map glyphs with a fixed 1024×1024 R8 atlas and the
SDF shader, GPU rendering into the layer, with the flush-before-CPU-
fallback rule. Test: `shot layer` of each screen matches the software
path pixel for pixel except at anti-aliased rounded edges; `ui: … us per
repaint` for a full repaint drops from ~6400 µs to well under 1000 µs.
2b: image textures (icons, weather), batching, gradient brushes in the
rectangle shader, atlas eviction. Test: notification list scroll stays at
59 fps with ~1 ms CPU.

Stage 3 (optional) — render straight into the back buffer: with
everything on the GPU the layer and the partial repainter are overhead;
`fill_background` becomes the FlatMesh draw and each frame is a full GPU
redraw. Only if stage 2's GPU time leaves room (mesh 1.1 ms + UI < 8 ms).

Stage 4 (only if needed) — option (a).

## 6. Stage 0 prototype (branch gpu-ui, uncommitted)

Files: `ui/ui/watchface.slint` (new `Screen` root with `kind`, the only
exported window), `ui/ui/face.slint` (`Face` global + `Watchface`
component, moved from the old root), `ui/ui/panel.slint` (`SidePanel`
placeholder), `ui/src/watch.rs` (one `MinimalSoftwareWindow` and layer per
`Screen`, `ui_tick` + `ui_update(panel)`, `ui_touch(panel, …)`,
`ui_modal`), `src/ui/ui.h` (`UI_PANELS`, `UI_LAYER_STRIDE`),
`src/ui/stack.{c,h}` (gestures, slide animation, composition),
`src/gpu/draw.{c,h}` (`gpu_draw_layer_at` with offset and fade,
`gpu_draw_fill`, a ring of 16 quads per frame), `src/gpu/shaders.h`
(shader e: tinted texture, compiled with ir3c), `src/main.c` (wiring),
`Makefile`, `tests/stubs.c` (host stubs main's console already needed).

Design points:
- One exported root. Slint embeds the default font once per exported
  `Window` component (`i-slint-compiler/passes/embed_glyphs.rs:177`): a
  second root doubled the image by 570 KB. `Screen { kind }` with
  `if root.kind == N:` branches keeps one copy; the watchface state moved
  into the `Face` global, set on the kind-0 instance from Rust.
- Geometry as in m7: watchface origin (fx, fy) is the whole state; rest
  positions (0,0), (W,0) notifications, (-W,0) weather, (0,-H) music; the
  side screens sit one screen away. Gesture rules copied from m7's
  `watch.rs` (40 px threshold, 300 ms flick, 30 % release, vertical drags
  on the notification screen go to Slint, press cancelled with an UP at
  -10000). Slide: 250 ms ease-out cubic in `stack_update`.
- Composition per frame (`stack_compose`, inside the mesh's
  `gpu_draw_begin/end`): black fill with alpha
  `max(|fx|/W, |fy|/H) × 0.4`, then only the layers that intersect the
  screen. Shader d for opaque layers, shader e (tint) when alpha < 1.
- Memory: layers at 0x0a000000 + kind × 1 MiB (665,600 bytes used each),
  cleaned per dirty row as before.
- Image: 1,284,236 bytes of text (+24 KB over main: the 22 px glyph set,
  `Screen`, the stack).

How to test on the watch (main session):
1. `make run` on the gpu-ui worktree (or merge into m7 first, see below).
   Boot log should show `ui: ready`; nothing else changes at boot.
2. Idle: `tick … 59 fps`, `gpu: … ~3000 us submit to idle`,
   `ui: 1 of 59 frames repainted` (seconds hidden) — same as before.
3. Swipe right/left/up from the watchface: the placeholder screen
   ("Notifications" / "Weather" / "Music" with a hint line) slides in
   over 250 ms with the background darkening to 40 %; the opposite swipe
   returns. Drag slowly and let go before 30 %: it snaps back. During a
   slide `ui:` repaints must not jump to every frame and `gpu:` should
   rise by well under 1 ms. Flick (< 300 ms) past 40 px switches too.
4. Vertical drag on the notifications placeholder: nothing happens
   (routed to Slint as a scroll); on the watchface a drag up opens music.
5. After a slide, `shot` (front buffer) must show no remnants; `shot
   layer` dumps layer 0 (the watchface) — extend `screenshot_to_file` to
   take a layer index (`UI_LAYER_BASE + n * UI_LAYER_STRIDE`) to check the
   others.
6. Tap the clock: seconds toggle (press reaches Slint); a notification
   or pairing code on screen blocks swipes and gets every touch.
7. Sleep/wake: `stack_home()` on sleep puts the watchface back.

Merging into m7: split m7's four `Rectangle` screens out of the single
window into `if root.kind == N:` branches of `Screen` (the notification
`Flickable`, weather and music become plain components like `SidePanel`);
move `drag/release/swipe/home/scrolls-vertically` out of the .slint and
`watch.rs` (they are now `stack.c`); keep the `Face`-global pattern for
the state m7 sets (notes model, media, weather belong to their screens'
instances, so `ui_add_notification` etc. act on panel 1's `Screen`);
`ui_scroll` becomes `stack_offset`; `ui_home` becomes `stack_home`; the
`full_until` NewBuffer workaround goes away; `shot layer` gains the index.

## 7. Licensing

- Our code: GPL-3.0-or-later. Slint: GPL-3.0-only (or commercial);
  compatible with our licence as used.
- Mesa (ir3 compiler, freedreno register and format tables): MIT. Using
  the compiler as a build tool puts no terms on its output; constants and
  sequences transcribed from `fd3_*.c` / `a3xx.xml` carry the MIT notice
  if copied as files (we transcribe register values, as draw.c already
  does).
- Linux kernel `drivers/gpu/drm/msm` and the Android/Qualcomm KGSL driver:
  GPL-2.0-only, incompatible with GPL-3; never copy. The A3xx bring-up in
  `a3xx.c` is reimplemented from reading; any new GPU code (stencil,
  tiling, perf counters) must be too.
- Fonts: Noto Sans under OFL 1.1 (`ui/fonts/OFL.txt`); the embedded glyph
  bitmaps are OFL derivatives, fine with the notice kept. Ionicons (m7):
  MIT.
- Rust crates that stage 2 may add (atlas packing: `etagere` or
  `guillotiere`, both MIT/Apache-2.0; `embedded-alloc`, `critical-section`
  already in use, MIT/Apache-2.0): fine. Avoid anything GPL-2.0-only or
  non-commercial.
- GPU microcode `a330_pm4/pfp.fw`: Qualcomm licence, loaded from the
  ramdisk, not linked (unchanged).

## 8. Stage 0 merged 2026-10-30 (main ed09267, 3a74afc, db0f242)

M7 screens ported onto the stage 0 layers: kinds 0 watchface, 1
notifications, 2 weather, 3 music, 4 overlay (notification popup and
pairing code, composed on top while `ui_modal`). Every Screen gets the
same state through its Face global; models are shared. A swipe on the
popup closes it, a tap dismisses it. `make preview` uses
`ui/ui/preview.slint`, which binds its properties to Face.

Measured on the watch (unattended, `touch` + `shot`): idle 60 fps, GPU
3.1 ms; on a side screen or during a slide GPU 4.9 ms; during a 4 s drag
`ui: 1 of 60 frames repainted` (the seconds), was every frame. Image
+30 KB.

Edge garbage in screenshots after slides (x 0-25 / 385-400 in text rows)
is in the square's corners outside the round panel, which the FlatMesh
does not cover and nothing clears; the pre-port single-layer build shows
the same. Invisible on the watch; a black clear of the corners would
fix screenshots.

## 9. Stage 1 done 2026-10-30 (main ff7591e, 7cd8947, 1f4d425, b44f612)

What a frame costs (temporary knobs, weather screen at rest, before the
changes): mesh ~1.0 ms (incl. the D-cache invalidates), each full-screen
blended quad ~1.8-2.1 ms (a layer or the 0.4 darkening fill). Removing
the `CP_WAIT_FOR_IDLE` between draws changed nothing (< 10 µs), so the
WFIs stay.

GPU vs bus: votes changed live over RPM (`clk2` id 0 BIMC, id 1 gfx3d,
`clk1` id 1 SNOC). GPU 200 MHz: 4.9 ms whatever BIMC (200 or 400 MHz);
GPU 320 MHz: 4.2 ms; GPU 450 MHz: 3.1 ms with BIMC 200 or 533 MHz, SNOC
100 or 200 MHz. So it is GPU-clock bound in GMEM bypass, ~2 GPU clocks
per blended pixel, not bandwidth bound. Vendor levels (kgsl node):
450/320/200/19.2 MHz with bus cases 3/2/1/0 (GPU→EBI ib 4.26/3.2/1.6
GB/s), initial level 200 MHz. We stay at 200 MHz, BIMC 200 MHz.

Changes:
- darkening folded into the mesh vertex colours (`flatmesh_view(...,
  shade)`, `stack_dim`), no fill pass;
- per layer, 25 bands of 16 rows each keep the column extent of their
  content (`stack_damage` scans what `ui_update` repainted; a repaint
  covering the whole band replaces the extent, a partial one widens
  it); the layer is drawn as one draw of the non-empty bands
  (`gpu_draw_layer_parts`, quad ring now 128);
- overlay fades in/out over 150 ms; while fading out its `ui_update` is
  skipped (`stack_overlay_frozen`) so the layer keeps the last picture.

GPU time per frame now: watchface 1.43 ms (was 3.1), weather 1.5 (was
4.9), music 1.4 (4.9), notifications list with 5 entries 2.15 (4.9),
popup up 3.6 (opaque black full-screen overlay over the face).
Screenshots of every screen and mid-slide match the previous build.

Charging: the battery icon animates while charging, `ui: 59 of 59
frames repainted` (panel 0, 22x8 at 159,338, ~165 µs). Not a regression;
looked like one when comparing a charging and a full run.

Seen once, not reproduced: an injected swipe after tap-dismiss was
logged as `swipe right (200,200 -> 340,200 in 33107 ms)`, i.e. the
touch driver still had the earlier tap's finger down. Three repeats of
notify / tap / swipe were fine.

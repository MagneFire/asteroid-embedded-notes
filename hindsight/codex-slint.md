**Keep—but change the rendering integration.** Slint was a defensible choice for rapid UI development; software rendering was a temporary compromise with the GPU requirement. The mistake was leaving fonts and renderer extensibility insufficiently validated before expanding the UI.

Your context understates today’s GPU support: `d36168e` already sends rectangles, images and glyphs through `TargetPixelBuffer` to a3xx. Recorded notification scrolling improved from 5–6.7 ms to 2.8–3.0 ms per repaint at 60 fps. Unsupported operations and GPU-off AOD retain software rendering. See [render integration](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/ui/src/watch.rs:559) and [measurements](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/GPU-UI.md:357).

Slint bought substantial productivity: bindings, reusable components, animation, text layout, input handling, partial repaint and [desktop preview](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/Makefile:117). Between `4ad450c` and `0a1e6fe`, four days produced the watchface, apps and seven launchers. That supports its selection. However, QML resemblance provides **translation convenience, not compatibility**: flick physics, gestures and effects still required reconstruction.

The costs are concrete:

- Font expansion dominates image growth: existing ELF symbols contain approximately **7.93 MB of glyph data** within 11.20 MB of text/read-only data. [Manual size enumeration](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/ui/build.rs:54) couples layout changes to asset generation.
- Renderer limitations distort UI structure: speed-dial fading duplicates the wheel across [clipped strips](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/ui/ui/launcher.slint:555); circular previews omit items. Rounded rectangles do **not** provide rounded child clipping.
- Five patched crates (`365e00e`, `9b3c992`, `a25005f`) and experimental acceleration create maintenance obligations. GPL fits this project, but misses your permissive-dependency preference.

These alternatives were credible initially; today each must justify replacing working screens. Efforts below are my estimates for one experienced developer, including parity work.

| Option | GPU, fonts, fidelity, footprint and iteration |
|---|---|
| **Existing Slint accelerator** | Lowest disruption; preserves declarative iteration. Finish runtime fonts; extend clipping/effects. Approximately **2–4 weeks** initially, with measured acceptance gates. |
| **Full Slint GPU renderer** | Preserves screens; enables proper masks, transforms and shaders. Reuse text infrastructure, but [renderer traits are internal/sealed](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/slint/i-slint-core/renderer.rs:41). Similar frontend footprint; **4–8+ weeks**, ongoing upgrade work. |
| **LVGL** | Stronger initial permissive/C fit; likely smaller configured runtime. [MIT](https://github.com/lvgl/lvgl), extensible [draw units](https://lvgl.io/docs/open/main-modules/draw/draw_units), runtime [TrueType](https://lvgl.io/docs/open/9.3/details/libs/tiny_ttf). Still needs a3xx rendering, accelerated masks/effects and every QML screen rewritten. Faster C builds; **6–10 weeks**. |
| **Custom retained/immediate UI** | Maximum GPU/shader control; potentially smallest runtime. Own text shaping, atlas, layout and interactions; slower screen authoring. Permissive building blocks such as [Nuklear](https://github.com/Immediate-Mode-UI/Nuklear) help. **8–12+ weeks**. |
| **QML-subset compiler/interpreter** | Potential source reuse; compact compiled output, bespoke GPU/fonts/effects. Bindings, JavaScript, models and Qt semantics become your responsibility. **Several months**. |
| **Qt Quick Ultralite** | Compiled [QML subset](https://doc.qt.io/QtForMCUs/qtul-qtquick-differences.html), static/runtime fonts; custom GPU port and effect gaps remain. [Commercial-only](https://doc.qt.io/QtForMCUs/qtul-licensing.html). Poor preference fit. |

Finish runtime fonts first—but fix [address-based atlas identity](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/gpu/paint.h:10) before enabling evictable glyph buffers. Then carry round-clip/mask information through the scene builder; the accelerator cannot recover discarded radii. Validate cold/warm text, screenshots, repaint time and image size. Escalate to a full Slint renderer only if that extension becomes sprawling.
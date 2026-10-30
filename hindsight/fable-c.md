# Hindsight C: was C the right language for the firmware?

Verdict: **stay, with two changes** (below). Not migrate, not even incrementally for new drivers.

## 1. What the history actually shows

Repo: `~/Downloads/AsteroidOS/asteroid-embedded`, 136 commits, 2026-10-25..30. ~17.2k lines of C/asm
under `src/` (soc 3.7k, bt 1.9k, gpu 1.8k, usb 1.8k, storage 1.7k, main 847) plus TinyUSB 0.21.0,
NimBLE 1.10.0, mbedtls 3.6.7 compiled in; ~940 lines of Rust in `ui/src/` and 2.7k lines of `.slint`.

Every "Fix" commit, classified by what would have prevented it:

| commit | bug | class | would Rust/C++/Zig have caught it? |
|---|---|---|---|
| 9595e4e | IRQ entry left SP 4-byte aligned; first handler using a doubleword store took an alignment fault | hand-written asm, AAPCS | No language catches asm. `aarch32-rt` 0.5 (rust-embedded) ships vetted trampolines with an `fpu_context` macro that keeps AAPCS alignment, so a Rust project *reusing it* would not have hit this; a Rust project writing its own `start.S` would. |
| 9217a14 | lk2nd leaves SPIs edge-triggered, peripherals are level; interrupts got stuck (also BLUETOOTH.md §11 bug 2) | hardware config | No. |
| be64200 | `tlmm_irq_config` appended a second handler instead of replacing; restart of BT exhausted 4 slots | logic in a fixed table | No (a `BTreeMap` would, but so would a C lookup). |
| c9f07f3, 6687d4c | watchdog bites: fbcon redraws per log line / `log` walked uncached memory > 3 s | design (superloop feeds WDT) | No. |
| e7bf745, 224672e, adb84c5 | charger not enabled; battery % wrong until the vendor BMS method was reproduced | missing vendor knowledge | No. |
| efae487 | 1 s timer tick while asleep cost 14 mA | power design | No. |
| e2d6e7f, 4b1f159, 0d66e56, 72817b9 | UI/notification logic | logic | No. |
| 1c9640c, 9ec72d3 | red/blue swapped: painter wrote XRGB (display order), Slint/compose expect R first | **type erosion at the C<->Rust seam** (colours cross as `u32`) | Yes-ish: a `Rgb`/`Xrgb` newtype on both sides. This is the one seam bug. |
| M0 (notes) | timer PPI 30 vs 19, SCM wdog-debug call missing | hardware facts | No. |
| M3 (notes) | TinyUSB `ci_hs_regs_t` base off by 0x100 | struct layout vs datasheet | No. |
| BLUETOOTH.md §11 | UART TX_READY sequencing, RPA resolution missing in NimBLE 1.10, reset storm | hardware sequencing / protocol | No. |
| EMBEDDED.md "Random boot hangs after linking Slint" | Rust `compiler_builtins` weak `__aeabi_uldivmod` won the link, ~2000x slower than libgcc's, `time_us()` 300 us, watchdog | **toolchain cost of mixing Rust and C** (link order) | Caused by Rust, not C. Known issue: Rust-for-Linux ARMv7 had the same fight (`rust: add compiler_builtins`, LKML 2025). |
| BOOTSLOW.md | 1000x memory crawl after warm reset, heisenbug, likely secure-world/RPM | SoC | No. |

Memory-safety bugs recorded in five days: **zero**. No overflow, use-after-free, null, data-race fix
exists in `git log` or in any notes file (grep of EMBEDDED/BLUETOOTH/SUSPEND/POWER/STORAGE/SENSORS/
GPU-UI/BOOTSLOW for overflow|race|uninit|corrupt|leak finds only hardware topics). The externally
reachable parsers are bounded by hand and I checked them: ADB sync path `len >= ADB_NAME_MAX` fails
before `SY_PATH` (`src/usb/adb.c:275`), `ADB_FILE_MAX` checked before the file memcpy (`adb.c:340`),
oversize payloads skipped via `rx_skip` (`adb.c:582`), HCI events sized against
`BLE_TRANSPORT_EVT_SIZE` (`src/bt/transport.c:22`). The two parsers with host tests (`tests/adb_test.c`
397 lines, `console_test.c`) are exactly the ones that take untrusted bytes.

Concurrency is where C's lack of enforcement would normally bite, and the code keeps it tiny: one
IRQ dispatch (`src/soc/gic.c:101`), IRQ-to-main handoff via a 16-entry ring with `volatile`
head/tail (`src/input/touch.c:80-93`), and exactly three `irq_disable()` critical sections
(`touch.c:244`, `soc/i2c_qup.c:262`, `gpu/draw.c:670`). NimBLE runs entirely in main context with
counting mutexes (`src/bt/npl.c` header). A Rust rewrite would spend `unsafe`/`critical_section`
on the same three places; the design, not the language, is what keeps this safe.

## 2. What C bought

- **Vendor-method reproduction is a copy, not a translation.** Darrel's standing rule is "reproduce
  the vendor kernel's method" (memory: feedback-prefer-proven-methods). Every driver in `src/soc`,
  `src/display`, `src/storage`, `src/bt/hci.c` is a register-sequence port from lk/lk2nd, the
  3.10 Android kernel or mainline (EMBEDDED.md "Reference trees"). In C the port is diffable
  against the source line by line (e2d6e7f, e7bf745 cite the vendor driver's workarounds). In Rust
  every sequence is re-expressed, and review becomes "does this translation match" instead of
  "does this copy match".
- **Three C stacks link in as-is.** TinyUSB (DCD port is a copied `.c` with an MSM header,
  `src/usb/dcd_ci_hs_msm.c`), NimBLE (a 150-line NPL shim, `src/bt/npl.c`), mbedtls (12 files,
  Makefile `MBEDTLS_SRCS`). The Rust alternatives are thinner: `embassy-usb` has no ChipIdea
  driver (closest: `imxrt-usbd`, a `usb-device` bus for NXP's ChipIdea-derived core, and `musb`);
  `trouble-host` 0.7 lists peripheral/central/GATT/L2CAP CoC but its README lists no security
  manager, pairing, bonding or bond storage, and the AsteroidOS profile needs LE legacy passkey
  pairing + LTK bonding (BLUETOOTH.md §11.3, §12); NimBLE already needed a host-side RPA fix
  (`transport.c:28`). Rust-everywhere would mean binding NimBLE/TinyUSB through bindgen and still
  writing the NPL/DCD glue in C-shaped Rust.
- **Toolchain and debug loop.** `arm-none-eabi-gcc -Os`, `-ffunction-sections`, link in seconds;
  fault records symbolize with `addr2line` (`tools/run.py`); `make TEST=hang|abort` proves the
  path (EMBEDDED.md M0). `-lgcc` had to be linked *before* the Rust lib because of the uldivmod
  trap above; the Rust side needed its own panic -> `ui_panic` -> fault-record bridge
  (`ui/src/lib.rs:56`, `src/ui/ui.c:7`) and a `critical_section` impl (`lib.rs:21`).
- **GPU command streams have no ecosystem in any language.** `src/gpu/draw.c` builds PM4 packets
  (`a3xx_ring.h`) from freedreno's fd3 code, with shader metadata transcribed from `tools/ir3c`.
  Rust offers nothing here; freedreno is the reference and it is C.
- **Zig** would have the same C interop and simpler build but is pre-1.0 (0.16, April 2026,
  removed `std.io`; every minor breaks), one more toolchain on pc, and no vetted Cortex-A runtime.
  **C++** buys RAII/`constexpr` and nothing against the bug classes above; `-fno-exceptions`
  freestanding C++ on this code would be C with classes.

## 3. What C cost

- The **FFI seam is the ugliest code in the project**: `ui/src/watch.rs` has 76 `unsafe`, a
  `Static<UnsafeCell>` singleton, strings as `(ptr, len)` pairs, events returned one at a time
  through nine parallel `pop()` queues (`ui_app_opened`, `ui_setting_toggled`, ...), and alarm
  edits bit-packed into an `i32` (`watch.rs:153`, documented in `src/ui/ui.h:28-33`). Colours
  cross as `u32` and that produced the one seam bug (1c9640c/9ec72d3). The C side of the seam is
  `src/ui/stack.c` + 43 `ui_*` prototypes in `ui.h`. This is a cost of *having two languages*,
  not of C; Rust-everywhere removes it, Rust-for-drivers-only would double it.
- The seam's build is the slow part of the loop: Slint crate with `lto = true`,
  `codegen-units = 1` (`ui/Cargo.toml`), five vendored and patched Slint crates
  (a25005f: 154 insertions to drop std). The C half rebuilds in seconds.
- No compile-time help with integer widths and wrap: `time_ms()` subtraction idiom
  (`main.c:379` `now - bt_start_t < 0x80000000u`), `(uint32_t)` casts in packing code. Rust's
  `wrapping_sub` would make the intent explicit; nothing was broken by it.
- Table-driven state with manual slot management (`handlers[MAX_IRQ]`, `pin_irqs[4]`,
  `streams[4]`): one real bug (be64200).

## 4. What Rust-everywhere would look like here (2026)

- Target `armv7a-none-eabihf` is **Tier 2 since Rust 1.92** (rollup #147574 merged 2025-10-11), so
  prebuilt core/alloc, no `-Zbuild-std`. `aarch32-rt` 0.5 (rust-embedded, ex Ferrous `cortex-ar`)
  gives vectors, per-mode stacks, exception trampolines with FPU context, SMP park hook; no MMU,
  no cache ops, no GIC. GICv2: `arm-gic` 0.8 (trustedfirmware) or `arm-gic-driver` 0.16 exist.
  Everything else (SPMI, RPM/SMD, QUP, MDP5/DSI, SDHCI, UARTDM, SAW/SPM, A3xx) would be
  hand-written from the same C references, with `unsafe` register access either raw or through a
  home-made `svd2rust`-style layer (no SVD exists for APQ8026).
- Async/embassy: `embassy-executor` has no Cortex-A arch; a `raw`/`spin` executor on WFI works but
  is new ground, and the superloop already does the job in 850 lines.
- USB: write a ChipIdea `usb-device` or `embassy-usb-driver` backend (model: `imxrt-usbd`), then
  re-implement the ADB services (today ~1.2k lines C with host tests).
- BLE: `trouble-host` + `bt-hci` over our UART (fits the H4 model) but would need SMP/bonding
  that its README does not claim; or keep NimBLE via bindgen with the NPL shim still in C.
- Cost estimate: 17k lines of driver C reproduced from vendor code = several weeks of the same
  bring-up the notes record (M0-M8 took five days *with* the references copyable), plus
  re-validating every sequence on the watch (sleep/SPM in SUSPEND.md took the most time and is
  the least language-sensitive). Benefit: removes the seam and the uldivmod-class link traps,
  gains bounds checks on parsers that are already tested. Net negative.
- Incremental "new subsystems in Rust" is the worst of both: a second seam per subsystem, two
  build systems per driver, and the vendor-copy workflow lost exactly where it matters most
  (new drivers).

## 5. Verdict: stay, but change two things

1. **Thicken the seam's types, not its language.** Replace `u32` colours and bit-packed events with
   `#[repr(C)]` structs shared via a generated header (cbindgen) or a hand-kept `ui_abi.h`:
   `struct ui_rgb`, `struct ui_alarm_edit`, one `struct ui_event { kind; payload }` queue instead
   of nine. This removes the only bug class the history pins on the seam and most of the 76
   `unsafe`.
2. **Keep hardening C where bytes come from outside.** The adb/console host tests are the right
   pattern; add the same for `src/bt/gatt.c` payload parsing (`payload[1024]`, `text[97]`) and
   `storage/kv.c`/`ext4.c` (eMMC-sourced structures), and build the host tests with
   `-fsanitize=address,undefined`. That buys the bounds checking Rust would give, on the
   three parsers that matter, for a day of work.

Everything else the history blames on hardware, missing vendor knowledge, or design; no language
fixes those, and C is the language the references are written in.

Sources: [Rust PR #147574 (Tier 2 rollup)](https://github.com/rust-lang/rust/pull/147574),
[aarch32-rt docs](https://docs.rs/aarch32-rt/latest/aarch32_rt/),
[rust-embedded/cortex-ar](https://github.com/rust-embedded/cortex-ar),
[trouble-host 0.7.0 README](https://docs.rs/crate/trouble-host/0.7.0/source/README.md),
[embassy-rs/trouble](https://github.com/embassy-rs/trouble),
[embassy-usb README](https://docs.rs/crate/embassy-usb/latest/source/README.md),
[imxrt-usbd](https://docs.rs/imxrt-usbd/latest/imxrt_usbd/index.html),
[arm-gic](https://docs.rs/crate/arm-gic/latest/source/README.md),
[arm-gic-driver](https://docs.rs/crate/arm-gic-driver/latest/source/README.md),
[Rust-for-Linux ARMv7 uldivmod thread](https://lkml.iu.edu/hypermail/linux/kernel/2501.3/07551.html),
[weak compiler_builtins symbols](https://users.rust-lang.org/t/weak-symbols-in-compiler-builtins/126016),
[Zig 0.16 migration notes](https://www.claudepluginhub.com/skills/vinnie357-all-skills/zig).

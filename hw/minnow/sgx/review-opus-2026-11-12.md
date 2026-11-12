# Review: SGX530 driver and GPU compositor (Opus, 2026-11-12)

Range `2ccbde4..81208e5` on main, read-only. No watch touched; no DDK user-space source read.
References: the vendor kernel driver (`minnow-kernel/drivers/gpu/pvr`, sgxinit/sgxreset/sgxpower/
sgxutils/sgxkick.c, system/omap3630), the notes (init-facts, ta-path, native-scene) and the plan.
"Unverified" = needs the hardware or the vendor's user space to settle.

## Blockers for the watch session

### B1. Unfed 1 s register waits in the boot-time start can reset the watch before the console is up
`src/gpu/sgx.c:90-97` (`wait_reg`), used by `invalidate_directory_cache` (`:192`), which `reset()`
calls once per fault in the first-reset loop (`:212-226`, up to 64 times) and once more at `:233`;
also `sgx_stop` (`:370`).

`wait_reg` does not feed the watchdog (bark 3 s, bite 4 s, `main.c:51`); `wait_word` does. On the
first `sgx_start` after boot the fault loop can call `invalidate_directory_cache` up to 65 times, each
allowed 1 s unfed. `gpu_init` now starts the GPU at boot (`sgx_compose.c:403-411`, from `main.c:74`),
before the console and USB are up.

Failure scenario: what a previous OS leaves behind keeps `BIF_MEM_REQ_STAT` reads from draining, or
faults keep coming back. Each pass waits 1 s and logs; after about 3 s the watchdog barks and resets
the watch during `gpu_init`. With a flashed image that happens on every boot. With `fastboot boot` the
watch falls back to the installed OS and the log of what went wrong is lost. This path ran once on
the watch, so the odds are low, but the cost is a watch you cannot reach and the fix is two lines.

Fix: `wdt_feed()` in `wait_reg`'s loop, as `wait_word` has; cap the total time of the fault loop
(e.g. stop after 200 ms in all and fail the start). For this first session, consider making the
boot-time start opt-in (`by_hand = true` at boot until `sgx ui on`). The checklist starts with `sgx`
anyway, and a boot that never touches the GPU keeps the console reachable whatever the GPU does.

### B2. A failed start is retried on every wake: ≥1 s per wake and a log flood
`src/gpu/sgx.c:330` (`built` stays false after a failed `build`), `:348-353` (an init timeout neither
latches nor marks anything), `src/gpu/sgx_compose.c:97, 403-409`, `src/frame.c:162-168`.

`failed` is set only when a GPU *frame* fails. If the microkernel does not come up (INIT_COMPLETE not
seen in 1 s), `gpu_init` tries again on the next wake: another 1 s, then `sgx_log_state`, which
prints 22 registers, 19 host words, the queue line and up to 512 trace lines. If `libsrv_init.so` is
missing or another build, every wake reads up to 107 KiB from eMMC (a path lookup per 4 KiB chunk)
and runs the bitwise CRC. If `sgx_draw_setup` fails (scene allocation not at the recorded address),
every wake powers the GPU up, starts the microkernel and stops it again (`start()` calls `sgx_start`
before `sgx_draw_setup`).

Failure scenario: after a few sleep/wake cycles the microkernel stops coming up (say, state left
after a failed `sgx_stop`, see R4). From then on every wake is ≥1 s late and pushes hundreds of log
lines through the log ring, which buries the lines the session is meant to capture. The "wake
latency" check (checklist 4) then measures this instead of the GPU.

Fix: latch a start failure like a frame failure. In `start()`, if `sgx_start` or `sgx_draw_setup`
fails, set `failed = true`, log once and stop retrying on wake (`sgx ui on` can clear it). In
`sgx.c`, remember a build failure (`build_failed`) so it is not retried, and log the full state dump
only on the first init failure.

## Bugs

### G1. frame.c dropping `have_gpu` leaves the SGX powered on through every sleep
`src/frame.c:78-82` with `:153-158`, `src/gpu/sgx_compose.c:548-556`.

`gpu_draw_end` returns false when the GPU could not take the frame *and* the calls could not be kept
(`!drawable && !kept`: more than 48 calls or 128 rects together with, say, more than 4
turn_vertices ranges, a texture it cannot place, or more than 64 draws). frame.c then sets
`have_gpu = false` for good. On that path the GPU was never halted (`end()` only halts after a real
GPU failure), so it stays powered with `wanted` true and `CM_CLKSTCTRL` = 2 (forced awake, FCLK on).
`frame_sleep` calls `gpu_suspend` only `if (have_gpu)`, so the SGX stays on through every sleep
until reboot. The same happens if the console runs `sgx`, `sgx tri` or `sgx ui on` after a GPU
failure: `sgx_start` powers it up and nothing stops it at sleep, because `have_gpu` is false.

Failure scenario: an unusual frame (a burst of overlapping animations) loses one frame. From then on
the CPU draws, as it should, but sleep current goes up by the SGX's idle current and nothing in the
log says why. The power goal treats any such gap as a bug.

Fix: in `frame_sleep`, call `gpu_suspend()` whatever `have_gpu` says (it costs nothing when the GPU
is off). Or have `gpu_draw_end` on minnow return true after a lost frame and drop the GPU itself
(`sgx_compose(false)`).

### G2. `sgx tri` before the GPU UI can use up the four map slots, and the GPU UI then never starts
`src/console/console.c:1084`, `src/gpu/sgx_draw.c:56, 121-138`, `src/gpu/sgx_compose.c:101-113`.

`sgx_tri` maps only the current back buffer (`FB_BASE` or `FB_BASE + 0x64000`, 400 KiB each).
Mappings are never released, and `sgx_draw` has 4 slots. After `sgx ui off` (or a failed boot-time
start) and two `sgx tri` runs, which alternate back buffers, two slots are gone. `sgx ui on` then
maps FB_BASE whole (1 MiB, contained in neither existing map), the layers and the pool. The fifth map
fails, and every later attempt fails too ("Tried again whole" retries against slots that stay full).

Failure scenario: Darrel turns the GPU UI off to compare, runs `sgx tri` twice, turns it back on: the
answer is "failed, see the log" (`sgx: <soft pool address> not mapped`) until reboot.

Fix: map `FB_BASE`, `FB_SIZE` in `sgx_tri`, the same region the compositor maps, so it is found
again. Or raise `maps[]` to 8.

### G3. A refusal by `sgx_draw_frame` counts as a GPU failure and turns the GPU off for good
`src/gpu/sgx_compose.c:327-332`, `src/gpu/sgx_draw.c:485-496`.

`frame()` returns false without touching the GPU for `!valid(f)` ("draws of a kind not recorded") and
for "the last scene still holds its render details". `end()` treats both like a timeout: `failed`,
`sgx_halt()`, CPU from now on. The compositor's own checks are meant to make `valid()` always pass,
so today this only happens through a compositor bug, or after a `sgx tri` that left the scene stuck.
It is conservative, but the log line then blames the GPU for a compositor bug.

Fix (small): have `sgx_draw_frame` say whether the GPU was touched (e.g. `stuck` set or not). On a
refusal the compositor replays on the CPU and logs once, without halting.

## Risks (unverified; the watch will tell)

### R1. Memory the GPU reads is rewritten in place every frame, and no GPU cache invalidate is ever sent (highest-ranked risk)
`src/gpu/sgx_draw.c:162-170` (target address patched into the *USSE code* of both tile-store programs
at 0x0f43a018/0x0f43a058, and into PDS data at 0x0dc100c8), `:404-408` (every ring restarts at frame
one's offset), `:465-469` (pixel-shader blend code), `sgx_compose.c:182-237` (palette and slots in
the same `aux` texture every frame), layers read in place; cache control is PT|PD only, after
mappings (`sgx_draw.c:114, 136, 147`).

The vendor appends to its rings, the tile-store code ring included (the "tile store 120" status word
is that ring's end). So in its recordings no GPU-read address ever holds two different contents in a
row. That includes code: a second frame writes its tile-store program at the next offset.
The native policy (native-scene "Ring policy") rewrites the same addresses. The notes justify that
for ordering (frames are serialised), but not for the GPU's own caches: USSE instruction cache, PDS
code/data, texture cache, and the BIF/MMU TLB only through PT/PD. The compositor makes this worse
than the recordings ever did: `display_backbuffer()` alternates between the two frame buffers, so
the tile-store *instruction* changes every frame. The palette/slot texture changes every frame at
one address. The layers change in place. The one-frame watch test exercised none of this.

Failure scenario: frame N's tile store still runs frame N-1's cached instruction and writes into the
buffer on the panel (the front buffer). The flipped back buffer then shows the frame before last:
flicker, judder, tearing that looks like a compositor bug. Stale palette texels give wrong app
background colours. Stale layer texels show as "seconds not updating" (checklist 3 already lists
this one).

Suggested handling:
1. Before the UI session, a two-buffer check: `sgx tri` with clear colour A into buffer 0, then with
   colour B into buffer 1. Invalidate both and read a pixel of each back to the log. Each buffer must
   hold its own colour; if buffer 0 holds B, the code cache is stale.
2. The vendor kernel's mechanism for "memory reused with new content" is `SGXMKIF_CC_INVAL_DATA`
   (0x8; `sgxutils.c:929-931`, set after a cleanup). Have a switch (console or compile-time) that ORs
   8 into the first kick's cache control of every frame, so a stale-data symptom can be confirmed or
   ruled out in one session. Whether INVAL_DATA also covers the USSE instruction cache is
   unverified.
3. If code staleness shows: keep one tile-store copy per frame buffer (two code addresses written
   once at setup) and switch the *data* word that points at the program, or render only into one
   fixed buffer.

### R2. The TA command ring's wrap rule has never met the real microkernel
`src/gpu/sgx_draw.c:205` (`ccb_at = (ccb_at + 0x540) % 0x10000`).

The first command that crosses 0x10000 is kick 49 (frame 25). The host test runs it only against
its own completion (`ctl[1] = ctl[0]`), and the recordings have a few frames. If the microkernel (or
the vendor's client CCB) wraps differently, e.g. back to 0 when a command does not fit, the
microkernel reads its 25th frame's command from the wrong place.

Failure scenario: about 2 s into the GPU UI, `sgx: first kick 49 not done`, then CPU for good. Not a
hang (1 s timeout), but it looks like a random GPU fault.

Handling: note the kick number of the first failure. A failure at kick 49 or 50 points here. Cheap
diagnostic: a console command that runs 30 `sgx tri` frames in a row.

### R3. `sgx_halt` cuts power on a possibly busy BIF
`src/gpu/sgx.c:380-391`.

After a timeout the GPU may still have memory requests out (the timed-out render writing the frame
buffer). `sgx_halt` soft-resets everything including the BIF, runs the deinit script and removes the
clocks without waiting for `BIF_MEM_REQ_STAT`. The vendor never does that: its recovery path
(`SGXReset(bHardwareRecovery)`) flushes requests through the dummy directory first. A reset or clock
cut in the middle of an OCP transaction can wedge the L3 interconnect, which would be a hard hang,
not a timeout. Unverified.

Fix: before the soft reset, run `invalidate_directory_cache()` (or poll `BIF_MEM_REQ_STAT` with a
short, watchdog-fed timeout), and run the flush loop of `reset()` with `reset_once` cleared, so the
next `sgx_start` flushes again.

### R4. A failed `sgx_stop` leaves the scene looking healthy
`src/gpu/sgx.c:363-378`.

If POWER_OFF_COMPLETE or the clock gating is not seen, the GPU is powered off anyway (correct), but
`sgx_draw` is not told. On wake, `sgx_start` brings the microkernel up on a scene it may have been in
the middle of. If the microkernel does come up, the first frame times out (1 s) and the GPU is dropped
for good. Acceptable, but combined with B2 it can turn into "slow wakes forever".

Fix: on a stop failure, mark the scene stuck (or set the compositor's `failed`), as a frame failure
does.

### R5. Page-table writes are not ordered before the register writes that use them
`src/gpu/sgx.c:216-223`.

The fault loop writes `pd[]`/`pt[]` (Normal non-cacheable) and then the Device registers that make
the BIF use them, with no barrier between. ARMv7 does not order Normal accesses against Device
accesses. In practice the 2 µs `settle()` hides it.

Fix: `dsb()` after the two stores (and after clearing them).

### R6. Boot cost and order
`main.c:74` starts the GPU before the UI (about 140 ms the first time, per notes). Acceptable. If the
system partition is slow to mount, `firmware_read` opens it from inside `gpu_init` on the boot path,
before `ui_init`. Measure in the session (`sgx: image of N KiB built in N us`).

## Nits

- `src/gpu/sgx_image.c:20`: `SGX_HEAP_SHARED_3D` and `SGX_HEAP_3D_PARAMETERS` share the base
  0x0b800000 with separate `next` pointers. Any allocation from heap 9 would overwrite the parameter
  buffer's PTEs. It is unused today; make the enum value an alias or assert it is never allocated.
- `src/gpu/sgx_image.c:106-116`: `sgx_map` takes an unaligned `phys` and ORs it into the PTE flags.
  Callers check alignment; an `if ((phys | size) & 0xfff) return 0;` here would make it safe on its
  own.
- `src/frame.c:183-189`: while `frame_hold` is active, `frame_draw` returns before the `wfi()`, so the
  main loop spins for the whole 10 s of `sgx tri` (heat and current during the test, misleading
  `ui: idle` numbers). Fall through to the wfi branch.
- `src/gpu/sgx.c:286`: `sgx_log_state` guards on `PWSTST & 3` (also true in RET) and FCLKEN only.
  ICLKEN, or `CM_IDLEST_SGX`, would be the full check before register reads.
- `src/gpu/sgx_compose.c:319-321`: `told` is never reset. A second, different kind of refused frame
  after the first is never logged, and the checklist asks "which screen it was". Log once per kind,
  or with a counter in the 1 s stats line.
- Every GPU frame cleans and invalidates 400 KiB twice and `display_flip` cleans it again
  (`frame.c:61, 83`; `display_minnow.c:454`). The flip's clean finds nothing dirty after a GPU frame.
  Measure; this may decide the 2.2 ms gate.

## Tests: what they prove and what they do not

- `tests/sgx_draw_test.c`: byte-for-byte against the recordings for frame 1, and for frame 2 in words
  that do not depend on ring offsets. Completion is faked by writing exactly the status pairs the
  command itself names (`complete()`, `:108-129`) and `ctl[1] = ctl[0]`. A wrong status *address* or
  meaning, or a wrong `done()` predicate, therefore passes. The real microkernel decides what
  "done" looks like. Transfer-context allocations (holes) and textures are not compared (stated).
  The multi-frame in-place policy (R1) and the CCB wrap (R2) cannot be proved here.
- `tests/sgx_compose_test.c`: the vertex checks (`clip()`, `:371`) re-implement `place()`, so they
  catch regressions and the mutations listed, but cannot show that the GPU's picture equals the
  CPU's. I checked by hand that the turn matches soft.c's `turn_frame`: both map a source point to
  `(c·x − s·Y, s·x + c·Y)` in pixel coordinates with y down, about the same centre. With the y flip
  after the turn, row 0 is the top. The fake `sgx_draw_frame` checks a different rule set from the
  real `valid()` (it does not run `valid()` itself), so a compositor frame that the real driver
  refuses (G3) would not show. Suggest linking the real `valid()` (a static function, so expose it)
  into the fake.
- `tests/sgx_image_test.c:136-141` and `sgx_draw_test.c` without `SGX_LIBSRV_INIT`/recordings print
  a line and pass. `make test` is green on any machine without the dump, so "byte-for-byte" holds only
  where the dump is. Print `SKIP` prominently, or fail when `SGX_REQUIRE_REFERENCE=1`.
- Qualcomm: the new sources are only in `SRCS_omap3`. console.c's SGX code is under `#ifdef
  SGX_BASE` (the headers are included unconditionally, which is harmless). soft.c is omap3-only.
  `frame_hold` (ea1d281) is shared code and changes the Qualcomm binary, harmlessly. The notes'
  byte-identical check covered the stage-6 work only.

## Checked and found fine

- Kernel CCB command layout and handlers: `{ServiceAddress, CacheControl, Data[6]}` with the argument
  in Data[1] (`sgx_mkif_km.h:70-75`, `sgxpower.c` POWEROFF in `ui32Data[1]`). Write offset +1 mod 256,
  kicker +1 mod 256, `InterruptClearFlags |= IDLE|ACTIVE_POWER`, then the kick: the same as
  `SGXScheduleCCBCommand` (`sgxutils.c:540-610`), with the `dsb` before `EVENT_KICK` where the vendor
  has its barrier. Queue-full check `(w+1)&0xff == r`.
- Cache-control bits consumed once per command, as the vendor clears `ui32CacheControl`. PT|PD after
  every mapping, as `mmu.c` does.
- ISR: status & HOST_ENABLE, clear SW|MASTER, HOST_CLEAR2, OCP IRQSTATUS_2 = 1, read back
  HOST_CLEAR: the same as `SGX_ISRHandler` plus `SysClearInterrupts` (omap3630 `sysconfig.c:991-997`,
  `SGX_OCP_NO_INT_BYPASS`). IDLE answered as `SGXTestActivePowerEvent` does. ACTIVE_POWER is never
  raised because the rate is 0. IRQ masked before power-off on both stop paths, and OCP status
  cleared before unmasking on start.
- Start order: scripts part 1, reset, kicker = 0, part 2, HostClock, InitStatus = 0, kicker +1,
  barrier, kick, poll INIT_COMPLETE: the same as `SGXInitialise`. The first-reset fault flush matches
  the vendor's `bHardwareRecovery |= bFirstTime` (`sgxinit.c:564`, `sgxreset.c`). The flush loop
  matches the vendor's, with a bound added.
- Power-off: POWER/POWEROFF, poll PowerStatus bit 3, clock gating on CLKGATESTATUS with the
  recorded mask 0xFFFFFFFF, deinit script, clocks and domain: the same as `SGXPrePowerState` +
  `SGXDeinitialise`. `PowerStatus = 0` before power-up as `SGXPostPowerState` does.
- OCP_SYSCONFIG 0x28 = smart idle + smart standby (type-2 SYSCONFIG fields).
- TA command READY last, after the shared header and the sync list, then `dsb` in the kernel kick.
  This matches `sgxkick.c:440` ("THIS MUST BE THE LAST THING WRITTEN"). The client write offset
  written before READY is harmless because READY gates the command.
- Sync bookkeeping: device sync list takes WriteOpsPending++ (pre-increment value) as
  `SyncTakeWriteOp`; TA/3D dependency on the last kick only, as recorded.
- MMU: SGX registers 1 MiB Device XN (0x0c16), GPU pool 16 MiB Normal non-cacheable (TEX 001 C0 B0,
  0x1c02), set before the MMU is on (`mmu_init`), so no cacheable alias of the pool exists. memmap has
  no overlaps (the asserts cover the new region). Frame buffers (two at +0, +0x64000), layers
  (1 MiB stride) and soft's pool (now 4096-aligned) are page aligned. `sgx_draw_map` checks alignment.
- CPU↔GPU coherency on the GPU path: vertices, palette, slots, commands, scene and status words are
  in the uncached pool. Layers are cleaned per damaged row (`frame.c`), at init and on the ambient
  path. The frame buffer is cleaned and invalidated before the GPU writes and again after. On a
  failed frame the CPU replay's dirty lines are cleaned by `display_flip` even though `wanted` is
  then false.
- Ring bounds: with 64 draws at most, PV ≤ ~0x5800 of 0xc800, MT 0x2000 of 0xc800, PP 0x2000 of
  0x19000, PC 0x1000 of 0x8000, VDM ~2.6 KiB of 0x5000. Index table 2048 entries = MAX_VERTS. The
  vertex buffer is bounded per frame. The TA command at the highest offset ends at 0x10517, inside
  the 0x10688 allocation.
- Compositor geometry: layer quads, UVs (texel edges, nearest, 1:1), slot copies (≤ 10 × 32 px),
  palette index bound, round 64-gon, y flip and turn order (see Tests). The kept calls replay the
  same `soft_*` sequence, VBOs are not overwritten within a frame (one `app_background` call a
  frame, static mesh VBO), and the indicator textures do not change within a frame.
- Watchdog in the frame path: `wait()` feeds and times out after 1 s, the command queue wait is 1 s
  unfed, so the worst stall in a frame is about 2 s, under the 3 s bark.
- Wake/sleep sequencing: `frame_sleep` → `gpu_suspend` → `sgx_stop`; `frame_wake` → `gpu_init` →
  `sgx_start` (image built once). `by_hand` and `failed` keep the GPU off across wakes as intended.

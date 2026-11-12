# SGX530 driver and compositor review — Sol, 2026-11-12

Reviewed `2ccbde4..81208e5` in asteroid-embedded, HEAD `81208e5e9623782568498378822d0eead5b7c916`. The specified range contains **17 commits**, rather than 14; this review includes the entire range. Paths without a prefix are relative to asteroid-embedded. Vendor references below are relative to `minnow/minnow-kernel/drivers/gpu/pvr/`.

This was a read-only review except for this report. No code changes, commits, builds, adb, fastboot, watch access, DDK user-space source, or proprietary headers. The owner's binary library was read by the existing image/draw tests. Hardware failure scenarios below are static findings, not reproduced watch failures.

## Blockers for the watch session

### B1. Failed power transitions have no safe recovery boundary

**Locations:** `src/gpu/sgx.c:367`, `src/gpu/sgx.c:369`, `src/gpu/sgx.c:374`, `src/gpu/sgx.c:348`, `src/gpu/sgx.c:380`; `src/gpu/sgx_draw.c:97`; `src/gpu/sgx_compose.c:403`.

**Wrong:** `sgx_stop()` sets `running = false` before attempting POWER/POWEROFF. A queue, handshake, or clock-gating timeout only logs; execution still runs the deinit script and cuts clocks, without asserting reset or invalidating the reusable software state. `sgx_halt()` cannot subsequently repair that state because it immediately returns when `running` is false. The init-timeout branch similarly calls only `power_off()`, while keeping `built` and possibly a previously prepared scene. A failed transition is therefore treated as a successful, state-preserving shutdown on the next start. `ready`, command offsets, counters, PB/context state, and compositor mappings survive.

**Failure scenario:** sleep or `sgx ui off` encounters a hung microkernel, or wake times out during initialization. The user wakes or issues `sgx ui on`; `sgx_start()` resets hardware, but `sgx_draw_setup()` immediately accepts the old scene. There is no established guarantee that the failed POWER command drained, that the microkernel saved its context, or that its queues/resources are consistent. A stale command or partially saved context can wedge the GPU again. Cutting clocks with undrained requests also defeats the intended controlled failure path. Successful vendor-style suspend/resume is not evidence for this error case.

**Suggested fix:** distinguish powered/initialized/running from a cleanly suspended state. Make forced shutdown usable during partial startup and after `running` is cleared: mask IRQs, disable the GPU interrupt, force reset while clocks are available, and establish shutdown completion with a bounded wait. On any failed transition, keep the compositor on the CPU until reboot, or explicitly rebuild all affected kernel/client state before retrying. Return/propagate shutdown failure rather than silently authorizing state-preserving resume. Add injected POWER, clock-gate, and init-timeout tests of the real `sgx.c` state machine.

**Confidence:** confirmed missing error handling; the resulting bus/context failure is hardware-dependent. I would fix this before a session that exercises sleep/wake and the on/off escape path.

### B2. A timed-out console triangle leaves a live GPU while the CPU may resume drawing into its target

**Locations:** `src/console/console.c:1095`, `src/console/console.c:1097`; compare the compositor's shutdown at `src/gpu/sgx_compose.c:327`.

**Wrong:** after `sgx_draw_frame()` fails, `sgx_tri()` invalidates the target, logs state, and returns without halting the GPU. A timeout is not cancellation. The normal compositor deliberately calls `sgx_halt()` before replaying on the CPU; the console path omits that protection. Its earlier setup/allocation failure also leaves a GPU it started powered on.

**Failure scenario:** `sgx ui off`, then `sgx tri`; the last kick times out but can complete late. `wanted` remains false, so subsequent frames go directly to the software renderer. The CPU and GPU can now write the same back buffer, and `display_flip()` can scan a buffer still being modified. No later compositor submission is guaranteed to perform the missing halt. With GPU composition enabled, the next compositor frame usually notices the stuck driver and halts it, but that does not cover the CPU-only sequence.

**Suggested fix:** on any submitted-frame failure, capture diagnostics while clocks are on, force the GPU quiescent, and only then invalidate/reuse the buffer or return to the UI. Make diagnostic submission use the same failure transition as the compositor. Unwind power started solely for a test if setup fails.

**Confidence:** confirmed control-flow bug; late GPU writes were not tested.

## Bugs

### F1. Reset timeouts can exceed the watchdog window and are ignored anyway

**Locations:** `src/gpu/sgx.c:90`, `src/gpu/sgx.c:186`, `src/gpu/sgx.c:211`, `src/gpu/sgx.c:212`, `src/gpu/sgx.c:227`, `src/gpu/sgx.c:342`.

**Wrong:** `wait_reg()` never feeds the watchdog. Each BIF directory-cache invalidate can wait one second; reset can repeat that wait in up to 64 fault-draining iterations, with additional waits before and after. Neither an invalidate timeout nor exhausting the 64-fault limit fails `reset()`. It marks `reset_once` and starts the microkernel despite an incomplete reset.

**Failure scenario:** inherited or broken GPU requests keep BIF reads outstanding through several iterations during boot. The watchdog bark reboots at roughly three seconds (`src/main.c:51`, `src/soc/omap3/wdt.c:43`, `src/soc/exceptions.c:59`), before the reset loop returns. If the watchdog does not fire first, firmware still proceeds with a faulting BIF and will skip the drain on a retry. This is not an unbounded software loop, but its aggregate bound is incompatible with the watchdog and the promised CPU fallback.

**Suggested fix:** give the whole reset operation a deadline, feed the watchdog during bounded register waits, return failure from cache invalidation/reset, and check that faults actually cleared before setting `reset_once`. Unwind through B1's partial-startup shutdown and continue on the CPU. Feeding alone must not turn this into a minute-long boot stall.

**Confidence:** confirmed.

### F2. Refused compositor frames leak their temporary vertex allocation

**Locations:** `src/gpu/sgx_compose.c:130`, `src/gpu/sgx_compose.c:318`; `src/gpu/sgx_draw.c:152`, `src/gpu/sgx_draw.c:511`.

**Wrong:** the vertex arena is reset only by `sgx_draw_frame()`. A compositor frame that allocates vertices and is then refused by `end()` never calls that function. Neither the next `begin()` nor CPU replay discards those allocations.

**Failure scenario:** repeatedly draw the normal 516-vertex mesh followed by an unsupported 64×64 layer, the same class of refusal covered by `tests/sgx_compose_test.c:580`. Each rejected frame consumes at least 12,384 bytes of the 262,144-byte arena. After 21 such allocations, the next mesh no longer fits; even returning to an ordinary supported UI frame keeps taking CPU fallback, because no submission remains to reset the arena. `wanted`/`gpu_ready()` still report GPU use, and the GPU stays powered while the CPU does the work.

**Suggested fix:** add a frame-begin/discard operation that resets temporary vertices once prior work is complete, and invoke it for every abandoned frame. Add a repeated-refusal test followed by a supported frame, linked to the actual draw allocator. The present fake allocator also accumulates allocations, but the refusal test runs too few frames to expose it.

**Confidence:** confirmed. Existing firmware UI calls mostly fit the supported repertoire, so this is chiefly a broken fallback/recovery guarantee rather than a claim that every normal UI frame triggers it.

## Risks

### R1. READY and producer-index publication rely on stronger ordering than “uncached” guarantees

**Locations:** `src/gpu/sgx_draw.c:205`, `src/gpu/sgx_draw.c:237`; `src/gpu/sgx.c:274`, `src/gpu/sgx.c:255`; `src/soc/omap3/init.c:12`, `src/asteroid.h:40`.

**Concern:** the client CCB write offset becomes visible before the shared header is finished. READY is the last C store to the header, but there is no release barrier before READY, or between filling kernel command words and publishing the kernel CCB write offset. The `dsb()` in `kick()` orders everything before the subsequent EVENT_KICK write; it does not establish ordering between those earlier memory stores for a microkernel already running and examining queues. `MMU_RAM_UNCACHED` maps Normal non-cacheable memory, not strongly ordered memory. Volatile prevents compiler elision, not all CPU/interconnect reordering.

**Failure scenario:** while the microkernel is active between the two TA kicks, or when reusing a CCB slot after wrap, it observes a new producer offset/READY before all associated words have arrived. It can read stale flags, status addresses, or dependencies and hang. I could not establish from the allowed sources that the microkernel only observes this memory after the host's new kick, so this remains a concurrency risk, not a demonstrated failure.

**Suggested fix:** make the publication protocol explicit: populate payload/shared words, apply an appropriate DMB/DSB before READY, publish indices only after their data is complete, and retain the barrier before the event register. Also order the temporary reset page-table stores before releasing BIF reset. Review the acquire side before reusing GPU-owned resources. Vendor `services4/srvkm/devices/sgx/sgxkick.c:436` requires READY last, and `sgxutils.c:608` supplies the kick barrier, but reproducing its final barrier alone does not prove this firmware's Normal-memory publication assumptions.

### R2. Reusing texture/program addresses assumes GPU cache invalidation that the recordings cannot establish

**Locations:** `src/gpu/sgx_compose.c:222`, `src/gpu/sgx_compose.c:253`, `src/gpu/sgx_compose.c:441`; `src/gpu/sgx_draw.c:167`, `src/gpu/sgx_draw.c:404`, `src/gpu/sgx_draw.c:469`, `src/gpu/sgx_draw.c:238`.

**Concern:** CPU-side cleaning is present, but the GPU repeatedly reads updated layer/aux texture data, PDS descriptors, and patched tile-store instructions at the same GPU addresses. Cache requests cover page tables/directories; they never request data invalidation. The texture invalidation API is a no-op. The native ring policy also overwrites frame one's locations, whereas the recorded vendor driver appends new programs. The notes explicitly assume that 3D start invalidates the texture cache; the available recordings never execute that start or any texture fetch.

**Failure scenario:** an updating clock or palette shows old texels, a moved layer uses a cached descriptor, or alternating frame-buffer targets continue using stale tile-store code. The one verified triangle frame does not test address reuse. These outcomes are possible, not established bugs: the microkernel may already perform the necessary invalidation.

**Suggested fix:** establish the SGX530 cache contract with the allowed kernel references and a targeted hardware test that changes texels, target address, descriptor content, and blend variant over repeated frames. If explicit invalidation is needed, implement the correct operation and completion protocol; do not assume PT/PD invalidation covers texture/instruction caches. If combining data and BIF invalidation, account for the vendor BRN_28889 path (`services4/srvkm/devices/sgx/sgxutils.c:325`). Immutable code variants/per-target code can reduce instruction rewriting but do not by themselves solve texture coherency.

### R3. Host success does not validate the hardware lifecycle or independent completion behavior

**Locations:** `tests/sgx_draw_test.c:108`, `tests/sgx_draw_test.c:681`; `tests/sgx_compose_test.c:113`, `tests/sgx_compose_test.c:189`; `tools/sgx/pvrkm.py:748`; `Makefile:251`, `Makefile:259`.

**Concern:** the draw fake unconditionally advances CCB reads, writes requested statuses, completes every sync, and releases resources. Its “GPU off between frames” case changes only `running`; it never calls `sgx_stop()`/`sgx_start()` or models saved/restored GPU state. The compositor fake replaces the entire driver. Thus none of these tests exercises actual IRQ/register access, POWER timeout, partial initialization, reset failure, ordering, PB mutation, or GPU caches. The maximum-draw/ring-wrap tests prove CPU construction under the fake, not that the GPU consumes or completes those commands.

**Failure scenario:** B1, B2, and F1 pass all existing tests. R1/R2 and real multi-frame PB/context problems also pass because the fake manufactures precisely the completion the driver waits for. `same_as_soft()` validates CPU dispatch/replay against software rendering; it is not a rendered SGX-versus-CPU image comparison. Its rotation helper is stubbed, which further limits quarter-turn image claims.

**Suggested fix:** add a host test of the real `sgx.c` using modeled registers/memory and delayed/failed transitions, and a compositor/real-draw-allocator integration case for F2. Keep the recording tests, but describe them as construction equivalence with enumerated substitutions. Reserve rendered output, context retention, and cache claims for hardware evidence. No additional proprietary source is needed to improve those host failure tests.

## Nit

### N1. README still describes a trace-alignment failure that was already fixed

**Location:** `tools/sgx/README.md:371`; current expectation is `tools/sgx/check_init.py:29`.

The README says `check_init.py` expects 0x1000 alignment and reports a failure for the trace buffer. The code now expects 0x10, matching the facts. Someone following the lab instructions may dismiss a real failure as this supposedly known one. Remove/update the obsolete known-failure entry. This was checked statically; I did not rerun the Unicorn init emulator.

## Checked and found fine, within the stated limits

- **Existing tests:** ran `sgx_image_test`, `sgx_draw_test`, and `sgx_compose_test` from `../asteroid-embedded-sgx/build/test/`, whose worktree is clean at the same HEAD, and `build/test/soft_test`. All exited 0. Set `SGX_LIBSRV_INIT` to the owner's `minnow/dump/extracted_data/system/lib/libsrv_init.so`, `SGX_REFERENCE` to the supplied worktree's `build/sgx/init`, and `SGX_RECORDINGS` to its `build/sgx/draw`. The image comparison and all 19 named recorded draw scenarios ran rather than being skipped. These were existing binaries; I did not rebuild them under the instruction to write only this report, so their build provenance was not independently reproduced.
- **Generated artifacts:** executed the current `mkreplay.py` against the supplied recordings with both output writes intercepted into memory. Both resulting strings match current `sgx_scene_data.[ch]` exactly: 88 allocation entries, 49 runs, 560 words. No source/output files were written. The generator's assertions passed.
- **Comparison masks:** `tests/sgx_draw_test.c:370` explicitly checks the native unshifted PD address instead of simply ignoring it. Transfer-context dependencies are substituted from the no-transfer recording, stale constants from the mesh recording, and later-frame ring content from frame one. Those substitutions are explained and checked against alternative reference bytes, not arbitrary blanket masks. Nevertheless they intentionally do not prove hardware acceptance of fixed-address ring reuse. Transfer allocations, holes, and caller texture data are excluded from the construction comparison; its result is not a comparison of the entire GPU address space or rendered pixels.
- **CPU MMU/memory layout:** the 0x50000000 register section is Device memory; the entire 16 MiB SGX pool at 0x8f000000 is overwritten as uncached in the CPU page table, with no second cached virtual alias introduced. Boundaries are MiB aligned. Fixed frame buffers, seven layer slots, screenshot area, UI heap, and SGX pool do not overlap and fit the declared 512 MiB DRAM. The page-aligned software pool remains inside the image region. No overlap found in the fixed allocations used here.
- **GPU MMU:** for the used, bounded inputs, 4 KiB allocation/page-table walks, physical translation, read-only/cache-consistent/EDM bits, and the unshifted 32-bit SGX530 directory address agree with vendor `sgxmmu.h` and `mmu.c:3446`. Dummy stencil mappings deliberately alias one page. `sgx_draw_map()` checks page alignment and containment/reuses existing mappings; compositor mappings are rounded to pages. PT/PD invalidation is requested when mappings are added. The generic allocator does not enforce heap limits or roll back failed allocations, but the current fixed allocations fit and setup failures are not reused as a successful setup.
- **Normal kernel duties:** init scripts/program patches agree with the reference test and supplied facts; reset ordering, 192 MHz selection, software wake hold, initial kicker handling, POWER argument placement, and active-power disabling match the intended SGX530 path. Normal successful power-off waits for completion and zero clock-gate status before deinit. Preserving context memory across a *successful* shutdown is consistent with vendor `sgxpower.c:472` and `sgxinit.c:586`; the problem in B1 is applying that policy after failure.
- **Submission/sync construction:** command handler/argument layout, byte ring offsets, first/last scene flags, status lists, destination/TA3D pending values, RT alternation, and MTE launch toggle have corresponding recording checks. The CCB allocation includes an overrun area (`src/gpu/sgx_scene_data.c:10`), so a 0x540-byte command straddling the 0x10000 ring end is not by itself an out-of-bounds allocation write. Current draw-count/ring capacities fit; no ring-size overrun found for 64 accepted draws.
- **Normal waits and IRQ path:** command-space, initialization, query, geometry, render, power, and clock-gating polls have timeouts. Memory-word/draw waits feed the watchdog. SGX SW event plus master clear matches the vendor LISR; the OCP interrupt is acknowledged and a readback is performed. IRQ attachment occurs after image/startup, and normal stop/halt masks the line before cutting clocks. Idle acknowledgment and command-side acknowledgment are serialized against the CPU IRQ. No unconditional normal-path SGX register access with clocks off was found. Physical bus reads themselves cannot be rescued by a software poll timeout if hardware never returns them.
- **CPU cache ownership:** vertices/aux data/page tables/shared blocks live in the uncached SGX pool. UI layer initialization and damaged rows are cleaned in `main.c`/`frame.c`; the ambient path cleans its changes too. Indicators are copied from cached software allocations into the uncached auxiliary texture. The frame buffer is cleaned/invalidated before GPU ownership and again afterward on successful GPU composition. The compositor halts before CPU replay on a draw failure, and `display_flip()` cleans CPU-rendered output, including the fallback after `wanted` is cleared. GPU-internal cache uncertainty is R2, separate from these CPU-side operations.
- **Compositor geometry:** the position y flip agrees with the verified target row convention; rotation uses the same clockwise vertex formula as Adreno before that flip. Layer bands use their source-relative UVs and translated destination positions. Full layers remain 320×320 with 1280-byte rows. Small indicators occupy distinct slots, and palette texels start below the slots; no overlap found. The 64-gon fan matches the existing Adreno geometry. Later flat-colored triangles use premultiplied palette texels and over blending; the supported first mesh has constant per-triangle colors. Actual texture channels, sampling/raster edges, and full-screen rotated output remain hardware checks.
- **Fallback/integration:** missing/wrong library or ordinary startup failure lets `gpu_init()` return the software initializer's success, so the frame/stack UI continues through software composition rather than the older single-panel path. Manual off survives sleep/wake; a compositor draw failure latches CPU mode and avoids automatic GPU restart. Input vertices are preserved for replay. Unsupported target/texture/vertex kinds are rejected before submission, subject to F2's arena leak. Existing UI call counts fit replay storage; overflow is explicitly reported as failure rather than replaying a truncated call list.
- **Qualcomm:** SGX and renamed software implementations are confined to `SRCS_omap3`; Qualcomm retains `a3xx.c`, `draw.c`, and `paint.c`, and the console command is guarded by `SGX_BASE`. The common `frame_hold` branch is inactive unless requested, and the added firmware API is unused by Qualcomm. No source-level Qualcomm regression found. I did not rebuild either firmware or independently reproduce the notes' Qualcomm byte-identity claim.

## Not verified

No hardware behavior was newly verified: textured/multi-draw rendering, repeated target reuse, texture/instruction caches, real PB/region/RTDATA mutation, full UI capacity, IRQ behavior under faults, power-domain completion, sleep/wake, on/off cycles, performance, or power consumption. The supplied successful startup/one-triangle session is accepted as prior evidence only. I did not run the vendor libraries under Unicorn again, execute every host test in `make test`, or regenerate firmware images. No new checks of vendor user-space source or private headers were performed.

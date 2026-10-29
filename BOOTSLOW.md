# Boot slowdown window after GPU init (analysis, 2026-10-29)

Code references: `FW:` = asteroid-embedded-m7 (same boot path as main e7bf745),
`PW:` = asteroid-embedded-power worktree, `LK:` = lk2nd, `K:` = minnow/sturgeon-kernel.
`[I]` marks inference not confirmed from code or a measurement.

## 0. Summary

- The failure is not "a slow memset" and not a watchdog artefact: it is a
  **transient window, ~1 s to >3 s long, during which memory-bound work on
  CPU0 runs ~1000x slower**, opening within ~100 ms after `spm_init()` /
  `gpu_init()` (`FW:src/main.c:179-180`). Three observations fit one window:
  fbcon `present()` memset after the self-test line (bark, >3 s), the 1.2 s
  `gpu: powered` → `pm4` gap (that gap contains the `present()` of the
  "powered" line, `FW:src/gpu/a3xx.c:182` → `FW:src/display/fbcon.c:54-61`),
  and, with no fbcon at all, the 1.1 s `selftest` → `ui: ready` gap (layer
  fill + `dcache_clean_range`, `FW:src/main.c:181-183`, `FW:ui/src/watch.rs:124-131`).
- 640 KB in >3 s is ≥1200x below the measured 2.49 ms. No clock setting
  explains that: CPU on XO is 41x, buses at their floor ~10x. Something
  must either **stall every transaction** (~300 µs per 64 B line),
  **monopolise the shared L2/BIMC path**, or **steal CPU0 invisibly**
  (secure FIQs are not in our IRQ counts, `FW:src/soc/gic.c:101-113` sees
  Group 1 only).
- Both reset kinds are the same mechanism: the bark handler calls
  `reboot()` (`FW:src/soc/exceptions.c:59-66` → `FW:src/soc/reboot.c:18-29`,
  PS_HOLD, PMIC set to warm reset at `FW:src/soc/pmic.c:33-36`). So the
  "alternation" is about what the **previous session left running**, not
  about the reset path. A bark session never got past the GPU self-test
  (no USB, BT, hub, touch, no sleep cycle, GPU idle); a full session ends
  with GPU/MDP/USB/BT/hub active and has done cluster power-downs through TZ.
- Ranked: (1) secondary cores not staying parked after
  `park_secondaries()`, (2) secure-world interrupt storm, (3) GPU/MMSS state
  surviving the warm reset and a live CP being re-initialised under traffic,
  (4) RPM-side transient (the RPM keeps APSS state across our warm reset),
  (5) PMIC side effects of `pmic_charger_configure()` (new the same day).
  The cheapest discriminator is a **PMU cycle/bus-event sample per tick**
  (§5.1): it splits "CPU stolen or slowed" from "CPU stalled on memory"
  in one boot.

## 1. Evidence, re-read

| Observation | Where it sits in the boot | What it says |
|---|---|---|
| Bark at ~3 s, pc in `memset` from `present()`, last ramoops line `gpu: selftest passed` | `log_printf` writes the ramoops ring **before** the sink (`FW:src/log.c:57-63`), so the stalled `present()` is the one for the self-test line itself: `gpu_selftest()` → `log_printf` → `sink_fbcon` → `present()` | Window open at the first big memory operation after the self-test. 640 KB not done in >3 s (the feed at `fbcon.c:56` precedes the memset). |
| Near miss 1: `gpu: powered` → `pm4 … micro engine running` 1.2 s (normal 17 ms), boot survived | Between the two lines: `present()` of the "powered" line (memset + `fbcon_draw` + `dcache_clean_range` + `pp_wait` ≤16.7 ms normal), VBIF/RBBM writes, 32 KB ring memset (NC), ~4k GPU register writes, `flush(100)` for ME_INIT (`a3xx.c:184-227`) | A 1.2 s gap with no "stuck" line means the ME_INIT flush was <100 ms; the time went into the memset and/or the register writes. Window ~1.2 s, then recovered. |
| Near miss 2 (PW build, no fbcon, no kick in `display_init`): `selftest` 2.292 s → `ui: ready` 3.390 s; `powered` → `pm4` normal | `ui_init` (heap init, Slint window, `layer.fill` of 640 KB) + `dcache_clean_range(layer)` normally ~1 ms | Window ~1.1 s **with the MDP idle** (no kick, panel still shows the aboot splash) and **no fbcon**. Kills MDP-scan and fbcon-specific theories. Window started later than in near miss 1: the onset is not tied to one GPU action. |
| IRQ counts at bark normal (tick only) | `gic.c:101-113` | No Group 1 storm. Says nothing about Group 0 / FIQ (secure) interrupts: NS cannot mask or see them (`FW:src/start.S:21` `cpsid if` only masks NS-visible FIQ; with SCR.FW=0 TZ owns FIQ) [I: SCR not readable from NS, but that is Qualcomm's standard configuration]. |
| 1M-iteration loop 10.1 ms, static-buffer memset 2.49 ms, RCG 0x501, PLL mode 7 L 0x29 locked, identical on 20+ boots | Measured at boot time, in builds that never hit the window | Only proves the clean state. Do the same reads **inside** the window (bark record) before trusting them. |
| "~2900 ticks in 5 s" | `timer.c:39-44` | If `time_ms()` at the bark says ~3 s since `timer_init`, ticks ≈ elapsed ms and IRQ delivery was fine. Log `ticks` together with `time_ms()` and the boot-start stamp to settle the 5 vs 3 s. |
| Alternation: boots after a full-session `reboot` fail, boots after a bark reboot pass; clean main 4/4; later 25/25 fine | Same PS_HOLD warm reset in both cases (`exceptions.c:65`, `main.c:268`, `adb.c:613`, `console.c:129` all call `reboot()`) | The difference is session state, not reset type. Heisenbug-like disappearance after unrelated reordering says timing/alignment matters too. |
| After AsteroidOS: dies in the memset on every warm boot until a 12 s key reset (SUSPEND.md:860) | Kernel `reboot bootloader` is a **warm** reset (`K:drivers/power/reset/msm-poweroff.c:205-210`), a plain `reboot` would be hard; 12 s key = hard reset (EMBEDDED.md:300) | Some state survives PMIC-warm resets but not hard resets and is produced by both Linux and our full sessions. |

Magnitudes: 640 KB at 2.49 ms = 257 MB/s. >3 s = ≥1200x = ~290 µs per
64-byte line or ~18 µs per word. 1.1 s for ~1 ms of ui work ≈ 1000x.

## 2. Boot order around the window

```
main.c:159-162  rpm_init(); rpm_bus_votes(); rpm_sleep_votes()   sync acks (rpm.c:149-187), BIMC 200 MHz, SNOC 100, PNOC 50, CNOC 50 (rpm.c:213-219); clk1 id 3 (mmssnoc_ahb) never voted, Linux votes 40 MHz (K:arch/arm/mach-msm/clock-8226.c:3624)
main.c:164      display_init()           100 ms TE measurement, two 640 KB memsets, kick (m7) / no kick (PW)
main.c:178      pmic_charger_configure() new in e7bf745 (2026-10-29): BOOT_DONE, CHG_EN, vendor hwinit
main.c:179      spm_init()               spm.c:239-267: CPU0 SAW enabled with the WFI seq; L2 SAW seq loaded, CTL 0, CFG 0x14, PMIC_DATA; 3 SCM calls; park_secondaries(): ACC release of CPU1-3 (spm.c:188-205), each runs TZ cold boot → secondary_park (suspend.S:124-143) → SMC TERMINATE_PC|HOTPLUGGED; wait ≤100 ms per core for park_count && ACC_COLLAPSED (spm.c:224-235); QTMR frame0 IRQ 40 + MPM wake IRQ 171 enabled
main.c:180      gpu_init()               a3xx.c:171-231: RPM clk2/1 200 MHz (sync), GDSC on only if PWR_ON clear (a3xx.c:149-159), 4 CBCRs, no BCR / RBBM_SW_RESET, VBIF limits, ring memset, ucode load, ME_INIT flush(100)
                gpu_selftest()           a3xx.c:233-252
main.c:181-184  ui_init(), dcache_clean_range(layer), "ui: ready"
```

Everything asynchronous that is new at the onset: three secondary cores
handed to TZ, the GPU power domain and clocks, one RPM request, two SMC
boot-address calls, the SAW/SPM configuration, the charger state machine.
Nothing before `spm_init()` has ever been seen slow (display_init's TE
loop and memsets are in every log at normal duration — worth confirming
on a failing boot's timestamps).

## 3. What survives our warm reset (facts and gaps)

- PMIC: everything (regulator settings, modes, PON). lk2nd's `fastboot boot`
  path never touches the reset type (`LK:target/msm8226/init.c:416` only in
  `reboot_device`); our boot sets warm every time (`pmic.c:33-36`).
- RPM: notes record that bus/DDR **votes survive** (EMBEDDED.md:470-472)
  and that the QTimer counter continues (EMBEDDED.md:301); SMD channel
  states read CLOSED after the reset (EMBEDDED.md:197). So the RPM keeps
  the APSS active and sleep sets across our reset, while something (SBL1
  [I]) resets the SMD descriptors. Whether the RPM processor itself is
  reset is **unknown**; `numshutdowns` at 0xfc428154 across a reboot would
  tell.
- DDR contents: yes (ramoops, SMEM). GPU ring/scratch at 0x1e000000 (NC)
  keep the previous session's contents until `gpu_init` zeroes the ring.
- MMSS/GPU/MDP registers: unknown. The stock aboot re-initialises the
  display every boot, so the MDP state at our entry is aboot's regardless.
  The GPU GDSC state at our entry is logged (`a3xx.c:182` prints GDSCR
  after power-on; the pre-power-on value is not logged — add it).
- lk2nd's `boot_linux` tail: `target_uninit` (mmc sleep, sdhci), `platform_uninit`
  (`display_shutdown` if a panel was initialised, `qtimer_uninit`), cache
  clean+disable, MMU off (`LK:app/aboot/aboot.c:1289-1313`,
  `LK:platform/msm8226/platform.c:72-79`). lk2nd on msm8226 never talks to
  the RPM. USB controller state at handover: not stopped in these paths
  (fastboot's own stop is in the command handler; not checked).
- TZ: reloaded by SBL1 on every boot [I]; its data about cluster/core
  state is therefore fresh [I] — this is the gap for H1's state dependence.

## 4. Hypotheses, ranked

### H1. Secondary cores do not stay parked (confidence: medium)

Mechanism: after `release_secondary()` each core runs TZ cold boot and
`secondary_park`, counts itself, enables its SAW with the pc sequence and
asks TZ to collapse it as hotplugged (`suspend.S:124-143`). The wait loop
is satisfied the first moment `park_count[cpu] && ACC_COLLAPSED` holds
(`spm.c:224-235`); a later wake-up is invisible. A woken core re-enters at
the warm-boot address (= `secondary_park`), counts again and collapses
again; if TZ bails out, `b secondary_park` (`suspend.S:143`) loops forever.
Either way the core runs with MMU and caches off: every `ldr/str` on
`park_count` is a strongly-ordered DDR transaction through the cluster's
single L2/AXI port, the `handoff_lock` spin hammers the SFPB mutex at
0xfd484380 over the CNoC, and each TZ warm-boot entry does cache
maintenance on behalf of that core (L1 for sure; L2 by set/way if TZ
believes it is the last core — L2OFF.md §0 documents TZ's cluster count
getting inconsistent). Three cores doing that would degrade CPU0's
memory path far more than any clock setting, and it would stop when the
wake source stops — a transient of about a second is the right shape.

For: timing (window opens right after `park_secondaries()`); the only
other cores in the system are started exactly there; the park counter is
designed to show re-entries ("re-parking the secondaries (works, park
count 2)", SUSPEND.md:791).
Against: no identified wake source for a collapsed secondary (all SPIs
are targeted at CPU0 by `gic.c:41-42`; PPIs are banked and never enabled
on the secondaries by us; Group 0 targets are TZ's and unknown). The
state dependence (previous session) has no mechanism unless TZ's cluster
state survives the reset.

Experiments (cheap):
1. In the bark handler and at `ui: ready`, log `park_count[1..3]` (after
   `dcache_invalidate_range`, it is in `.data`) and `ACC_PWR_STATUS` of
   CPUs 1-3 (`0xf9098008`, `0xf90a8008`, `0xf90b8008`, bit 19). Counts
   >1 or a core not collapsed inside the window: confirmed.
2. Log how long each core took to park and whether the 100 ms timeout
   was hit ("did not park" is already logged; check failing logs).
3. Kill test: build with `park_secondaries()` skipped (`cluster_parked`
   false; sleep still works without cluster power-down). 20 boots
   alternating with full sessions. Window gone: cause is inside
   `spm_init`; bisect further by skipping only the SAW writes.

### H2. Secure-world interrupt storm stealing CPU0 (confidence: medium-low)

Mechanism: Group 0 interrupts (xPU/NoC errors, secure peripherals) are
FIQs handled in TZ and never reach `irq_handler`; a storm would make every
NS instruction stream crawl while IRQ counts look normal. A per-interrupt
TZ handler of 100-300 µs matches the ~300 µs-per-line magnitude better
than any bus effect. Which master could fault repeatedly after GPU
power-on is unknown; the GPU region (0x1e000000, `mmu.c:32`), FB
(0x05000000) and UI heap (0x06000000) all lie in plain DDR; the only
TZ-sensitive neighbours are `sbl_mem` 0x02f00000 and `qsecom` 0x03280000
(`K:arch/arm/boot/dts/qcom/msm8226-w-memory.dtsi:34`,
`msm8226-w-qseecom.dtsi:17`), which we only read (SMEM at 0x03000000).

Experiment (cheap, decisive for this hypothesis): dump the TZ diag
buffer in IMEM at 0xfe805720 (`K:arch/arm/boot/dts/qcom/msm8226.dtsi:1306-1309`,
already mapped device by `mmu.c:39`). Layout
(`K:drivers/firmware/qcom/tz_log.c:131-180`): u32 magic, version,
cpu_count, vmid_info_off, boot_info_off, reset_info_off, **int_info_off**
(+0x18), ring_off (+0x1c), ring_len; `num_interrupts` is the u32 at
`int_info_off - 4`; each entry (`tz_log.c:84-109`) is u16 int_info, u8
avail, u8 spare, u32 int_num, char desc[16], u64 int_count[cpu_count],
size = (ring_off - int_info_off) / num_interrupts. Snapshot the counts at
boot, after `ui: ready`, and in the bark handler; print deltas plus the
desc of any entry that moved. Thousands in the window: confirmed; flat:
killed. The ring buffer at `ring_off` (text) may also name the master
("XPU", "NOC").

### H3. GPU/MMSS state from the previous session (confidence: medium-low)

Mechanism: `power_on()` skips the GDSC sequence if `PWR_ON` is already set
(`a3xx.c:149-159`) and `gpu_init` never resets the block (no
`MMSS_OXILICX_BCR`, no `RBBM_SW_RESET_CMD`, no `CP_ME_CNTL` halt before
`load_ucode`, `a3xx.c:184-218`); the ring is zeroed under a possibly live
CP (`a3xx.c:202`). If the warm reset leaves the MMSS running, a full
session (GPU awake at reboot, VBIF allowed 24 outstanding requests,
`a3xx.c:184-187`) hands us a GPU still fetching/draining, and the VBIF
traffic competes with CPU0 on the BIMC until it faults or drains. A bark
session leaves an idle CP: nothing to drain. After AsteroidOS: kgsl's GPU
is on if the screen was on. A 12 s hard reset clears it.
Against: a chip-level warm reset should reset the MMSS [I]; the self-test
passes, so the CP is sane after ME_INIT; the PW near miss had a normal
ucode load and the window after the self-test.

Experiments (cheap, mostly from existing logs):
1. Check failing vs good logs for the `gdsc %08lx` value and for
   `display: … fb %08lx` (aboot's splash address vs one of ours).
2. Log GDSCR, the four CBCRs, `RBBM_STATUS`, `CP_RB_RPTR/WPTR` **before**
   `power_on()`; a PWR_ON=1 or GPU_BUSY=1 at entry on a failing boot is
   the smoking gun.
3. After the self-test, poll `RBBM_STATUS` bit 31 for 200 ms and log the
   busy fraction; busy while idle → confirmed.
4. Fix test: assert `MMSS_OXILICX_BCR` (0xfd8c4030) or
   `RBBM_SW_RESET_CMD` and halt the ME before loading ucode (kgsl order);
   call `gpu_suspend()` in `reboot()`.
5. Correlate failures with whether the previous session rebooted awake or
   asleep (previous ramoops log: last `sleep`/`wake` line).

### H4. RPM-side transient (confidence: low-medium)

Mechanism: the RPM keeps the APSS votes across our reset
(EMBEDDED.md:470). The only RPM traffic near the window is the gfx3d
request (`a3xx.c:147-148`), acked synchronously, but the RPM applies
clock/rail changes (MMPLL0, CX) on its own time, and a DDR/BIMC frequency
switch halts the BIMC for the duration. A single switch is ~100 µs; a
1 s effect would need the RPM to oscillate (conflicting sets) or to apply
the previous session's **sleep set** (XO off vote, `rpm.c:227-231`) while
we run. The RPM vmin counter (0xfc19dbd0 + 0x18, SUSPEND.md §8.2) advances
only when the RPM believes the APSS is down: if it moves during the
window, the RPM is treating us as asleep.
Against: no RPM action is known to take a second; the ack latencies in
the log were presumably normal (check the `rpm: msg` timestamps on a
failing boot).

Experiments:
1. Log `numshutdowns` (0xfc428154) and the vmin accumulated counter at
   boot start, after `ui: ready`, and at the bark. Vmin moving in the
   window: confirmed (and `rpm_sleep_votes()` becomes suspect: drop it for
   a test series). `numshutdowns` continuing across reboots settles
   whether the RPM is reset at all.
2. Hygiene: vote clk1 id 3 (mmssnoc_ahb) 40 MHz like Linux; re-send the
   bus votes after `gpu_init` and see if the window shortens.

### H5. Charger configuration side effects (confidence: low)

`pmic_charger_configure()` (`main.c:178`, e7bf745, landed 2026-10-29, the
day of the failures) runs immediately before `spm_init`/`gpu_init` and
starts fast charging (~260 mA) with BOOT_DONE/CHG_EN. A PMIC-side
transient (input current limit, VBUS droop, S2 in auto mode under the
GDSC inrush) could disturb the APC/CX rails or the A7 PLL for a while.
Against: a rail droop crashes rather than slows; the sensors-branch
alternation may predate the commit (check).
Experiments: move the call after `ui_init` (or skip it) for a series;
read A7 PLL STATUS/MODE, APCS RCG, S2 VSET/mode, S1 VSET in the bark
record and at `ui: ready`.

### H6-H8. Low

- MDP scanning the buffer: killed by the PW near miss (no kick, idle MDP).
- CPU clock / caches off: at most 41x and 10x; `ACTLR.SMP` is set
  (`start.S:31-33`), WB attributes (`mmu.c:15,29-31`), FB at 0x05000000 is
  cached, not in the NC window. Still re-read SCTLR/ACTLR/RCG/PLL inside
  the window (free in the bark record).
- lk2nd leftovers (USB controller with fastboot dTDs, UART): USB DMA is
  too weak to starve the BIMC; nothing new happens at the onset.
- Thermal: TSENS interrupts are NS (184) and not enabled; no RPM CPU
  throttling on this SoC [I].
- RPM sleep set applied at reset time (XO off during SBL): the chip boots
  to lk2nd fine every time, so the rails and XO are up before us.

## 5. Instrumentation to add regardless (cheap, one build)

1. **PMU sample per tick.** Enable the Cortex-A7 PMU from NS (PMCR E+C+P,
   PMCNTENSET bit 31 and counter 0, PMUSERENR not needed in PL1), count
   event 0x19 (bus access) or 0x17 (L2 write-back) in counter 0, and in
   `tick_irq` store `{PMCCNTR delta, counter0 delta, irq_frame pc}` into a
   64-entry ring. Dump it in the bark record and after `ui: ready`.
   Reading: ~787k cycles per ms with few bus events = CPU runs, stalled
   on memory (H1/H3/H4); far fewer cycles per ms = CPU stolen or clocked
   down (H2/H5/H7). This splits the field in one failing boot.
2. **Progress in the bark record.** `wdt_bark_handler` passes `regs=NULL`
   (`exceptions.c:64`); pass `irq_frame` (r0-r3, r12, pc) so the memset's
   destination pointer (r0) shows how far it got in 3 s: a rate, or stuck.
3. Timestamps already exist (`log.c:70-71`); add one line after
   `park_secondaries()` and one after `gpu_selftest()` so the onset can be
   placed to ~1 ms on the next failure.
4. Keep the display un-kicked and fbcon off until `ui: ready` (PW build):
   it removes the watchdog from the picture and lets the window be
   measured instead of fatal.

## 6. Open questions for the session that owns the watch

- Failing-boot logs: durations of `display_init` lines, `rpm: msg` ack
  latencies, `gdsc` value, `display: … fb` address, any `did not park`
  line, and whether the previous session was awake or asleep at `reboot`.
- Whether `numshutdowns` (0xfc428154) continues across our warm reset.
- Did the sensors-branch alternation predate e7bf745?

## 7. Watch results 2026-10-29 evening

Trigger: boot AsteroidOS (`fastboot boot backup/sturgeon/boot-asteroidos.img`),
`adb reboot bootloader`, then our firmware several times.

- **First boot after AsteroidOS, 2 of 2:** lk2nd hands over a different device
  tree (`boot: device tree 08600000, ramdisk 00000000-00000000` instead of
  `01e00000`, `02000000-0200ca00`), so no boot-image files: `gpu: no
  microcode`, and earlier the same day `bt: patch file 4343A0.hcd ... failed`.
  Separate bug from the slowdown; the next boot is normal again.
- **Slowdown reproduced once** (boots 3 and 4 after AsteroidOS, back to back,
  build e7bf745e51+ with `dbg` logging):
  - boot 3: `gpu: powered` 2.153 -> `selftest` 2.451 (300 ms, normally 33),
    bark 5.451. Secondaries: park counts 1 1 1, ACC status 00080460
    (collapsed) at the bark. IRQ frame r0..r3 = 05000000 00000000 050a2800
    0501382b: the fbcon memset of buffer 0 had done 0x1382b bytes (80 KB of
    650 KB) in ~3 s, i.e. ~27 KB/s, ~150 us per 4-byte store.
  - boot 4: bark at 3.47 s after `boot:` with park counts 0 0 0 (the bark
    came before `spm_init()` released the secondaries), memset of buffer 1
    (r0 050a2800, r3 050b5ca2: 77 KB done).
  - So **H1 (secondaries) is killed**: parked once and collapsed in one
    failure, never released in the other. **H3 (GPU state) and H5
    (charger) are killed** by boot 4: the window was open before either
    runs (display/fbcon stage). Remaining: H2 (secure FIQs) and H4 (RPM /
    bus), plus anything that makes each store cost ~150 us (bus or XPU
    timeouts per transaction, DDR in a throttled state).
  - GDSCR before GPU power-on was 00222001 (off) in every boot, failing or
    not.
- **Heisenbug:** after adding a probe to the bark handler (loop timing, 16 KB
  memset timing, 100 MPM timetick reads, A7 RCG/PLL), 2 more AsteroidOS
  round trips' worth of boots (18) did not reproduce. Third time
  instrumentation has made it go quiet; code layout or image size may matter
  (check what the image end / bss / heap overlap after a size change).

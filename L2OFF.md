# Cluster power-down with L2 off on sturgeon: Linux vs. the firmware

Research notes, 2026-10-28. This is a source comparison only: no watch access
and no code changes. It follows on from `SUSPEND.md` (§2.2-2.4, §8), which it
does not repeat.

**Notation**

- `K:` is the local vendor kernel `~/Downloads/AsteroidOS/minnow/sturgeon-kernel`
  (msm-3.10, HEAD 97abcf5b2468). Line numbers are from that checkout.
- `K318:` is `~/Downloads/AsteroidOS/skipjack-kernel` (msm-3.18 for
  msm8909w, also Cortex-A7 with SCM TERMINATE_PC). It is used only where it
  explains a flag.
- `FW:` is `~/Downloads/AsteroidOS/asteroid-embedded/src/soc/`.
- **[V]** means verified in source. **[I]** means inferred, with the
  reasoning given.

## 0. Summary

The firmware's suspend sequence matches Linux's closely: the same SAW
sequences, SPM_CTL values, SCM encoding, flags, lock, MPM image, boot
addresses and secondary parking. The real differences are these:

1. **The firmware invalidates the whole D-cache, L2 included, by set/way on
   every resume** (`FW:suspend.S:92`, `dcache_invalidate_all` = DCISW down to
   LoC). Linux never does an invalidate-only cache operation on resume or
   warm boot. Its `cpu_resume` touches no D-cache at all
   (`K:arch/arm/kernel/sleep.S:128-152`, `K:arch/arm/mm/proc-v7.S:116-148`),
   and secondary start only does an L1 *clean+invalidate*
   (`proc-v7.S:262-266`, `v7_flush_dcache_louis`).
   - TZ runs its warm-boot path with caches on before it jumps to
     `cpu_resume`, so the cache holds TZ's newest writes (cpu_count, its
     L2/cluster state, saved context).
   - If an NS DCISW drops those dirty lines, TZ's DDR copy goes back to the
     values it flushed at power-down. With flag 1 that state is "cluster
     down / count 0". **The next flag-1 call then sees inconsistent state
     and hangs, while flag-0 calls, which don't need the count, keep
     working. That is the observed "flag 1 works once" behaviour.**
   - [I] The architecture lets an implementation upgrade an NS
     invalidate-by-set/way to clean+invalidate for Secure lines. I could not
     confirm from local sources whether Cortex-A7 does. Removing the
     invalidate costs nothing, so try it first (§5, E1).
2. **Flag 0 combined with the L2 SAW in "pc" is a combination Linux never
   produces.** `set_l2_mode` derives the TZ flag from the L2 SAW mode
   (`K:drivers/cpuidle/lpm-levels.c:188-218`), and the last core passes that
   flag (`lpm-levels.c:1017-1021`). With flag 0, Linux flushes only L1
   (`K:drivers/power/qcom/msm-pm.c:212-215`), and TZ presumably flushes only
   L1 too. TZ's dirty lines in L2 are then lost when the L2 SAW cuts L2 power.
   That fits the random PS_HOLD reset a few seconds later. Treat flag 0 with
   L2 SAW pc as a dead end, not a workaround.
3. **"PS_HOLD reset, no fault record" is what our own watchdog produces** when
   the CPU hangs with IRQs masked or sleeps for more than 4 s. Bark is 3 s and
   bite 4 s (`asteroid-embedded/src/main.c:134`). The bark IRQ (GIC 35) is in
   the MPM bypass list (`K:arch/arm/boot/dts/qcom/msm8226-v2-pm.dtsi:225`),
   so it cannot wake the cluster, and while we spin in `handoff_lock` or sit
   in TZ, IRQs are masked anyway. A bite goes through TZ, which drops
   PS_HOLD. Linux stops the watchdog for suspend
   (`K:drivers/soc/qcom/watchdog_v2.c:114-126`), and its bark is 11 s with
   bite at bark + 3 s (`msm8226.dtsi:736-744`, `watchdog_v2.c:545-547`). Both
   "dies within 10 s" and "random reset" may therefore be a hang that the
   watchdog turns into a reset, not a TZ crash. A breadcrumb will tell which
   (E2).

## 1. The Linux sequence for the deepest level (L2 PC + RPM, cluster level 3)

The path is `lpm_suspend_enter` (`lpm-levels.c:864-888`), on CPU0, with CPUs
1-3 already hotplugged. dmesg from a real sturgeon shows mode 3
(POWER_COLLAPSE) entered back-to-back many times
(`asteroid-embedded-notes/hw/sturgeon/dmesg.txt:1028-1065`, "CPU0:
msm_cpu_pm_enter_sleep mode:3 during suspend"), so repeated flag-1 collapses
work on this TZ.

1. **Watchdog off** in the device suspend phase (`watchdog_v2.c:114-126`).
2. `cpu_prepare`: in suspend there is no broadcast timer (`lpm-levels.c:635-637`).
3. `cluster_prepare` → `cluster_select` (level 3 in suspend) →
   `cluster_configure` (`lpm-levels.c:449-510`):
   1. **L2 SAW first**: `set_l2_mode(PC)` sets `tz_flag = MSM_SCM_L2_OFF (1)`.
      The CTI save is a stub (`CONFIG_CORESIGHT_CTI` is off,
      `include/linux/coresight-cti.h:28,85`). Then
      `msm_spm_config_low_power_mode(l2, PC, notify_rpm=true)`
      (`lpm-levels.c:188-218`) writes SPM_CTL = EN | start 26 = **0x1a1**
      (`spm_devices.c:184-216`, `spm-v2.c:135-149,299-322`).
   2. `msm_rpm_enter_sleep()` masks the SMD-RPM IRQ and flushes the sleep set.
      `msm_mpm_enter_sleep()` writes the vMPM and rings IPC bit 1
      (`lpm-levels.c:480-494`).
4. `msm_cpu_pm_enter_sleep(POWER_COLLAPSE)` → `msm_pm_power_collapse`
   (`msm-pm.c:337-381`):
   1. AVS: stubs, Krait-only.
   2. `ramp_down_last_cpu`: `clk_disable(cpu0_clk)`. If the refcount reaches 0,
      the a7ssmux RCG switches to its safe source, GPLL0 300 MHz
      (`clock-local2.c:1351-1362`, `clock-a7.c:32-34`) [I: depends on the
      refcount; `l2_clk` is absent with synced-clocks, `msm-pm.c` probe].
   3. `msm_pm_spm_power_collapse(cpu, from_idle=false, notify_rpm=true)`
      (`msm-pm.c:227-281`):
      - CPU SAW → POWER_COLLAPSE, notify_rpm = **0x199** (start 25). The bytes
        are identical to spc at start 5 (= our 0x59; `msm8226-v2-pm.dtsi:25-29`).
      - `msm_pm_boot_config_before_pc` writes the per-CPU slot in
        `msm_pm_boot_vector` and cleans that line (`pm-boot.c:50-70`). TZ
        itself is **not** called again.
      - `msm_jtag_save_state`: stub, no `CONFIG_MSM_JTAG*` (`include/soc/qcom/jtag.h:16-24`).
      - `cpu_suspend(0, msm_pm_collapse)` → `msm_pm_collapse` (`msm-pm.c:205-225`):
        1. `lpm_cpu_pre_pc_cb()` (`lpm-levels.c:995-1039`) takes the cluster
           lock, picks the flag (L2_ON unless all CPUs are in sync, otherwise
           `lpm_dev->tz_flag`), and then **always** takes `scm_handoff_lock`
           with TID `128 + cpu` before releasing the cluster lock.
        2. For flag 1: `flush_cache_all()` (DCCISW to LoC plus I-cache).
           Otherwise: `flush_cache_louis()` when L1 is write-back
           (`msm-pm.c:212-215`).
        3. `scm_call_atomic1(SVC_BOOT=1, TERMINATE_PC=2, flag)`:
           r0 = `SCM_ATOMIC(1,2,1)` = **0x00402221**, r1 = &context, r2 =
           flag (`scm.c:390-426`). Only for hotplug is
           `SCM_CMD_CORE_HOTPLUGGED (0x10) | (flag & SCM_FLUSH_FLAG_MASK=3)`
           used (`msm-pm.c:47-49,197-198`). There are no other bits.
5. **Resume**, in this order:
   1. TZ jumps to `msm_pm_boot_entry` (`idle-v7.S:23-55`): MPIDR → slot →
      `cpu_resume`.
   2. `cpu_resume` / `cpu_v7_do_resume` invalidate the TLB and I-cache and
      restore CP15. They write **ACTLR only if it differs**
      (`proc-v7.S:136-138`), then turn the MMU on. **There is no D-cache or L2
      maintenance and no l2x0.**
   3. `local_fiq_enable`. `msm_jtag_restore_state` is a stub.
   4. CPU SAW → CLOCK_GATING **0x09** (`msm-pm.c:264-279`).
   5. `ramp_up_first_cpu` (`msm-pm.c:313-335`).
   6. `cluster_unprepare` (`lpm-levels.c:557-617`): `msm_rpm_exit_sleep`,
      `msm_mpm_exit_sleep`, then L2 SAW → DISABLED. That only clears EN, so
      SPM_CTL reads 0x1a0 (`spm-v2.c:218-235`). The firmware writes 0, which
      is equivalent.
   7. The watchdog is re-enabled in device resume (`watchdog_v2.c:128-140`).

**Secondaries (hotplug)**:

- Each one goes through `lpm_cpu_hotplug_enter`, which picks the lowest
  ss_power CPU level, "pc" (`lpm-levels.c:1048-1091`).
- Its path is `msm_pm_power_collapse` → `msm_pm_spm_power_collapse(cpu,
  false, true)`: CPU SAW 0x199, then `msm_pm_pc_hotplug` (`msm-pm.c:183-203`).
  That takes the handoff lock and issues TERMINATE_PC `0x10 | 0`, because
  CPU0 is still online, so the cluster is not in sync and the flag is L2_ON.
- On a spurious wake it loops (`hotplug.c:37-63`).
- The firmware does the same: `FW:suspend.S:125-144` (0x59, the lock, 0x10).

**Boot addresses**:

- Warm: set once at boot, all four CPUs (0x56), one entry
  (`pm-boot.c:28-49,84-94`), using the buffer-form `scm_call`
  (`scm-boot.c:21-33`).
- Cold for CPU1-3: once, flags 0x29 (`platsmp.c:369-415`).
- **Nothing is re-registered before a collapse.** The firmware's single
  registration at init matches. It uses the atomic form, which is accepted
  (it returns 0, and flag-0 resume works).

## 2. SAW values: firmware vs. DT

| | DT (`msm8226-v2-pm.dtsi`) | Firmware (`FW:spm.c`) |
|---|---|---|
| CPU SAW cfg/dly/ctl base | 0x00 / 0x3c102800 / 0x8 (:14-30) | same (:232-234) |
| CPU wfi / spc / pc bytes | :25-29 | :35-41, identical; pc = spc bytes |
| CPU SPM_CTL in PC | 0x199 (pc, rpm=1) | 0x59 (same bytes at start 5) |
| L2 SAW cfg/dly | 0x14 / 0x3c102800 (:94-95) | same (:237-238) |
| L2 PMIC_DATA0/1 | 0x02030080 / 0x00030000 (:97-98) | same (:239-240) |
| L2 ret / gdhs / pc bytes, offsets 0/4/26 | :104-109 | :46-55, identical |
| L2 SPM_CTL pc | 0x1a1 | 0x1a1 (:143) |
| L2 after wake | 0x1a0 (EN clear) | 0 |

**No sequence or register difference.** The only theoretical one is the
CPU SAW start offset, and the bytes behind both offsets are identical.

## 3. TZ requirements

- **Handoff lock.** SFPB mutex: the block is at 0xfd484000, 8 locks in
  0x400, so the stride is 0x80 and lock 7 is at **0xfd484380**
  (`msm8226.dtsi:1353-1357`, `drivers/hwspinlock/msm_remote_spinlock.c:144-145,180`).
  The TID is `REMOTE_SPINLOCK_TID_START (128) + cpu`
  (`include/linux/msm_remote_spinlock.h:26-27`). The write-and-read-back
  loop is at `msm_remote_spinlock.c:213-225`. The firmware is correct on all
  of these.
  - Linux takes the lock on **every** TERMINATE_PC after lpm probe, the
    hotplug path included (`msm-pm.c:188,210` → `lpm-levels.c:1034`).
  - Before probe it takes no lock (`lpm-levels.c:1003-1004`), and mainline's
    cpuidle-qcom-spm never takes it. For a single running core it serializes
    nothing [I]. It is harmless as long as TZ releases it, which SUSPEND.md
    §8 found that it does.
  - Risk: we spin on it with IRQs masked, and if it is ever stuck, the
    watchdog bites with no record (§0.3).
- **Flags do not have to match.** The secondaries use `0x10|0`; only the
  last core passes 1. The last core is always CPU0 in suspend (CPU0 is not
  hotpluggable here). The cluster levels are `last-core-only`
  (`msm8226-v2-pm.dtsi:144,156,169`; `lpm-levels.c:414-416`).
- **cpu_count bookkeeping is TZ-internal.** The only kernel contract is the
  lock plus the flag (comment at `lpm-levels.c:1022-1029`). Our parking gives
  TZ the same picture as Linux hotplug.
- **Flag meaning** [V for the kernel side, I for TZ]:
  - 0 = L2 stays powered; TZ maintains L1 only.
  - 1 = L2 will lose power; TZ cleans L2. The kernel also does
    `flush_cache_all`.
  - 3 = GDHS, no L2 flush. msm-3.18 picks GDHS exactly when the level is
    marked `no_cache_flush` (`K318:drivers/cpuidle/lpm-levels.c:366-372`).
  - 2 = RET is defined (`include/soc/qcom/pm.h:42-47`) but no 8226 level
    uses it.
  - msm-3.18 also sends L2_OFF for a hotplug before probe "to make sure that
    L2 is flushed" (`K318:lpm-levels.c:1440-1450`). That is the only case
    where a hotplug call carries flag 1.

## 4. L2 GDHS as an alternative

- **What it is**: L2 SAW sequence `gdhs` at offset 4, registered with
  notify_rpm=1 (`spm_devices.c:560`), selected with SPM_CTL = **0x41**.
  - TZ flag **3** (`lpm-levels.c:202-206`).
  - The kernel flushes L1 only (`msm-pm.c:212-215`).
  - Whatever the TZ flag, the CPU SAW still uses 0x199 (or our 0x59).
- **DT**: cluster level 1 "l2-cache-gdhs" (`msm8226-v2-pm.dtsi:135-145`) has
  **no `qcom,notify-rpm`**, so Linux never flushes the sleep set or programs
  the MPM with GDHS (`lpm-levels.c:480-494`). Only level 3 (pc + notify-rpm)
  gets XO shutdown or VDD min. In suspend, level 3 always wins (lower
  ss-power).
  - **So Linux never runs GDHS with XO off or VDD min on 8226.**
- [I] The gdhs and pc byte strings share the `42 … 4e 02 02 … 50` pattern,
  which may be the RPM handshake. The pc string has an extra
  `f0 11 07 01 b0 … 12 … f0`, which may be PMIC_DATA_1, the APC rail off.
  GDHS would keep S2 on. The RPM might still allow XO off, but that is
  untested anywhere I can see.
- The retention sequence (`00 03 00 0f`, offset 0, SPM_CTL 0x01) is not used
  by any level.

## 5. Experiments, most likely fix first

**E1. Stop invalidating caches on resume.**

- Delete `bl dcache_invalidate_all` at `FW:suspend.S:92`. Linux has no
  equivalent. Cortex-A7 invalidates L1 (and L2 after a power-on) in hardware
  at reset, and TZ owns L2 after flag 1.
- If you want a belt-and-braces step, use a **clean+invalidate** of L1 only
  (DCCISW at level 0, like `v7_flush_dcache_louis`). Never DCISW, and never
  L2.
- Then test the Linux combination: flag **1**, L2 SAW 0x1a1, the lock,
  `dcache_clean_invalidate_all` before the SMC (already there), the MPM and
  the sleep set.
- Pass: more than 2 consecutive cluster collapses, and `numshutdowns` in RPM
  master stats (0xfc428154) rising each time.

**E2. Find out what the "death" is (diagnostic, do it alongside E1).**

- Write breadcrumbs to an uncached word that survives a warm reset: IMEM
  0xfe805668. That is inside the 0x40-byte `qcom,pm@fe805664` region that
  only HLOS uses (`msm8226-v2-pm.dtsi` qcom,pm node) [I]. The RAMOOPS
  console zone also works.
  - Values: 1 = before the lock, 2 = lock held, 3 = SMC returned (bailout),
    4 = `cpu_resume` entry (MMU off; use the physical address), 5 = MMU on,
    6 = back in `spm_idle`.
  - Also read ACTLR after resume and log it. SMP (bit 6) must be 1. If the
    NS write is ignored and TZ did not set it, caches misbehave.
- Separately, either stop the watchdog across the cluster collapse as Linux
  does (`writel(1, WDT_RST); writel(0, WDT_EN)` before and re-arm after;
  base 0xf9017000), or raise the bite above the longest tick.
  - A "hang" then stays a hang you can inspect with the power key. A crumb
    of 2 means the lock or TZ; 4 without 5 means our resume.

**E3. If flag 1 still fails after E1: try GDHS.**

- L2 SAW SPM_CTL 0x41, TZ flag 3, L1-only clean (DCCISW level 0) before the
  SMC. Keep the MPM and the sleep set.
- Check whether `numshutdowns` and the RPM vmin count still rise. If they
  do, this gets most of the cluster saving without TZ's L2-off state
  machine, and it is safe with respect to secure L2 data.

Further experiments, if those don't settle it:

- **E4. Drop the handoff lock** on CPU0's path, or make it a bounded trylock
  that bails out of the collapse. Linux before probe and mainline both work
  without it for a single core. This removes one source of IRQs-off spin.
- **E5. Register boot addresses the Linux way**: one buffer-form
  `scm_set_boot_addr(entry, 0x56)` with an MPIDR dispatcher like
  `msm_pm_boot_entry` that sends CPU0 to `cpu_resume` and CPUs 1-3 to
  `secondary_park`, plus cold 0x29. This rules out any per-CPU address
  overwrite in this TZ's legacy BOOT_ADDR handling. It is low probability,
  since flag-0 resume already lands correctly.
- **E6. Before the cluster collapse, move the CPU onto GPLL0 or the safe
  source**, as `ramp_down_last_cpu` may do, so the cluster comes back on a
  clock that does not depend on the A7 PLL or the L8 / sr2 sleep-set votes
  [I].
- **E7. Cosmetic**: after wake, write 0x1a0 to the L2 SAW instead of 0, and
  re-enable FIQ (`cpsie f`) after a real collapse, as `msm-pm.c:266-267`
  does.

## 6. Open points

- Whether a Cortex-A7 NS DCISW can drop Secure dirty lines. The ARM TRMs are
  not available locally. E1 makes the question moot.
- What TZ does internally on flag 1 (it cleans L2, but what state does it
  keep for warm boot?). No sturgeon TZ image is available locally. The
  rubyfish `tz.img` is a different SoC.
- The meaning of the SPM command bytes (§4) is still undocumented.

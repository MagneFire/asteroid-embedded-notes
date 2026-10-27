# Deep sleep on sturgeon (APQ8026): how the downstream kernel does it

Research notes for reproducing the vendor kernel's deepest system sleep
bare-metal: APCS power collapse with the RPM handshake, XO shutdown and VDD
min. Written 2026-10-26.

**Sources and notation**

- `D:` is the downstream kernel `kernel/msm` branch
  `android-msm-sturgeon-3.10-marshmallow-dr1-wear-release` (gitiles). Line
  numbers refer to the files on that branch as fetched on 2026-10-26.
- `ML:` is mainline Linux master as of the same date (torvalds/linux).
- **[V]** means verified in source, with the file:line given. **[I]** means
  inferred, with the reasoning given. Anything without a tag is a summary of
  [V] items next to it.
- DT chain for sturgeon: `D:arch/arm/boot/dts/apq8026-sturgeon.dts:15` includes
  `qcom/apq8026-v2.dtsi`, which includes `msm8226-v2.dtsi`, and that includes
  `msm8226-v2-pm.dtsi` (`msm8226-v2.dtsi:20`). All SPM, LPM and MPM data comes
  from `D:arch/arm/boot/dts/qcom/msm8226-v2-pm.dtsi` (abbreviated `pm.dtsi`
  below). The sturgeon files (`apq8026-sturgeon/*.dtsi`) do **not** override
  any lpm, spm or mpm node [V: grep of all sturgeon dtsi]. Their only
  sleep-relevant settings are `rpm-regulator-vsa1 { regulator-always-on }`
  (`apq8026-sturgeon-pm.dtsi:143-147`) and the PON long-press reset
  (`apq8026-sturgeon-pm.dtsi:69-83`, see §6).
- The kernel config is `D:arch/arm/configs/sturgeon_defconfig`.
  `ARCH_MSM8226` selects `MSM_SPM_V2`, `MSM_L2_SPM`, `MSM_PM if PM`,
  `MSM_RPM_SMD` and `MSM_SCM` (`D:arch/arm/mach-msm/Kconfig:246-285`).
  `MSM_RPM_SMD` selects `MSM_MPM_OF` (`D:drivers/soc/qcom/Kconfig:131-132`).
  `lpm-levels.o` is built under `CONFIG_MSM_PM` (`D:drivers/cpuidle/Makefile`).
  The defconfig also sets `CONFIG_PM_AUTOSLEEP=y` and `CONFIG_CPU_IDLE=y`.

---

## 1. Low-power levels

The source is `pm.dtsi:112-206` (`qcom,lpm-levels`), parsed by
`D:drivers/cpuidle/lpm-levels-of.c`. Mode strings map to modes as follows:
`wfi`, `standalone_pc` and `pc` are CPU modes (`lpm-levels-of.c:447-470`), and
`active`, `gdhs`, `pc` and `retention` are L2 SPM modes
(`lpm-levels-of.c:340-354`).

### CPU levels (pm-cpu, per core)

| idx | mode | latency-us | ss-power | energy-overhead | time-overhead-us | flags |
|---|---|---|---|---|---|---|
| 0 | `wfi` (SPM clock gating) | 1 | 530 | 52800 | 100 | |
| 1 | `standalone_pc` (core PC, L2 on, no RPM) | 500 | 410 | 603400 | 1200 | use-broadcast-timer |
| 2 | `pc` (core PC; triggers cluster levels) | 550 | 372 | 700000 | 1410 | use-broadcast-timer |

`pm.dtsi:176-203` [V]. No `retention` level is defined, so
`msm_pm_retention()` (`D:drivers/power/qcom/msm-pm.c:130-162`) is unused.

### Cluster ("system" / L2) levels

`spm-device-names = "l2"` resolves to the SPM device named `system-l2`
(`lpm-levels-of.c:299-308`).

| idx | label | L2 SPM mode | latency-us | ss-power | time-overhead-us | min-child-idx | flags |
|---|---|---|---|---|---|---|---|
| 0 | l2-cache-active (default) | active, which means SPM disabled | 10 | 3000 | 110 | | |
| 1 | l2-cache-gdhs | gdhs | 700 | 372 | 1410 | 2 | last-core-only |
| 2 | l2-cache-pc-no-rpm | pc | 1000 | 315 | 2400 | 2 | last-core-only |
| 3 | l2-cache-pc | pc | 12700 | 315 | 2400 | 2 | **notify-rpm**, last-core-only |

`pm.dtsi:117-170` [V]. The deepest state is level 3: the whole APCS (all
cores, L2 RAM and the APC rail) goes off, and the RPM is notified, which lets
it do XO shutdown and VDD min.

The levels differ in practice as follows:

- **Only level 3 calls `msm_rpm_enter_sleep()` and `msm_mpm_enter_sleep()`**
  (`D:drivers/cpuidle/lpm-levels.c:480-494`). That is the RPM sleep-set
  flush plus MPM programming.
- `set_l2_mode()` always calls `msm_spm_config_low_power_mode(ops->spm, lpm,
  true)` with `notify_rpm = true` (`lpm-levels.c:218`). Both L2 "pc" levels
  therefore run the same L2 SAW sequence, the one registered with
  notify_rpm=1 (§2.2). Levels 2 and 3 differ only in the software steps.
- The L2 flag handed to TrustZone is MSM_SCM_L2_ON=0, L2_OFF=1, L2_RET=2 or
  L2_GDHS=3 (`D:include/soc/qcom/pm.h:42-46`). `set_l2_mode` uses L2_OFF for
  pc and L2_GDHS for gdhs (`lpm-levels.c:194-217`).
- In suspend (as opposed to idle), `lpm_suspend_enter()` picks the deepest
  allowed CPU level (`lpm-levels.c:864-888`). `cluster_select()` then picks
  the lowest-power cluster level; the notify-rpm level is skipped only when
  `suspend_in_progress && from_idle` (`lpm-levels.c:428-429`). In suspend
  `sleep_us` is `~0`, so it chooses level 3 [V `lpm-levels.c:339-346,
  431-443`].
- A cluster level needs every CPU in the cluster "in sync". Offline CPUs are
  counted as in sync (`lpm-levels.c:773-787`). Before suspend, CPUs 1-3 are
  hotplugged off into PC via `lpm_cpu_hotplug_enter()`
  (`lpm-levels.c:1048-1091`, `D:arch/arm/mach-msm/hotplug.c:39-42`), which
  uses SCM TERMINATE_PC with `0x10 | flag` (`msm-pm.c:183-203`).
- Unused DT properties: `qcom,pm@fe805664`'s `qcom,pc-mode = "tz_l2_int"`,
  `qcom,use-sync-timer` and `qcom,synced-clocks` (`pm.dtsi:335-341`). Only
  `synced-clocks` is read (`msm-pm.c:770-787`, which means no `l2_clk`). The
  others appear nowhere in the fetched C sources [V grep]. The register at
  0xfe805664 (IMEM) only receives the physical address of the PC debug
  counters (`msm-pm.c:818-829`).

---

## 2. Deepest suspend, step by step

### 2.1 Addresses

| Block | Address | Source |
|---|---|---|
| CPU0 SAW2 (v2.1) | 0xf9089000; CPUn at 0xf9089000 + n*0x10000 | `pm.dtsi:14-84` |
| L2 / APCS SAW2 | 0xf9012000 | `pm.dtsi:86-110` |
| CPU0 ACC sleep status | 0xf9088008 (+n*0x10000), mask 0x80000 (bit 19 = core collapsed) | `pm.dtsi:343-348`, `msm-pm.c:438-469` |
| QGIC2 dist / cpu | 0xf9000000 / 0xf9002000 | `D:.../msm8226.dtsi:76-81` |
| APCS IPC (outgoing interrupts to RPM) | 0xf9011008: bit 0 = SMD RPM, bit 1 = MPM | `msm8226.dtsi:807-816`, `pm.dtsi:210-216` |
| vMPM (in RPM msg RAM) | 0xfc4281d0 | `pm.dtsi:208-212` |
| RPM sleep stats | 0xfc19dba0 (v2, 2 records) | `pm.dtsi:361-366` |
| RPM master stats | 0xfc428150, stride 2560 (APSS is master 0) | `pm.dtsi:374-380` |
| MPM2 sleep counter (32768 Hz) | 0xfc4a3000 + 0 | `msm8226.dtsi:96-100`, `D:arch/arm/mach-msm/msm_mpmctr.c:35` |
| QTimer (mem-mapped arch timer) | 0xf9020000; frame0 0xf9021000 (phys SPI 8 = GIC 40) | `msm8226.dtsi:116-129` |
| GCC | 0xfc400000 (APCS_GPLL_ENA_VOTE +0x1480, BRANCH_ENA_VOTE +0x1484, SLEEP_ENA_VOTE +0x1488) | `D:arch/arm/mach-msm/clock-8226.c:427-429` |

### 2.2 SAW2 programming (what spm-v2 writes)

**Register offsets, SAW2 v2.1** (`D:drivers/soc/qcom/spm-v2.c:42-67`):

| Offset | Register | Offset | Register |
|---|---|---|---|
| 0x00 | SECURE | 0x2C | AVS_HYSTERESIS |
| 0x04 | ID | 0x30 | SPM_CTL |
| 0x08 | CFG | 0x34 | SPM_DLY |
| 0x0C | SPM_STS | 0x40..0x5C | PMIC_DATA_0..7 |
| 0x10 | AVS_STS | 0x80.. | SEQ_ENTRY (32 words) |
| 0x14 | PMIC_STS | 0xFD0 | VERSION |
| 0x18 | RST | | |
| 0x1C | VCTL | | |
| 0x20 | AVS_CTL | | |
| 0x24 | AVS_LIMIT | | |
| 0x28 | AVS_DLY | | |

The driver reads the version at `0xfd0` (`qcom,saw2-ver-reg`) and requires
major 2, minor 1 for this table: `VERSION[31:28]` = 2, `[27:16]` = 1
(`spm-v2.c:204-216, 524-539`). ML's `spm.c` calls these SAWs
`qcom,msm8226-saw2-v2.1-cpu` and the L2 SAW `qcom,msm8226-saw2-v2.1-l2`
(local copy `dts/mainline/qcom-msm8226.dtsi:413-519`).

**Init order** (`msm_spm_drv_init`, `spm-v2.c:506-568`; `msm_spm_dev_init`,
`D:drivers/soc/qcom/spm_devices.c:218-261`) [V]:

1. Shadow values come from DT (`spm_devices.c:533-549, 634-639`). Missing
   properties are 0.
2. The driver writes every shadow register from enum index 0 up to
   `PMIC_DATA_0 + num_pmic_data`. `num_pmic_data = SAW2_ID[6:4]`
   (`spm-v2.c:181-187`). The registers written are CFG, AVS_CTL,
   AVS_HYSTERESIS, SPM_CTL, (PMIC_DLY), AVS_LIMIT, AVS_DLY, SPM_DLY and
   PMIC_DATA_0..n-1.
   - PMIC_DLY has no offset in the v2.1 table, so it lands at offset 0x00 with
     value 0. This is harmless; skip it bare-metal.
   - SPM_CTL is written with its DT value, which has EN (bit 0) clear.
3. The mode sequences are concatenated byte-wise in DT order: wfi, ret, gdhs,
   spc, pc, each only if present (`spm_devices.c:557-563, 641-653`). Bytes
   pack little-endian into 32-bit words; each sequence ends with 0x0f and the
   next continues in the same word (`spm-v2.c:267-297`). Each mode's
   `start_addr` is its byte offset (`spm_devices.c:239-252`). All 32 words go
   to SEQ_ENTRY (`spm-v2.c:236-253`).
4. ML writes the sequence **before** the control registers. Its comment: a
   core held in reset could otherwise start the SPM state machine on a
   half-written sequence (`ML:drivers/soc/qcom/spm.c` probe). Do it in that
   order.

**Selecting and triggering a mode** (`spm_devices.c:184-216`,
`spm-v2.c:135-149, 218-235, 299-322`) [V]:

- Mode DISABLED clears SPM_CTL.EN (bit 0).
- Any other mode sets EN and writes the start byte offset into
  `SPM_CTL[10:4]`.
- Nothing else is needed. The sequence runs on the core's next WFI (the
  core's WFI is what the SAW intercepts).
- The `(mode, notify_rpm)` pair picks the sequence. When no exact match
  exists, start_addr stays 0 (`spm_devices.c:202-210`).

**CPU SAW** (0xf9089000; `pm.dtsi:14-30`): CFG=0x00, SPM_DLY=0x3c102800,
SPM_CTL base=0x8, no PMIC data. Sequences:

```
wfi (CLOCK_GATING, rpm=0): 60 03 60 0b 0f                                     start 0
spc (POWER_COLLAPSE, rpm=0): 20 10 80 30 90 5b 60 03 60 3b 76 76 0b 94 5b 80 10 26 30 0f   start 5
pc  (POWER_COLLAPSE, rpm=1): (identical bytes)                                start 25
```

- SEQ words at +0x80: 0x0b600360, 0x8010200f, 0x605b9030, 0x763b6003,
  0x5b940b76, 0x30261080, 0x8010200f, 0x605b9030, 0x763b6003, 0x5b940b76,
  0x30261080, 0x0000000f. The remaining words up to 31 are 0.
- SPM_CTL per mode: clock gating = **0x00000009**, spc = **0x00000059**,
  pc = **0x00000199**.
- ML's `spm_reg_8226_cpu` has exactly the wfi+spc bytes with start indices
  0 and 5 [V].
- The meaning of SPM_CTL bit 3 (DT `qcom,saw2-spm-ctl = <0x8>`) is not
  documented in either tree. ML does not set it. Keep it set, as downstream
  does.

**L2 SAW** (0xf9012000; `pm.dtsi:86-110`): CFG=0x14, SPM_DLY=0x3c102800,
SPM_CTL base=0x0, PMIC_DATA_0=0x02030080, PMIC_DATA_1=0x00030000.
`vctl-port 0`, `phase-port 1`, `pfm-port 2`, `cpu-vctl-mask 0xf` (this SAW
owns the APC rail for all 4 cores). Sequences:

```
ret  (RETENTION, rpm=0): 00 03 00 0f                                                         start 0
gdhs (GDHS, rpm=1):      00 20 32 6b c0 e0 d0 42 03 50 4e 02 02 d0 e0 c0 22 6b 02 32 50 0f   start 4
pc   (POWER_COLLAPSE, rpm=1, "APCS_PMIC_OFF_L2RAM_OFF"):
     00 32 b0 10 e0 d0 6b c0 42 f0 11 07 01 b0 50 4e 02 02 c0 d0 12 e0 6b 02 32 50 f0 0f     start 26
```

- SEQ words at +0x80: 0x0f000300, 0x6b322000, 0x42d0e0c0, 0x024e5003,
  0xc0e0d002, 0x32026b22, 0x32000f50, 0xd0e010b0, 0xf042c06b, 0xb0010711,
  0x02024e50, 0xe012d0c0, 0x5032026b, 0x00000ff0.
- SPM_CTL per mode: disabled = EN clear, ret = 0x01, gdhs = 0x41,
  **pc = 0x000001a1**.

The SPM command bytes themselves are not documented anywhere in either
tree; copy them verbatim. PMIC data decoding is partly verified:
`msm_spm_turn_on_cpu_rail()` enables the CPU supply by writing **0x30080**
to VCTL (`spm_devices.c:300-302`), which is port 3, data 0x80.
PMIC_DATA_0 = 0x02030080 is therefore "APC rail (S2) on" and PMIC_DATA_1 =
0x00030000 is "off" [I: same port/data layout; bits 25:24 = 2 unexplained].
Do not touch VCTL; the APC voltage is changed through it by the
spm-regulator/CPR (`spm-v2.c:368-425`).

**SAW states around a deep suspend:**

| When | CPU0 SAW SPM_CTL | L2 SAW SPM_CTL |
|---|---|---|
| Runtime idle / WFI | 0x09 (clock gating; `msm-pm.c:278`) | EN clear (cluster level 0 "active" → DISABLED) |
| Just before the SCM call | 0x199 (`msm-pm.c:242-244`) | 0x1a1 (`lpm-levels.c:473-479` → `set_l2_mode`) |
| After resume | 0x09 again (`msm-pm.c:278-279`) | EN clear again (`lpm-levels.c:606-612`) |

### 2.3 TrustZone calls

**Warm-boot address, set once at boot** (`D:drivers/power/qcom/pm-boot.c:28-49,
84-94`, a postcore_initcall) [V]:

- If `scm_is_call_available(BOOT, 0x11)` (SVC_INFO=6, cmd 1, buffer call with
  arg `(1<<10)|0x11`, `D:drivers/soc/qcom/scm.c:607-620`), downstream uses
  `SCM_BOOT_ADDR_MC`. Otherwise it uses
  `scm_set_boot_addr(phys(msm_pm_boot_entry), flags)`.
- Flags (`D:include/soc/qcom/scm-boot.h:15-22`): WARMBOOT_CPU0=0x04,
  CPU1=0x02, CPU2=0x10, CPU3=0x40. Coldboot CPU1/2/3 = 0x01/0x08/0x20.
  4 CPUs give 0x56. **Bare metal, CPU0 only: flags = 0x04.**
- `scm_set_boot_addr` is a **buffer (non-atomic) SCM call**:
  `scm_call(SVC_BOOT=1, SCM_BOOT_ADDR=1, {u32 flags; u32 addr}, 8, NULL, 0)`
  (`D:drivers/soc/qcom/scm-boot.c:21-33`). The legacy buffer convention
  (`scm.c:67-85, 165-187, 253-290`):
  - The buffer is physically contiguous and cache-cleaned. Layout:
    `{len = 16+8+12 = 36, buf_offset = 16, resp_hdr_offset = 24,
    id = (1<<10)|1 = 0x401}`, then `{flags, addr}` at +16, then the response
    header `{len, buf_offset, is_complete}` at +24.
  - Call: `r0 = 1`, `r1 = &context`, `r2 = phys(buffer)`, `smc #0`. Repeat
    while r0 == 1 (interrupted).
  - Then invalidate the response header and poll `is_complete` until it is
    nonzero.
- Alternative [I]: ML sends the same command as a **register (atomic) call**:
  `qcom_scm_set_boot_addr()` with `QCOM_SCM_ARGS(2)`, `args[0] = flags`,
  `args[1] = phys addr` (`ML:drivers/firmware/qcom/qcom_scm.c:403-424`; warm
  bits {BIT2, BIT1, BIT4, BIT6} at :135-137). ML tries the MC variant first
  and falls back to this. In the existing `src/soc/scm.c` that is
  `scm_call2(1, 1, 0x04, entry_phys)`, r0 = **0x00401222**. Mainline uses
  this on msm8226 but it is not verified on this TZ build. If it returns
  nonzero, use the buffer form.
- The TZ always jumps to that one address. Downstream points it at
  `msm_pm_boot_entry` (`D:drivers/soc/qcom/idle-v7.S:23-55`). That stub reads
  MPIDR, bumps a debug counter, loads `msm_pm_boot_vector[cluster*4+cpu]` and
  jumps to it. Before each PC the kernel writes that slot
  (`pm-boot.c:50-70`): `cpu_resume` if the core's context is saved,
  `msm_secondary_startup` for hotplug. The slot's cache line is cleaned
  (`dmac_clean_range`). Bare metal can register its resume entry directly
  and skip the indirection, since the address is MMU-off physical.

**Power collapse** (`msm-pm.c:47-49, 205-225`) [V]:

```
r0 = SCM_ATOMIC(svc=1, cmd=2 /*TERMINATE_PC*/, nargs=1) = 0x00402221
r1 = &context (any scratch word)
r2 = flag: 0 = L2 on (standalone PC), 1 = L2 off (full APCS PC), 3 = GDHS
     hotplug path ORs in 0x10 (SCM_CMD_CORE_HOTPLUGGED), msm-pm.c:197-198
smc #0
```

- ML is identical: `qcom_scm_cpu_power_down(flags & 3)`
  (`ML:drivers/firmware/qcom/qcom_scm.c:485-496`).
- On success the call does not return; the core reappears at the warm-boot
  address.
- The call returns only on **bailout** (an interrupt was pending). Downstream
  counts that as "PC Bailout" and unwinds (`msm-pm.c:219-224`). ARM
  `cpu_suspend` forces a nonzero return in that case, so `collapsed = false`
  (`msm-pm.c:257-258`).
- Cache maintenance before the call: for L2_OFF the kernel does
  `flush_cache_all()`. Otherwise, if L1 is write-back, it does
  `flush_cache_louis()` (`msm-pm.c:210-215`, check at `:97-122`). Bare
  metal: clean and invalidate all D-cache levels by set/way, then dsb.
- `lpm_cpu_pre_pc_cb()` also takes the SMEM remote spinlock "S:7"
  (`scm_handoff_lock`), which the secure monitor releases. It serializes
  multi-core PC against TZ's cpu_count (`lpm-levels.c:50-51, 995-1039`). [I]
  It is not needed with one core ever online: ML's
  `cpuidle-qcom-spm.c:32-58` does SPC on this SoC without it.

### 2.4 Exact downstream sequence for the deepest suspend

This is `suspend_ops.enter = lpm_suspend_enter`, with CPUs 1-3 already
hotplugged into PC.

1. **prepare_late** (`lpm-levels.c:848-855`). `suspend_in_progress = true`.
   Then `msm_mpm_suspend_prepare()` (`D:drivers/soc/qcom/mpm-of.c:619-632`):
   if every wake-enabled IRQ is MPM-mappable (§4.3), it drops the MPM driver's
   CXO vote (`cxo_lpm_clk`), which allows XO shutdown. Otherwise it keeps the
   vote.
2. **syscore suspend.**
   - `gic_suspend()` saves GICD_ISENABLERn, clears all enables and enables
     only the wake set (`D:drivers/irqchip/irq-gic.c:216-241`). Wake-enabled
     IRQs include the MPM IRQ SPI 171 (§4.4) and the SPMI arbiter IRQ
     (`D:drivers/spmi/spmi-pmic-arb.c:1155-1161`).
   - VFP state saved (`vfp_pm_suspend`, `D:arch/arm/vfp/vfpmodule.c:457`).
3. `lpm_suspend_enter` → `cpu_prepare` (no broadcast timer in suspend,
   `lpm-levels.c:635-637`) → `cluster_prepare` → `cluster_select` gives
   level 3 → `cluster_configure` (`lpm-levels.c:449-510`):
   1. **L2 SAW → pc**: tz_flag = 1, coresight CTI save, L2 SAW SPM_CTL =
      0x1a1.
   2. **`msm_rpm_enter_sleep(0, cpumask)`** (`D:drivers/soc/qcom/rpm-smd.c:1350-1366`):
      - Mask the RPM→APSS SMD interrupt in the GIC (SPI 168 = GIC 200,
        `msm8226.dtsi:807-816`; `smd.c:2302-2341`), so incoming acks cannot
        abort the sleep.
      - **Flush the cached sleep-set requests** (§3.2, `rpm-smd.c:392-457`).
   3. **`msm_mpm_enter_sleep(sclk, false, cpumask)`**: write the vMPM, then
      ring IPC bit 1 (§4).
      - In suspend, `get_cluster_sleep_time()` returns `~0ULL`, which is
        truncated to `u32 us = 0xffffffff` (`lpm-levels.c:339-346, 484`).
        Divided by 30 that gives sclk = 143165576 (`lpm-levels.c:492-493`).
        The MPM wake timer is therefore set **~83.9e9 ticks ≈ 72.8 min**
        ahead, not "never" [V arithmetic from `mpm-of.c:531-551`].
      - With `msm_pm_sleep_time_override` set, it is that many seconds
        instead.
4. `msm_cpu_pm_enter_sleep(PC)` → `msm_pm_power_collapse()`
   (`msm-pm.c:337-381`):
   1. Print enabled clocks (`:356-358`; the downstream tool for finding
      XO-shutdown blockers). AVS is disabled (Krait-only feature, no effect
      here [I]).
   2. `ramp_down_last_cpu`: `clk_disable(cpu0_clk)`. `l2_clk` is not
      acquired with synced-clocks.
   3. `msm_pm_spm_power_collapse(cpu, false, true)` (`:227-281`):
      - CPU SAW SPM_CTL = 0x199.
      - `boot_vector[0] = phys(cpu_resume)`.
      - JTAG save.
      - `cpu_suspend(0, msm_pm_collapse)`. This saves the CP15 context (list
        below), then: pre-pc callback, flag 1, cache flush, **SMC 0x00402221
        with r2=1**.
5. **Hardware/TZ/RPM part** [I, from the sequence names, the master-stats
   fields and the comments]:
   1. TZ saves its own state and executes WFI.
   2. The CPU SAW runs the "pc" sequence: clamps and powers the core down.
   3. Once all four cores are down, the L2 SAW runs the "pc" sequence: L2
      RAM off, APC rail off via PMIC_DATA_1 over SPMI, plus the hardware
      shutdown handshake to the RPM. The RPM records it as
      `shutdown_req`/`numshutdowns` in master stats
      (`D:drivers/soc/qcom/rpm_master_stat.c:53-63`).
   4. The RPM applies the APSS sleep set and loads the MPM hardware from the
      vMPM.
   5. If all masters are asleep and the aggregated votes allow it, the RPM
      turns XO off and, beyond that, puts CX/MX at retention (VDD min).
6. **Wake.**
   1. The MPM sees an enabled pin edge or level, or its timer expires.
   2. The RPM restores XO and the rails, then interrupts the APSS on **SPI
      171 (GIC 203, rising edge)**. That interrupt must be GIC-enabled, or
      the SPM is never woken (comment `mpm-of.c:182-191`; request and wake
      `:731-752`).
   3. The L2 SAW re-powers the APC rail (PMIC_DATA_0) and releases L2. The
      CPU SAW releases the core.
   4. TZ warm boot jumps to the registered address with the MMU off.
   5. `cpu_resume` (`D:arch/arm/kernel/sleep.S:128-148`) **itself forces SVC
      mode with IRQ and FIQ masked**, restores CP15, enables the MMU and
      returns 0 from `cpu_suspend`.
7. **Unwind**:
   1. `local_fiq_enable`, `msm_pm_boot_config_after_pc` (NULL).
   2. CPU SAW back to 0x09 (`msm-pm.c:264-279`), `ramp_up_first_cpu`.
   3. `cluster_unprepare` (`lpm-levels.c:557-617`):
      - `msm_rpm_exit_sleep()` unmasks GIC 200 (`rpm-smd.c:1372-1379`).
      - `msm_mpm_exit_sleep(false)` reads the vMPM STATUS words, ANDs them
        with the wake mask and marks edge-type Linux IRQs pending (level
        ones are still asserted) (`mpm-of.c:553-595`).
      - L2 SAW back to DISABLED, CTI restore.
   4. syscore resume: `gic_resume_one` restores the enables
      (`irq-gic.c:304-317`), then VFP. Then `.wake` runs
      `msm_mpm_suspend_wake()`, which re-evaluates the CXO vote for idle.

### 2.5 State to save and restore

**CP15** [V, `D:arch/arm/mm/proc-v7.S:97-148`]:

- Saved: FCSE PID, TPIDRURO, TTBR1, DACR, TTBCR, SCTLR, ACTLR, CPACR.
- Resume: TTBR0 is set to the physical pgd. PRRR/NMRR are rewritten from
  constants. TLB and I-cache are invalidated before the MMU goes on.
- ACTLR is written only if it differs, because the NS world may not write it
  (`proc-v7.S:136-138`). TZ is expected to set ACTLR.SMP on warm boot [I].
- Not saved by Linux because it uses high vectors, but needed bare metal if
  you use them: **VBAR**, TPIDRPRW/TPIDRURW, the CNTKCTL/CNTV/CNTP timer
  state. Also the banked SP/LR/SPSR of every mode you use, and your MMU
  tables (they are in DDR, which is retained).

**GIC** [V]:

- The downstream never saves the distributor in this path. There is no
  `cpu_cluster_pm_enter()` in `lpm-levels.c`/`msm-pm.c`, and `gic_dist_save`
  runs only on CPU_CLUSTER_PM_ENTER (`irq-gic.c:811-838`).
- The CPU-interface save (`gic_cpu_save`) runs only through `cpu_pm_enter()`,
  which is called only from idle (`msm-pm.c:239-240`). In suspend nothing
  GIC-side is saved except the enable masks.
- [I] So the QGIC distributor state survives APCS PC on this SoC, being
  outside the APC rail, and TZ restores the secure/banked interface.
  Bare metal should still rewrite GICC_CTLR/PMR/BPR and the banked PPI/SGI
  enables (GICD_ISENABLER0) after resume. It is cheap and covers both
  cases.

**Timers** [I]:

- CNTPCT (system counter) keeps counting: the MPM wake value is computed as
  `cntpct + delta` (`mpm-of.c:541-546`), which only makes sense if it does.
- Per-core CNTP_CTL/CVAL are in the collapsed core, which is why both PC
  levels are marked `use-broadcast-timer` (`pm.dtsi:192,202`). Rearm the
  tick after resume.
- VFP: FPEXC.EN is cleared on suspend (`vfpmodule.c:457-480`). After resume,
  restore CPACR (from the saved context), then FPEXC. NSACR is TZ's.

**Caches:** with flag 1 everything is lost. DDR stays in self-refresh, done
by the RPM/BIMC [I]. Clean anything the resume path reads (stack, saved
context) before the SMC; the full flush does that.

---

## 3. RPM side

### 3.1 Message format

`D:drivers/soc/qcom/rpm-smd.c:95-116, 1074-1170` [V] matches `src/soc/rpm.c`:

```
{ service 'req\0' = 0x00716572, request_len = 20 + data_len }
{ msg_id, set, resource_type, resource_id, data_len }
{ key, nbytes, value } ...
```

`set`: 0 = active set, **1 = sleep set** (`D:include/soc/qcom/rpm-smd.h:22-25`).
The sleep set takes effect only while the APSS is in RPM-assisted PC.
`rpm.c` currently hard-codes set 0 (`pkt[n++] = 0` after msg_id).

**Default rule** [V, `D:drivers/regulator/rpm-smd-regulator.c:192-201,
536-548`]: "if an active set request is present, but not a sleep set
request, then the active set request is used at all times, even when the
Apps processor is power collapsed." Everything the bare-metal firmware has
enabled with set 0 therefore **stays on in sleep** until a set 1 request
overrides it.

### 3.2 What the kernel sends and when

- Sleep-set requests are **not sent when created**. `msm_rpm_send_data()`
  caches them in an rb-tree keyed by (type, id), merging KVPs
  (`rpm-smd.c:1137-1140`, `msm_rpm_smd_buffer_request` `:313-344`,
  `tr_update` `:281-311`).
- At `msm_rpm_enter_sleep` the cache is **flushed**: each changed entry gets
  a new msg_id and is written to SMD with noirq, **without waiting for
  acks**. Acks are drained only after 24 messages, so the 1 KiB FIFO does
  not overflow (`rpm-smd.c:392-457`).
- Acks that arrive later are consumed after wake by the normal SMD path.
- There is **no "going to sleep", "invalidate" or "ack" message**. The
  handshake is the L2 SAW sequence (hardware) plus the vMPM IPC (§4).
- Bare metal [I]: sending set-1 requests early, synchronously and with an
  ack wait is equivalent and simpler. The RPM stores sleep sets per master.
  After every wake, drain any unexpected 'msg' acks from the RX FIFO before
  the next `rpm_request()`: `rpm.c` reads exactly one reply per request.

Sleep-set votes in this kernel [V where cited]:

| Resource | type / id / key | Sleep-set behaviour |
|---|---|---|
| CXO | `clk0` 0x306b6c63 / 0 / `Enab` 0x62616e45 | `xo` (normal) votes the same value in both sets; `xo_a_clk` (active-only) votes **0 in the sleep set** (`D:drivers/clk/qcom/clock-rpm.c:73-137`). The kernel always holds `xo_a_clk` ("CXO is expected to remain on whenever CPUs aren't power collapsed", `clock-8226.c:3613-3618`). Non-AO `xo` voters: `cxo_lpm_clk` for the MPM device (only while non-monitorable wake IRQs exist, `mpm-of.c:596-617`), `cxo_otg_clk` for USB, PIL voters (`clock-8226.c:2850-2855, 3074-3112, 3211`). In a clean suspend: active Enab=1, **sleep Enab=0 → XO shutdown allowed**. |
| Bus clocks | `clk1` 0x316b6c63: pnoc 0, snoc 1, cnoc 2, mmssnoc_ahb 3; `clk2` 0x326b6c63: bimc 0, gfx3d 1, ocmem 2; key `KHz` 0x007a484b | `_a` variants are active-only, so sleep vote 0; normal variants vote the same KHz in both sets (`clock-rpm.c:73-87`; ids `clock-8226.c:183-219`). `mmssnoc_ahb_a` 40 MHz is active-only (`:3620-3625`). The final sleep values depend on msm_bus clients and are not derivable from source alone. |
| CX (VDD_DIG) | `smpa` 1, key `corn` 0x6e726f63 | `8226_s1_corner` set=3 (both) for vdd_dig/USB/etc.; `8226_s1_corner_ao` set=1 for `vdd_sr2_dig` (A7 PLL), so sleep 0 (`D:.../msm8226-regulator.dtsi:129-151`, `msm8226.dtsi:1005-1007`). |
| MX | `ldoa` 3 | Sleep-only handle `8226_l3_so` set=2 with `init-voltage 750000` (`msm8226-regulator.dtsi:223-231`). It has no consumer in these DTs and no `qcom,send-defaults`, so it is not sent unless used [V grep; probe sends defaults only with that property, `rpm-smd-regulator.c:1486-1513`]. |
| L8 (SR2 PLL 1.8 V) | `ldoa` 8 | `l8_ao` set=1 is used by `vdd_sr2_pll` (`msm8226.dtsi:1006`), so it is off in sleep. `l8_so` (set=2, init-enable 0) is unused, like l3_so. |
| VS1 | `vsa` 1 | `regulator-always-on` (sturgeon-pm.dtsi:143-147). Stays on in sleep. |

Regulator keys: `swen` 0x6e657773, `uv` 0x7675, `ma` 0x616d, `corn`,
`lsmd`, `ssmd`, `pcen`, `pcmd`, `freq`, `hr`, `vfc`
(`rpm-smd-regulator.c:113-129`).

**GCC hygiene done once at boot** (`clock-8226.c:3597-3610`) [V]: set GPLL0
in APCS_GPLL_ENA_VOTE, and write **APCS_CLOCK_SLEEP_ENA_VOTE (0xfc401488) =
0**, "No clocks need to be enabled during sleep". [I] A nonzero value left
by the bootloader keeps branch clocks, and with them XO, requested during
APSS sleep.

### 3.3 What the RPM does on wake

This is all [I]: RPM firmware, not in the kernel. The RPM detects the wake,
re-enables XO/PLLs and raises CX/MX to the active-set corners. It sends the
APSS bringup (master stats `bringup_req`/`bringup_ack`, plus
`wakeup_reason`: 0 = rude, 1 = scheduled; `rpm_master_stat.c:53-63`), then
raises SPI 171. The vMPM STATUS words show which pins fired.

### 3.4 Instrumentation (read-only, safe)

- **RPM sleep stats** at 0xfc19dba0, version 2, **2 records of 48 bytes**
  (`D:drivers/soc/qcom/rpm_stats.c:61-69, 110-160, 286-290`):
  `{u32 stat_type (4-char ASCII, e.g. XO-shutdown / VDD-min), u32 count,
  u64 last_entered, u64 last_exited, u64 accumulated (19.2 MHz ticks),
  u32 client_votes, u32 reserved[3]}`. The XO-shutdown and VDD-min counts
  are the success criteria.
- **APSS master stats** at 0xfc428150 + 0
  (`rpm_master_stat.c:53-63, 109-150`): `+0 active_cores`,
  `+4 numshutdowns`, `+8 shutdown_req (u64)`, `+0x10 wakeup_ind`,
  `+0x18 bringup_req`, `+0x20 bringup_ack`, `+0x28 wakeup_reason`,
  `+0x2c/+0x30` transition durations. MPSS, LPSS and PRONTO follow at
  +2560, +5120 and +7680.
- **MPM2 sleep counter** at 0xfc4a3000 (32768 Hz, survives XO off) for
  measuring the time actually slept.

---

## 4. MPM

### 4.1 Hardware and transport

- The vMPM is a register image in RPM message RAM at **0xfc4281d0**. The
  APSS writes it and then interrupts the RPM by writing **(1 << 1) = 0x2 to
  0xf9011008** (`qcom,ipc-bit-offset = <1>`). The RPM copies it into the
  real MPM block before sleep (`pm.dtsi:208-216`; `mpm-of.c:156-229,
  697-729`) [V].
- ML's `irq-qcom-mpm.c` does the same through a mailbox ("Notify RPM to
  write vMPM into HW", `mpm_pd_power_off`). That driver targets newer SoCs,
  with no timer words and the ENABLE register first [V].
- 64 pins, register width 2 words (`D:include/linux/irqchip/msm-mpm-irq.h:20`,
  `mpm-of.c:76`).

vMPM layout (`mpm-of.c:113-120, 156-172`) [V]:

| Offset | Register | Contents |
|---|---|---|
| +0x00 / +0x04 | WAKEUP | 64-bit **absolute CNTPCT** wake time, low then high (`~0` = none) |
| +0x08 / +0x0c | ENABLE | pins 0-31 / 32-63 |
| +0x10 / +0x14 | FALLING_EDGE | |
| +0x18 / +0x1c | RISING_EDGE | |
| +0x20 / +0x24 | POLARITY | 1 = active high |
| +0x28 / +0x2c | STATUS | kernel writes 0 before sleep; after wake, pending pins |

Write sequence (`msm_mpm_set`, `mpm-of.c:193-229`): for each word index i
in 0..1, write WAKEUP[i], ENABLE[i], FALLING[i], RISING[i], POLARITY[i],
STATUS[i] = 0. Then wmb, then IPC.

In suspend the ENABLE word is the **wake** set; in idle it is the
**enabled** set (`mpm-of.c:202`).

### 4.2 Trigger-type encoding

`mpm-of.c:306-351` [V]:

| Linux type | FALLING | RISING | POLARITY |
|---|---|---|---|
| edge rising | 0 | 1 | 0 |
| edge falling | 1 | 0 | 0 |
| level high | 0 | 0 | 1 |
| level low | 0 | 0 | 0 |

### 4.3 Pin map relevant to sturgeon

`pm.dtsi:219-332` [V]. In `<pin hwirq>`, hwirq is the GIC ID (SPI + 32) or
the GPIO number.

| MPM pin | Source | Use on sturgeon | Type to program |
|---|---|---|---|
| 62 | GIC 222 = SPI 190 `ee0_krait_hlos_spmi_periph_irq` (`msm8226.dtsi:941-952`) | **All PMIC interrupts**: PON KPDPWR (periph 0x800, `msm-pm8226.dtsi:30-37`), RTC alarm (0x6100, irq 0x61, `:498-500`), charger/USB_IN | level high (the arbiter requests IRQF_TRIGGER_HIGH, `spmi-pmic-arb.c:1132-1133`) |
| 8 | GPIO 17 | Touch attention (synaptics, `interrupts = <17 0x2008>` = level-low + oneshot, `synaptics-dsx.dtsi:23,29`; `synaptics,is_wake` in sturgeon-common:19) | level low |
| 29 | GPIO 65 | MCU→AP wake (`mcu-wake-ap-gpio`, sturgeon-mcu.dtsi:38-43) | per driver (type 0 in DT) |
| 28 | GPIO 64 | BT host-wake, polarity 0 (sturgeon-bcm.dtsi:44-45) | level low [I] |
| 38 | GPIO 108 | `mcu-ap-status-gpio` | |
| 47 | GIC 172 = SPI 140 | USB `async_irq` of `usb@f9a55000` (`msm8226.dtsi:332-336`; the pm.dtsi comment says hsic) | |
| 53 | GIC 104 | MDSS | |
| 2 | GIC 216 | TSENS upper/lower | |

Other GPIO pins: 3/1, 4/4, 5/5, 6/9, 7/13, 9/21, 10/27, 11/29, 12/31,
13/33, 14/35, 15/37, 16/38, 17/39, 18/41, 19/46, 20/48 … 25/54, 26/62,
27/63, 30/66 … 35/72, 36/106 … 40/110, 41/115, 54/111, 55/113.

**Bypassed IRQs** (pin 0xff: never monitored, but they do not block XO
shutdown either): arch timer PPIs 18/19, QTimer 39/40, WDT bark 35, **TLMM
summary 240**, all `rpm_ipc` lines including **SMD RPM 200**, USB HS 166,
BLSP1 QUP5 131 (touch I2C), UART3 141, SDC1/2, LPASS/WCNSS lines and more
(`pm.dtsi:223-289`). Consequences:

- Timers cannot wake the system from RPM-assisted sleep themselves; the
  vMPM WAKEUP time stands in for them.
- GPIO wake has to come through the gpio-map pins, not the summary IRQ.

**Unlisted IRQs block deep sleep.** A wake-enabled IRQ that is neither
mapped nor bypassed sets `allow = false`. The MPM driver then keeps the
`cxo_lpm_clk` vote, so the CXO sleep vote stays 1 and XO cannot shut down
(`mpm-of.c:255-303, 483-529, 596-632`) [V]. Bare metal: only enable wake
on mapped sources if you want XO off.

### 4.4 Interrupts that must stay GIC-enabled across sleep

- **SPI 171 (GIC 203)**, rising edge, the MPM/RPM wake interrupt
  (`pm.dtsi:213`; `mpm-of.c:731-752`). Ack it after wake by clearing it in
  the GIC. Its handler only returns IRQ_HANDLED.
- The actual wake source's GIC line, e.g. SPI 190 (GIC 222) for PMIC, or
  the TLMM summary SPI 208 (GIC 240) for GPIOs.
- **Masked** during sleep: SMD RPM SPI 168 (GIC 200)
  (`rpm-smd.c:1357`).
- After wake, edge-type wake IRQs may not be latched in the GIC/TLMM. The
  kernel re-pends them from vMPM STATUS (`mpm-of.c:576-593`). Bare metal:
  treat the STATUS bits as "this source fired" and poll the device (touch
  controller status, PMIC interrupt status) rather than relying on a
  latched GIC pending bit.

### 4.5 PMIC-side requirements for pin 62

These must already be set up, as they are at runtime [V register names,
`D:drivers/spmi/qpnp-int.c:41-48`; I: the bare-metal applicability]:

- Per PMIC peripheral: `SET_TYPE` (0x11), `POLARITY_HIGH`/`LOW`
  (0x12/0x13), `LATCHED_CLR` (0x14), `EN_SET` (0x15).
- On the arbiter: the peripheral's APID accumulator enabled
  (`SPMI_PIC_ACC_ENABLEn`, base+0x200+4*n on v1, `spmi-pmic-arb.c:129,
  255`).

Without these, power key or RTC alarm never asserts SPI 190.

---

## 5. Timer during sleep

- **System sleep (RPM-assisted):** the only timer wake is the **vMPM
  WAKEUP** value, an absolute CNTPCT (19.2 MHz) time. The RPM/MPM runs it
  from the 32 kHz sleep clock.
  - Downstream computes it from the next timer event: `sclk = us / 30`,
    `wakeup = sclk * 19200000 / 32768 + cntpct` (`lpm-levels.c:484-493`,
    `mpm-of.c:531-551`). The `/30` is a slightly short approximation of
    `/30.5`, so wakeups come early, never late.
  - In suspend this gives the ~72.8 min ceiling (§2.4.3). Real alarms use
    the **PMIC RTC alarm** (pm8226 0x6100) through MPM pin 62.
- **Standalone PC (core only, L2 and GIC alive):** the per-core arch timer
  is lost [I; DT `use-broadcast-timer`, `pm.dtsi:192,202`]. Downstream uses
  the broadcast timer, the QTimer memory-mapped frame 0 at 0xf9021000
  (CNTP_TVAL +0x28, CNTP_CTL +0x2c, physical IRQ **SPI 8 = GIC 40**;
  `msm8226.dtsi:116-129`, `D:drivers/clocksource/arm_arch_timer.c:33-39,
  80-122`). Use frame 0 for bare-metal SPC wakeups. Keep the CP15 timer for
  WFI-only operation.
- WFI (clock gating): the CP15 CNTP tick works as now. In the cpuidle path
  the kernel also arms an hrtimer early by the level latency
  (`lpm-levels.c:180-186, 313-323`).

---

## 6. Recommended bare-metal bring-up order

Each step gives a measurable drop or a measurable counter change. All
current numbers are expectations only [I]. The 127 mA starting point
suggests the CPU is at a high clock with many rails and clocks still voted
on.

**0. Instrumentation, no risk.**

- Add readers for RPM sleep stats (0xfc19dba0), APSS master stats
  (0xfc428150) and the MPM2 sleep counter (0xfc4a3000).
- Dump GCC 0xfc401480/1484/1488.
- Read the SAW IDs/versions: 0xf9089fd0 and 0xf9012fd0 should read major 2,
  minor 1. Also read the current SPM_CTL of both SAWs; record what the
  bootloader left.

**1. Hygiene, low risk.**

- Write APCS_CLOCK_SLEEP_ENA_VOTE = 0.
- Turn off every RPM resource you do not need, in the active set.
- Lower the A7 clock before idling, if not already done.
- Measure. This is likely the largest single drop while the CPU still only
  does WFI.

**2. CPU0 SAW clock-gating WFI, low risk.**

- Program the CPU0 SAW (§2.2): sequence first, then CFG, DLY,
  SPM_CTL=0x08, then SPM_CTL=0x09.
- WFI now goes through the SPM. Small drop.
- Risk: a corrupted sequence hangs the WFI. Recovery: the APCS watchdog
  bite is still active (core only).

**3. Warm-boot plumbing via standalone PC, medium risk.**

1. Register the warm-boot vector with SCM (buffer form, or atomic
   0x00401222 with flags 0x04).
2. Implement save, cache clean, SMC 0x00402221 with r2 = 0, and resume.
3. Set CPU0 SAW SPM_CTL = 0x59. Leave the L2 SAW disabled.
4. Wake: QTimer frame 0 (GIC 40) or a GPIO/PMIC IRQ enabled in the GIC.
5. Check: a resume counter increments (and bailouts are counted). Measure
   the core-leakage drop.

Risks:

- A wrong entry address or mode means no return. Keep the APCS WDT
  (0xf9017000) running with `scm_wdog_debug_disable()` done, so a bite
  resets the chip. The core-only collapse leaves the WDT powered [I].
- Bailout (immediate return) is normal when an interrupt is pending. Make
  sure the tick IRQ is quiesced.

**4. Full APCS PC with the RPM handshake, XO kept, higher risk.**

1. Sleep set CXO `clk0/0 Enab = 1` (set 1) to isolate the step.
2. Program the L2 SAW (§2.2): SPM_CTL = 0x1a1 just before sleep, EN clear
   after.
3. vMPM: WAKEUP = cntpct + 5 s; ENABLE pin 62 (polarity 1); STATUS = 0.
   Then IPC 0x2.
4. GIC: enable 203; disable 200; keep the wake source line enabled.
5. Flush all caches, then SMC 0x00402221 with **r2 = 1**.
6. Check: APSS master stats `numshutdowns` +1, and the wake comes after
   about 5 s (MPM2 counter).

Risks:

- If SPI 171 is not enabled, the vMPM is wrong or the IPC is missed, the
  chip never wakes. The APCS WDT is probably not running with the APC rail
  off [I]. **Recovery is the PMIC power-key long press.** Downstream
  configures KPDPWR S1 = 10256 ms, S2 = 10 ms, S2 type 7 (hard reset)
  (`apq8026-sturgeon-pm.dtsi:76-82`). That configuration is written by the
  Linux qpnp-power-on driver; **verify or program the PON KPDPWR S1/S2 reset
  registers (PMIC 0x840 S1_TIMER, 0x841 S2_TIMER, 0x842 S2_CNTL,
  0x843 S2_CNTL2; `D:drivers/platform/msm/qpnp-power-on.c:49-52`) before
  this step**. Otherwise only battery
  drain or charger insertion (pin 62, if enabled) recovers.
- Cores 1-3 have never been released, so their ACC/SAW were never touched
  (`D:arch/arm/mach-msm/platsmp.c` release code). Whether the L2 SAW treats
  never-powered cores as down is **not verified** [I]. Linux always has
  them in hotplug-PC. If `numshutdowns` never increments, boot each
  secondary into a stub that sets its own SAW to pc (0x199) and issues SMC
  TERMINATE_PC with `0x10 | 0`, then retry.
- Stale sleep-set acks in the SMD RX FIFO after wake: drain them.

**5. XO shutdown.**

- Sleep set `clk0/0 Enab = 0`.
- Wake-enable only MPM-mapped sources.
- Check that the RPM stats XO-shutdown count increments and the current
  drops sharply.
- If it does not: other masters (MPSS/LPASS/WCNSS are not booted here;
  their RPM-side votes are unknown), sleep-set rails or a GCC sleep vote are
  holding XO.

**6. VDD min and rail trimming.**

- Send sleep-set `swen = 0` for every LDO/LVS that is not needed while
  asleep: display rails, USB L10/L20, etc. Keep the touch rails (L19, LVS1)
  on if touch is a wake source. VS1 is always on downstream anyway.
- Add MX `ldoa 3 uv = 750000` in the sleep set as the DT intends [I].
- Check that the VDD-min count increments. Linux reaches a few mA here.

**7. Wake sources.**

- Pin 62 (power key via PON INT_EN, RTC alarm, charger).
- Pin 8 (touch GPIO 17, level low). The touch IC must stay powered and
  configured for wake gestures.
- Pin 29 (MCU wake), pin 28 (BT host-wake).
- For each, verify in vMPM STATUS after wake.

## 7. Open points

- SPM command byte semantics, SAW SPM_CTL bit 3 and PMIC_DATA bits 25:24
  are undocumented here.
- How the TZ handles L2 for flag 1 on Cortex-A7 (whether it also cleans L2)
  is unknown. The kernel flushes everything itself, so do the same.
- The RPM's treatment of the APSS master when the APSS has never sent a
  sleep set is unknown.
- Which sleep-set values Linux actually holds at suspend on a real
  sturgeon needs a runtime dump. `msm_rpm_flush_requests(print=true)` or
  the rpm-smd debug mask would show it, but the downstream passes print=0
  (`lpm-levels.c:486`). If an AsteroidOS kernel on sturgeon is still
  available, enabling that print is the cheapest way to get the exact
  list.

## 8. Bring-up results (2026-10-27)

- **Secondaries must be parked first.** With cores 1-3 never started, any
  TERMINATE_PC with a cluster flag (1 or 3) never returns. Starting them
  (ACC release sequence `arm_release_secondary`, cold+warm boot address via
  `scm_call2(1,1,0x29/0x52,stub)`) into a stub that sets its SAW to 0x59 and
  calls TERMINATE_PC `0x10|0` fixes it. Afterwards the ACC status shows
  bit 19 and the park counter is 1 per core.
- **Flag 1 (L2 off) works exactly once.** After one real cluster power
  down every later flag-1 call hangs, even without the L2 SAW; flag 0 core
  collapse keeps working. Not caused by: GIC state, SAW config, PLL,
  L2CTLR/ACTLR, S:7 handoff lock (TZ does release it), RST of the L2 SAW,
  re-parking the secondaries (works, park count 2), timing. Workaround in
  the firmware: always flag 0 + L2 SAW pc (0x1a1) + own full cache
  clean/invalidate; 1700+ cycles without a fault.
- RPM master stats confirm each cycle (numshutdowns, wakeup_reason 1 =
  scheduled by the vMPM timer). With the CXO sleep vote 0 the RPM "vmin"
  count increments every cycle; USB drops while XO is off.
- A wake time < ~20 ms ahead hangs the VDD-min path; the firmware falls
  back to core collapse then.
- SMBB USB_RT_STS USBIN_VALID (0x1310 bit 1) stays set after unplug; PON
  0x810 bit 2 is never set. The ChipIdea PORTSC (CCS && !SUSP) is the
  reliable "host present" signal; a new host's bus reset clears SUSP even
  while the CPU sleeps, so enumeration works when XO is kept on then.
- Coulomb counter: PM8226 BMS 0x4000, CC_DATA0 0x408a (36-bit), hold via
  0x4042 bit 0; uAs = dcc * 542535 * 56 / 32764 / 970. Frozen while USB
  power is present. Linux BMS uses the same rsense (9700 uOhm).
- **Current, unplugged (CC average):** core collapse 72 mA, cluster/VDD min
  62 mA. AsteroidOS awake with screen off ~40-50 mA. S2 (APC FTS2) was in
  PWM (0x11745 = 0x80) → auto saves ~6 mA. Ruled out as the remaining
  floor: L12/17/18/19/21/S4 off, LDO LPM, panel (DSTB, reset, enable),
  MCU reset (-4 mA), GPIO 58/59/114 to Linux's config. Measuring on
  battery while plugged: write 0x1347 = 1 (USB_SUSP).

### 8.1 Floor hunt (2026-10-27, later)

- AsteroidOS suspended with AOD, unplugged: ~4-7 mA average (charge
  counter before/after a 227 s suspend, charging parts subtracted). The
  firmware in VDD min: 47-62 mA (varies between runs; compare only within
  a run). So ~45 mA is unexplained.
- Timebase verified: CNTPCT vs MPM2 sleep counter agree within 1%.
- BMS IADC trim (0x36f2/3) equals Linux's, 0x3848 = 1 (external rsense);
  gain-offset 3267 vs ideal 3291. The CC reading is trustworthy.
- Within-run effects: USB PHY LPM (ULPI 0x98 clear 3, PORTSC PHCD, USBCMD
  bits 29/30) -7 mA; DSI PLL GLB_CFG 0xfd922a20=0 + PHY 0xfd922c70/d98=0
  -2 mA. No effect: L10/L20 off, A7 PLL off, GPIO60 (DRV2605 EN) low,
  MCU sleep handshake (108/62 low or 108 high), MCU reset, flash enable
  0x1d346 0x60 -> 0 (Linux has 0), sleep-set bus 0 / CX ret / MX 750 mV /
  LDOs off. WLED/LPG/vibrator are off. MMPLL0/1/2 off.
- Booting AsteroidOS first and then warm-rebooting into the firmware does
  not lower the floor (48 mA), so it is no persistent setting Linux makes.
- Codex review (codex-answer in the session scratchpad) ranked USB/DSI PHY
  first; the local kernel checkout is minnow/sturgeon-kernel at the
  AsteroidOS recipe commit.

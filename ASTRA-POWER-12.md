**§23’s arithmetic holds; “A adds no detectable saving” holds. “A equals V within ±0.1 mA” and “wakes cannot matter” are stronger than the evidence.** Read-only review completed; no edits, commits or device access. **READ** includes calculations from the supplied logs; **INFER** marks interpretation.

**1. Numbers and wakes.** **READ:** I merged consecutive identical masks, discarded the first 180 seconds after each change, and retained only complete approximately 60-second intervals. Each treatment has 36 retained intervals; the initial B has 16. Contrasts use the mean of the bracketing B blocks. The unbracketed final A is excluded. [Night log:535](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-night-gav-2026-11-06-sturgeon.txt:535)

| Treatment | Block contrasts against B, mA | Mean |
|---|---|---|
| G | +0.209, +0.393, +0.246 | **+0.283** |
| V | −0.393, −0.248 | **−0.320** |
| A | −0.433, −0.259 | **−0.346** |

**INFER:** A−V = **−0.026 mA**. Pairing their contrasts within each schedule cycle gives −0.041 and −0.011. Even that favourable pairing yields an illustrative 95% *t* interval of approximately **−0.22 to +0.17 mA**, assuming independent, normally distributed cycle errors. Two cycles cannot validate those assumptions or remove fixed-order drift. Thus ±0.1 is not an established confidence bound; neither equivalence nor physical non-additivity is proved.

**READ:** Retained blocks average **29 ms/min outside VDD-min**, using the independent 32.768-kHz counter; subtracting residency from the CC interval gives approximately 36 ms. The misleadingly named `slept` field is elapsed sleep-clock time, not a separate CPU-residency measurement. [main.c:824](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:824)

**INFER:** At an assumed **100 mA battery current throughout non-VDD-min time**, that contributes roughly **0.05–0.06 mA**. Your scale argument is sound; the unconditional bound is not: 100 mA is assumed, and wake-triggered peripheral activity or calibration effects can persist inside VDD-min. A 60-versus-300-second comparison is low priority for explaining a substantial gap, but not meaningless. The counter establishes RPM-labelled residency, **not CX/MX voltage, rail modes, peripheral shutdown or identical Linux sleep state**. Its layout matches the vendor driver. [rpm_stats.c:61](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/soc/qcom/rpm_stats.c:61)

**2. Why savings may fail to add.** **READ:** A physically removed L4/L15, so this is not merely an acknowledged off request. The IADC calibration averages 64 noisy conversions; one trim code corresponds to roughly half a milliampere. Longer integration reduces sample noise but does not eliminate offset drift. [Night log:946](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-night-gav-2026-11-06-sturgeon.txt:946), [pmic.c:647](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:647)

**INFER:** Shared-parent bias savings, automatic PFM/PWM transitions, and RPM aggregation could make effects nonlinear. **Sharing a parent alone does not explain non-additivity**, and the inspected material does not establish a common parent for these particular rails. RPM also retains sleep overrides; absent overrides inherit active requests, while other consumers can maintain a resource. [rpm-smd-regulator.c:538](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:538)

**Cheapest discriminating test:** repeat **V–A–A–V**, then reverse it, with settled temperature, unchanged calibration cadence and physical-enable checks. This directly measures the missing incremental saving without subtracting separate B contrasts. If still null, a same-session **B/L/V/L+V factorial** separates reproducible interaction from §22 drift; record SMPS mode/voltage alongside it. Do not alter calibration and rail policy simultaneously.

**3. Remaining candidates, ranked — INFER ranking; READ evidence.**

| Rank | What remains possible | Settled now versus new evidence |
|---|---|---|
| **1** | **CX/MX corners and L3/L8 sleep ownership** | Linux defines CX active/both-set consumers, L3 sleep-only initialization at **750 mV**, and L8 sleep-only disable. These declarations do not prove effective aggregate sleep voltage. Neither firmware RPM implementation establishes equivalent CX/MX policy. Capture Linux requests from boot through suspend; awake register reads cannot settle actual VDD-min rails. **Do not repeat blanket L8 LPM.** [DT:223](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:223), [DT:296](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:296), [sleep-parity rpm.c:275](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-sleep/src/soc/rpm.c:275) |
| **2** | **GPIO pulls, pad contention, powered BT/hub/touch interfaces** | Firmware UART stop makes pins inputs with pulldowns; Linux’s board UART configuration uses no pulls. A powered peer driving high can therefore draw through a pull. Hub reset is not rail removal. Notably, the Linux snapshot shows **BT reset GPIO67 high**, despite the nominal BT-off comparison: verify rfkill state. Existing GPIO output lacks complete pull/mux evidence; capture raw TLMM and suspend transitions. [uart_dm.c:327](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/uart_dm.c:327), [gpiomux.c:144](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:144), [snapshot:925](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/snap/aos-snap-1793824759.txt:925) |
| **3** | **PMIC BMS/IADC operation, vibrator, LPG, clocks/XO buffers** | Existing captures contain trim, not the full peripheral controls. Compare BMS sampling/enable configuration, vibrator/LPG enables, and XO-buffer votes; do not assume BMS should be off. Sturgeon also has external vibrator control pins. New control-register captures are needed; RPM clock logging covers requests, not every physical buffer state. [snapshot script:39](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/aos-snapshot.sh:39), [PMIC DT:792](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:792) |
| **4** | **SMPS mode/voltage and remaining clock policy** | Existing **awake** firmware/Linux snapshots already agree: S1–S4 `40 80`, S5 `80 00`; this weakens a simple persistent mode mismatch. Auto-mode agreement does not prove identical switching behaviour or sleep voltage. Harness bus sleep votes are zero; production uses Linux-like 100 kHz votes. New sleep-request evidence remains necessary. [fw-regs:50](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/fw-regs.txt:50), [Linux snapshot:83](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/snap/aos-snap-1793824759.txt:83) |

For the **next AsteroidOS capture**, these are proposed commands, not executed. Copy the existing snapshot script to `/tmp/aos-snapshot.sh`; then, in a root shell:

```sh
cat /sys/module/rpm_smd_regulator/parameters/debug_mask > /tmp/vreg-mask.old
cat /sys/module/rpm_smd/parameters/debug_mask > /tmp/rpm-mask.old
echo 7 > /sys/module/rpm_smd_regulator/parameters/debug_mask
echo 5 > /sys/module/rpm_smd/parameters/debug_mask
systemd-run --unit=parity-snap --on-active=120 \
  --timer-property=WakeSystem=true /bin/sh /tmp/aos-snapshot.sh
```

Let the screen turn off, unplug, and allow suspend/timer-resume. After replug:

```sh
journalctl -k -b -o short-monotonic > /tmp/parity-kernel.log
cat /sys/class/rfkill/rfkill*/{name,state} > /tmp/parity-rfkill.txt
cat /tmp/vreg-mask.old > /sys/module/rpm_smd_regulator/parameters/debug_mask
cat /tmp/rpm-mask.old > /sys/module/rpm_smd/parameters/debug_mask
```

Use `rpm_smd_regulator.debug_mask=7 rpm_smd.debug_mask=5` on the **next kernel command line** to capture initialization too: runtime enabling cannot recover unchanged earlier requests. Regulator mask 7 includes duplicate/cached aggregates; distinguish `cached`, `prev`, and `sent`. [regulator driver:295](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:295), [RPM driver:43](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/soc/qcom/rpm-smd.c:43)

Additional control reads, using the existing SPMI debug interface:

```sh
S=/sys/kernel/debug/spmi/spmi-0
for a in 0x3640 0x3840 0x4040 0x1c040 \
         0x1b140 0x1b240 0x1b340 0x1b440 0x1b540 0x1b640; do
  echo "$a" > "$S/address"; echo 64 > "$S/count"; cat "$S/data"
done > /tmp/parity-peripherals.txt
```

These are **awake/post-resume** controls. Definitive transient sleep pins/rail settings require suspend-stage instrumentation or RPM-side evidence; no userspace snapshot can read while its own AP is collapsed.

**4. Before reboot. INFER:** preserve volatile evidence, but no urgent experiment is required. Save the remaining console log and run `status`, `mem fc19dba0 12`, `mem fc19dbd0 12`, and `pmic 36f2 2`. Replug already restored the measures and restarted BT, so current reads cannot recover last night’s asleep rails. Eleven hours’ uptime adds history, not a unique measurement opportunity. [Night log:2956](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-night-gav-2026-11-06-sturgeon.txt:2956)

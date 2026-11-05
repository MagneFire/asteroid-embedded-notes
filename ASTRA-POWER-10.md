# Codex (gpt-6-astra) power round 10, 2026-11-05: measures to vendor-parity commits

**Keep vendor parity as the criterion, but replace the harness’s blanket sleep policy.** No edits, commits, or device access. **READ** below means inspected source/logs; **INFER** means recommendation or interpretation.

| Measure | READ: vendor/current behavior | INFER: real commit |
|---|---|---|
| **U — committed** | Vendor uses PHCD/STP and clock gating, with distinct charger/bus-suspend restrictions. Firmware’s unplugged policy is committed in `2751917`. [phy-msm-usb.c:1002](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1002) | **Keep.** Gate on **USB absent**, independently of screen/AOD. Charger-only suspend needs source classification; non-enumeration does not justify cutting supplies. |
| **R — bus votes** | Linux snapshot has **100 kHz** non-active-only BIMC/PNOC/SNOC votes; harness requests zero. GCC sleep-enable zero matches vendor. These are votes, not measured asleep frequencies. [snapshot:904](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/snap/aos-snap-1793824759.txt:904), [rpm.c:253](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:253) | **Replace zero with vendor-matching sleep votes**—100 in RPM’s kHz units for confirmed buses; verify CNOC separately. Preserve active rates and GCC zero. |
| **H / S — hub** | Vendor lowers AP_STATUS and enables MCU wake; firmware already has that handshake. H resets/reinitializes the MCU; S disables tilt **and steps**. [hwmcusleep.c:145](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmcu/hwmcusleep.c:145), [hub.c:488](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:488) | **Drop H; replace blanket S with per-service policy.** Keep MCU running, requested step counting active, tilt active when enabled, unrequested sensors off. AP_STATUS low during AP sleep, wake interrupt retained. S’s null result supports this direction, but does not price enabled services. |
| **T / Q — touch** | **Tap-to-wake exists**, default enabled; current firmware wakes on `TOUCH_DOWN`. Vendor gesture suspend preserves power/IRQ; non-gesture suspend sleeps the sensor and disables its analog supply. [main.c:522](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:522), [synaptics_dsx_core.c:3851](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3851) | **Replace unconditional T/Q.** Tap enabled: vendor gesture mode, doze cycle **8 (80 ms)**, L19/LVS1 retained, wake IRQ enabled, gesture-report decoding and normal-mode restoration. Merely setting F01 sleep breaks tap. Tap disabled: T then Q is the vendor branch; validate power-cycle recovery/pin isolation. Applies during inactive UI, including AOD. |
| **E — eMMC** | Vendor sleeps the card, powers down VCC/L17 through host power policy, and reinitializes on resume. L6 interface supply is retained. Harness only CMD5-sleeps and gates clocks. [mmc.c:1852](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/core/mmc.c:1852), [sdhci-msm.c:1897](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1897) | **Keep E first; add L17-off separately**, with full re-identification. Gate on storage quiescence, wake lazily before I/O—not every timer/AOD wake. Charging does not itself require storage awake. |
| **V — USB L10/L20** | Vendor removes supplies only in eligible collapse states, excluding DCP and host/device bus suspend. [phy-msm-usb.c:1085](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1085) | **Keep**, after successful U, **USB absent only**; restore supplies before PHY access. Null savings do not invalidate parity. |
| **M — L4/L6 LPM** | Vendor full panel-off disables L4. L6 is always-on; lowering its load requires `lpm_sup`, absent from the inspected sturgeon DT configuration. Harness’s fixed 1 mA sleep requests are not that policy. [sdhci-msm.c:1919](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1919) | **Drop blanket M.** Put rail/load management under its actual consumers; retain L6’s vendor configuration. |
| **A — amplifier** | Captured idle register `09=0265` already has powerdown set. Harness implements a speaker-stop sequence, not an established kernel suspend requirement. [POWER.md:908](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:908), [speaker.c:48](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/audio/speaker.c:48) | **Drop A as a sleep measure.** An eventual audio driver should own mute/powerdown whenever playback stops, including awake idle. |
| **P — panel** | Vendor sends deep-standby commands, releases supplies/reset, and fully initializes on wake. Physical snapshots retain L8; P leaves all rails supplied. [ASTRA-POWER-9.md:17](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/ASTRA-POWER-9.md:17) | **Keep commands, then add L4/L15 shutdown separately.** Vendor sequencing supports feasibility, not proven firmware safety. Retain L8; restore L4 → 20 ms → L15, enable/reset, full initialization. Budget roughly **155 ms minimum wake delays**, plus initialization; off commands wait 375 ms. **Never deep-standby/cut supplies during AOD**, including nightstand AOD. |
| **D — SD rails** | Sturgeon disables SDC2; Linux snapshots have L18/L21 off. Exact boot-time shutdown provenance remains unproven. [ASTRA-POWER-9.md:7](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/ASTRA-POWER-9.md:7) | **Keep as board-declared unused-rail cleanup**, once at initialization, independent of screen/AOD/charger. Preserve voltage/mode; exclude any SD/TPIU consumer. |

**INFER — commit order:** R → board-declared D → V → service-aware hub → E without rail removal → gesture-aware T/Q → panel commands → panel rails → eMMC L17. Drop H/M/A harness policies. Each commit should own rollback/error handling and validate its transition before proceeding.

Use runtime board capabilities and driver callbacks. Sturgeon has RM69080/RMI4/STM32/TFA9895; sparrow has RM69032/IT7260/EM7184/no speaker. Sparrow touch additionally consumes **L6**, alongside L19/LVS1, and its hub already implements AP-suspended signaling. Thus sturgeon Q/M/panel assumptions cannot be shared blindly. Add explicit rail lists, panel sequences/reset pins and supported policies; leave unverified sparrow rail shutdown disabled. [sparrow.c:84](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/board/sparrow.c:84), [touch_it7260.c:88](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch_it7260.c:88), [hub_em7184.c:812](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub_em7184.c:812)

**READ/INFER — extraction hazards:** keep out `powertest`/`measures`, masks/schedules, forced BT/AOD settings, USB hold-up, rest-level comparisons, BATFET experiments, calibration/statistics instrumentation and their test stubs. Replace the `panel.lines == 434` capability test. RPM retains keys independently: conflicting sleep-set `swen` can resurrect a rail; give each rail one owner and track partial failures. Never import the L8/L19 LPM profiles that reset the watch. E must honor card wake timing and block transfers after failed recovery; H caused calibration reads/eMMC wake and about **11 seconds** to reach S in the night run. S currently marks success after transmission, not validated service acknowledgements. [rpm.c:297](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:297), [night log:1496](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-night-2026-11-05-sturgeon.txt:1496)

**Before reboot — INFER:** capture cumulative RPM records and restored state; nothing uniquely requires another experiment now. Proposed console commands, one per line:

```text
status
hub
mem fc19dba0 12
mem fc19dbd0 12
mem fc401488 1
mem fd511190 2
mem fd5114e0 2
mem fd5116c0 2
pmic 36f2 2
pmic 14345 2
pmic 14545 2
pmic 14745 2
pmic 14945 2
pmic 14e45 2
pmic 15045 2
pmic 15145 2
pmic 15245 2
pmic 15345 2
pmic 15445 2
```

These cover RPM history, GCC vote, panel/reset/AP_STATUS pins, trim and relevant rail modes/enables. **Do not issue `measures <mask>` for capture: it mutates state; bare `measures` only prints usage.** Replug already restored measures to zero, so current reads cannot recover asleep voltages or service state. [console.c:955](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:955), [night log:2369](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-night-2026-11-05-sturgeon.txt:2369)

**§21 — READ:** recomputing with whole intervals after the three-minute exclusion gives B **2.733**, D **2.885**, P **2.707**, S **2.534 mA**: your main conclusion holds. “Want=have” means **eventually**, not immediately. Three qualifications:

- **INFER:** ~2 mA AOD cost is a cross-run estimate; earlier AOD activity was inferred, not frame-logged. §19 savings remain AOD-conditioned.
- **READ:** retained B samples average trim **bbd6.1**, whereas “Linux ~2.0 mA” used §19’s **bbd7.3**. Applying that same conditional slope gives Linux ~1.4 mA and an apparent ~1.3 mA gap. **INFER:** “0–0.8 mA” is too narrow; no precise physical gap is established.
- **INFER:** 2.7 mA is the **BT-off, tap-disabled-by-T, hub-reset baseline**, not yet the feature-preserving production floor.
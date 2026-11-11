# Codex (gpt-6-astra) review of the smelt battery drain, 2026-11-09

Prompt: why smelt drains quickly under the firmware when AsteroidOS lasted longer; SMELT.md's last
sections, SMELT-M4.md §8, logs-smelt-2cfe8c9-run-2026-11-09.txt, the vendor kernel on pc,
meta-smelt. Asked to break the "worn cell, about 150 mAh, firmware matches Linux" explanation.
Read-only. K = vendor kernel on pc, L = the log.

## Verdict

**INFER: the "about 150 mAh worn cell, firmware matches Linux" conclusion is premature.** The
strongest counter-evidence is status `0002` throughout the run: POR is set. The firmware neither
restores the gauge configuration nor clears POR, and explicitly stops charging because of it on
the next boot. A worn cell remains plausible, but gauge misreporting, incomplete charging and
genuinely higher firmware consumption remain unresolved.

## 1. Current measurement

- READ: scaling agrees. Signed Current/AvgCurrent x 1.5625 uV / 10 mOhm = 156.25 uA per count.
  The firmware reverses the sign for discharge; Linux truncates its multiplier to 156 uA, 0.16 %
  (src/soc/max17050.c:36; K drivers/power/max17042_battery.c:336-368; smelt-common.dtsi:458).
- READ: vendor FilterCFG 0x87A4 is an 11.25 s time constant, also the reset default; not a
  one-minute charge integral (datasheet p.24).
- READ: src/stats.c:24-44 samples once a minute asleep and resets its deadline every second
  awake. Samples fall about 11 s after the redraw early in the log (L472-490) and just before it
  later (L1180-1193).
- INFER: sampling can miss awake tails, redraw energy and Bluetooth bursts, with a bias that
  changes with phase. The redraw spans are short and do not by themselves account for the gap.
  Absolute calibration is unverified. No source shows a path around the sense resistor; without a
  schematic it can be neither excluded nor asserted.

## 2. Percentage and missing Linux maintenance

- READ: `0002` is POR. A power-loss POR resets model, configuration and learned adjustments; the
  host must restore them. The bit is sticky, so it does not date the reset (datasheet pp.27-28,
  35).
- READ: Linux initialises on POR or a config-version mismatch: reloads the characterisation,
  FullCAP, FullCapNom, DesignCap, seeds Cycles and RepSOC, then clears POR (K driver 554-618,
  679-730, 1351-1356). Its worker is initialisation, not periodic learning. `temp-conv` only
  transforms the temperature given to userspace (315-334).
- INFER: with a valid retained configuration the gauge needs no periodic Linux work. That
  prerequisite is unverified here, so the percentage slope cannot be turned into a capacity.

## 3. What the log supports

- READ, from L1-2369: AOD ends around 14 771 s. The 236 asleep samples before average 9.63 mA,
  the 17 after 5.35 mA. Awake time 228 s. "About 50 mAh" is a reasonable sparse-sample estimate,
  not measured charge.
- READ: nine gaps over 65 s (longest 160 s) around interactive use. 34 NimBLE notifications and
  media traffic; L680-690 ends in 89 wakeups and 44 mA while nominally asleep.
- READ: the level falls 39 -> 37 over 44 min, then 24 -> 20 over 28 min at similar asleep
  readings (L788, 1200, 1925, 2067). At 37 % the voltage falls 3826 -> 3429 mV across a wake
  (L1200-1206); at the end 17 % recovers to 3735 mV (L2364).
- INFER: the sag supports high cell or path resistance, not a particular capacity. The uneven
  fall undermines a proportional calculation. The 2026-11-07 Linux samples cannot establish total
  consumption or parity within 1 mA either (SMELT-M4.md:153-163).

## 4. Real Linux advantages

- READ: L2400-2401 says "charging stopped ... 17%, gauge not trusted";
  src/soc/gauge_max17050.c:85-96 rejects POR. Linux repairs it. The firmware also applies the
  thermal limits from boot and counts five taper readings at 30 s polls against healthd's 60 s
  (charge_policy.c:1-17; SMELT.md:48-55).
- INFER: a shorter runtime could be incomplete charging; this log cannot show the starting charge.
- READ: the firmware omits the panel idle commands, keeps the panel powered when blanked and keeps
  the hub accelerometer on; the worktree addresses the display, not the hub. Both sides cap the
  ambient backlight at code 36. meta-smelt enables Bluetooth LPM and CPU collapse
  (patchram.service:8, underclock:4-19). INFER: credible differences, not quantified.

## Measurements proposed

- Under 10 min: snapshot the gauge from the firmware before Linux boots, then after Linux has
  initialised it: Status, FullCAP, FullCapNom, Cycles, DesignCap, RepCap, RepSOC, FilterCFG,
  LearnCFG, Config and version. A changed model, capacity or SOC exposes the POR problem.
- 10 min per OS: compare QH (0x4D) deltas off USB with the same AOD brightness and Bluetooth
  state. QH counts charge independently of the percentage and of minute sampling. It separates
  under-counted consumption from a wrong SOC, but does not prove the cell's capacity.

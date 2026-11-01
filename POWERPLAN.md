# Where the current goes: the recurring question

"Find out where our N mA goes" has come up at every stage since the
first sleep bring-up. This file keeps the history and the lessons in one
place, so the next attempt starts from them instead of from scratch.
The working detail stays in POWER.md, SUSPEND.md and L2OFF.md; the
plan for the next attempt is at the end.

## The rounds so far

| when | figure | how measured | where | what came of it |
|---|---|---|---|---|
| 2026-10-27 | 45 mA gap, ~23 mA VDD-min floor | CC + RPM residency | SUSPEND.md §8, §8.2 | most of the gap was the firmware's own wake overhead; USB PHY LPM, DSI off, MDSS GDSC |
| 2026-10-29 | cluster power down | CC | SUSPEND.md §9, L2OFF.md | L2 collapse working |
| 2026-10-30 | ~14 mA asleep with BT (day log) | CC | POWER.md §0-§5 | ranked candidates F1-F11 |
| 2026-10-30 | F1 (no 1 Hz tick): 0 +/- 1 mA floor | CC | POWER.md §9 | tick dropped |
| 2026-10-31 | AOD/BT split: BT 5-6.5 mA, AOD 0.3-1.8 mA, floor 2.9 mA | CC, powertest arms | POWER.md §10 (second) | BT ranked largest |
| 2026-11-01 | CC 3 mA vs OCV ~14-17 mA | CC vs OCV slope | POWER.md §11-§12.2 | counter distrusted, cell capacity ~275 mAh |
| 2026-11-01 | stale IADC offset trim; CC now 12-16 mA | CC vs OCV | POWER.md §13 | 1c7378a; all CC figures before it are low by ~10 mA |

## Lessons

1. **Validate the meter before splitting the budget.** Every split before
   1c7378a used a counter that read ~10 mA low asleep (stale offset
   trim). The 0 mA floor of §9 and the 2.9 mA floor of §10 are artefacts.
   Keep a cross-check in every run: hardware OCV slope (sturgeon takes one
   every ~2 min asleep) against the CC.
2. **The vendor's housekeeping is part of the measurement.** Trim
   recalibration every 300 s, external rsense selection (0084d42), the
   board's sense resistor (83572ad): each was a silent error.
3. **Arms must be short, automated and interleaved.** Darrel finds long
   tests too long; 30 min arms ABAB give ~15 OCVs each on sturgeon and
   cancel drift. Long single runs mix in phone activity (media updates
   at 11 mA) and the first minutes off the charger (surface charge) are
   unusable.
4. **AsteroidOS is measured with its own counter.** The 1.6 mA
   reference had the same counter on its own (fresh) trim, so it is a
   real reference only if re-measured by the same CC-and-OCV method.
5. **sparrow takes no hardware OCVs**, on AsteroidOS too, so its
   voltage cross-check must come from VBAT under load or a long run.
6. Keep the harness out of main: test commands live as patches in
   `patches/` (sleep-debug-harness.patch precedent).

## Plan (2026-11-01, planning pass)

**First, a finding the plan turned up (checked in the code):** the three
most trustworthy old savings never reached main. SUSPEND.md §8.1 measured,
with a trim that matched Linux's, USB PHY LPM -7 mA, DSI PLL/PHY off -2 mA
and MDSS GDSC collapse -1 mA, in the debug harness
(`patches/sleep-debug-harness.patch`). Main has no PHCD/ULPI low power
writes in `src/usb/`, and `display_sleep()` (`src/display/display.c`) only
sends DCS 0x28/0x10. That is ~10 mA of the ~13 mA asleep.

### 1. Method: the counter is the meter, the OCV is the audit

- OCVs scatter 3-5 mV; at ~0.25 mAh/mV near 4.2 V (0.5 near 3.85 V) a
  25 min arm gives the current to only +/-2-4 mA from the OCV. The shadow
  CC (0x40a8) resolves ~1 uAs and repeated within 0.2 mA across arms.
- Log per asleep stats line: the raw 36-bit shadow CC and `time_ms()`
  (not truncated mA), wakeups, BT host-wakes, awake us between
  `spm_idle` calls, RPM VDD-min count and time (SUSPEND.md §3.4) to prove
  each arm reached VDD min, the IADC trim, die and battery temperature,
  the BT interval/latency; VBAT on sparrow. Keep the `bms: new ocv` and
  `powertest: arm` lines.
- Arms: one unplugged session of at most 2 h, no interaction. Two levels
  ABBA, 25 min arms after a 15 min settle; three or four levels mirrored
  (ABCD DCBA), 13 min arms. Drop the first 2 min of each arm; keep OCVs
  from the first 25 min after unplug out of the fits. Test floor fixes
  with BT and AOD off so they are not diluted.
- Per arm: CC mA = charge / time, SE from 5 min batch means, median of the
  blocks beside the mean, burst minutes flagged (>4 wakeups, media
  traffic). Effects as paired ABBA differences. OCV slope times the
  profile's dV/dQ at the arm's OCV and temperature (275 mAh) gives
  I_ocv +/- SE.
- Session audit: fit V = a_arm + b * Q_cc(t) (one intercept per arm takes
  the I*R step); compare b with the profile and the total CC charge with
  the pooled OCV drop. Pass when |CC - OCV| <= max(1.5 mA, 15 %); a failed
  session is not used.
- Minimum detectable difference (2 sigma): ~0.5 mA (25 min ABBA), ~0.6 mA
  per effect (13 min mirrored). Report smaller effects as "< MDD", not 0.
- sparrow gets no OCVs because its sleep current is above the BMS S3
  threshold. The vendor raises 0x4077 to lowest sleep current + 3 mA
  after an hour without one (qpnp-bms.c qpnp_bms_update_ocv_setting,
  :4999-5066); the firmware never writes it. The harness does the same at
  session start; if it behaves, it becomes a real fix.

### 2. The budget to produce (POWER.md §14), each line by difference

| component | contrast |
|---|---|
| total | baseline: AOD on, phone at its own parameters |
| BT link | bt fast - bt idle (chip on, host stopped) |
| slow BT parameters (F11) | bt fast - bt slow |
| BT chip standby | bt idle - bt off |
| AOD total | aod on - aod off, BT off |
| AOD redraw | aod on - aod static (no minute redraw) |
| AOD panel/MDSS rest | aod static - aod off |
| wake overhead | E_wake x rate, E_wake from a 30/min forced-wake arm; BT host-wakes priced the same (F2) |
| floor | bt off, aod off |
| inside the floor | USB PHY (F3), DSI PLL/PHY + GDSC (F4), hub (F7), touch (F6), eMMC (F5), LDOs (F8) |
| residual | floor minus the above: the VDD-min floor, compared with AsteroidOS's BT-off arm |

S1's 2x2 also gives the BT x AOD interaction; if above the MDD, report
the budget per context.

### 3. Sessions (each at most 2 h), then fixes

| # | session | arms | expected |
|---|---|---|---|
| S1 | skeleton | BT{fast,off} x AOD{on,off}, ABCD DCBA, 13 min | total ~13, the BT/AOD/floor shares |
| S2 | floor fixes | F3 USB PHY LPM x F4a DSI PLL/PHY off, BT and AOD off | F3 5-7 mA, F4a ~2 mA |
| S3 | BT detail | fast/slow/idle/off, AOD off | slow parameters 0.5-3 mA |
| S4 | wakes and AOD split | floor / floor + 30 wakes/min / aod on / aod static | E_wake, redraw vs panel |
| S5 | hub | gpio 108 float / low / NRST (gpio 87) held, ABCCBA 15 min | 0-4 mA |
| S6 | touch and eMMC | F6 sleep x F5 CMD5 + SDCC1 clocks off | 0.1-1 mA |
| D | one-shot dumps from an asleep wake | PMIC EN_CTL/MODE_CTL per regulator, TLMM, 0xfc401488 | F8/F9 candidates |
| A | AsteroidOS on sturgeon | BT on/off, AOD on, ABBA 25 min | checks the 1.6 mA figure |

Implement properly only what an arm shows at >= 0.5 mA. Likely order:
1. F3 USB PHY LPM while unplugged, as the vendor (phy-msm-usb.c
   :884-1141), with the usbin-valid wake on MPM pin 62 (POWER.md F3).
2. F11 slow BT parameters, if >= 1 mA and notifications stay timely.
3. F4 display: PLL/PHY off, then GDSC, then rails (mdss_dsi.c:518-565);
   with AOD, PLL off between redraws (the vendor's ULPS clock-off path).
4. F7 hub handshake (hwmcusleep.c:145-167).
5. F5, F6, F8 as the dumps and arms justify.
6. F2/F10 wake work only if S4 prices wakes above the MDD.

sparrow: S1 and S2 again with the S3 threshold forced, after sturgeon.

### 4. Harness and tools (out of main)

- `patches/power-harness.patch` against main 83572ad, replacing today's
  uncommitted powertest code, `pmic_batfet_lpm`/`pmic_iadc_raws` and
  stubs (the `bt_host_slow` code goes with it unless S3 justifies it).
  Scheduler: `powertest <settle> <arm_min> <arm>;<arm>;... [mirror]`,
  each arm a knob set `bt=fast|slow|idle|off aod=on|off|static
  wake=<n/min> usbphy=on|lpm dsi=on|off hub=float|low|reset
  touch=on|sleep emmc=on|sleep`, each switch logged as one self-describing
  line. `wake=` caps `app_next` in `src/main.c`; `aod=static` skips the
  minute redraw in `src/power.c`; `bt=idle` is the host stopped with the
  chip on. The extended stats line, sparrow's S3 threshold write, and a
  `dump` command.
- `tools/powerlog.py` (notes repo): reads firmware or AsteroidOS logs;
  per arm the used minutes, CC mA +/- SE and median, wakeups, host-wakes,
  awake ms/min, VDD-min residency, trim drift, temperature, BT
  parameters, OCV count and I_ocv +/- SE; per session the audit
  (PASS/FAIL), every named contrast with its uncertainty or "< MDD", and
  the §2 table with the residual once enough sessions exist.
- `tools/aos-powerlog.sh` on AsteroidOS as a `systemd-run` unit: wakes
  with the system (AOD minute) and goes by wall clock, logging
  `charge_counter_shadow` (same counter, vendor trim), raw OCV 0x4090,
  0x4077, the trim, RPM stats, wakeup sources and BT state via debugfs;
  BT arms with `bluetoothctl power` at wall-clock times.

### 5. Definition of done

1. On each watch, one 2 h session passes the CC/OCV audit (sparrow with
   the forced S3 threshold).
2. POWER.md §14 holds the budget for sturgeon, then sparrow: components
   sum to the total within 1 mA, residual under 1.5 mA or equal to
   AsteroidOS's floor.
3. AsteroidOS measured on sturgeon by the same method; our total within
   1 mA of it, or the gap assigned to named components.
4. Every fix worth >= 0.5 mA committed with its figure; every null result
   written down with its MDD so it is not retested.
5. The harness patch and powerlog.py stay in the notes; after any
   power-relevant change one S1 session is the regression check. The
   question is then answered by rerunning S1, not by a new hunt.

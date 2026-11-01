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

## Plan

(next section, from the planning pass)

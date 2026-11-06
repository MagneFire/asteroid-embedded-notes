**§25’s main numbers reproduce; its exclusions are too strong.** READ below includes calculations from the files; INFER marks interpretation and recommendations. No edits, commits or device access.

**1. Numbers and conclusions**

**READ:** Starting at the boot logged at 210.102 s, merging consecutive identical masks, and excluding intervals beginning within 180 s of a change:

| Arm | Retained minutes | Mean mA |
|---|---:|---:|
| D | 56 | 2.542 |
| M | 347 | 2.689 |
| F | 68 | 2.581 |
| L | 36 | 5.591 |
| C | 36 | 5.220 |

D/M/F have approximately **99.94% VDD-min**; L/C have zero. F ran for 80 minutes before exclusions. The reported block contrasts reproduce: **−0.145, −0.396, +0.106 mA**, mean **−0.145**, SE **0.145**. [§25](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:1171)

- **“Votes do not outlive adb reboot” — INFER: narrow it.** The log contains **two reboots**, with an intervening plugged-in boot, between the earlier blocking votes and this run. It establishes that the blocking state did not persist through that sequence. It does not establish universal vote erasure, its mechanism, or retrospectively prove the rehearsal’s initial state.
- **“Either rail alone blocks VDD-min” — READ, for the tested requests.** CX sleep **corner 6** with MX 750 mV blocks it; MX **1280 mV** with CX 0 blocks it. **INFER:** this does not establish the threshold or behavior at Linux’s last active corner **3**. Say “either tested high sleep request blocks VDD-min.”
- **“Never voted is no worse than M” — overclaimed.** READ: D is **0.146 mA lower raw**, but occurs only once, first. Also, M installs active CX/MX votes **and L8 sleep-on**, so this is not an isolated comparison of two sleep voltages. [Implementation](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:317)
- **“L8: no detectable saving and no harm” — split it.** No detectable saving is fair. READ: timer resumes succeeded without logged resets; panel wake was not tested during F. INFER: general functional safety is unproved. Even an illustrative three-contrast *t* interval is roughly **−0.77 to +0.48 mA**, before accounting for shared controls and drift.
- **“CX, MX and L8 are out” — replace with:** **INFER: “These votes reveal no convincing saving in this run and substantially weaken the active-level CX/MX hypothesis; smaller effects and L8 savings remain unresolved.”** There is also no precisely established remaining firmware–AsteroidOS gap yet.

**2. Your trim/temperature fit**

**READ:** The pooled fit reproduces **0.284 mA/code and 0.314 mA/°C**. Adding D/F indicators gives adjusted D−M **+0.085 mA**, explaining the quoted +0.08; the checked-in analyzer does not calculate that indicator model.

**INFER:** Sound as an exploratory association; unsuitable as a causal correction or equivalence test:

- **READ:** The analyzer assigns a newly logged trim to the CC interval ending immediately afterward. Most of that interval used the **previous trim**. Weighting trim by exposure time changes the pooled slopes to approximately **0.361 and 0.392**; with arm indicators, to **0.384 and 0.466**, and D−M to **+0.162 mA**.
- **INFER:** Temperature, trim, time and arm order are entangled. Battery temperature is also an imperfect proxy for the analogue offset’s temperature. Residualizing cannot recover the missing repeated D controls.
- **INFER:** Minute samples sharing calibration and slow drift are not independent replicates; their SEs understate uncertainty in treatment comparisons.
- **READ:** The final F contrast uses a **247-minute** following M block. Prefer nearby, comparable-duration controls; this particular contrast barely changes when shortened, but the method should be explicit.

**READ:** [an-day-mx.py](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/an-day-mx.py:1) also opens nonexistent `day-run.log`, does not select the 210-s boot, and encounters unsupported masks in earlier boots if simply pointed at the complete file. Its published results require preprocessing.

**3. What remains, and the single next run**

**INFER ranking:** First resolve **measurement/state mismatch**. If a gap survives, prioritize **unmatched PMIC peripheral/clock policy**, then **GPIO/interface loading**, then **remaining panel/L17 effects**. Direct wake-time consumption is lower priority given residency; persistent consequences of wakes remain possible.

**INFER — next run:** choose the **matched OS crossover**, because it answers the actual goal.

Use **O F F O / F O O F**, where O = AsteroidOS and F = one fixed firmware configuration. **Eight 90-minute unplugged arms: discard 30 minutes, retain 60**, approximately 12 hours plus transitions. Standardize boot/unplug preparation for every arm, including repeated identical arms; extend settling if temperature is still changing appreciably.

Keep screen/AOD off, Linux **rfkill blocked and verified**, firmware BT off, comparable battery voltage and temperature, and matched touch/hub functionality. Use common 300-s measurement wakes, retain trim history and raw counter/calibration information, and compare within each quartet without importing a cross-day trim slope. **A stripped harness baseline only establishes baseline parity; production features require their own comparison.**

| Candidate | What it would decide |
|---|---|
| **Matched O/F crossover — next** | Whether a reproducible firmware excess exists under matched conditions; cannot identify its component. |
| **V A A V / A V V A** | Incremental panel/L17 saving beyond V. Use 30-minute arms, three paired quartets, discard transition intervals. Does not establish OS parity or fully identify non-additivity. |
| **BT-off pin changes** | Whether removing UART pulls and driving WL_REG_ON low reduces this baseline’s current. Keep other policies fixed; a combined positive result needs separate follow-up arms. |
| **PMIC peripherals** | Whether an identified control mismatch matters. First compare controls, then toggle one supported function; blanket changes would be ambiguous. |

**READ:** Vendor UART configuration uses no pulls, and Wi-Fi initialization explicitly drives GPIO110 low. Existing firmware reads already show low levels, weakening a large contention explanation without excluding weak internal loading. [UART configuration](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:144), [WL_REG_ON](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8026-wifi.c:184)

**4. Production**

**INFER:** **Yes, retain M and L8-off as vendor-parity candidates under your rule; no measured saving is not grounds to discard them.** Neither is ready for unconditional promotion solely from this run.

Validate first:

- **M:** acknowledged active requirements before sleep reductions; active corner sufficient for every supported clock/load. Harness corner **6** is not Linux’s observed **3**: justify its cost and requirement rather than blindly copying either. Exercise retention, repeated resumes, memory integrity, display/GPU, storage, USB and BT.
- **L8-off:** active 1.8-V supply and appropriate load restored before CPU PLL/display use; real button/touch/USB wakes, repeated panel initialization, first-frame correctness, AOD transitions and idle while the panel remains active.
- **Integration:** prevent sleep-off while a live consumer needs L8; handle vote failures and wake ordering. Recheck current on the actual production branch.

**READ:** F used panel deep standby. The inspected sleep-parity display path uses ordinary sleep-in, so F’s successful timer wakes do not validate that production combination. [Harness display](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:457), [sleep-parity display](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-sleep/src/display/display.c:405)

**5. Before reboot**

**INFER:** Preserve the remaining volatile log, `status`, and these existing read-only console snapshots:

```text
mem fc19dba0 12
mem fc19dbd0 12
pmic 36f2 2
```

Optionally capture PMIC peripheral controls for later matched comparison. **READ:** the supplied state file already contains the three snapshots above. Replug restored measures, restarted BT and installed high sleep votes, so present plugged-in reads cannot reconstruct F’s sleeping rails. Ten hours’ uptime creates no unique opportunity beyond preserving history. [Replug sequence](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-day-mx-2026-11-06-sturgeon.txt:3013)
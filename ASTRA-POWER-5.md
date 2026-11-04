# Codex (gpt-6-astra) power round 5, 2026-11-04: next steps under long run times

**Do a short matched AsteroidOS comparison first, then screen panel full-off and hub services-off together. Reserve CX/MX or DDR changes for a demonstrated policy mismatch.** §19 establishes a reproducible **4.70 mA reading**, but state-dependent trim still prevents treating the difference from historical Linux readings as a calibrated power gap. Retire V/Q/M as individual experiments; their small results do not justify another night now. [POWER.md:934](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:934)

Read-only review completed; no edits, commits or device access.

**Priority by expected saving × confidence ÷ implementation, measurement and failure cost**

The ranges below are **guesses about additional battery-current savings**, not measured budgets or additive quantities.

| Priority | Candidate | Why / cheapest discriminating check |
|---|---|---|
| **0** | **Matched AsteroidOS reference** | Highest information value: determines whether an expensive remaining-gap investigation is warranted. Combine it with one peripheral-register snapshot and RPM request capture. |
| **1** | **RM69080 complete off commands**; guessed **0–1.5 mA**, medium confidence in omission, low in saving | Concrete difference: firmware sends only `28`/`10`; vendor adds **120 ms wait, `00 00`, 255 ms wait, `4F 01`**, with specified packet types/HS transmission. Test commands before supply removal. Cold recovery is the main implementation cost. [display.c:449](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:449), [panel DT:57](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/dsi-panel-auo-rm69080-hvga-video.dtsi:57) |
| **2** | **Hub services disabled, MCU allowed to sleep, versus reset**; **0–1 mA**, low confidence | Reset does not prove downstream sensors stopped. Use acknowledged service deactivation and the existing AP-status handshake. No supply-map reverse engineering needed initially. [hub.c:462](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:462) |
| **3** | **CX/MX sleep requests**; **0–1+ mA**, low confidence | Capture Linux’s actual active/sleep requests first. MX’s 750 mV sleep contribution is source-backed, but neither final voltage nor a recoverable saving follows from that alone. Only test an identified excess firmware vote. [regulator DT:223](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:223) |
| **4** | **GPIO and PMIC inventory**; ordinarily **0–0.5 / 0–0.3 mA**, low confidence | **Do these cheap reads early**, despite ranking interventions lower: reset/unpowered-device pins; amp/haptic standby; unused LPG/WLED/vibrator and ADC enables. A concrete active-output or back-power fault jumps ahead of CX/MX. [audit details:216](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/ASTRA-POWER-4.md:216) |
| **5** | **DDR/BIMC**, then panel/eMMC rail removal | DDR saving is unquantified; high investigation/risk cost. **BIMC sleep-rate zero is already in B**, so repeating that is not a new candidate. Audit retention policy after CX/MX. Panel rails require cold recovery/shared-L8 ownership; eMMC L17 removal offers guessed **0–0.5 mA** but needs full card reinitialization. [rpm.c:255](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:255) |

**First session: establish the target cheaply.** After a short logger rehearsal, use the same sturgeon, similar battery voltage/temperature, fully blank display, BT off, and documented touch/sensor settings. Start with **15 minutes settling plus 30–60 minutes unplugged Linux measurement**, locally logged to RAM; compare with a nearby firmware baseline window. This screens a multi-mA gap; it does not promise ±0.2 mA.

Use Linux’s accumulated **`charge_counter_shadow`** property, verifying availability and continuity. Raw shadow-register endpoint subtraction is invalid across Linux’s counter resets. Its property also applies gain/temperature corrections absent from firmware’s raw shadow conversion; document those differences. Check actual calibration channel and trim history—the reviewed vendor DT selects a different offset channel. A stable shared meter is not independent absolute calibration. [qpnp-bms.c:1441](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1441), [calibration audit:38](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/ASTRA-POWER-4.md:38)

Collect persistent peripheral states and RPM request logs during that visit. **An awake snapshot cannot reveal live collapsed CX/MX voltage or DDR self-refresh**; it can expose configuration differences. If Linux is near 4.7 mA, defer risky platform work. If materially lower after measurement reconciliation, pursue the ranked candidates. Use an existing external battery meter if readily available; do not make acquiring one the first project.

**Short checks before overnight measurement.** Register reads, service acknowledgements and request logs can establish policy, not its current saving. For panel/hub or an obvious active peripheral, a **10-minute A/B is a large-effect screen only**; reverse it before accepting a >1 mA result. Short-arm noise is not established by the 13-minute data. The conservative confirmation is **four 13-minute ABBA arms: 52 minutes**. A null short test cannot exclude 0.2–0.5 mA.

**Share the next overnight between two candidates, not every possibility.** Let B retain the five measures, P add panel full-off, and S **replace hub reset** with services-off/normal MCU sleep:

`B, P, P, B, B, S, S, B` — repeat five times.

That is **40 × 13 minutes = 8 h 40 min**, plus settling. Discard two minutes after successful state application; keep complete integration intervals. Each candidate gets five independent ABBA contrasts.

With independent **0.3 mA arm SD**, one ABBA contrast has approximately 0.3 mA SD:

- Five contrasts/candidate: **±0.27 mA at 2 SE**; approximately ±0.37 using a small-sample 95% interval.
- Ten contrasts: approximately **±0.19 at 2 SE**, ±0.21 at 95%.
- Twelve contrasts: approximately **±0.19 at 95%**—**10 h 24 min for one candidate**, twice that for two.

These are planning estimates; drift/correlation can require more. Screen both one night, then spend precision time only on the worthwhile unresolved candidate.

**Rehearse the exact schedule first:** one-minute arms through every transition and restoration, followed by one full-length baseline/test pair. Verify panel repaint/recovery, service acknowledgements, eMMC re-sleep, unchanged residency/trim, sufficient log retention and explicit invalidation on failure. Hub release currently restarts tilt/steps and reads calibration from eMMC; merely clearing H does not create S. Suppress disabled-service flushes too. [hub.c:237](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:237), [hub.c:488](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:488) The analyzer’s hardcoded masks must also understand these new states. [powerlog.py:165](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:165)

**Parity changes need functional checks, not another power night:** implement the supplied Android touch-doze 3/8 policy with register readback and responsiveness checks; it should not improve B’s already-sleeping touch sensor. Preserve/assert amplifier idle power-down—the measured `0x0265` already has it set—and check haptic standby writes/failure cleanup. These prevent regressions; claim no new saving. [touch control:3725](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3725), [POWER.md:909](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:909), [haptics:118](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/haptics_drv2605.c:118)
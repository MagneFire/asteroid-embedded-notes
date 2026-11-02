# Codex (gpt-6-astra) power review, 2026-11-02

Read-only review of the firmware, these notes, the logs and the vendor kernel, asked for a budget of sturgeon's 8.8 mA (AOD on, BT off), a vendor suspend comparison and the next experiments. Brief: see the end of POWERPLAN.md context. Claude checked against the code: RMI4 has no .sleep, no APCS_CLOCK_SLEEP_ENA_VOTE write, no USB PHY LPM, and the rpm.c:205 comment contradicts the vendor rule (no sleep-set vote = active vote applies in sleep). The component budget is Astra's guess; only the total is measured.

My best estimate is **about 8.4 mA of persistent sleep load and 0.4 mA of wake overhead**, totaling 8.8 mA. The split is provisional: the recent logs establish infrequent cluster collapses, but do not measure time outside RPM VDD-min. **USB PHY LPM is the strongest remaining individual candidate; its present-day saving is unknown.**

I read the working tree, including the uncommitted harness, and the relevant notes, logs and vendor code. No files were edited and nothing was run on a device.

References below use **FW** for `asteroid-embedded`, **K** for `minnow/sturgeon-kernel`, and **N** for `asteroid-embedded-notes`.

**1. The budget is mostly persistent load; its component allocation is still a hypothesis.**

The strongest measurements remain:

- PLL off versus old rest: **−0.14 mA, ±0.54 mA at 2 SE**.
- MDSS collapse versus old rest: **−0.08 mA, ±0.63 mA at 2 SE**, using the paired result in the notes.
- Pooled MDSS-run currents: **8.64 mA collapsed, 8.64 mA PLL-off, 8.90 mA old rest**. I reproduced these pooled values with the existing analysis script.

These establish no detectable saving from those rest changes. They do **not** establish that the panel, display supplies or redraws cost nothing. See [N:POWER.md:775](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:775) and [N:POWER.md:806](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:806).

Here is my working allocation. **Only the total is measured; the component numbers are deliberately rounded guesses for prioritization.** The ranges are plausible investigation ranges, not statistical confidence intervals, and cannot be added independently.

| Rank | Component | Working allocation | Plausible range | Confidence and basis |
|---|---|---:|---:|---|
| 1 | USB PHY and associated supplies | **3 mA** | 0–7 mA | Low confidence in size; high confidence that vendor LPM is missing. The old −7 mA result warrants retesting, not booking the saving. |
| 2 | Unassigned platform floor: DDR/RPM/PMIC, regulator quiescent current, inherited votes and other rails | **2.5 mA** | 1–7 mA | Low. This is the residual, **not a measured intrinsic silicon floor**. |
| 3 | AOD panel emission, panel electronics and display supplies | **1.2 mA** | 0.3–2.5 mA | Low. Current AOD-off measurement should constrain this; old AOD splits used the faulty meter. |
| 4 | Sensor hub and enabled sensors | **0.8 mA** | 0.1–3 mA | Low. AP-status handshake exists, but neither its steady load nor the sensor-service cost has a trustworthy modern isolation measurement. |
| 5 | eMMC/card supplies | **0.5 mA** | 0.1–1 mA | Low. Card sleep and host clock gating remain absent. |
| 6 | All wake work, including AOD redraw and hub wake housekeeping | **0.4 mA** | 0.1–0.9 mA | Medium on being relatively small, low on exact energy. Calculation below. |
| 7 | Touch controller | **0.3 mA** | 0.1–0.6 mA | Low. Sturgeon still lacks a sleep/gesture-mode callback. |
| 8 | GPIO leakage and miscellaneous board loads | **0.1 mA** | 0–0.5 mA | Low. No evidence presently supports a multi-mA GPIO explanation. |
| | **Total** | **8.8 mA** | | Allocation constrained to the measured total. |

Bluetooth radio activity should contribute approximately zero in these arms: `powertest_bt(false)` stops the host and chip; `bt_stop()` disables host-wake, stops the UART and drops chip power. The UART stop also gates its application clock and pulls its pins down. [FW:console.c:1194](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:1194), [FW:bcm.c:212](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:212), [FW:uart_dm.c:327](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/uart_dm.c:327).

The **3.2–7.2 mA difference** between 8.8 mA and the reported 12–16 mA connected runs is a useful indication of BT-associated cost, but is not a paired estimate of radio consumption alone.

For wake overhead, my recount after each arm’s first two minutes gives:

| Log | Retained asleep samples | Mean “wakeups” per sample, approximately one minute | Successful core / cluster collapses during those intervals | Bailouts |
|---|---:|---:|---:|---:|
| PLL run | 361 | 2.053 | 0 / 722 | 19 |
| MDSS run | 530 | 2.064 | 0 / 1,089 | 5 |

For example, the MDSS log keeps the core count at 632 while cluster counts advance: [N:MDSS log:146](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-mdss-collapse-2026-11-02-sturgeon.txt:146).

Using the historical **13 mA·s per cycle** as an order-of-magnitude estimate:

\[
I_{\text{wake}} \approx (2.05/60)\times13 = 0.44\ \mathrm{mA}.
\]

That energy is about **50 mJ per wake at 3.8 V**. A broader 3–25 mA·s/wake range gives **0.10–0.85 mA**. This includes transition work; CPU execution time alone would miss RPM bring-up/shutdown.

The historical 150 ms outside VDD-min per wake would imply **99.5% residency today**, rather than the old 86% at 1 Hz. But this is an extrapolation from [N:SUSPEND.md:834](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/SUSPEND.md:834), not a contemporary measurement.

The new residency log can sharply distinguish the explanations. Assuming an illustrative 90 mA outside VDD-min:

| Measured VDD-min residency | Implied current while in VDD-min, for an 8.8 mA total |
|---:|---:|
| 99.5% | 8.39 mA |
| 99% | 7.98 mA |
| 95% | 4.53 mA |
| 92% | 1.74 mA |

Thus a Linux-like 1.6–2 mA floor would require roughly **8% of the time outside VDD-min**, or approximately **2.3 seconds per wake** at today’s rate. That is possible to test directly, but substantially larger than the historical transition estimate.

“VDD-min floor” here means **whole-watch current while the APSS is in that state**, including panel and peripheral loads.

**3. Vendor parity gaps are concentrated in peripheral shutdown and explicit resource policy.**

| Area | Current firmware | Vendor suspend behavior | Assessment |
|---|---|---|---|
| **Cluster/TZ/MPM** | Programs L2 PC, passes cluster flag to `cpu_suspend`, uses handoff lock and cache flush. Cluster entry requires quiet display, no USB connection, sleeping BT/hub, parked secondaries and ≥20 ms remaining. [FW:power.c:232](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/power.c:232), [FW:spm.c:154](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/spm.c:154), [FW:suspend.S:48](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/suspend.S:48). | Selects cluster mode, enters RPM sleep and programs MPM; obtains TZ flag and handoff lock. [K:lpm-levels.c:473](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/cpuidle/lpm-levels.c:473), [K:lpm-levels.c:1017](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/cpuidle/lpm-levels.c:1017). | Broad sequence already matches. Successful SPM collapse is insufficient proof of XO shutdown or VDD-min residency. |
| **XO and bus sleep votes** | Explicit sleep `clk0/0 Enab=0`; BIMC 200 MHz, SNOC 100 MHz, PNOC/CNOC 50 MHz are active requests without corresponding explicit sleep requests. [FW:rpm.c:220](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:220). | Active-only clocks vote zero in sleep; normal clocks retain their requested rates, aggregated with peers. Holds active-only XO and MMSSNOC-AHB votes. [K:clock-rpm.c:73](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/clk/qcom/clock-rpm.c:73), [K:clock-8226.c:3612](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/clock-8226.c:3612). | XO permission is present. Bus sleep policy is incomplete/implicit. Linux’s final aggregate rates cannot be inferred from `_a` definitions alone. |
| **CX/MX** | No explicit CX corner or MX voltage request in `rpm_sleep_votes()`. [FW:rpm.c:240](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:240). | CX has both-set and active-only handles. MX has a sleep-only 750 mV handle. [K:msm8226-regulator.dtsi:129](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:129), [K:msm8226-regulator.dtsi:223](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:223). | **Do not claim Linux always sends MX=750 mV:** the notes’ consumer/default analysis finds that handle unused. Actual RPM policy and other masters remain relevant. |
| **Regulator modes and sleep sets** | Helpers mainly send `swen`/`uv`; touch enables L19/LVS1 without load/mode policy. [FW:rpm.c:193](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:193), [FW:touch.c:52](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch.c:52). | Aggregates consumers and sends differing sleep requests; maps LDO mode requests to `lsmd`. USB, MMC and display consumers lower loads or disable supplies. [K:rpm-smd-regulator.c:538](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:538), [K:rpm-smd-regulator.c:1157](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:1157). | Real parity gap. A missing regulator sleep vote preserves the active request; the comment at FW `rpm.c:205` says otherwise and is misleading. [K:default rule:192](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:192). |
| **USB PHY** | Enables AHB/system clocks and external session-valid override; no PHCD/STP LPM sequence. [FW:usb.c:43](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:43). | Sets/polls PHCD, asserts STP, conditionally enables asynchronous wake, gates clocks, releases XO, disables/LPMs PHY regulators, lowers CX and drops bus vote. [K:phy-msm-usb.c:965](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:965), [K:phy-msm-usb.c:1065](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1065). | Strongest unimplemented sequence. PMIC attach wake is already implemented at [FW:pmic.c:413](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:413); it needs integration with PHY resume, not reinvention. |
| **eMMC** | Enables SDCC1 clocks; wakes a sleeping card during initialization; no matching runtime card-sleep path. [FW:emmc.c:172](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/emmc.c:172), [FW:emmc.c:489](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/emmc.c:489). | Disables cache, sleeps/deselects card; host removes bus votes with clocks off. Regulator path disables non-always-on supplies or requests LPM load. [K:mmc.c:1850](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/core/mmc.c:1850), [K:sdhci-msm.c:1897](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1897), [K:sdhci-msm.c:3470](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:3470). | Clear gap. DT assigns L17 VCC and always-on L6 VCCQ, with 250 µA LPM **load request**, not measured battery current: [K:DT:133](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-720p-mtp.dtsi:133). |
| **Sturgeon touch** | RMI4 driver has no `.sleep` callback; the generic `touch_sleep()` call therefore does nothing for it. [FW:touch.c:333](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch.c:333), [FW:drivers.c:18](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/board/drivers.c:18). | Uses wake-gesture mode when enabled; otherwise masks IRQ, requests sensor sleep and disables its regulator. [K:synaptics_dsx_core.c:3851](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3851). | Real gap. Sparrow’s IT7260 sleep implementation does not close it. |
| **Sensor hub** | Drives AP-status low during cluster sleep, enables MCU MPM wake, then flushes steps on every resume. [FW:hub.c:237](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:237), [FW:hub.c:464](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:464). | Drives AP-status low and enables host-wake IRQ. [K:hwmcusleep.c:145](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmcu/hwmcusleep.c:145). | Handshake gap is closed. Sensor configuration, UART clocks and per-wake flush cost remain candidates. |
| **BT chip/UART** | BT-off shuts chip and UART down. Connected sleep only holds UART RX; it does not gate UART clocks. The one-second dev-wake deadline is implemented. [FW:bcm.c:248](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:248), [FW:uart_dm.c:355](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/uart_dm.c:355). | Nitrous drops UART runtime-PM references; UART driver gates core/interface clocks and removes PNOC vote. RF-kill drops chip power. [K:nitrous.c:100](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/bluetooth/nitrous.c:100), [K:msm_serial_hs.c:379](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/tty/serial/msm_serial_hs.c:379). | Connected-state parity gap, not a strong explanation of these BT-off runs. |
| **Display** | ULPS, PLL-off, GDSC collapse, secure restore and register restore exist. No equivalent panel-supply load policy. [FW:display.c:309](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:309), [FW:display.c:365](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:365). | Footswitch idle collapse; ULP changes regulator optimum modes; full panel-off disables controller/PHY and invokes supply shutdown. [K:mdss_mdp.c:2960](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_mdp.c:2960), [K:mdss_dsi.c:184](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_dsi.c:184), [K:mdss_dsi.c:518](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_dsi.c:518). | Rest hardware gap largely closed. Supply policy and panel load remain separate. |

Two additional differences deserve a targeted dump:

- **GCC sleep-enable vote:** Linux explicitly clears `APCS_CLOCK_SLEEP_ENA_VOTE` at `0xfc401488`; I found no corresponding firmware write. Compare [K:clock-8226.c:3597](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/clock-8226.c:3597) with [FW:clock.c:40](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/clock.c:40). Read its value before assigning it any current.
- **TLMM and idle peripheral clocks:** firmware sets pins directly without a general active/suspended state mechanism; Linux applies suspended configurations when users release pins, and peripheral PM selects sleep states. Examples: BT I²S pins 68–71 become GPIO/pulldown/2 mA. Firmware QUP clocks and hub UART remain enabled. [FW:tlmm.c:5](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/tlmm.c:5), [FW:i2c_qup.c:183](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/i2c_qup.c:183), [K:gpiomux.c:119](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/gpiomux.c:119), [K:board-8226-gpiomux.c:605](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:605), [K:i2c-msm-v2.c:3844](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/i2c/busses/i2c-msm-v2.c:3844).

A branch enable bit is not proof of a continuously running clock through XO shutdown. These omissions may cost primarily during transitions, or may prevent deeper states; residency distinguishes those cases.

**4. I would run these five experiments next, after consuming the already-running screen-off result.**

For every session: BT off unless explicitly varied, fixed face/brightness and sensor settings, automatic completion, raw CC plus OCV audit, and actual arm start/end timestamps. Use 15 minutes settling; exclude the first 25 minutes after unplug from OCV fitting. Keep all experimental code in the harness patch.

| Priority | Experiment and expected effect | Arms | Required harness code |
|---|---|---|---|
| **1** | **USB PHY LPM.** My working expectation is a few mA; retain **0–7 mA** as the honest range. | A=current USB, B=PHY LPM; **ABBA, 25 min**, AOD off. Keep display rest identical. | Add reversible USB LPM/resume to `src/usb/usb.c`; start from the old patch’s PHCD/STP operation, add timeout/error checking and state readback. Restore before USB register polling/enumeration on PMIC attach. Initially leave USB rails unchanged to isolate PHY LPM. |
| **2** | **Price wakes and split AOD panel from redraw.** Expected baseline wake cost **0.1–0.9 mA**; 30 extra wakes/min should add roughly **1.5–12.5 mA** for 3–25 mA·s/wake. Panel/rest difference guessed **0.3–2.5 mA**. | A=screen off; B=off +30 extra wakes/min; C=AOD static; D=normal AOD. **ABCDDCBA, 13 min**. | Add a forced-wake deadline in `main.c`; suppress minute redraw in `power.c` for static mode. Apply AOD transitions immediately—the current `ambient` state is latched at sleep entry. Measure actual collapse rate and outside-VDD-min time. |
| **3** | **Explicit RPM/GCC sleep policy.** Expect **<0.5 mA if residency is already excellent**, potentially several mA if inherited policy prevents deeper sleep. | A=current policy; B=explicit zero APSS bus sleep votes plus zero GCC sleep-enable vote; **ABBA, 25 min**, AOD off. | Harness-only set-1 clock requests and GCC save/restore. Seed both A and B policies explicitly: once a sleep vote is sent, “return to unspecified” is not a reliable reverse arm. Log XO/VDD-min statistics and request acknowledgements. Keep CX/MX voltage experiments separate until actual vendor votes are known. |
| **4** | **Peripheral isolation screen.** Hub **0–3 mA**, eMMC **0.1–1 mA**, touch **0.1–0.6 mA** are investigation ranges. | A=baseline; B=hub held reset; C=eMMC asleep/clocks off; D=touch sensor sleep. **ABCDDCBA, 13 min**, AOD off. Each non-A arm changes only its named subsystem. | Hub arm must suppress polling/retries and restore initialization/service state. eMMC needs flush/deselect/CMD5 sleep, busy completion and reversible clocks. Touch needs F01 sleep plus IRQ/MPM handling and restored mode. Record residency so reduced wake traffic is not mistaken for steady peripheral consumption. |
| **5** | **Matched AsteroidOS reference.** Expected result unknown; earlier references imply a **1.8–7.2 mA gap**, but that gap is unverified. | BT off throughout; AOD on/off **ABBA, 25 min**, same watch, similar voltage/temperature, matched lit area/brightness as closely as possible. | Standalone logger surviving adb disconnect; raw shadow CC, hardware OCV, trim, temperatures, RPM XO/VDD-min and wake sources. Take regulator/TLMM/clock snapshots around suspend. Analyze with the same conversions and exclusions. |

The old USB function is at [N:sleep-debug-harness.patch:180](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/patches/sleep-debug-harness.patch:180). It is a starting point, not a complete vendor suspend/resume implementation: notably, Linux sets `ASYNC_INTR_CTRL` conditionally.

Before those sessions, the highest-value harness additions are:

- Raw **shadow CC and timestamp**, avoiding gaps from resettable BMS integration.
- **64-bit XO and VDD-min accumulated times**, count deltas, and elapsed sleep-clock time.
- CPU-active time between idle calls, separately from RPM transition time.
- A finite arm count, explicit end marker, actual applied-state readback and failure markers.

The existing scheduler at [FW:console.c:1209](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:1209) is suitable, but currently repeats until plug-in and only implements BT, BATFET and display-rest variants. The proposed modes are additions, not commands available today.

For vendor parity, I would retain correctly implemented suspend sequences even when their individual effects fall below detection, provided their resume behavior is sound. That does not justify continuing to claim the historical savings.

**2. The measurement concerns that materially affect this report are these.**

- **Neither old log contains actual asleep CPU-active time.** `wakeups` increments on every asleep `power_update()` pass, not every hardware interrupt. Collapse counters are cumulative successful core/cluster returns plus bailouts. The UI’s asleep-time accounting measures logical screen state, not silicon residency. [FW:power.c:148](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/power.c:148), [FW:spm.c:163](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/spm.c:163).
- **The new VDD-min logger is useful at one-minute cadence, with one caveat:** it reads only the low 32 bits of accumulated 19.2 MHz ticks. Modular subtraction works when the accumulated increment is below **223.7 seconds**; longer gaps can silently undercount. Reset its baseline after awake gaps, or read the full counter. Preserve the printed milliseconds: integer percentages hide the difference between, for example, 99.1% and 99.9%. It also does not independently log XO shutdown. [FW:main.c:805](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:805).
- **`powerlog.py` does less than POWERPLAN proposes.** It excludes reset-crossing intervals, but consequently samples only part of each arm. If OCV resets preferentially exclude particular current states, the selection is biased. It prints OCV slopes without profile conversion or a formal audit. Despite its docstring, its two-label uncertainty calculation is **unpaired**, and three-label block contrasts are not implemented. [N:powerlog.py:52](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:52), [N:powerlog.py:93](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:93).
- **OCV is a session audit, not a precise 13-minute meter.** In the MDSS analysis, individual arms include −56, −11 and even **+16 mV/h**. Near the observed upper-voltage region, −32 mV/h with the 275 mAh capacity corresponds roughly to 8–10 mA, depending on local profile slope. Use temperature-dependent local interpolation; firmware’s nominal profile still contains ~321–322 mAh. [FW:sturgeon.c:49](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/board/sturgeon.c:49).
- **Scaling/sign do not show an obvious sturgeon defect.** The shadow path correctly sign-extends 36 bits and uses the expected resistor/time constants. However, it omits the gain/temperature corrections used by the resettable BMS path, and its printed whole-mA value truncates toward zero. Do not treat the two reported means as interchangeable. [FW:pmic.c:702](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:702), [FW:bms.c:313](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/bms.c:313).
- Preserve the established charger exclusion, and reject incomplete final arms. The MDSS file contains 24 arm starts but only **23 arms with usable CC integration**. The screen-off rest setter now immediately reapplies hardware state, closing the earlier no-op-arm problem. [FW:display.c:174](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:174).

The old experiments remain useful for ranking mechanisms. An offset error can cancel in a within-run difference, but trim drift, changed sampling states and different residency can prevent that cancellation. Their absolute budgets should not be carried forward.

**5. Sparrow’s cause is still unresolved; the evidence points toward an offset or sampling-state problem.**

Both counter paths go negative while OCV falls. For example, [N:sparrow log:1](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-dsi-rest-2026-11-02-sparrow.txt:1) shows negative resettable CC and negative shadow-current lines together. That makes a `powerlog.py` reset-handling bug insufficient to explain it.

The 9.7→10 mΩ correction is only **3%** and cannot reverse the sign. The established lead-shorting register result rules out that fix. Ordinary positive gain and temperature corrections likewise cannot explain a negative raw discharge delta.

The current trim write matches the vendor’s external-offset channel and secure MSB/LSB sequence: [FW:pmic.c:655](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:655), [K:qpnp-adc-current.c:954](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:954). The vendor additionally has revision-specific gain handling and fabrication/system-gain compensation, but those are parity differences—not a demonstrated explanation for this sign error.

The next diagnostic should record, together, **raw main/shadow counter deltas, VSENSE_AVG, external-channel and offset conversions, stored trim readback, IADC/BMS configuration and temperature**, across awake and asleep states. Repeat under Linux on sparrow. If large-load discharge has the correct sign while only low-current operation goes negative, a residual zero offset or state-dependent BMS sampling error becomes much more likely than reversed polarity. The present code and logs do not identify which one.
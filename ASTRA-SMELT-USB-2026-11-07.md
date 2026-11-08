# Codex (gpt-6-astra) review of the smelt USB unplug root cause, 2026-11-07

Prompt: the SMELT.md section "Why smelt resets when USB is unplugged", the PMIC dump and logs of the day, branch attach main..840074e, vendor kernel and LK sources. Read-only.

## 1. Verdict and evidence limits

**INFER — the supply-loss diagnosis is convincing; the detailed root cause is not established.** Commit `840074e` is a plausible experiment, not yet a demonstrated fix. Two register interpretations need correcting, and neither the proposed latch nor its debounce-dependent release is proved by these sources.

**READ:** Crash2 and crash3 record `pon 02`, `warm 0000`, `poff 0020`. The vendor names these SMPL and UVLO. [crash2:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-smelt-crash2-2026-11-07.txt:21), [crash3:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-smelt-crash3-2026-11-07.txt:21), [qpnp-power-on.c:163](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/platform/msm/qpnp-power-on.c:163).

**READ:** The notes report three successful asleep unplugs and three failed awake unplugs; Linux was unplug-tested **only asleep**. They report the unsuccessful register experiments and USB_SUSP deaths. The supplied session log is not a command-by-command transcript establishing each experiment independently. [SMELT.md:192](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/SMELT.md:192), [SMELT.md:214](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/SMELT.md:214).

## 2. Register and ADC interpretation

**READ:**

- **Debounce correct:** mask `0x03`; bypass/5/10/20 ms encode as 0/1/2/3. Thus `0x21` selects 5 ms. [qpnp-charger.c:1979](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1979).
- **Battery-OV claim incorrect:** BUCK bit 1 is `VREF_OV_IRQ`, named `vreg-ov` in DT; **bit 0 is `VBAT_OV_IRQ`**. `0x42` asserts VDD_LOOP and VREF_OV, with VBAT_OV clear. [qpnp-charger.c:194](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:194), [aos-dtb-0.dts:6025](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:6025).
- **BATFET correct:** BAT_IF bit 2 is BAT_FET_ON; the driver explicitly uses it to answer “closed.” `0x03` means battery-present and temperature-OK, without FET-on. [qpnp-charger.c:203](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:203), [qpnp-charger.c:847](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:847).
- **Linux `0x08` is VCHG_LOOP**, not ICHG_LOOP (`0x10`). Calling it the input-current loop conflates distinct signals. [qpnp-charger.c:195](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:195).
- **ADC channels/scaling correct:** USBIN=0, VBAT_SNS=6, VSYS/VPH_PWR=7. DT selects scaling index 4 for USB and 1 for both battery/system channels; the ratios are 1/20 and 1/3. [qpnp-adc.h:27](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/qpnp/qpnp-adc.h:27), [qpnp-adc.h:910](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/qpnp/qpnp-adc.h:910), [DT:6376](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:6376), [DT:6409](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:6409).

## 3. What the proposed mechanism establishes

**READ:** The session records VPH/VBAT_SNS=4971 mV, USB=5140 mV, and approximately zero instantaneous gauge current. The dump confirms BUCK=`42`, BAT_IF=`03`, USB_OVP_CTL=`21`. [session:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-smelt-pmic-session-2026-11-07.txt:21), [session:61](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-smelt-pmic-session-2026-11-07.txt:61), [dump:292](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/smelt-pmic-dump-2026-11-07.txt:292).

**INFER:** These support USB supplying the system while the cell contributes little. Equal ADC readings do not establish permanent board wiring, the reason BATFET is off, or a particular latch mechanism. No supplied waveform establishes the asserted approximately 2 ms rail-collapse time.

**READ:** The driver uses the debounce setting to delay an OVP health check after **coarse-detect rises**. It does not document BATFET turn-on timing after USB falls. [qpnp-charger.c:2011](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:2011).

**INFER:** “USB-invalid waits 5 ms, then closes BATFET” remains a hardware hypothesis. USB_SUSP deaths likewise do not independently prove that USB-invalid never asserted.

**READ:** Battery removal disables charging; batteryless operation receives a higher USB-current allowance explicitly to avoid UVLO. BATFET regulator operations control low-power mode, not an unconditional close override. [qpnp-charger.c:2303](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:2303), [qpnp-charger.c:1142](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1142), [qpnp-charger.c:1926](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1926).

**INFER:** Resolve the “otherwise identical registers” claim: if Linux also has BAT_IF=`03`, its FET is not reported closed either. Cell current could involve a diode or another path. Discharging proves net cell contribution, not that USB supplies nothing.

## 4. Alternative explanations for Linux’s state

**READ:** The extracted smelt DT disables the charger parent, but retains MDSS’s `batfet-supply` and marks BMS **`ok`**. “MTP only” and “BMS disabled” are therefore inaccurate descriptions of this extracted tree. [DT:2886](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:2886), [DT:5991](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:5991), [DT:6072](/private/tmp/claude-501/-Users-darrel-Downloads-AsteroidOS-asteroid-embedded/5b231a66-b8fe-4305-8d9d-718bd0504428/scratchpad/aos-dtb-0.dts:6072).

**INFER:** The disabled charger normally prevents its BATFET regulator provider from registering, so the MDSS reference alone cannot explain closure. Actual kernel configuration/probe evidence remains necessary.

**READ:** BMS configures IADC sense circuitry; its BATFET-open work temporarily changes sample delay and recalibrates. IADC’s documented open-FET channel substitution concerns PM8941. These are concrete additional paths to audit, not demonstrated SMBB hand-over operations. [qpnp-bms.c:4818](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:4818), [qpnp-bms.c:3820](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3820), [qpnp-adc-current.c:939](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:939).

**READ:** USB PHY current requests can reach charger suspend/current-limit writes through power-supply callbacks; that route requires an active charger consumer. [phy-msm-usb.c:1420](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1420), [qpnp-charger.c:3414](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:3414).

**INFER:** Autonomous input-voltage regulation/collapse is an alternative worth distinguishing from USB-invalid, particularly given VCHG_LOOP. Neither software AICL nor a boot-load sag is established here.

**READ:** LK contains a broken-battery test that changes VCP/trickle settings and restores several values, but I found no caller in this checkout. `fastboot boot` reaches the common `boot_linux` handoff. [pm8x41.c:770](/Users/darrel/Downloads/AsteroidOS/lk2nd/dev/pmic/pm8x41/pm8x41.c:770), [aboot.c:3472](/Users/darrel/Downloads/AsteroidOS/lk2nd/app/aboot/aboot.c:3472).

**INFER:** LK2nd cannot establish what Motorola’s stock aboot does. The 3.1-second reading cannot distinguish reset, bootloader, or early firmware effects. Equal final dumps cannot exclude transient writes.

## 5. Debounce-zero risk and better fix

**READ:** The patch preserves other USB_OVP_CTL bits. The vendor chooses 20 ms without checking that BATFET is closed. [pmic.c:484](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:484), [qpnp-charger.c:6171](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:6171).

**INFER:** Bypass can expose insertion/contact bounce as repeated valid transitions, power-path switching and wake interrupts. The vendor default argues for filtering, but does not prove bypass unsafe on smelt—or explain the observed 5 ms configuration.

**INFER:** No inspected source provides a proven, UVLO-free sequence to force Linux’s state. CHG_ON_BAT_FORCE expresses that intent, but its reported failure needs explanation; BATFET LPM-off is not equivalent. Do not substitute undocumented overrides or forced charging. Establish the transition using synchronized rail/status measurements and the actual Linux initialization path. Debounce-zero failure would not uniquely identify slow FET turn-on.

## 6. Firmware-diff findings

- **READ:** Events ignore `kv_set` failures after advancing cached cable state. **INFER:** failed persistence is not retried until another event. Dual CRC slots help interrupted writes, not lost events. [events.c:43](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/events.c:43), [kv.c:137](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/kv.c:137).
- **READ:** Sampling begins after 5 seconds and runs at one-second intervals; `batt_cable()` is dock **OR USB**. **INFER:** dock movement with USB present and brief disconnects can leave no event. Writes also add load during marginal power. [events.c:51](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/events.c:51), [gauge_max17050.c:178](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/gauge_max17050.c:178).
- **READ:** Gauge USB IRQ consumption is unconditional and rising-edge-only. **INFER:** appropriate for insertion wake; bypass increases bounce sensitivity. [gauge_max17050.c:215](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/gauge_max17050.c:215), [pmic.c:443](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:443).
- **READ:** PMIC writes accept unchecked address width/trailing arguments; SPMI masks addresses to 20 bits and wrappers discard errors. **INFER:** typos can target another register; readback is not reliable success reporting. [console.c:327](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:327), [spmi.c:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/spmi.c:21), [spmi.c:113](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/spmi.c:113).
- **READ:** Boot ADC formatting does not reject negative channel results. **INFER:** timeouts can become misleading voltages. [pmic.c:74](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:74).
- **READ:** The deliberate cookie is uncommitted; normal reset clears it. **INFER:** its diagnostic purpose is consistent, but surviving IMEM is required. [reboot.c:24](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/reboot.c:24).

Read-only review completed; no edits, commits, builds, or device access.
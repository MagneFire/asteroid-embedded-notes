**INFER: plausible offset-error explanation, but not established by this log. The updated script is not yet a valid measurement fix.** Two premises need correcting: property reads already trigger temperature checks, and Linux **does clear the raw shadow counter**.

**READ — calibration path.** `qpnp_iadc_work` schedules another calibration after 300,000 ms of jiffies-based time; it is not a suspend wake alarm. Suspend time does not advance that deadline like wall time. However, calibration also occurs through:

`charge_counter_shadow → calculate_cc → qpnp_iadc_get_gain_and_offset → qpnp_check_pmic_temp`

A hwmon read reaches the same check through `qpnp_iadc_read`. It recalibrates only when die temperature differs from the remembered value by **more than 5°C**, provided automatic calibration is enabled. Other BATFET-related paths exist too. [IADC source](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:1037)

**READ — firmware differs materially.** It refreshes on the first `bms_poll` after 300 elapsed seconds, averaging **64 external-offset conversions**. The inspected Linux DT selects internal calibration, with no hardware averaging configured. Thus adding periodic reads does **not** match firmware’s calibration policy. [Firmware](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:658), [poll](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/bms.c:840), [Linux DT](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:423)

**READ — what the log establishes:**

| Shadow change | Elapsed | Apparent current |
|---|---:|---:|
| 9008 → 8368 µAh | 1016 s | −2.27 mA |
| 8368 → 8572 | 1802 s | +0.41 mA |
| 8572 → 8464 | 1801 s | −0.22 mA |

Trim is already `bbd3` at the second sample and remains there; instantaneous readings include −3298 and −515 µA. Battery temperature falls 25.0→17.0°C, but **PMIC die temperature and calibration timing are missing**. The script reads the property before trim, so the reported trim can have been installed during that very sample. [Log](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-rpm-2026-11-06/aos-power.log:236)

**INFER:** nine codes × 0.3–0.5 mA/code gives a plausible **2.7–4.5 mA** error budget, not a demonstrated error. The endpoint trim difference does not establish nine codes of staleness throughout the interval. Negative instantaneous current strengthens the offset hypothesis independently of cumulative-property rescaling. The vendor explicitly says BMS uses new calibration on its **next vsense sample**; that supports prospective hardware correction, not retroactive correction of accumulated charge. [Vendor comment](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3843)

**READ — rescaling and resets.** The property is:

`banked software µAh + currently scaled hardware subtotal`

Normal SOC calculation banks and **resets both counters**, including shadow. Previously banked charge is not rescaled. Only the outstanding hardware subtotal receives the current gain and compensation factors. [Conversion](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1441), [normal resets](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1848)

**INFER:** rescaling can cause property steps, but ordinary changes look too small to explain −640 µAh alone: nine codes against gain≈3291 is about 0.27%; the documented GF temperature factor changes about 0.27% over 8°C. These estimates are not an exclusion—the actual gain, die temperature and outstanding subtotal are absent. **Raw endpoint subtraction across Linux resets is invalid**, even with firmware’s conversion constants.

**READ/INFER — script review:** `sh -n` passes; measurement validity does not.

- **READ:** `iadc()` silently tolerates no matching file, suppresses errors and discards results. **INFER:** resolve one actual channel path and log success/result; do not treat this as forced calibration.
- **READ:** Linux holds `HOLD_OREG_DATA` at `0x4042`, waits ≥60 µs, reads five bytes, then releases it under `bms_output_lock`. Firmware similarly holds and waits 100 µs. **INFER:** two unlatched reads are diagnostic only; the script neither checks agreement nor establishes atomicity. Use a driver-mediated snapshot. Shell manipulation of HOLD can race the driver. [Latch protocol](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:524)
- **INFER:** rigorous nominal integration requires raw accounting **at every reset**, plus coherent snapshots, reset reasons, gain/offset and calibration timestamps. Five-minute debugfs sampling cannot supply that.
- **READ:** the five-second wakelock is never explicitly released; raw and property are separate, sequential records. The header’s “no wakealarm” claim is outdated. Prior logs already demonstrate ~302-second timer wakes; `WakeSystem=true` uses suspend-inclusive timing. [systemd documentation](https://freedesktop.org/software/systemd/man/latest/systemd.timer.html)

**INFER — overhead:** do not assume comparability. Five seconds awake per 300 seconds is 1.67% duty cycle—**1.67 mA at an illustrative 100 mA excess awake current**. Firmware’s reported ~30 ms outside VDD-min per minute is much smaller. Shorten/release Linux’s lock safely and measure actual suspend residency. Firmware need not change merely to diagnose this claim; for Astra’s explicitly matched crossover, use 300-second firmware stats too, but equal cadence alone does not equalize overhead.

**INFER — ≤60-minute rehearsal, before 12 hours:**

1. **0–5 min:** verify running kernel/DT, one logger, successful hwmon read, timer wakes and return to suspend. Enable narrowly scoped existing driver diagnostics if available: raw subtotal, software accumulator, gain/offset, calibration and resets.
2. **5–25 min:** observe natural post-charge cooling at 300-second wakes. Capture trim before and after property/hwmon reads, die temperature, current and reset-aware counter data.
3. **25–35 min:** keep Linux awake long enough to observe its periodic calibration; record the actual event and resulting trim. This deliberately perturbs temperature, so exclude it from current comparison.
4. **35–55 min:** resume five-minute sampling and settling. Compare nominal raw integration with the property, and relate slope changes to calibration events.

**INFER:** property reversal with nonnegative reset-corrected raw integration supports rescaling/accounting; negative raw integration that changes with calibration supports hardware offset error. No reversal in one hour does not kill the mechanism. **Without reset-aware diagnostics, this rehearsal can validate logging but cannot prove the causal claim.**

**INFER — settling and switching:** start retained crossover measurements thermally settled, irrespective of calibration; “cold” means comparable stable ambient conditions, not artificially chilled. For the diagnostic rehearsal, cooling is useful. Before reboot, preserve volatile firmware logs and `status`; optionally save passive `pmic 3600 8`, `pmic 36f0 8`, and `pmic 4040 4` snapshots. The existing state file already preserves RPM counters and trim. The `iadc` command additionally measures gain/offset but performs ADC transactions, so it is not purely passive.

**INFER: yes, reasonable to switch to AsteroidOS now for diagnosis after preserving those records. Do not start the 12-hour comparison with this logger as the claimed fix.** No edits, commits or device access performed.
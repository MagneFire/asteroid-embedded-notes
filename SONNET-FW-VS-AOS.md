# Firmware vs AsteroidOS in the power tests (Sonnet 5.5, 2026-11-04)

Read-only comparison of the firmware and the vendor kernel/AsteroidOS for the
sleep-current measurements (POWER.md §19-§20). Claims marked READ come from
code or logs, INFER are reasoning. Not yet checked on the watch.

Summary: the two counters probably measure the same thing within noise (AOS
settled 4.55 mA vs firmware 4.70 mA). The weak point is AsteroidOS's trim:
one conversion, rarely refreshed in suspend, probably from the internal
offset channel 6 (the sturgeon IADC DT node lacks qcom,rsense,
msm-pm8226.dtsi:423-437; channel choice qpnp-adc-current.c:954-960), so its
number is ±~1.5 mA, and the 2.1 mA endpoint figure is a stale-trim artefact
while cooling.

Ranked differences:
1. AOS trim: single unaveraged conversion, delayed work does not advance in
   suspend (trim bbce unchanged ~30 min while cooling, then bbdb for 36 min);
   ±1.5 mA on AOS, up to ~5 mA on the cooling stretch.
2. Panel: Linux powers the panel supplies off (mdss_dsi.c:64-98; L15 panel
   2.8 V, L8, L4 per msm8226-mdss.dtsi:128-130) and sends the deep-standby
   writes; firmware only DCS 28/10. Firmware higher by ~0.1-0.8 mA (INFER).
3. Touch: Linux keeps touch in wake-gesture doze with L19 on
   (synaptics_dsx_core.c:3851-3856, WAKEUP_GESTURE true :43, is_wake in
   sturgeon-common.dtsi:19); firmware sleeps the sensor (T, +0.8 mA).
4. Wake cost: similar wake rates (~4-6 VDD-min entries/min), Linux resume
   heavier; firmware wakes for BMS calc every 20 s and the minute stats.
5. Linux ADC-TM monitors at 1 s and the battery thermistor bias forced on
   (qpnp-bms.c:3464, :4902; qpnp-charger.c:6800, :6083): ~0.02-0.1 mA on AOS.
6. Counter scaling: same constants and rsense; Linux adds gain and
   revision/temperature compensation (~1-3%).
7. Sleep-set votes: Linux votes CX/MX in both sets; firmware none (active
   applies in sleep). Unknown, 0-1 mA.
8. Protocol: AOS cooled 24->17 C and started right after a charge; firmware
   settled at 20-23 C; battery 4.22-4.25 V vs 4.19-4.03 V.

Suggested checks: firmware logs the 64-sample ch6 mean beside ch5 plus the
gain; AOS rerun after cooling with timer wakes, trim logged each sample (or
forced to the firmware's 64-sample value); an AOS snapshot (regulator_summary
for L15/L8/L4/L19/L17/L10/L20, touch wakeup_gesture, wakeup_sources,
/proc/interrupts diff, the running IADC DT node); then the panel full-off
night (P).

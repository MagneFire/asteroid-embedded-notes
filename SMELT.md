# Smelt (Moto 360 2015) as the next platform (2026-11-05, read-only research)

Verdict: feasible. Same SoC family, so `src/soc/` carries over, but about 2-3x sparrow's effort
(judgement, not measured). Kernel: `android-msm-smelt-3.10-marshmallow-mr1-wear-release` in the
mirror on pc. Most of the below comes from its device trees.

Hardware: APQ8026 (msm-id 199), NT35350/NT35355 360x330 cmd panel with a flat tire, TE gpio 24,
401 lines; LM3535 backlight on QUP3 at 0x38; Atmel mXT touch at 0x4a on QUP5, irq 17, reset 16;
M4 hub (STM32) at 0x43 on QUP2; TSL2584 ALS; BCM43430A1 on UART6, reg_on 26, host wake 27, dev
wake 30; PM8226 vibrator 2300 mV; MAX17050 gauge at 0x36 on QUP3; Qi charging via bq5105x, dock
detect gpio 54; PMIC charger and BMS disabled in the kernel. USB PHY init 44 68 24 13.

New drivers: touch, hub, gauge, backlight. Rework: charger and battery calls behind a table, as
smelt has no PMIC charger or BMS. Board data: panel, USB, BT, haptics. Small: firmware name
length (41-char patch name).

Risks: DTB path first (3-cell msm-id, no board-id, about 12 variants; `qcdt.py` needs changes;
Moto aboot and QCDT unknown; no lk2nd dts); no labelled UART, USB through the pogo dock; a flat
binary on Moto aboot is untested; reboot-to-fastboot restart reason unknown; no AsteroidOS
current baseline; `pmic_charger_configure` must not run until SMBB wiring is known.

Milestones: 1 boot and identify (`board: smelt`, adb over the dock, back to fastboot); 2 usable
watch (panel, LM3535, MAX17050, charger off, gpio 54, touch); 3 BT, hub without flashing, tilt
wake, cluster collapse, current against an AsteroidOS measurement.

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

## First boot on a real smelt (2026-11-06)

Main b4954a0 from RAM, `fastboot boot`, bootloader SMELT_50.22, unlocked, panel nt35350 large.
logs-smelt-first-boot-2026-11-06.txt. Up: board by panel size (SMEM platform read 0), gauge,
LM3535 answers, eMMC, store on cache, mXT family 82, USB, BT, M4 firmware 0084, GPU.

Not working: nothing reaches the panel, which keeps the Motorola logo. PP0 done never fires, so
each frame times out at 100 ms (10 fps) and the display never rests. CTL_LAYER0 reads 0 where
sturgeon has 0x200 (RGB0 on stage 1), CTL_FLUSH stays ffff. display_init relies on the bootloader
leaving the pipeline set up. Next: set it up as mdss_mdp_ctl does. DT has cont-splash, TE pin,
mdp-trigger "none", dma-trigger sw. Taps did nothing visible, touch not checked further.

Heat: gauge 50 -> 56 C in about 3 min on the dock at 100%, back much hotter, thermal shutdown
suspected. Unproved lead: bq5105x-ctrl only exports chg_term 53, chg_rate 58, chg_n 94 (input); userspace (healthd.smelt, charge-restart-level=98) ends charging, and the firmware
drives none of them. The firmware has no temperature limit here.

AsteroidOS autosleep drops USB: hold a wakelock for adb. usbproxy-bm holds back the tail of a
fastboot download that is not a multiple of its 4096-byte chunk: pad the image. Backup of the cache
head verified (smelt-cache-head-2026-11-06.gz, sha1 364c9397; boot sha1 a90433e1, not pulled).

## Charging policy (healthd.smelt, 2026-11-06)

Binary: wrynose build tmp/work/smelt-oe-linux-gnueabi/android/marshmallow/image/system/bin/healthd.
It writes /sys/devices/0.bq5105x-ctrl/chg_term and chg_rate, reads chg_n and the gauge's
current_avg. Values from the boot log, temperatures in 0.1 C:

- Monitor every 60 s charging; discharging 600 s, or 60 s when warm. Thermal rules start 300 s after boot.
- Above 45.0 C (hyst 3.0) periodic charging: 600 s on, 300 s off. A reduced rate exists too.
- Terminate at 53.0 C (hyst 1.0).
- Complete after 1800 s, or current_avg at or under 16 mA 5 times; restart at 98 %.

The firmware has none of this: it started at 50 C and ran past 53 C still charging. From its code: chg_term 1 stops
charging, 0 allows it; chg_rate 1 is the reduced rate; it also writes 1 to the dock's smart_debounce.
So AsteroidOS already had the cell near 50 C on this dock.

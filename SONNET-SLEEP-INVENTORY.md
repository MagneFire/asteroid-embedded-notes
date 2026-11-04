# Sleep-state inventory, firmware vs AsteroidOS (Sonnet 5.5, 2026-11-04)

Read-only, code and AsteroidOS logs. READ = seen in code/logs, INFER =
reasoning. Not yet checked on the watch.

Headlines:
1. Trim-independent support for a physical gap (INFER, rough): battery voltage
   fell ~14 mV/h under the firmware (§19, BMS OCV 4168 -> 4068 mV in 7 h) vs
   ~7 mV/h under AsteroidOS (day run, wake samples): ~3.9 vs ~1.6 mA, a gap of
   ~2 mA (1.5-3).
2. Linux costs more on touch (wake-gesture doze, L19 on) than the firmware's
   sensor sleep, so the firmware's real excess elsewhere is larger.
3. Linux's sleep set turns L8 off (sleep-only handle 8226_l8_so with
   init-enable 0, msm8226-regulator.dtsi:296-303; aggregation
   rpm-smd-regulator.c:480-545) and puts MX at max(sleep handles, 750 mV)
   (l3_so, :223-231). SUSPEND.md's "not sent" claim looks wrong. Our L8 LPM
   vote reset the chip while Linux's off-in-sleep survives: resume order differs.
4. dmesg.txt in logs-aos-2026-11-04 is the 5 s RTC-alarm loop (eMMC re-init on
   alternate resumes), not the quiet day run.

Ranked candidates for the gap:
1. Bootloader-left hardware Linux collapses at late init ("clock_late_init:
   Removing enables held for handed-off clocks", journal:740; regulator late
   cleanup journal:219-224): MMSS GDSCs (venus, vfe, jpeg, oxili GX), clocks,
   extra rails. 0-1+ mA. Check: firmware `mem` of the GDSCRs (0xfd8c1024,
   0x3664, 0x35a4, 0x4024, 0x4034, 0x2304; offsets to verify) and `pmic` of all
   Ln/Sn enables vs the snapshot's gdsc_* states, enabled_clocks, regulators.
2. Hub in reset vs MCU sleeping with sensors as configured: -0.5 to +1.5 mA.
   Check: the S arm.
3. Panel left in sleep-in with L15/L8/L4 up (Linux: 00 00, 4F 01, rails off,
   reset low); GPIO 78 (display enable, possibly an external AMOLED supply):
   0.1-0.5 mA, up to 1.5. Check: `mem 0xfd5114e0` (gpio 78) and the P arm.
4. CX/MX/DDR votes inside VDD-min: 0-1 mA. Check: Linux rpm_smd_regulator
   debug_mask=2 lines for smpa 1 / ldoa 3 in the sleep set.
5. eMMC VCC (L17) off in Linux: 0.05-0.3 mA. 6. USB L10/L20: measured 0.1-0.2.
7. Firmware wake overhead ~0.1-0.3 mA. 8. PMIC auxiliaries, pull-ups: <0.2 each.

TLMM: no pin found driving a powered-down device above ~0.1 mA (table in the
session report); GPIO 25 differs (Linux pull-up into the off panel).
Cheapest step: one firmware pass reading PMIC enables (L1-L28, S1-S5, LVS1),
MMSS GDSCRs and TLMM cfg/io words, diffed against one AsteroidOS snapshot.

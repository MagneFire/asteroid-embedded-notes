# Minnow port: second Opus review, 2026-11-11

Three Opus reviewers read the parts the first review did not cover: storage,
the peripherals, and sleep / display rest / Qualcomm regressions. Vendor paths
are relative to `minnow/minnow-kernel/`.

## Qualcomm regressions

None found. The reviewer built every commit for qcom and compared the
disassembly: the renames, the directory move, the Makefile split, start.S,
cache.S, log.c, the linker script and all third-party objects are identical;
the remaining splits were read statement by statement.

## Fixed on the branch (folded into the commits they belong to)

- squashfs: the symlink rewrite could write 7 bytes past `target[256]` for a
  long `/system/...` link; the length check now counts the skipped prefix.
- MBR/EBR: a logical partition's start and size are checked against the
  extended partition (a damaged EBR could name any sector `cache`).
- Bluetooth: `bt_sleep` held RTS while asleep, as on Qualcomm, where the UART
  clock stops. On OMAP3 the UART keeps its clock and nothing else could wake
  the watch (CTS interrupt off, pad wake-up unused), so chip traffic waited for
  the next timer wake. `bt_sleep` now does nothing: a received byte wakes the MPU.
- UART: erratum i202 (`omap-serial.c:1708-1740`): 2 us wait, FIFO clear and
  wait after every MDR1 write.
- Charger: rising-edge interrupt on the charging line (gpio 176), as placing
  the watch on the pad only makes lines rise; det high (gpio 22) counts as
  docked, per the table in `bq5105x_detect.c:36-50`, which also stops the
  1.5 s undock after charging stops with det still high.
- Pads: gpio 78, 83, 86, 87, 129 (core 0x126 and wkup 0x05a), 21 and 28 are
  now muxed as GPIO outputs as in `omap3-minnow.dtsi:719-765, 909`, instead of
  trusting MBM.
- Sleep: NEON domain follows the MPU (`pm34xx.c:316-318`); RTA disabled
  (erratum i608, `pm34xx.c:836-842`); CORE and PER clock domains set to never
  idle and the crystal's automatic stop cleared, so "the rest stays up" no
  longer depends on what MBM left.
- GPIO: wake-up enable set for every line with an interrupt
  (`gpio-omap.c:324-328`).
- DSI: BTA (VC bit 5) and ULPS (CIO bit 30) enabled in the interrupt enables,
  as both are polled.
- New commit: a time set in the settings or with `rtc` also goes to the hub
  (minnow reads its clock from the hub at start).

## Left open

- HSMMC2 SYSCONFIG is no-idle; the vendor uses smart idle. Only matters once
  CORE retention is tried.
- Hub light sensor: raw value, not lux (vendor scale 0-2330,
  `leds-lm3535.c:467-492`), and the first reading after enabling is stale.
- `bt_tx_activity` gives up after 5 x 50 ms and treats the chip as awake; the
  vendor waits for the ack for ever. After that the watch does not sleep
  deeply until the chip says it sleeps again.
- Screen status sent to the hub is 1 or 0; the vendor sends the real state
  0-3 (`m4sensorhub-extern.c:92-124`).
- A GATT time write while the hub is still starting is overwritten by the
  hub's time.
- charge_term polarity (gpio 78 high stops) is inferred; the vendor kernel
  never drives it.
- DSS power domain and DPLL4's DSS output stay on at display rest (power only).
- A hub wake that lands between power_idle's checks and wfi waits for the
  next tick (same pattern on Qualcomm).
- No host tests for hsmmc.c, the .bts runner, HCILL, or the hub's byte-wide
  interrupt registers.
- Still open from the first review: relocation if MBM loads at or just above
  0x88000000; TinyUSB writing 0x340/0x342.

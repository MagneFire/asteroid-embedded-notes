# Hindsight: why the smelt bring-up was harder than sturgeon and sparrow (2026-11-07)

Verdict: mostly the **platform**, made worse by the **process**. Firmware complexity was not the
cause; what hurt were assumptions that held on two watches close to Qualcomm's reference design.
Smelt is the one that departs from it. (No wren unit was ported; the comparison is with sparrow,
its larger sibling.)

Sources: `git log` eac1042..f93f312 (25 smelt commits, 10 before the first boot, 15 fixes
after), SMELT.md, SMELT-PORT.md, CODEX-SMELT-SAFETY-2026-11-06.md, EMBEDDED.md "Sparrow
bring-up", the smelt logs from 2026-11-06.

## 1. Smelt is a non-reference board

| Area | sturgeon / sparrow | smelt | What it cost |
|---|---|---|---|
| Charging | PMIC charger and BMS, termination in hardware | PMIC charger off; bq5105x Qi receiver on GPIOs 53/58/54/94, stop rules in userspace `healthd.smelt` | No charge policy in the firmware: overheated on the first boot (15ed191). The most dangerous bug of the three ports |
| Display | Bootloader splash leaves the MDP pipeline set up, `display_init` reads it back | Moto aboot leaves `CTL_LAYER0` 0; flat-tire panel | No picture, every frame times out (71d8784, 7ddece1) |
| Detection | board-id in the DTB | No board-id, 3-cell msm-id, appended DTBs, SMEM platform reads 0 | Three detection commits: panel size, SMEM, fuel gauge (2e549db, 4e7b216, b4954a0) |
| Sensor hub | EM7184, firmware upload | STM32 M4 through its ROM bootloader; stalls its bus, needs restarting | 345144f, 80a8975, I2C recovery |
| Touch | IT7260 / RMI4 | Atmel mXT at full sensitivity, no low-power config from NVM | Self-wake, palm, edge gestures (c28d144, c77a835, a9390ba) |
| Power in | USB cable | Qi dock with a glitchy detect line, USB through the pogo proxy | Dock debounce (1124c47), wake bursts, fastboot images padded to 4096 bytes |
| Debug access | lk2nd with ramoops (sturgeon), stock fastboot (sparrow) | No UART, no ramoops, no AsteroidOS current baseline | Crashes without a log |

Sparrow's worst item (IT7260 dozing off and NACKing its address) cost hours. Smelt had about
eight items of that size.

## 2. Process: written before there was a watch

SMELT-PORT.md is headed "no watch attached": all four drivers, detection and the battery table
were written from the kernel sources on 2026-11-05, so the first boot on 2026-11-06 was also the
first integration test. Sparrow was brought up with the watch on the desk, one device at a time.
The final merge (f93f312) was never booted, and its shared changes were not rechecked on
sturgeon or sparrow.

## 3. Firmware: latent assumptions, not complexity

Smelt exposed real bugs in shared code that the other two watches never triggered:

- I2C: one timeout stopped the bus until reboot (8d6afd8); the M4 bus was the first to time out.
- Watchdog stopped only for sleeps over 1 s, so a late wake reset the watch (f93f312); the cause
  of the late wake is still unknown.
- Short button presses missed while asleep (04fd688), a generic bug.
- Display relied on the bootloader's pipeline, battery code assumed a PMIC charger: each needed an
  abstraction (eac1042, e47e3f1).

These fixes now protect all three watches.

## Lessons for the next board

- Before writing drivers, list what the stock kernel **and userspace** do that the bootloader
  doesn't: charge policy, pipeline setup, low-power touch config.
- Anything safety-related that lives in vendor userspace (healthd) blocks the first boot.
- Get the board's own drivers working on the watch before one-image and detection work.
- Boot main on sturgeon and sparrow before pushing shared changes from a port.

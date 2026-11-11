<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

I've mapped the vendor driver against hub_m4.c. **The current driver won't work on minnow unchanged.** The wire protocol and bootloader opcodes match smelt, but four things differ: the GO address, the firmware mark, the bank numbers and the interrupt registers. Nothing below has run on a watch.

Vendor files below are under `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/`. Ours are under `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-minnow/src/`.

## 1. Transport, pins, interrupts

**Register framing is the same as ours.**
- A read is a write of `{bank, offset}`, then a repeated start and N bytes read back. A write is `{bank, offset, data...}`, little endian. There is no checksum (`drivers/mfd/m4sensorhub-reg.c:126-131`, `:198-222`).
- When a mask is given, a write first reads the register back and changes only the masked bits (`reg.c:202-218`). The interrupt enables are always written this way.
- Retries: 10 per transfer, 20-50 µs apart (`reg.c:28-30`, `:392-404`).
- Our framing in `m4_proto.c` and `hub_m4.c:122-134` needs no change.

**Sizes, speed, timeouts.**
- Largest register is 2048 bytes (`include/linux/m4sensorhub/m4sensorhub_registers.h:28`). Bootloader reads and writes go up to 256 bytes (`m4sensorhub-stm32_401-fw.c:101`).
- Our OMAP I2C allows 64-byte writes and 256-byte reads (`soc/omap3/i2c.c:48-49`), which is enough.
- The bus runs at 400 kHz (`arch/arm/boot/dts/omap3-minnow.dtsi:338-340`).
- The vendor's per-transfer timeout is 500 ms (`drivers/i2c/busses/i2c-omap.c:59`); the OMAP controller itself waits out clock stretching. Our 1 s allowance (`hub_m4.c:32`) covers it.

**One I2C address, 0x39, for both the ROM bootloader and the application.** The kernel keeps a single client. 0x39 is also what selects the STM32F401 loader path (`m4sensorhub-core.c:136`, `:449-454`).

**Pins** (DT at `omap3-minnow.dtsi:347-352`, driver at `m4sensorhub-core.c:194-245`). The driver passes NULL for the flags, so every DT flag below is ignored.

| gpio | DT name | vendor use | pad |
|---|---|---|---|
| 59 | irq | Input, hub to AP. Requested as `IRQF_TRIGGER_HIGH \| IRQF_ONESHOT` and made a wake source (`m4sensorhub-irq.c:196-204`). It is active high even though the DT flag is 1. | 0x08e = 0x4104, already in our `board/minnow.c:9` |
| 129 | reset | Output, held low from probe until the firmware load starts. Then 0 = in reset, 1 = running, driven high, not released to input. DT flag 2 is ignored. | wkup pad 0x05a MODE4 output (`dtsi:909`). The core pad 0x126 is also labelled "GPIO129" (`dtsi:733`), which is unclear. |
| 21 | boot0 | Output, starts low, set to 1 before every reset and never lowered again. | 0x5ba MODE4 output (`dtsi:762`) |
| 126 | wake | Output, driven low once, never used again. | 0x102 is MODE7, safe mode with pull-down (`dtsi:731`), so the pin isn't even routed to the GPIO block. Leave it alone. |
| 28 | enable | Output, driven low once and never changed. The driver calls it `mpu_9150_en_gpio`, a leftover of an older design. | 0x5c8 MODE4 output (`dtsi:765`) |

The smelt "wake line" role belongs to **gpio 59** on minnow. Our `wake_pin()` does nothing on OMAP (`soc/omap3/sleep.c:18`); waking from sleep depends on the pad's OFFWAKEUP bit, which is already set.

The M4's debug UART is OMAP **UART4** (pads 0x0a0/0x0a2, `dtsi:288`, `:997-1002`). Its panic dumps should appear there, which could help on the watch.

**Interrupt registers are a different design from smelt** (`include/linux/m4sensorhub/m4sensorhub_irqs.h`, `irq.c:113-123`):
- There is no wake/nowake split and no 32-bit masks. There are three 1-byte enables in GENERAL at 0x0b, 0x0c, 0x0d and three 1-byte statuses at 0x0e, 0x0f, 0x10.
- INT0 bits: 0 pressure, 1 temp, 2 gyro, 3 pedometer, 4 compass, 5 fusion, 6 accel, **7 GESTURE**.
- INT1 bits: **0 STILL, 1 MOTION**, 2 activity, 3 download response, 4 mic, 5 wrist, 6 passive buffer full, 7 ALS.
- INT2 bits: 0 HR sensor, **1 AP_ALARM_EXPIRED**, 2 heart rate data, 3 significant motion.
- The vendor reads the three statuses one byte at a time. The comment says the hub clears them on read (`irq.c:722-732`).
- Our 4-byte read at 0x0e would run past the 17-byte bank. Whether one 3-byte read clears all three registers is **unknown**, so copy the vendor's three 1-byte reads.

## 2. Boot

The vendor always goes through the ROM bootloader with boot0 high, like smelt, but the addresses differ.

**Reset sequence** (`m4sensorhub-core.c:136-146`):
1. boot0 = 1, wait 5-10 ms.
2. reset = 0, wait 10-12 ms.
3. reset = 1, driven high. Wait 400 ms.

**Loader** (`m4sensorhub-stm32_401-fw.c`):
- Opcodes are the same as ours: ACK 0x79, NACK 0x1F, BUSY 0x76, read 0x11, GO 0x21. The address is sent big endian with an XOR byte. BUSY is polled up to 60 times, 100 ms apart (`:38-70`, `:396-429`, `:442-563`).
- **Firmware base is 0x08040000**, flash sectors 6-7 (`:73`). The version is a u16 at 0x08040200 (`:74-75`).
- **The mark is 4 bytes, 0x0ACEC0DE, at 0x0807FFFC** (`:79-80`). In flash that reads `DE C0 CE 0A`.
- The flash is 512 KB, so the image is limited to 256 KB minus 4 (`:98`).
- **GO goes to 0x08040000**, followed by a 100 ms wait (`:767-793`).
- The firmware file checks out: p2_5 starts with SP 0x20008030 and reset vector 0x0806448D, and its version at offset 0x200 is 0x00F4. The p0 image's version there is 0x00D7.

**When it reflashes** (`:176-262`):
- If the mark is missing: erase sectors 6 and 7, then write.
- If the mark is present: compare the device version with the file version and reflash only when they differ. Before reflashing it boots the hub once so the RTC driver can cache the time (`rtc-sensorhub.c:241-303`).
- With no firmware file, it runs what is already in flash (`:156-162`).
- `fw_version` is always taken from the file, never read from the hub (`:323`).

**Readiness check after GO** (`:337-385`):
- Read bank 0 offset 0, 1 byte. Up to 3 tries, with 100 and 200 ms waits; a retry does a full reset and GO again.
- If all three fail, the vendor panics the kernel (`:381`).

**Does "only read memory and GO" still work?** Yes, it's safe and sufficient, but the code needs these changes:
- `M4_FLASH_BASE` → 0x08040000 (`m4_proto.h:17`). Sectors 0-5 hold unknown content, so GO to 0x08000000 would be wrong.
- `M4_BARKER_ADDR` → 0x0807FFFC (`m4_proto.h:18`), `M4_BARKER_SIZE` → 4, mark = `DE C0 CE 0A`.
  - An 8-byte read at 0x0807FFF8 would return 4 unknown bytes followed by the mark, so the current check fails.
  - The test at `m4_test.c:15` asserts the old address.
- Use the vendor's reset timing and drive reset **high** to release it. Our `reset_pulse` releases it to input (`hub_m4.c:153`), and whether there is a pull-up on minnow is **unknown**.
- Optionally read the u16 version at 0x08040200 through the bootloader before GO; this is where the vendor's version lives.
- The flash may hold p0 (0x00D7) or p2_5 (0x00F4) depending on what stock last loaded. **Read it on the watch.**

## 3. Register map: smelt vs minnow

Minnow's banks follow `enum m4sensorhub_type` (`include/linux/m4sensorhub/m4sensorhub_bank_enum.h`):

| id | bank | id | bank | id | bank |
|---|---|---|---|---|---|
| 0 | ACCEL | 9 | GYRO | 18 | GESTURE |
| 1 | TEMP | 10 | METS | 19 | PASSIVE |
| 2 | GENERAL | 11 | USERSETTINGS | 20 | EMG |
| 3 | PRESSURE | 12 | POWER | 21 | HEARTRATE |
| 4 | PEDOMETER | 13 | LOCATION | 22 | HRSENSOR |
| 5 | TCMD | 14 | DOWNLOAD | 23 | LIGHTSENSOR |
| 6 | LOG | 15 | AUDIO | 24 | DEBUG |
| 7 | FUSION | 16 | TIMEPIECE | 0xFF | panic, separate |
| 8 | COMPASS | 17 | WRIST | | |

Offsets and sizes come from the generated table in `drivers/mfd/m4sensorhub-reg.h:34-205`; bank sizes are at `:208-234`.

| Our use (`m4_proto.h`) | Smelt | Minnow | Mismatch |
|---|---|---|---|
| ACCEL rate | 0 / 0x02, 2 bytes | 0 / 0x02, s16 ms, −1 = off, fastest 40 | same |
| ACCEL X/Y/Z | 0 / 0x08, 0x0c, 0x10 | **0 / 0x04, 0x08, 0x0c**, s32 each (`MemMapAccelSensor.h`) | **offset**. Scale is **unknown**; the `/32` assumes 65536 per g. |
| GENERAL bank | 1 | **2** | **bank** |
| UTC | 0x00, 4 bytes | 0x00, u32 | same |
| VERSION | 0x0a, 2 bytes | 0x0a, **1 byte** | **size**. Read 1 byte, or read the flash version instead. |
| NOWAKE/WAKE enable | 0x0c / 0x10, 4 bytes each | **INT0/1/2 enable at 0x0b/0x0c/0x0d, 1 byte each** | **different design** |
| NOWAKE/WAKE status | 0x14 / 0x18 | **INT0/1/2 status at 0x0e/0x0f/0x10** | **different design** |
| Wake bits STILL/MOTION/GESTURE | bits 0/1/2 | **INT1 bit 0, INT1 bit 1, INT0 bit 7** | **different bits** |
| PEDOMETER bank | 3 | **4** | **bank** |
| Pedometer enable, 6-byte block at 0x02, steps at 0x04 | same layout | 0x00 / 0x02 activity, 0x03 equipment, 0x04 u32 steps | layout same, bank differs |
| METS enable | 9 / 0 | **10** / 0 | **bank** |
| POWER bank | 11 | **12** | **bank** |
| POWER enable, still timeout, device state | 0x01 / 0x02 (u16) / 0x08 | same offsets; device state 0 = still, 1 = motion | same |
| GESTURE bank | 13 | **18** | **bank** |
| GESTURE offsets | 0x01..0x03 | 0x01 gesture1, 0x02 confidence1, 0x03 value1 (s8) | same |
| Panic probe | 0xFF / 0xCD → 0xDEADBEEF | same (`m4sensorhub-panic.c:27-29`) | same. A healthy hub answers unknown banks with 0xFF (`panic.c:255`). |

Minnow has 0x0b/0x0c and 0x0e/0x0f/0x10 inside GENERAL, so our current writes would land on the wrong registers.

## 4. Features to add

**(a) RTC** (`drivers/rtc/rtc-sensorhub.c`)
- Time is u32 UTC seconds since 1970 in GENERAL (bank 2) at 0x00. Read and written the same way (`:142-156`, `:206-225`).
- At init the vendor **reads the hub's time and sets the system clock from it** (`:315-365`). The hub's clock survives resets: the vendor resets the hub on every boot and never rewrites it after a hub panic.
- Our `set_time()` (`hub_m4.c:189-195`) goes the other way, writing `rtc_read()` to the hub. On minnow the hub is the RTC, so this needs a `get_time` hook. Write only when the time is actually set.
- **Alarm:** write a u32 *relative* delay in seconds to GENERAL 0x04 (APALARM), at most one day ahead (`:107-128`). Then enable INT2 bit 1; the alarm then arrives as an interrupt (`:368-370`).
- Other registers:
  - LOCALTIMEZONE: GENERAL 0x08, 2 bytes. Only the hub-driven clock face uses it.
  - USERSETTINGS 0x07 (RTCRESET): writing 1 tells the hub the clock changed (`m4sensorhub_display.c:173-183`). Only that same path uses it.

**(b) ALS** (`drivers/misc/m4sensorhub_als.c`)
- Rate: LIGHTSENSOR (bank 23) 0x02, s16 ms. −1 = off, fastest 80 (`:162-192`, `:440-442`).
- Value: 0x04, u16, polled. There is no interrupt; INT1 bit 7 exists but nothing uses it.
- The value is "raw" (`MSC_RAW`). Lux conversion happens in the HAL: `AmbientLightSensor::luxValue` in `sensors.minnow.so`, which I didn't decode, so **the units are unknown**.
- The backlight curve treats it as 0-2330 (`drivers/leds/leds-lm3535.c:467-492`). With the ALS off and a charger connected, the vendor samples every 10 s (`:45`).

**(c) Screen status** (`m4sensorhub-extern.c:92-124`, `panel-minnow.c:3182-3213`)
- USERSETTINGS (bank 11) 0x00, 1 byte: 0 normal off, 1 normal on, 2 ambient off, 3 ambient on.
- Written on every display state change. When docked it is forced to 1 "to block all wakeup gestures" (`panel-minnow.c:3187-3190`). So the hub gates its gestures on screen state.
- The panel driver starts with its cache set to 1 (`:2542`). This suggests the hub's default is "on", which would mean **no tilt interrupt until we write 0 or 2**. That's inferred, not verified.
- AUDIOSTATUS at USERSETTINGS 0x06 tells the hub about the C55 voice processor (`drivers/misc/c55_ctrl.c:171`).
- The "m4display" driver lets the hub drive the panel itself (TIMEPIECE bank 16, enable 0x01). Nothing calls `m4sensorhub_set_display_control`, so it is unused; ignore it.

**(d) One line each**
- **Passive** (bank 19): the hub logs steps, calories, heart rate and healthy minutes into 12-slot buffers while the AP sleeps. Enable at 0x00; buffer-full interrupt is INT1 bit 6.
- **Still mode** (POWER 0x02, u16 seconds, default 600): writing the value restarts the hub's still timer. The vendor rewrites it on every power-key press (`drivers/mfd/cpcap-key.c:111`, `m4sensorhub_stillmode.c:93-110`). STILL and MOTION are always enabled.
- **Fusion** (bank 7): orientation output (Euler angles, gravity, linear accel, rotation vector, heading). Rate at 0x02.
- **Significant motion**: enable at METS (bank 10) 0x18; interrupt INT2 bit 3, which the vendor enables at init.

**(e) Heart rate** (`drivers/misc/m4sensorhub_heartrate.c:110-140`)
- HEARTRATE (bank 21). Rate is an s32 at 0x04: ms, −1 = off, fastest 80. Heart rate is a u16 at 0x08, confidence a u8 at 0x0a. Polled.
- The ENABLE register at 0x00 (u32) is never written by the vendor.

**(f) Battery/charger:** the hub has no registers for these. The fuel gauge (MAX17050) and charger are on the AP side.

**(g) Vibrator:** confirmed not on the hub. It is `mot,vib-gpio` powered from ldo6 (`dtsi:131-133`).

## 5. Power management and panics

**Suspend/resume:**
- The core only sets a debug flag (`m4sensorhub-core.c:925-937`). No "AP power state" register is written.
- The clients' suspend hooks just retry their last sample rate (e.g. `m4sensorhub_accelerometer.c:478-483`). Nothing is turned off.
- gpio 59 is always a wake source. Whatever is enabled in the masks wakes the AP: STILL, MOTION, significant motion and download response always; AP_ALARM when an alarm is set; GESTURE and PASSIVE when the HAL enables them.
- The only state the AP passes to the hub is screen status and audio status.

**Keep-alive:** I found nothing on minnow like the smelt accelerometer finding. The accelerometer starts disabled (`accelerometer.c:426`) and nothing keeps it on. Whether the F401 image has the same accelerometer watchdog is **unknown**. Keep the "accelerometer always on" policy at first and A/B test it on the watch.

**Panic recovery** (`m4sensorhub-irq.c:734-737`, `m4sensorhub-panic.c:271-318`):
1. Interrupt fires and all three statuses read 0.
2. Send `FF CD`, read 4 bytes. 0xDEADBEEF means the hub panicked.
3. Restart it with reset and GO, then test readiness (`BUG()` if that fails).
4. Run the restore callbacks in order: display, HR, passive, fusion, ALS, accel, compass, gyro, pedometer (user data, enables, step base), extern (screen and audio status), and the interrupt masks last (`irq.c:822-846`).

Our `crashed()` and `restart()` logic carries over once the registers are fixed. After a restart we should also restore screen status and the still timeout.

## 6. Wrist tilt

Same as smelt apart from the bank and bit:
- Interrupt INT0 bit 7. Read GESTURE (bank 18) 0x01, 0x02, 0x03 one byte at a time (`m4sensorhub_gesture.c:55-100`).
- Gesture values: VIEW = 1 with value 0 for view on and 1 for view off; WRIST_ROTATE = 2 (`include/linux/m4sensorhub/MemMapGesture.h`). Our `m4_is_tilt` is correct.
- WRIST_ROTATE wakes the display. VIEW on/off only switches between ambient-on and ambient-off while in ambient mode; that switch is `is_gesture_view_on` (`panel-minnow.c:480-492`, `:583-595`).
- The gesture interrupt is enabled only when the HAL sets a rate (`gesture.c:147-176`).
- Gesture delivery likely depends on screen status (§4c).

## 7. Changes, most necessary first

1. **`m4_proto`:** GO to 0x08040000; 4-byte mark at 0x0807FFFC (`DE C0 CE 0A`); GENERAL = 2, PEDOMETER = 4, METS = 10, POWER = 12, GESTURE = 18; VERSION is 1 byte; accel X/Y/Z at 0x04/0x08/0x0c. Update `m4_test.c`.
2. **Interrupts:** replace the 32-bit wake masks and status with three 1-byte enable/status registers. Init writes 0 to 0x0b/0x0c/0x0d, then INT1 = 0x03 (still, motion) and INT0 = 0x80 (gesture when wanted). Read 0x0e, 0x0f, 0x10 one byte each. A panic is all three reading 0.
3. **Reset:** boot0 high, wait 5-10 ms, reset low 10 ms, reset **driven high**, wait 400 ms. Keep reset low until we're ready.
4. **Board table** (`board/minnow.c`): `.hub = &hub_m4`, I2C bus 2, address 0x39, irq 59 (level high), reset 129, boot0 21. Drive gpio 28 low. Leave gpio 126 alone. Add pads 0x5ba, 0x5c8 and wkup 0x05a if the bootloader doesn't set them.
5. **RTC:** add a hub `get_time`. At boot set our clock from GENERAL 0x00; write it only when the time is set. Optionally add the alarm through 0x04 and INT2 bit 1.
6. **Screen status:** write USERSETTINGS (bank 11) 0x00 on every display change (0, 1 or 3), and again after a hub restart.
7. Still timeout 600 at init (already done), with the new bank.
8. ALS at bank 23 (rate 0x02, value 0x04), and heart rate if wanted.

**Only the watch can settle:**
- Which image is in flash (0x00D7 or 0x00F4).
- Whether reset has a pull-up.
- Whether a 3-byte status read clears all three registers.
- The hub's default screen status, and whether the tilt interrupt needs 0 or 2.
- The ALS lux scale and the accelerometer scale.
- Whether the F401 image has the accelerometer-watchdog crash or the TOTALSTEPS-read crash.
- What is in flash sectors 0-5.
- Clock-stretch lengths on this image.
- What gpio 28 actually drives.

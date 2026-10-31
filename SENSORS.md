# Sensors on sturgeon (APQ8026): the sensor hub MCU

Research notes for bringing up the sensors bare-metal. Written 2026-10-29.
No watch access was used; everything below comes from the vendor kernel,
the vendor Android system image and the AsteroidOS layers.

**On the watch (2026-10-29, branch `sensors` of asteroid-embedded)**

- Confirmed: UART1 115200 8N1 without flow control, the framing and CRC,
  the version query (`11.900.12.01.00`, matching `mcu.bin`), the handshake
  `00 01 00`, and wrist tilt activate `01 01 33 00 00`. First try, no bad
  frames.
- The MCU reset must happen **before** UART1 is opened. With the UART
  opened first, every other boot (the ones after a normal reboot) hit the
  watchdog about 2 s later, with the main loop starved; for some reason,
  the cause was not traced (an interrupt storm from the line glitch during
  the MCU reset is the guess). The vendor kernel resets at board init,
  long before the tty is opened.
- Not yet tried: a real tilt event, the gpio 108 / MPM pin 29 wake from
  cluster sleep (needs USB unplugged), the sleep current with UART1 on.

**Sources and notation**

- `K:` is the downstream kernel at `~/Downloads/AsteroidOS/minnow/sturgeon-kernel`
  (head `97abcf5b2468`, branch `android-msm-sturgeon-3.10-emr1`).
- `SYS:` is the vendor Android 6 `/system` tarball that AsteroidOS installs
  through `meta-sturgeon/recipes-android/android/android_sturgeon-mm.bb`
  (`system-sturgeon-m.tar.gz`, in the pc's `/media/Data/AsteroidOS/cache/downloads/`).
  Binaries in it are closed Huawei code: `SYS:bin/shd`, `SYS:bin/mcu.bin`,
  `SYS:lib/libsensorhub.so`, `SYS:vendor/lib/hw/sensors.sturgeon.so`.
- `MS:` is `~/Downloads/AsteroidOS/meta-smartwatch/meta-sturgeon`, `MA:` is
  `~/Downloads/AsteroidOS/meta-asteroid`, `SFW:` is `~/Downloads/AsteroidOS/sensorfw`.
- **[V]** verified in source or binary (file:line, or the binary and what was
  found in it). **[I]** inferred, with the reasoning. **[?]** open.

## 1. Summary

- **None of the sensors are wired to the APQ8026.** They all sit behind a
  sensor hub: an **STM32F411** running Huawei firmware on **Huawei LiteOS**,
  connected to the SoC over **BLSP1 UART1** (0xf991d000, gpio 0-3) at
  **115200 8N1** plus four handshake gpios, a reset gpio and two boot-mode gpios.
- The physical sensors hang off the MCU's own I2C. Linux has no driver for
  any of them, only a GPIO wake/sleep helper and a GPIO reset/boot helper.
- Algorithms (step counter, step detector, significant motion, **wrist tilt
  gesture**, **heart rate bpm with wear detection**, fusion: gravity, linear
  acceleration, rotation vectors) run **on the MCU**. The host only enables
  sensors and receives events.
- The host protocol is implemented in the closed userspace daemon `shd`
  (also run by AsteroidOS). It frames messages with **async HDLC: 0x7D/0x7E
  byte stuffing, CRC-16/X.25, closing 0x7E**, and is now decoded offline from
  both ends (`shd` and the MCU firmware): 4-byte header
  `channel, type, tag, cmd`, sensor tags, commands, event layouts and a
  bring-up byte script are in §5. Wrist tilt = tag 0x33, activate =
  `01 00 33 00`.
- The MCU runs from its own internal flash. `shd` reflashes it through the
  STM32 ROM UART bootloader only when the version differs from
  `SYS:bin/mcu.bin` (11.900.12.01.00). Bare-metal does not need to load
  firmware and must never trigger that path.
- **Tilt-to-wake fits cluster sleep well:** the MCU raises **gpio 65
  (rising edge)**, which is **MPM pin 29**, the pin right next to BT
  HOST_WAKE (gpio 64 = MPM 28) that the firmware already wakes on.

## 2. Hardware

### 2.1 Sensor parts

From the HAL's sensor table (`SYS:vendor/lib/hw/sensors.sturgeon.so`
strings) **[V]**. The HAL ships two tables, `sensorlist_STM` and
`sensorlist_BMI`, and picks one based on the IMU the MCU reports (the string
`LSM6DS3` is compared) **[V strings; selection logic I]**:

| Android sensor | Part (vendor) | Where computed |
|---|---|---|
| accelerometer, gyroscope | **LSM6DS3** (ST) or **BMI160** (Bosch), two board variants | MCU driver |
| pressure | **BM1383GLV** (ROHM) | MCU driver |
| heart_rate | **ADPD153GGRI** (Analog Devices) PPG front end | MCU algorithm |
| step_counter, step_detector, significant_motion | "Huawei SensorHub" | MCU algorithm |
| wrist_tilt_gesture | "huawei wrist tilt gesture" | MCU algorithm |
| gravity, linear_acceleration, rotation_vector, game_rotation_vector | Huawei | MCU fusion |
| com.huawei.watch.motionhealth | Huawei (steps, calories, distance history) | MCU algorithm |

There is **no magnetometer and no ambient light sensor** in either table
**[V]**. `SYS:etc/permissions/` declares barometer, gyroscope, heartrate,
stepcounter and stepdetector only **[V]**.

The MCU firmware confirms the same parts: driver strings for `lsm6ds3`,
`bmi160` (chip ID check against 0xD1), `ADPD142`/`ADPD153` (`ADPD153
CHIP_ID=%x`), `Barometer ID err`, `i2c1 read error ... sad = 0x%x`, plus
`algorithm_health_task`, `algorithm_motion_*`, `gesture_set_isr`,
`hrm_wear_detect_callback` **[V strings of `SYS:bin/mcu.bin`]**. The sensors
are on the MCU's I2C1 **[V string]**; the APQ never sees them.

### 2.2 The MCU

- **STM32F411**: the image contains the build path
  `D:\mcu_code\Mercury\STM32F411\Application\...` and LiteOS sources
  (`liteos\kernel\src\mem\los_memory.c`) **[V strings]**.
- `SYS:bin/mcu.bin` (197463 bytes) = 224-byte Huawei header + raw flash
  image. Header: magic `ff aa aa ff`, `0x000000e0` header length,
  `0x00030277` image length (197239 = file size - 224), a 16-bit value
  `0x38e6` (checksum? [?]), version string `11.900.12.01.00` at offset 0x20
  **[V hexdump]**. The image starts with a Cortex-M vector table: SP
  0x2001d390, reset handler 0x0802f629, i.e. linked for flash at 0x08000000
  **[V]**.
- Firmware updates (`shd` strings **[V]**): `mcu_get_current_version` is
  compared with the header's version (and `persist.mcu.version`); if they
  differ: `set_update_gpio, set mcu to update mode`, `send 7F cmd to
  handshake with mcu`, `extended_erase_cmd`, `write memory`, `mcu_end(set
  gpio to normal mode)`. This is the **STM32 ROM USART bootloader
  protocol** (0x7F autobaud, Extended Erase, Write Memory) over the same
  UART with even parity (§2.4). The image is never loaded at runtime.
- **Licensing:** `mcu.bin`, `shd`, `libsensorhub.so` and the HAL are closed
  Huawei binaries. We do not need to ship any of them: the MCU already holds
  its firmware. Only the protocol has to be reimplemented.

### 2.3 Pins and buses

| Signal | APQ pin | Direction / config (vendor) | Source |
|---|---|---|---|
| UART TX / RX / RTS / CTS | gpio 0 / 1 / 2 / 3, func 2, 8 mA, no pull | BLSP1 UART1 | `K:arch/arm/mach-msm/board-8226-gpiomux.c:144-186`; `K:arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-mcu.dtsi:15-32` |
| UART core | 0xf991d000, GIC SPI 107, `GCC_BLSP1_UART1_APPS_CLK` | msm_serial_hs_lite (`ttyHSL1`) | mcu.dtsi:16-18; mainline `dts/mainline/qcom-msm8226.dtsi:572-579` |
| MCU wakes AP (`mcu-wake-ap-gpio`) | **gpio 65**, input, pull-down, **IRQ rising edge**, wake IRQ | MCU -> AP | mcu.dtsi:38,41-43; `K:drivers/hwmcu/hwmcusleep.c:514-516`; gpiomux.c:513-536 |
| AP wakes MCU (`ext-wake-mcu-gpio`) | **gpio 62**, output, default low, pull-down | AP -> MCU | mcu.dtsi:39; gpiomux.c:547-563 |
| AP status (`mcu-ap-status-gpio`) | **gpio 108**, output, init high, pull-down | AP -> MCU: 1 = AP awake | mcu.dtsi:37; hwmcusleep.c:477-478, 524; gpiomux.c:209-232 |
| MCU status (`mcu-status-gpio`) | **gpio 114**, input, pull-down | MCU -> AP: 1 = MCU awake | mcu.dtsi:40; hwmcusleep.c:105-109 |
| MCU NRST | **gpio 87**, GPIO, 2 mA, pull-up | AP -> MCU, active low | `K:arch/arm/mach-msm/board-8226-gpiomcu.c:31`; gpiomux.c:188-206 |
| MCU BOOT0 / BOOT1 | **gpio 111** / **gpio 106**, GPIO, pull-down | AP -> MCU, only for flashing | gpiomcu.c:29-30; gpiomux.c:444-466 |

- **MPM:** gpio 65 is **MPM pin 29** (`K:arch/arm/boot/dts/qcom/msm8226-v2-pm.dtsi:318`,
  same in `msm8226-v1-pm.dtsi:304`), next to gpio 64 = MPM 28 (BT
  HOST_WAKE). gpio 62 = MPM 26, 106 = MPM 36, 108 = MPM 38, 111 = MPM 54;
  gpio 114 and 87 have no MPM pin (pm.dtsi:292-332) **[V]**.
- **Power:** the DT has no regulator for the MCU or its sensors, and the
  kernel never switches one **[V: no supply in mcu.dtsi; hwmcusleep.c has no
  regulator calls]**. The MCU is powered whenever the watch is **[I]**.
- Reset at boot: `board_mcu_gpio_init()` drives gpio 87 low, waits 20 ms,
  drives it high (`gpiomcu.c:239-243`). It does not set the BOOT pins, which
  stay at their pull-downs (normal boot from flash) **[V]**.

### 2.4 UART settings used by shd

From the disassembly of `SYS:bin/shd` **[V]**:

- Device `/dev/ttyHSL1` (normal and update paths, code at 0x2956, 0x624e,
  0x64de).
- Normal mode (0x28ec-0x291c, 0x6274-0x62a4): `cfmakeraw`, `c_cflag |=
  0x830` (CS8 | CLOCAL, **no CRTSCTS**), `cfset[io]speed(B115200)`
  (0x1002). So **115200 8N1, no hardware flow control**, although gpio 2/3
  are muxed to the UART.
- Update mode (0x6526-0x654e): `c_cflag` with `0x930` (CS8 | PARENB |
  CLOCAL) at B115200: **8E1**, as the STM32 bootloader requires.

## 3. Wake and sleep handshake (`K:drivers/hwmcu/hwmcusleep.c`)

`shd` drives this through `/proc/mcusleep/sleep` and `/proc/mcusleep/lpm`
**[V strings]**:

- **AP -> MCU, before sending** (`shd` writes `0` to `/proc/mcusleep/sleep`,
  `mcusleep_write_proc_sleep()` :275-314): if gpio 114 is low or the link
  is not marked ready, `mcusleep_sleep_deny()` (:172-201): gpio 108 high,
  gpio 62 high, wait 30 ms (`MIN_MCU_DELAY_TIME`, :75), then gpio 114 must
  read high; gpio 62 back low. If 114 stays low it fails with -EIO and
  `shd` logs `BoardSerial wakeup mcu failure`.
- **AP going to sleep** (`mcusleep_suspend()` :574-579 ->
  `mcusleep_sleep_allow()` :145-167): gpio 108 low, gpio 65 IRQ armed as
  wake source. `shd` also writes `1` to `/proc/mcusleep/sleep` when idle.
- **MCU -> AP** (`mcusleep_hostwake_isr()` :132-138, tasklet :115-123):
  on a rising edge of gpio 65, gpio 108 goes high and the link is marked
  ready; `shd` then reads the UART. The kernel never lowers 108 except on
  suspend.
- `/proc/mcusleep/lpm` only takes or drops a wakelock (:231-257).

[I] The MCU therefore holds outgoing data while gpio 108 is low, raises
gpio 65, and sends once 108 is high. Whether it waits indefinitely or with
a timeout is [?] and needs a capture (§7).

## 4. How AsteroidOS uses the sensors today

Chain: QtSensors -> sensorfw (`sensorfwd`) hybris adaptors -> libhybris ->
`sensors.sturgeon.so` -> `libsensorhub.so` -> local sockets `shdctl` /
`shddata` -> `shd` -> `/dev/ttyHSL1` -> MCU **[V]**:

- `shd` is started from Android init: `MS:recipes-android/android-init/android-init/init.rc:23-24`
  (`service sensorhd /system/bin/shd`, class core). The binary comes from the
  vendor `/system` tarball (`MS:recipes-android/android/android_sturgeon-mm.bb`).
  The ADSP boot on line 2 of that file is for audio, unrelated.
- `sensors.sturgeon.so` only `dlopen`s `/system/lib/libsensorhub.so` and
  forwards `sensorhub_sensor_active/deactive/setdelay/setbatch/flush/getinfo`
  **[V strings]**. `libsensorhub.so` is a thin socket client
  (`socket_local_client`) with extra calls `sensorhub_set_mcu_sys_time`,
  `sensorhub_set_mcu_health_parameter`, `sensorhub_set_mcu_raw_data`,
  `sensorhub_get_mcu_version`, `sensorhub_sensor_selftest/clibration`
  **[V strings]**. No QMI, no ADSP sensor (SSC) libraries exist in the
  image **[V: no `*sns*`/`*qmi*`/`libsensor1` files; NEEDED lists are only
  libc/libcutils/liblog/libm/libstdc++/libutils]**.
- `shd` at start: handshake (`Send Handshake to sensorhub`, retry, reboot
  MCU through gpio 87 on repeated timeouts), version check / update, set
  MCU log level, `InitParameter` (reads `/nvdata/accclibration` and
  `/nvdata/BARO` calibration from the nvdata partition, mmcblk0p10, and
  sends them), date/time (`McuDateTimeConfig`), then `Set parameter OK,
  start loop` **[V strings]**.

Consumers:

| Feature | Sensor type | Where |
|---|---|---|
| **Tilt-to-wake** | `SENSOR_TYPE_WRIST_TILT_GESTURE` (26) via sensorfw `wristgesturesensor` | adaptor `SFW:adaptors/hybriswristgestureadaptor/hybriswristgestureadaptor.cpp:30-35`; enabled in `SFW:config/sensord-hybris.conf:12` (installed as primaryuse.conf, `MA:recipes-nemomobile/sensorfw/sensorfw.inc:49`); mce wakes the display on the event (`MA:recipes-nemomobile/mce/mce/0002-tilt-to-wake-Wake-screen-when-wrist-gesture-arrives.patch`, `GESTURE_TILT_TO_WAKE`); toggle in asteroid-settings `DisplayPage.qml:33,154` |
| Heart rate app (`asteroid-hrm`, in `MS:conf/machine/sturgeon.conf:20`) | heart_rate via `hybrishrmadaptor` (200 ms delay patch `MS:recipes-nemomobile/sensorfw/sensorfw/0002-...`) | |
| Step count (watchfaces, community asteroid-health) | step_counter via `hybrisstepcounteradaptor` (200 ms patch `0001-...`) | |
| Pressure | `hybrispressureadaptor` configured; no consumer found in the local app repos | |
| Compass | not installed on sturgeon, and there is no magnetometer | |
| ALS (mce auto-brightness, `MS:recipes-nemomobile/mce/mce/20als-defaults.ini`) | the HAL has no light sensor, so this config has nothing to read [I] | |

`shd` logs the event types it forwards: `SENSOR_TYPE_HEART_RATE bpm:%f
status:%x`, `SENSOR_TYPE_STEP_COUNTER step:%u`, `SENSOR_TYPE_WRIST_TILT_GESTURE
event`, `SENSORS_MOTION_HEALTH_HANDLE ... step ... status` **[V strings]**.

## 5. The host protocol

Decoded offline from both ends: `shd` (sender), `libsensorhub.so`/the HAL
(socket side) and `mcu.bin` (receiver). Every finding below is from code;
no capture has been made yet. Tools: Ghidra 12.1 headless decompile of
all four binaries, unicorn to run the MCU's RAM initialiser.

**Address conventions in this section**

- `shd@0x1xxxx` is the Ghidra address, i.e. ELF vaddr + 0x10000 (the
  older notes used ELF vaddrs: `shd@0x11e8a` = old `0x1e8a`).
- `mcu@0x08xxxxxx` is the flash address. File offset in `SYS:bin/mcu.bin`
  = address - 0x08000000 + 0xe0 (224-byte header).
- `mcu RAM 0x200xxxxx` values come from running the IAR init table
  (`__iar_data_init3` at mcu@0x0802c87c, table 0x0802d0f0-0x0802d138:
  zero-init 0x19b20 bytes at 0x20001870, two LZ77-compressed copies to
  0x20000000/0x20000400) in unicorn. The MCU firmware is built with IAR
  (`__low_level_init` / `__iar_data_init3` / main = mcu@0x080167b8).

### 5.1 Framing [V both ends]

- Host encoder `shd@0x11e8a`, MCU encoder `mcu@0x08018eac`: escape every
  0x7D/0x7E as 0x7D, byte ^ 0x20 (`shd@0x11e44`, `mcu@0x08018e54`), append
  the CRC **little-endian**, escaped the same way, then a single **0x7E**.
  **No opening flag.**
- CRC: CRC-16/X.25 (init 0xFFFF, reflected poly 0x8408, final XOR 0xFFFF).
  The MCU's table at mcu@0x0802aea0 is the standard table (checked against
  a bitwise implementation). Receivers run the CRC over payload + FCS and
  require the residue **0xF0B8** (`shd@0x11ee8`, `mcu@0x08018f2a`).
- **MCU receive path [V]:** the modified HAL RX interrupt
  (`mcu@0x0801ba14`) stores bytes and **completes a reception at every
  0x7E byte**; the buffer goes to the comms task, which decodes it with a
  **fresh decoder state** (`mcu@0x080152c2` -> `mcu@0x08018fec`) and then
  re-arms reception (1024-byte buffer). Consequences:
  - one frame per 0x7E-terminated chunk; the decoder ignores everything
    after the first complete frame in a chunk, so never pad;
  - a stray leading 0x7E is a 1-byte "frame" with a bad CRC: logged
    (`Data Packet Error len %d pkt_len %d ret %d`) and dropped, harmless.
    A lone 0x7E is therefore a safe resync byte after line noise;
  - frames are small: `shd` builds at most 32 payload bytes
    (`shd@0x12974`, encoded buffer 0x40). The MCU accepts up to 1024.
- Line: 115200 8N1, no flow control (§2.4).

### 5.2 Message header [V both ends]

Payload byte 0 is the **channel**. `shd` logs the 4 header bytes as
`channel =%x, type =%x, serivce = %x, cmd = %x` (`shd@0x163ca`
area), which names them:

| Byte | Name | Values |
|---|---|---|
| 0 | channel | 0 = control, 1 = service (sensor/system messages), 4 = MCU log text, 5 = raw-data dump, 7 = core dump |
| 1 | type | 0 = request (AP -> MCU), 1 = response (MCU -> AP), 2 = event/report (MCU -> AP) |
| 2 | service | the **tag**: sensor or system service id (§5.3) |
| 3 | cmd | channel 1 only; channel 0 has a 3-byte header |

- Channel 0 = `[0, type, cmd]`, channel 1 = `[1, type, tag, cmd]`, then
  the body. Channels 4/5/7 have a 1-byte header, then the body
  (`shd@0x121ce` parser).
- MCU dispatch (`mcu@0x08015382`, `mplat_message_dispatch`): channel 0
  -> control table in mcu RAM 0x200016f0 (2 entries: cmd 0 -> handshake
  mcu@0x08015340, cmd 1 -> no-op); channel 1 -> registered tag table
  (`mcu@0x08015438`, `mplat_serve_process_pkt`; registration
  `mcu@0x080153b6`, max 20 tags). An unregistered tag gets the error
  response `[01 01 tag cmd ff]` (`mcu@0x08016264` with status -1).
- `shd` dispatch of received frames (`shd@0x15b38`): channel 1 type 2 ->
  sensor event handler `shd@0x14880`; channel 1 other types and channel 0
  -> queued as the reply for the pending request; channel 4 -> logged as
  `mcu: %s`; 5 -> raw data files; 7 -> core dump.
- **Request/response pairing [V]:** `SendSensorMsgAndWait`
  (`shd@0x12a9c`) sends one request and takes **whatever reply is queued
  next** (no matching), with a 2 s or 10 s timeout. Bare-metal should send
  one request at a time and match the reply on (tag, cmd).
- **Reply body [V]:** byte 0 of the body is a status: 0 = OK, 1 = failure,
  0xFF = unknown command/tag (`shd` logs `... failure ret:%d` when non-zero).
  Exceptions are listed per command below.

### 5.3 Tags (service byte)

Sensor tags, from the MCU sensor table at mcu@0x0802b768 (11 entries ×
24 bytes; byte 1 = tag, byte 2 = report cmd 0x10, byte 16 = wake-up flag),
cross-checked with the `shd` handle -> tag table (ELF file offset 0x8c84,
28 pairs `{HAL handle, tag}`, lookup `shd@0x125d4`) and the HAL's
`sensor_t` table (`sensors.sturgeon.so` .data 0x7000, 68-byte entries)
**[V]**:

| Tag | Sensor | HAL handle / Android type | MCU wake-up sensor | Event sample |
|---|---|---|---|---|
| 0x10 | accelerometer | 0 / 1 | no | 6 B: 3 × int16 |
| 0x11 | gyroscope | 5 / 4 | no | 6 B: 3 × int16 |
| 0x16 | pressure | 6 / 6 | no | 4 B: uint32 |
| 0x17 | Huawei private sensor [?] | 25 / 0x10001 (not in the HAL list) | no | 10 B: uint64 + uint16 |
| 0x20 | linear acceleration | 10 / 10 | no | 12 B: 3 × float |
| 0x21 | gravity | 9 / 9 | no | 12 B: 3 × float |
| 0x23 | rotation vector (also game rotation vector, handle 15) | 11 / 11 | no | 16 B: 4 × float |
| 0x30 | step counter | 19 / 19 | no | 4 B: uint32 |
| 0x32 | heart rate | 21 / 21 | no | uint32 bpm + uint8 status |
| **0x33** | **wrist tilt gesture** | 26 / 26 | **yes** | none used |
| 0x40 | motion health (steps/calories history) | 27 / 65538 | yes | 16-byte records |
| (0xff) | step detector, significant motion | 18, 17 | - | virtual: `shd` derives them from 0x30 |

System tags **[V]**:

| Tag | Use | Handler |
|---|---|---|
| 0x0c | date/time | mcu@0x0801ff1a |
| 0x0d | MCU log level (cmd 0), raw-data mode (cmd 1), a 0-100 value (cmd 2) [?] | mcu@0x080123a6 |
| 0x0e | sensor status bitmaps (14-byte reply) [I] | mcu@0x080165c2 |
| 0x0f | version (cmd 0), chip info (cmd 1) | mcu@0x08019028 |
| 0x40 | also health parameters (cmd 0x20) | |

### 5.4 Commands (channel 1, type 0)

Builders in `shd`: `shd@0x12180` makes `[01 00 tag cmd]`, `shd@0x1219a`
adds a uint32. Generic sensor command handler in the MCU:
`mcu@0x08016444` (cmd < 0x10), cmd >= 0x10 goes to `mcu@0x08013d64`.
All multi-byte fields are little-endian.

| Request | Bytes after the header | Reply | Source |
|---|---|---|---|
| **handshake** | channel 0: `00 00 00` | `00 01 00` | shd@0x131e0; mcu@0x08015340 [V] |
| **version** | `01 00 0f 00` | `01 01 0f 00` + 48-byte NUL-padded ASCII + status = 53 bytes | shd@0x161f4 / 0x130e4; mcu@0x08019028 [V] |
| chip info | `01 00 0f 01` | same layout, string from mcu@0x0801c26a [?content] | [V layout] |
| **activate** | `01 00 tag 00` | `01 01 tag 00 status` (sent by the sensor task when done, callback mcu@0x08016264) | shd@0x1395c; mcu@0x08016444 [V] |
| deactivate | `01 00 tag 01` | `01 01 tag 01 status` | shd@0x1385c [V] |
| set delay | `01 00 tag 02` + uint32 delay_ms | `01 01 tag 02 status` | shd@0x12d94 [V] |
| batch | `01 00 tag 03` + uint32 period + uint32 batch count + uint32 (byte 0 = flags) | `01 01 tag 03 status` | shd@0x12b90; mcu stores +4/+8/+0xc [V] |
| flush | `01 00 tag 04` | `01 01 tag 04` + int16 queued samples + uint8 status + pad, then the buffered data as events | shd@0x14e0a; mcu@0x080163be [V] |
| self test | `01 00 tag 11` | status | shd@0x12f64 [V] |
| calibrate | `01 00 tag 12` | 6 (tag 0x10) or 4 (0x11/0x16/0x17) bytes + status; `shd` saves accel calibration to `/nvdata/accclibration` | shd@0x12e60, 0x1225c [V] |
| set parameter (calibration) | `01 00 tag 13` + data (tag 0x10: 6 B, 0x11/0x16/0x17: 4 B) | status | shd@0x13028 [V] |
| get info | `01 00 tag 22` | `01 01 tag 22` + 48-byte string + status | shd@0x12c80; mcu@0x08016364 [V] |
| **set time** | `01 00 0c 01` + uint64 **UTC milliseconds since the epoch** (`shd` sends `tv_sec * 1000`) | `01 01 0c 01 status` | shd@0x1342c; mcu@0x0801ff1a [V] |
| get time | `01 00 0c 00` | 24-byte reply [?layout] | mcu@0x0801ff1a [V] |
| MCU log level | `01 00 0d 00 01 lvl` (lvl 0-5, both bytes must be < 6) | status | shd@0x13240; mcu@0x080123a6 [V] |
| raw-data mode | `01 00 0d 01 type 00` (1 = alg acc, 2 = hrm ppg+acc, 3 = both) | status | shd@0x13508 [V]; debug only |
| health parameters | `01 00 40 20` + u8, u8, u16, u16 (6 bytes) | status | shd@0x13310 [V fields, meaning ?] |

### 5.5 Events (channel 1, type 2) [V]

Sent by the MCU as `[01 02 tag 10]` + one or more samples
(`mcu@0x080160f0` FIFO report, `mcu@0x08016216` single report). Decoded by
`shd@0x14880` / `shd@0x14544`; sample count = body length / sample size.

- **0x33 wrist tilt:** any `01 02 33 10 ...` frame is one tilt event. `shd`
  ignores the body (it reports data[0] = 0). The MCU detects the gesture in
  software (`gesture_type 0x%x`, mcu@0x080232c8; codes 1/7 and
  0x101/0x103/0x107/0x108 call the tilt callback).
- **0x30 step counter:** uint32 = MCU step count. `shd` adds its own offset
  saved across MCU reboots. The count is not reset by the host.
- **0x32 heart rate:** uint32 bpm at +0 (converted to float), uint8 status
  at +4 (Android accuracy/wear status).
- **0x10 accel:** int16 a, b, c -> Android x = b·k, y = -a·k, z = c·k,
  k = 0x3b9cd0e7 = 9.8/2048 m/s² per LSB (±16 g). **0x11 gyro:** x = a·k,
  y = -b·k, z = -c·k, k = 0x3aa00db1 = 0.0012211 rad/s per LSB (2000 dps).
  **0x16 pressure:** uint32 / 2048 = hPa (k = 0x3a000000). Constants at
  shd ELF offsets 0x484c-0x4854.
- **0x20/0x21:** 3 floats. **0x23:** x, y, -z, w floats (z negated).
- **0x40 motion health:** 16-byte records: uint32 date at +0, uint16 step
  at +4, uint8 status at +6 (`SENSORS_MOTION_HEALTH_HANDLE dataindex:%d
  date:%u step:%d status:%d`); `shd` copies all 16 bytes into the event.
- **Delivery while the AP sleeps [V, mcu@0x08015fe0]:** wake-up sensors
  (0x33, 0x40) are always sent. The others are sent only while the MCU
  believes the AP is awake (gpio 108 high, see §5.6); without batching
  configured they are **dropped** while it is low, with batching they stay
  in the MCU FIFO until it fills or a flush. Read the step counter after
  waking (activate/flush) rather than expecting events during sleep.

### 5.6 GPIO handshake, MCU side

MCU GPIO table at mcu@0x0802b4cc (24-byte entries: index, port, pin mask,
HAL mode, pull) and EXTI callbacks in mcu RAM 0x200014e4. Mapping to the
APQ pins is [I] from how each is used, except where marked:

| MCU pin (table index) | Config | APQ gpio | Use |
|---|---|---|---|
| PA1 (5) | output | 65 (MCU wakes AP) | pulsed by the send path [V code, I mapping] |
| PB0 (7) | input, pull-down | 108 (AP status) | read before every send [V code, I mapping] |
| PA0 (4) | EXTI rising | 62 (AP wakes MCU) | handler mcu@0x080156e8 re-reads PB0 [I] |
| PB1 (8) | output, set high at init (mcu@0x0801570e) | 114 (MCU status) | [I] |

- **Send path [V, mcu@0x080151c4, duplicate at mcu@0x0801a470]:** if PB0
  is high, send at once. If low: PA1 high, then up to 3 × 50 ms polls of
  PB0; as soon as it is high, PA1 low and send. If PB0 stays low for
  ~150 ms: PA1 low and the **frame is dropped** (`commu_task Send Data ERROR
  ret =-4`). The vendor kernel raises 108 straight from the gpio 65 IRQ
  tasklet, well inside that window.
- **Before the handshake** (flag mcu RAM 0x2001b38a, set by the handshake
  handler) the MCU treats the AP as awake: `mcu@0x0801578c` returns 1
  without reading PB0. So the version query and handshake work with no
  GPIO activity at all, and so do events until the first handshake.
- **AP -> MCU** (vendor): `shd`'s `BoardSerial` write (ELF 0x23f8) writes
  `0` to `/proc/mcusleep/sleep` before **every** UART write, i.e.
  `mcusleep_sleep_deny()` (§3): 108 high; if 114 is low, 62 high, 30 ms,
  check 114, 62 low. A write failure is only logged; the UART write
  still happens.
- MCU log text (channel 4) is sent only if the log level was set with tag
  0x0d and the AP is awake (`mcu@0x08012512`). It is off after reset (the
  flag is in zero-init RAM).
- How the MCU itself sleeps (STOP mode etc.) was not found [?]; keep the
  vendor contract (62 pulse, wait for 114) before sending.

### 5.7 Vendor startup order [V, shd@0x11528]

1. Open `/dev/ttyHSL1` 115200 8N1 raw.
2. **Version query** `[01 00 0f 00]` on a separate fd, up to 5 tries; after
   3 failures it resets the MCU (BOOT0 = BOOT1 = 0, reset 0, 12 ms,
   reset 1; `shd@0x1619c`). Compared with the version in the `mcu.bin`
   header (§5.9).
3. **Handshake** `[00 00 00]`, 2 s timeout, retried every 2 s.
4. Optional log level (`persist.huawei.shd.mculog`).
5. Set parameter (cmd 0x13) for tags 0x10 (6 B), 0x16, 0x17, 0x11 (4 B
   each), values from `/nvdata` calibration.
6. Main loop. Per sensor the HAL sends batch/set delay, then activate.
   When motion health (0x40) is enabled after an MCU reboot, `shd` also
   sends the time (tag 0x0c) and the health parameters
   (`shd@0x13d7c`).

### 5.8 Bring-up script (bare-metal)

Frames below are exact wire bytes, CRC computed with the MCU's own table
(script: `frame.py` in the session scratchpad; the CRC is
CRC-16/X.25, LE).

```
TX version     01 00 0f 00 ad 63 7e
RX expect      01 01 0f 00 "11.900.12.01.00" 00×33 00(status) 10 6a 7e   (53-byte payload; CRC shown is for exactly that string)
TX handshake   00 00 00 cc c6 7e
RX expect      00 01 00 14 df 7e
TX tilt on     01 00 33 00 af 7c 7e
RX expect      01 01 33 00 00 42 b1 7e         (status 0 = OK)
RX tilt event  01 02 33 10 <body?> <crc> 7e    (match the first 4 bytes, ignore the body)
TX tilt off    01 00 33 01 26 6d 7e
TX step on     01 00 30 00 c7 56 7e
TX HR on/off   01 00 32 00 77 65 7e / 01 00 32 01 fe 74 7e
TX time        01 00 0c 01 <uint64 LE UTC ms> <crc> 7e
               e.g. 2026-10-29T00:00:00Z: 01 00 0c 01 00 d4 f4 84 a1 01 00 00 77 79 7e
```

Procedure:

1. UART1 115200 8N1, no flow control. gpio 108 high (AP awake), 62 low,
   87 high, **106 and 111 low** (§5.9).
2. Optionally send a lone `7e` to resync the MCU's receiver.
3. Send version and wait up to 1 s for a CRC-valid frame with header
   `01 01 0f 00`. Proves framing, CRC and RX/TX. If nothing comes back,
   reset the MCU (87 low 20 ms, high, BOOT pins low) and retry after
   ~1 s [I: boot time not known].
4. Send the handshake until `00 01 00` arrives (vendor: 2 s timeout).
   From now on the MCU obeys gpio 108 (§5.6).
5. Send the time (tag 0x0c), then tilt on. Expect `01 01 33 00 00`.
6. Receive loop: unescape, check residue 0xF0B8, dispatch on
   (channel, type, tag). Ignore channel 4/5/7 frames.
7. Sleep: gpio 108 low, arm gpio 65 rising (MPM pin 29). On wake: 108
   high **within ~100 ms** (MCU gives up after ~150 ms and drops the
   frame), UART RX running before that. Then expect `01 02 33 10 ...`.
8. Before each TX while the MCU may sleep: as the vendor kernel does
   (62 high, 30 ms, require 114 high, 62 low).

### 5.9 The bootloader path: what to avoid [V]

- **Entry condition:** `shd`'s update (`shd@0x1649c`) writes
  `/proc/mcu/gpio_mcu_boot1` = `0`, `gpio_mcu_boot0` = `1`, then
  `gpio_mcu_reset` = `0`, `1` (the proc files set the gpio level directly,
  `K:arch/arm/mach-msm/board-8226-gpiomcu.c:85-101`). So: **gpio 111
  (BOOT0) high + a reset pulse on gpio 87** boots the STM32 ROM
  bootloader. It then reopens the UART at **8E1** and sends **0x7F**
  (autobaud, ACK 0x79), then Extended Erase and Write Memory.
- **What triggers it in `shd`:** version reply missing after 5 tries,
  or different from the `mcu.bin` header (length or string,
  `shd@0x16878`; also needs the `.900` field to match); more than 10
  handshake timeouts at start; more than 10 UART reopen or handshake
  failures in the MCU reboot thread (`shd@0x13d7c`).
- **The application cannot enter the bootloader or erase itself:** no
  reference to system memory (0x1FFF0000), and no FLASH unlock key
  (0x45670123) anywhere in `mcu.bin` **[V: literal search]**. A 0x7F byte
  at 8N1 while the application runs is just a bad HDLC frame.
- **Rule for our firmware:** keep gpio 111 and 106 low at all times and
  for every reset pulse; never switch the UART to even parity; never
  send 0x7F/0x44. A version mismatch must only be logged.

### 5.10 Open points

- Wrist tilt event body (size/content). Not needed (`shd` ignores it).
- Meaning of tag 0x17, the 0x0e status reply, health parameter fields,
  the get-time reply layout.
- MCU boot time after reset, its sleep mode, and whether the 62/114
  handshake is needed when 114 is already high (the kernel skips it).
- No public source counterpart was found. Huawei's GPL "inputhub" kernels
  use a different header (TAG_/CMD_ with transaction ids); none of the
  names here (`mplat_*`, `SendSensorMsgAndWait`) turned up in a search.
  Everything above comes from these binaries.
- Confirm on the watch: the version and handshake exchange (step 3 of
  §7) validates framing, the header and the CRC at once.

## 6. Tilt-to-wake bare-metal

- **Detection is on the MCU** (`algorithm_motion_*`, `gesture_set_isr`,
  `gesture_type 0x%x` in `mcu.bin`) **[V strings]**. The gesture codes are
  handled in MCU software (mcu@0x080232c8, §5.5); whether the IMU's own
  tilt engine feeds it is [?] and does not matter to the host.
- **Wake path:** enable the wrist-tilt sensor once over the UART (§5), then
  before cluster sleep: drive gpio 108 low (as `mcusleep_sleep_allow()`),
  arm MPM pin 29 rising (`spm_wake_pin(29, true)` in `src/soc/spm.c`; TLMM
  gpio 65 as input, pull-down, rising-edge IRQ). On wake: gpio 108 high,
  read and parse the frame(s), wake the display on a wrist-tilt event.
  The SoC stays in cluster sleep between tilts; the MCU and IMU carry the
  cost.
- **Current cost [?]:** not measured, and the MCU is powered regardless
  (§2.3), so the extra cost is only the enabled gesture algorithm and the
  IMU rate it needs. Measure with the BMS current, gesture on vs off, after
  bring-up.
- **Answered from the MCU code (§5.6) [V]:** after raising gpio 65 the MCU
  polls gpio 108 3 × 50 ms and then **drops** the frame, so 108 must be high
  within ~150 ms of the 65 edge. Only wake-up sensors (wrist tilt 0x33,
  motion health 0x40) are sent while 108 is low; the others are dropped or
  stay in the batch FIFO. Each frame goes out as soon as 108 is high, so the
  UART RX must be running **before** 108 is raised.

## 7. Proposed bring-up order

| Step | Work | Effort | Needs the watch |
|---|---|---|---|
| 0 | Optional: confirm §5 by capturing the vendor exchange on AsteroidOS (`strace -f -tt -xx -s 1024 -e trace=read,write,openat /system/bin/shd` after stopping the init instance, then toggle tilt/HR) | 0.5 day | yes, once (Darrel or an agent with adb) |
| 1 | Make `uart_dm.c` multi-instance (it keeps one static `base/port/irq/ring`; BT uses UART4) and add a no-flow-control option. UART1 = 0xf991d000, SPI 107, gpio 0-3 func 2, 115200 | 0.5-1 day | no (build only) |
| 2 | MCU GPIOs: 62 out low, 108 out high, 65/114 in pull-down, 87 reset pulse (low 20 ms, high) as `gpiomcu.c:239-243`. Log 114 and 65 levels and any RX after reset | 0.5 day | yes; autonomous log read is enough |
| 3 | HDLC framing + CRC-16/X.25; version query then handshake (§5.8), expected `11.900.12.01.00` | 1 day | yes, autonomous |
| 4 | Wrist tilt: activate, event parse, sleep handshake, MPM pin 29 wake, display on | 1-2 days | yes; tilting needs Darrel |
| 5 | Step counter (and date/time set, which the step day-reset probably relies on [I]) | 1 day | yes |
| 6 | Heart rate (bpm and wear status come computed from the MCU) | 1 day | yes, worn |
| 7 | Pressure, accel/gyro raw, calibration from `/nvdata` (needs a read-only ext4 reader on mmcblk0p10 [?]) | optional | |

**Heart rate algorithm:** runs on the MCU; the host receives bpm and a
status (`SENSOR_TYPE_HEART_RATE bpm:%f status:%x`). There is a debug raw
mode (`McuRawDataConfig`, `g_p_hrm_ppg_raw_data`, `persist.huawei.shd.rawdatatype`)
that streams raw PPG/accel samples **[V strings]**, but we do not need an
open algorithm: the vendor method is to use the MCU's bpm.

**Risks**

- **Bricking the hub:** only possible through the bootloader path (BOOT0
  gpio 111 high + reset + 0x7F + Extended Erase). Never drive gpio 111/106
  high and never send 0x7F at 8E1. Recovery would need `mcu.bin` and our own
  STM32 bootloader client.
- **Firmware version on the watch:** the protocol is tied to the MCU
  firmware. AsteroidOS's `shd` reflashes the MCU to 11.900.12.01.00 when
  they differ, so a watch that ran AsteroidOS should run that version [I];
  check the version reply (step 3).
- The protocol is reverse engineered from closed binaries; capture-based
  understanding may miss rarely used commands (calibration, self test).
  These are not needed for steps 1-6.
- Missing calibration (`/nvdata/accclibration`, `/nvdata/BARO`) may degrade
  accuracy if the MCU does not keep its own copy [?].
- UART1 shares the BLSP1 AHB clock and the GPLL0 vote with UART4 (BT); the
  multi-instance refactor must not break the BT path.

**Verifiable without Darrel:** all of the offline RE; on the watch (fastboot
boot + log read, no interaction): gpio 114/65 levels after reset, any bytes
after reset, a CRC-valid handshake reply and the version string. Tilt, HR
and steps need someone to wear or move the watch.

## 8. Steps and heart rate (2026-10-30, branch `health`, not on main)

Worktree `../asteroid-embedded-health`, uncommitted. Verified on the watch
without wearing it:

- After the tilt batch: set time `01 00 0c 01` + u64 UTC ms -> `(0)`,
  activate step counter `01 00 30 00` -> `(0)`. Flush `01 00 30 04` while
  sitting still returns no events.
- Heart rate activate `01 00 32 00` gets a reply; no 0x32 events in 8 s
  off the wrist (expected [I]). Deactivate `01 00 32 01`.
- UI: steps and a heart icon on the battery row; tapping the heart
  measures for 60 s (keeps the screen on), then switches the sensor off.
  Steps today = running total (kv `steps`: total, day, day start) + MCU
  count since its reset at boot; saved at sleep and day change.

Still to check with the watch worn/walked: the step event sample (assumed
u32, last sample of a batch used), the heart rate sample layout (assumed
u32 bpm + u8 status at +4), whether steps taken while asleep arrive on the
wake flush, and the status values.

## 9. Steps and heart rate on main (2026-10-31, a5eac3a, 8f8b3dd, 1eb49a2)

Ported from the `health` worktree onto main after the arch refactor
(steps.c common, hub stubs in src/board/stubs.c). Battery-row UI dropped;
heart rate is a Heart Rate app after asteroid-hrm (screenshots taken on
AsteroidOS on this watch: it reads ~97 bpm even on the charger).

- 0x32 events confirmed: `01 02 32 10` + uint32 bpm + uint8 status (3),
  first one ~25 s after activation, then every 8-40 s. Readings on the
  desk/charger too (no wear detection gate seen).
- Activated again after a deactivate, the MCU sent nothing for > 1 min;
  with set delay `01 00 32 02` + 200 ms before activate (vendor order,
  sensorfw 200 ms) it reads every time (8f8b3dd).
- The app keeps the screen on until the second reading, like
  asteroid-hrm's preventBlanking.
- Steps: counter on + time set at boot verified; step events still
  unverified (needs walking).
- Side effect found: console commands run from the main loop since
  ba39d0a, so `log 3000` blocks the loop (and the screen) for ~4 s.
  Output should be produced in chunks.

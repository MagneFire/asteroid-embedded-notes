# asteroid-embedded: development notes

Design, hardware facts, milestones and lessons for the bare-metal AsteroidOS
runtime in `../asteroid-embedded`. The code repo stays clean; everything
that explains *why* and *where it came from* lives here.

## Goal

AsteroidOS without a Linux kernel or root filesystem: one flat image booted
over `fastboot boot`, a build/test loop measured in seconds, a watch that
boots in well under a second. First target: Huawei Watch (sturgeon,
APQ8026, quad Cortex-A7, 512 MB). Second: ASUS ZenWatch 2 (sparrow, same
SoC). Features: touch, display, GPU, deep sleep, USB (ADB-style transport),
Bluetooth speaking the existing AsteroidOS BLE profile so the Sync apps work
unchanged (notifications included), battery charging and fuel gauge, RTC
and a default watchface (extensible), animated FlatMesh, the current apps
(rewrites), always-on display later.

Decisions (2026-10-25): raw superloop, no lk kernel; register-level driver
files may be copied from lk under their BSD headers; the UI layer is decided
later but must render on the GPU; BTstack preferred over NimBLE (runs in a
superloop); commits and code never mention the reference projects or the
lab USB appliance.

## Reference trees (never vendored)

- lk2nd `msm8916-mainline/lk2nd` @ fd380ac6 (2026-09-28): `app/aboot/aboot.c`
  (fastboot decision ~5590–5616, `boot_linux` 1202), `platform/msm_shared/
  {hsusb.c,i2c_qup.c,spmi.c,mipi_dsi.c,uart_dm.c,smd.c,rpm-smd.c,reboot.c}`,
  `platform/msm8226/include/platform/iomap.h`, `lk2nd/display/cont-splash/
  {refresh.c,pipe.c,target_display.c}`, `lk2nd/ramoops/ramoops.c`,
  `lk2nd/device/dts/msm8226/apq8026-{huawei-sturgeon,asus-sparrow}.dts`,
  `dev/pmic/pm8x41/`, `dev/fbcon/font5x12.h` (copied into the code repo).
- `FlorentRevest/bare-metal-adreno` @ 1d80739 (2025-06-26): lk2nd minimized
  for sparrow, booted with `fastboot boot`; `app/a3xx.c` = A305B GDSC,
  clocks, PM4/PFP firmware load, ringbuffer, IRQ, hand-written IR3 compute
  shader. GPU seed for M4.
- usbproxy-bm (`~/Downloads/usbproxy-bm`): startup, GIC, timer, log ring,
  fault record, TinyUSB port shape, ADB framing (`src/bridge/bridge.c`).
- Mainline Linux: `arch/arm/boot/dts/qcom/qcom-apq8026-huawei-sturgeon.dts`,
  `qcom-msm8226.dtsi` (copies in `dts/mainline/`); `drivers/soc/qcom/spm.c`
  for SAW2 sequences; `drivers/watchdog/qcom-wdt.c` (kpss layout).
- Android 3.10 sturgeon kernel (`android-msm-sturgeon-3.10-marshmallow-dr1-
  wear-release`): `arch/arm/boot/dts/apq8026-sturgeon/*.dtsi` (copies in
  `dts/android-sturgeon/`), defconfig in `meta-smartwatch/meta-sturgeon`.
- AsteroidOS BLE profile: `AsteroidOSSync/app/src/main/java/org/asteroidos/
  sync/utils/AsteroidUUIDS.java`; payload formats in `asteroid-btsyncd`.

## Boot path

- Stock bootloader STURGEONV3.4 (Huawei lk/aboot) and lk2nd both accept
  `fastboot boot <boot.img>`. The "kernel" is a flat binary copied to the
  header's kernel address (0x8000; lk2nd forces 0x8000 regardless) and
  entered with r0=0, r1=machtype, r2=tags, MMU and caches off, IRQs masked,
  SVC mode, non-secure world (TrustZone owns the secure side: CNTFRQ is
  read-only, GIC group assignment is fixed, ACTLR.SMP may be ignored).
- The boot image needs a QCDT table (`tools/qcdt.py`, v2 entries) with an
  entry matching the SoC: sturgeon msm-id `<199 0x20000>` (APQ8026 v2),
  board-id `<8 4>` (MTP subtype 4); sparrow board-id `<8 3005>`. The DTB
  must contain `/memory` and `/chosen` nodes or aboot's DT update fails.
  The AsteroidOS boot image uses an appended DTB (dt_size 0) instead.
- lk2nd built with `LK2ND_FORCE_FASTBOOT=1` stays in fastboot on every
  boot (no key presses). `SCRATCH_SIZE=0x0F000000` is also needed: the
  msm8226 target assumes 1 GB and would put its ramoops region above RAM.
  Build: `make TOOLCHAIN_PREFIX=arm-none-eabi- LK2ND_FORCE_FASTBOOT=1
  SCRATCH_SIZE=0x0F000000 lk2nd-msm8226` (GNU make 3.81 on macOS is fine).
  Flash to `boot` (mmcblk0p21, 20 MB); the AsteroidOS boot image is backed
  up in `backup/sturgeon/boot-asteroidos.img`.
- This sturgeon boots the `recovery` partition, not `boot` (a known quirk of
  the unit): lk2nd had to be flashed to both (backups of both in
  `backup/sturgeon/`).
- Return to fastboot: a warm reset with no restart reason. The stock aboot
  then loads lk2nd from `boot` as usual. Do not write FASTBOOT_MODE
  (0x77665500) to IMEM 0xFE80565C: the stock aboot would enter *its own*
  fastboot and never load lk2nd.
- Warm vs hard reset is decided by PM8226 PON `PS_HOLD_RESET_CTL` (0x85A,
  type 1 = warm, 0x85B bit 7 enables); the firmware sets warm at boot so
  DRAM survives its own PS_HOLD drop (MPM2 0xFC4AB000) and a watchdog bite.
- A watchdog bite and a PS_HOLD drop only reset the chip after the secure
  world's "watchdog debug" is disabled: SCM boot service (1), command 9
  (`SCM_WDOG_DEBUG_BOOT_PART`), arg 1, legacy register convention
  (`src/soc/scm.c`). The Android kernel makes the same call before every
  restart; without it the first firmware sat forever on a bite.
- The generic timer PPIs are wired as 18 (secure physical), 19 (non-secure
  physical), 20 (virtual) on this SoC, not the architectural 29/30/27. lk
  uses 19 too (`INT_QTMR_NON_SECURE_PHY_TIMER_EXP`).
- IMEM download cookies (0xFE805000 +0 two words, +0xFE0 three words) must
  be cleared: the Android kernel sets them at boot (`CONFIG_MSM_DLOAD_MODE`)
  so an unexpected reset lands in Qualcomm download mode (9008).

## Crash dumps

lk2nd's ramoops support reads a pstore `persistent_ram` layout from
`SCRATCH_ADDR + SCRATCH_SIZE - 512K` (= 0x1EF80000 with the override):
32 dump records of 8 KiB, then a 256 KiB console ring; each zone is
`{sig "DBGC", start, size}` + data. `fastboot oem ramoops raw` stages the
whole region, `get_staged` fetches it (`tools/run.py` parses it). The
firmware writes its log into the console ring and one fault record (kernel
`====<s>.<us>-D` header + text) into record 0, which the next boot prints
and clears. The region is mapped non-cacheable.

## Memory map (sturgeon)

- DRAM: 0x00000000–0x02efffff and 0x04700000–0x1fffffff (512 MB). The hole
  holds the bootloader's framebuffer (0x03200000) and other reserved memory.
- Firmware image at 0x8000 (link in `ld/asteroid.ld`), MMU L1 table and
  stacks right after it. lk2nd itself lives at 0x07F00000 (1 MB).
- Framebuffer as the bootloader leaves it (read back from pipe RGB_0 at
  MDSS+0x1E00): base 0x04200000, 400x400, RGB888 (3 bytes/pixel), stride
  400 px, format 0x2243f, DSI command mode, autorefresh off (so every frame
  needs a CTL_START kick); MDP rev 0x10010001. The scan-out is rotated 180°
  relative to the watch (lk2nd's menu and the firmware console appear flipped
  and mirrored); set the pipe flip bits (SSPP_SRC_OP_MODE +0x38, bits 13/14)
  or draw rotated. The Android kernel instead used 32 bpp, stride 416 px, panel
  `auo rm69080 hvga` on this unit (EDO RM67160 is the other variant).
- Peripherals mapped as device memory: 0xF9000000 (GIC 0xf9000000/+0x2000,
  QTMR frames 0xf9020000, APCS watchdog 0xf9017000, USB 0xf9a55000),
  0xFC400000 (GCC 0xfc400000, PS_HOLD 0xfc4ab000, SPMI arbiter 0xfc4c0000
  with v1 channel registers at +0xF800), 0xFD500000 (TLMM 0xfd510000),
  0xFD800000 (MMSS CC 0xfd8c0000, MDSS 0xfd900000, DSI 0xfd922800, GPU
  0xfdb00000), 0xFE800000 (IMEM 0xfe805000).

## Hardware facts (sturgeon)

- Display: DSI command mode with TE, 400x400 AMOLED, `qcom,cont-splash-
  enabled`. MDP5 rev 1.1 (8x26): CTL0 at MDSS+0x600 (TOP +0x14 bit 17 =
  cmd mode, FLUSH +0x18, START +0x1C), pipes VIG0 +0x1200, RGB0 +0x1E00,
  DMA0 +0x2A00, PP0 +0x21B00 (SYNC_CONFIG_VSYNC +0x04, AUTOREFRESH +0x30
  bit 31). MDP GDSC at MMSS CC +0x2304 bit 31.
- Touch: Synaptics RMI4/DSX, `blsp1_i2c5` at 0xf9927000, address 0x20.
- Bluetooth: Broadcom BCM43430A0 on the high-speed UART (gpio 12 rx, 13 tx,
  14 rfr, 15 cts; mainline calls it blsp1_uart4), power gpio 67, host-wake
  64, dev-wake 63; patchram `4343A0.hcd` (copy in `hw/sturgeon/firmware/`).
  HCI H4. WiFi is BCM43430 over SDIO (out of scope).
- GPU: Adreno A305B (`qcom,adreno-305.18`), 0xfdb00000, OXILI GDSC and
  clocks in MMSS CC; firmware `a330_pm4.fw`/`a330_pfp.fw` (copies in
  `hw/sturgeon/firmware/`).
- PMIC PM8226 on SPMI sid 0: REVID 0x100, PON 0x800 (reasons 0x808–0x80D,
  PS_HOLD reset 0x85A/0x85B), RTC, SMBB charger, BMS. Battery 300 mAh
  HB442528EBC (profiles in `dts/android-sturgeon/`). Haptics DRV2605 on
  `blsp1_i2c2` at 0x5a. An MCU on the low-speed UART (gpio 0–3) with
  wake/status gpios 62, 65, 108, 114 (sensor hub; role to be found).
- Deep sleep: SAW2 v2.1 per CPU (0xf9089000 + n*0x10000) and L2
  (0xf9012000); RPM over SMD; wake sources touch IRQ, PON key, BT
  host-wake, RTC alarm, VBUS.
- USB: ChipIdea `qcom,ci-hdrc` at 0xf9a55000, HS PHY; IRQ SPI 134.

## Display (M1 findings)

- The bootloader leaves the pipe in RGB888 with no flips, the ping-pong tear
  check off (all PP registers 0) and gpio 24 (TE) as a plain input (cfg 0x1).
  Kicks then run as fast as the DSI link drains a frame: ~12.3 ms, 81 Hz.
- Tear check as mainline mdp5_cmd_encoder does it: SYNC_CONFIG_VSYNC =
  COUNTER_EN | IN_EN | 19.2e6/(434*60) (434 = 400 + 16 + 16 + 2 porch
  lines), SYNC_CONFIG_HEIGHT = 434 (mainline uses 2*vtotal as a 30 Hz
  fallback when TE is not wired; with real TE one frame height is right),
  VSYNC_INIT_VAL = START_POS = 400, RD_PTR_IRQ = 401, SYNC_THRESH = 4|4<<16,
  TEAR_CHECK_EN = 1. TE pin: gpio 24 function 1, input, pull-down; it
  pulses at 60 Hz (12 edges per 100 ms measured). Result: 60 flips/s, 2.4 ms
  render + 14.5 ms PP_DONE wait per frame.
- PP registers (base MDSS+0x21B00 on this MDP rev): TEAR_CHECK_EN 0x00,
  SYNC_CONFIG_VSYNC 0x04, SYNC_CONFIG_HEIGHT 0x08, SYNC_WRCOUNT 0x0C,
  VSYNC_INIT_VAL 0x10, INT_COUNT_VAL 0x14, SYNC_THRESH 0x18, START_POS 0x1C,
  RD_PTR_IRQ 0x20, WR_PTR_IRQ 0x24, AUTOREFRESH 0x30. MDP INTR_STATUS at
  MDSS+0x114 (PP0_DONE bit 8, PP0_RD_PTR bit 12), CLEAR +0x118, EN +0x110.
- Pipe switch to XRGB8888: SRC_FORMAT 0x0002243f→(0x3<<9|0x3<<6|0x3<<4|0x3<<2|
  0x3|1<<17|3<<12), UNPACK 0x03020001, YSTRIDE in bytes, OP_MODE FLIP_UD
  bit 14 (FLIP_LR bit 13), CTL_FLUSH bit 3 for RGB0, CTL_START.
- DSI command DMA (DSI0 0xfd922800): DMA_CMD_OFFSET +0x48, DMA_CMD_LENGTH
  +0x4C, INT_CTRL +0x110 (write 0x03030303 then poll bit 0), SW trigger
  +0x90. Packet bytes: data0, data1, type (0x05/0x15/0x39), 0x80 last.
  Panel (Raydium RM69080): brightness DCS 0x51, off 0x28, sleep 0x10, sleep
  out 0x11 (+120 ms), on 0x29; idle mode 0x39/0x38 (page select FE 00 first)
  for AOD later; deep standby 4F 01 in the Android off sequence.
- Software FlatMesh: 172 triangles, flat colours, scanline fill with the
  FPU, 2.4 ms per 400x400 frame on one A7 core.

## Touch, PMIC and RPM (M2 findings)

- **Regulators are RPM resources.** SPMI writes to LDO/LVS enable registers
  on slave 1 are refused (reads work); the touch rails (LDO19 analog, LVS1 =
  I2C pull-ups) came up only through RPM requests. With LVS1 off, SDA sits
  low and a bit-banged read returns all zeros with fake ACKs.
- **SMEM is at 0x03000000** (mainline is right; the Android `smem@fa00000`
  node is a different mapping and reads as zeros). Header: alloc table at
  +0xD0, 16 bytes per entry {allocated, offset, size, base_ext}. Item 13 =
  SMD channel table (32-byte entries: name[20], cid, ctype, refs); the RPM
  edge is `ctype & 0xff == 15`, channel name `rpm_requests`, cid 4 here.
  Items 14+cid (88 bytes: two 11-word stream descriptors, ours then the
  RPM's) and 338+cid (FIFO pair, 1024 B each way) have `base_ext =
  0xfc428000` = the RPM message RAM; the address is base_ext + offset
  (mainline masks base_ext only to find the region).
- SMD open handshake: set OPENING (+DSR/CTS/CD, fBLOCKREADINTR, indices 0,
  fSTATE), ring APCS IPC 0xf9011008 bit 0, wait for the remote to be
  OPENING/OPENED, set OPENED, ring, wait for remote OPENED (both immediate
  here). After a warm reset both states read CLOSED. Packet = 5-word header
  (length) + payload; responses arrive in the second FIFO ('req', 12,
  'msg#', 4, id = ack). RPM request: {'req', 20 + data} {msg_id, set 0,
  type, id, data_len} {key, 4, value}; types 'ldoa' 0x616f646c, 'smpa'
  0x61706d73, 'vsa' 0x00617376; key 'swen' 0x6e657773 (enable), 'uv'
  0x7675 (microvolts), 'ma' 0x616d.
- **QUP I2C (BLSP1 QUP5 at 0xf9927000) hangs**: clocks on (RCG 0x860 root
  from XO, branch 0x848, AHB vote 0x1484 bit 17), HW version 0x20030002,
  state RESET valid; lk's driver then hangs on a register read once the
  core is moved to RUN state (bus stall, not a loop; the watchdog record
  lands in the poll). Deferred; touch uses bit-banged I2C on gpio 18/19
  (func 0) for now. Candidates: the I2C mini-core clock/`QUP_CONFIG`
  sequence for v2.3, or the BLSP1 "sleep"/BAM clocks.
- **Touch**: Synaptics DS4-firmware controller, product `MCRYHW_002`, I2C
  0x20, reset gpio 16 (160 ms power delay, 10 ms low, 150 ms after),
  attention gpio 17 (low while pending, polled), I2C on gpio 18/19. The
  RMI4 function table starts AT 0xE9 and grows downwards (entry = 6 bytes
  read upwards from 0xE9, 0xE3, 0xDD...; reading from 0xE4 gave nonsense):
  F34 (flash) q 0x73, F01 q 0x7c d 0x13, F11 q 0x99 c 0x3e d 0x15. F11, not
  F12: 5 fingers → 2 status bytes, then 5 bytes per finger {x[11:4],
  y[11:4], y[3:0]<<4|x[3:0], wy<<4|wx, z}; range from F11 ctrl 6-9. The
  Android DSX driver (`hw/sturgeon/synaptics_dsx_core.c`) is the reference;
  touch coordinates match the flipped display without extra transforms.
- **PM8226**: power key = PON INT_RT_STS (0x810) bit 0. RTC seconds at
  0x6048 (write 0x6040 with ctrl 0x6046 bit 7 toggled), alarm at 0x6140 /
  ctrl 0x6146 bit 7 / clear 0x6148. VADC at 0x3100 (lk's register list):
  MODE 0x40, EN 0x46 bit 7, CHAN 0x48, DIG_PARAM 0x50, SETTLE 0x51, CONV_REQ
  0x52 bit 7, STATUS 0x08 (==1 done), DATA 0x60/61; channels VBAT_SNS 6
  (÷3), REF 0.625 V = 9, REF 1.25 V = 10; absolute calibration gives
  4.23 V on a full battery. Charger SMBB: RT status CHGR 0x1010 (done bit 7,
  fast 5, trickle 4), BAT_IF 0x1210 (temp ok 1, present 0), USB 0x1310
  (gone 2, valid 1); limits CHG_VMAX 0x1040 (3240 + n*10 mV), VSAFE 0x1041,
  IMAX 0x1044 (n*50 mA), ISAFE 0x1045, VIN_MIN 0x1047 (3400 + n*50 mV),
  USB_IMAX 0x1344 (n*100 mA above 200). Sturgeon profile: 4.35/4.37 V,
  300/600 mA, 100 mA termination, 300 mAh cell.
- Deviations from the M2 exit criteria: touch is polled, not IRQ-driven
  (TLMM summary IRQ 240 and the gpio interrupt config are still to do);
  charger "not charging" at 4.23 V with USB valid is the PMIC's own state
  (battery near full), not yet cross-checked against a discharged battery.

## Lab notes

- Never kill a fastboot command mid-flight: the bootloader's USB writes block
  until the host reads them, and a killed host process leaves lk2nd (or the
  stock aboot) waiting forever; only a power-key reboot recovers. Use long
  timeouts instead. `fastboot oem log` hung lk2nd on this Mac (not needed).
- The stock fastboot sometimes enumerates at full speed on the Mac and then
  refuses every command; re-seating / rebooting into fastboot fixes it.
- DRAM content (the ramoops log) survived even a power-key reset, although
  the PON config lists the key as a hard reset (`qcom,s2-type = <7>`).
- The generic-timer counter is not reset by a warm reset: boot time stamps
  continue from the previous boot (e.g. `[16.079]` at the first line).

## Milestones

| # | Milestone | Exit criterion |
|---|---|---|
| M0 | Boot loop + crash dumps | `make run` boots, shows text, reboots itself; hang and abort builds come back with a symbolized record; no key presses |
| M1 | Display | own double-buffered fb, 60 Hz with TE, DCS sleep/wake/brightness, software FlatMesh |
| M2 | Touch + PMIC | RMI4 IRQ-driven, power key, RTC, battery %, charger state and limits |
| M3 | USB/ADB | TinyUSB ci_hs gadget, CDC console, ADB shell/sync/reboot; go/no-go on loop speed |
| M4 | GPU | A305B bring-up, clear → quad → FlatMesh via ir3_compiler |
| M5 | UI layer | GPU-rendered toolkit, launcher, default watchface behind an interface |
| M6 | Sleep tier 1 | WFI + display off + rails, wake sources, current measured |
| M7 | Bluetooth | UARTDM + patchram + BTstack, AsteroidOS profile, notifications end to end |
| M8 | Sleep tier 2/3 | SPM power collapse, RPM sleep set |
| M9 | Apps | one at a time |
| M10 | Always-on display | panel idle mode, minute updates from RTC wake |

## Log

- 2026-10-25: research done; plan approved. lk2nd and bare-metal-adreno
  cloned next to the repos. Sturgeon facts gathered over adb (`hw/sturgeon/`),
  boot partition backed up, firmware blobs pulled. lk2nd built with forced
  fastboot and the scratch override. Firmware M0 code written and building
  (8.8 KB). Blocked on flashing: the stock fastboot enumerates on this Mac
  (`fastboot devices` lists it) but every command (`getvar`, `oem`,
  `reboot`) times out ("could not clear input pipe"), the same macOS
  incompatibility the lab USB appliance exists for. The watch is stuck in
  the stock fastboot until a power-key reboot. Alternatives: flash lk2nd
  from AsteroidOS with `dd` over adb (no fastboot needed), then see whether
  lk2nd's fastboot behaves on the Mac; otherwise run the loop through the
  appliance.
- 2026-10-26: M0 DONE. Direct Mac fastboot works once the watch is cleanly
  in fastboot (the earlier hangs were self-inflicted: killed commands).
  lk2nd flashed to `boot` and `recovery`. First boot stalled at "tick 0":
  wrong timer PPI (30 instead of 19) and no SCM watchdog-debug disable, so
  neither the tick nor the bite happened. Fixed: `make run` = boot 0.2 s,
  5 ticks, self-reboot, back in fastboot 6.9 s later, log fetched across the
  reset; TEST=hang returns a watchdog record with pc at the stuck loop,
  TEST=abort a dabt record with dfar=0xe0000000, both symbolized. Firmware
  8.3 KB.
- 2026-10-26: M1 code done: own double buffers, pipe in XRGB8888 with
  FLIP_UD, TE-synced 60 Hz flips, DCS brightness/sleep/wake, software
  FlatMesh at 2.4 ms/frame with the console as overlay. Awaiting a visual
  check (orientation, colours, fade, blank/wake).
- 2026-10-26: M2 DONE. Blockers on the way: QUP I2C bus hang (bit-bang
  instead), touch rails RPM-owned (SMD/RPM client written), SMEM at
  0x03000000 with RPM items in the message RAM, PDT scan direction, F11
  instead of F12. Verified on the watch: dot follows the finger, tap and
  swipe classified, power key reboots, RTC/battery/charger logged every
  second at 59 fps. Paused here at Darrel's request.

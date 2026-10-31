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
later but must render on the GPU; BLE host is NimBLE (Apache-2.0; changed
2026-10-28, BTstack's non-commercial clause conflicts with the GPL, see
BLUETOOTH.md); commits and code never mention the reference projects or
the lab USB appliance.

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
- **QUP I2C (BLSP1 QUP5 at 0xf9927000) works** with the downstream
  sequence (`drivers/i2c/busses/i2c-qup.c` of the sturgeon 3.10 kernel, a
  copy is not kept): SW_RESET → wait RESET valid → CONFIG 0, OPERATIONAL
  0xff0, ERROR_FLAGS_EN 0x7c, CONFIG = I2C_MINI_CORE (2<<8) | N_VAL 0xf,
  I2C_CLK_CTL 0, I2C_STATUS 0xfffffc; per transfer wait for QUP_STATE
  MAST_GEN (bit 4), IO_MODE PACK|UNPACK (+MX_READ_CNT), RUN, then write
  I2C_CLK_CTL (3<<8 | (19.2M/bus/2-3)), PAUSE, fill FIFO (16-bit tag|byte,
  two per word, low first: START 1, DATA 2, STOP 3, REC 4), RUN; done on
  MX_INPUT_DONE (reads) or out-FIFO empty and bus idle (writes). lk's
  driver "hung" because it skipped the mini-core/MAST_GEN steps; my first
  port also waited for RESET between transitions (5 ms timeout each,
  frame rate halved) instead of just STATE_VALID. Clocks: RCG 0x860 (cfg 0
  = XO), branch 0x848, AHB vote 0x1484 bit 17; pins gpio 18/19 func 3;
  FIFO 32 entries; IRQ SPI 99. 384 kHz (downstream value): 111 µs per
  one-byte register read. Bit-banged I2C kept as fallback.
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
- Touch is interrupt-driven since 2026-10-26: TLMM pin interrupt config at
  0xfd511008 + n*0x10 (enable bit 0, polarity 1, detection 2-3, raw status
  4, target apps = 4 << 5), status at +0x100c (write 0 to ack), summary SPI
  208 (GIC 240). QUP completion on SPI 99 (GIC 131): OPERATIONAL_MASK
  0x028 masks OUT_SVC for reads; OUT_SVC ends writes, MX_INPUT_DONE reads.
  Attention handler masks the pin, chains F01 status + F11 data reads in
  interrupt context, queues the event, unmasks. ~40 reports/s while
  dragging. Traps: IRQ entry must keep the stack 8-byte aligned (alignment
  fault on STRD otherwise); the main loop must drain the whole event queue
  per frame or the dot lags.
- Remaining M2 deviation:
  charger "not charging" at 4.23 V with USB valid is the PMIC's own state
  (battery near full), not yet cross-checked against a discharged battery.

## USB (M3 design)

- Controller: ChipIdea at 0xf9a55000 (capability regs +0x100, operational
  +0x140), IRQ SPI 134 (GIC 166), clocks GCC USB_HS_AHB 0x488 and USB_HS_SYSTEM
  0x484 (RCG 0x490 from GPLL0/8 = 75 MHz), block reset BCR 0x480, ULPI PHY via
  the viewport at +0x170 (MISC_A set 0x97: VBUSVLDEXTSEL|VBUSVLDEXT, plus
  GENCONFIG_2 bit 7 and USBCMD bit 25 for external session-valid), PHY rails
  L10 (1.8 V) and L20 (3.3 V) via RPM, PHY init-seq (mainline) writes ULPI
  0x80+n. The bootloader leaves the PHY configured, so the firmware only
  resets the controller core (USBCMD RST) and re-applies the ULPI select.
- TinyUSB 0.21.0 submodule; the ChipIdea DCD is compiled from a copy with an
  MSM variant header (reg base, GIC mask/unmask); cache maintenance through
  the dcd_dcache hooks; OPT_MCU_NONE with TUP_USBIP_CHIPIDEA_HS and 16
  endpoints declared by hand.
- Gadget 18d1:4ee7, CDC-ACM console (itf 0/1, ep 0x83/0x84/0x04) + ADB
  interface ff/42/01 (ep 0x81/0x01). ADB header and payload are separate
  bulk transfers in both directions; the OUT side queues exactly the number
  of bytes the parser expects (24 or the payload length) so a full-packet
  payload completes without waiting for the next short packet.
- ADB device services (shell:, shell:<cmd>, sync: to a RAM file table,
  reboot:) and the command console were written by an Opus 5.5 agent against
  a transport contract, with host-side unit tests (`make test`).

## M3 results (2026-10-26)

- The init assert was a wrong base: TinyUSB's `ci_hs_regs_t` begins with a
  256-byte reserved block before CAPLENGTH, so `reg_base` is the controller
  base 0xf9a55000, not the capability block at +0x100.
- Enumerates as 18d1:4ee7 at high speed ~1 s after start; adb CNXN 0.5 s
  later (host max payload 1 MiB, we cap WRTE at 4096).
- `adb shell <cmd>` round trip 18 ms; 64 KiB push/pull byte-exact; each
  push/pull ~25 ms (adb process start dominates).
- **Loop**: `adb reboot` → lk2nd fastboot 1.8 s → `fastboot boot` → adb
  online again 3.7 s after the reboot command. Go.
- `make run` = adb reboot (if online) + fastboot boot + `adb shell log N`;
  if the image dies before adb comes up, it fetches the ramoops region.

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
| M7 | Bluetooth | UARTDM + patchram + NimBLE host, AsteroidOS profile, notifications end to end (done 2026-10-28); media, weather, notification list, screenshot in progress |
| M8 | Sleep tier 2/3 | SPM power collapse, RPM sleep set (done 2026-10-29: cluster PD + VDD min, SUSPEND.md §9) |
| M9 | Apps | one at a time |
| M10 | Always-on display | panel idle mode, minute updates from RTC wake |

Open items (2026-10-29), not tied to a milestone:

- fbcon `memset` watchdog at boot: c9f07f3 (feed in present) did not end
  it. With the sensor hub builds it came back on about every other boot
  (watchdog ~3 s after boot start, pc in the fbcon memset right after the
  GPU self-test), then stopped reproducing (25 clean boots). IRQ counts at
  the bark were normal (~1 kHz tick only), CPU loop and memset speed
  measured at boot were the same every time, and one near-miss boot took
  1.2 s from `gpu: powered` to `pm4` (normally 17 ms): the whole system
  slows down, which points at bus/DDR clocks (RPM bus votes?) rather than
  interrupts. Next time: log RPM acks and the BIMC/SNOC rates.
- End of charge / resume not yet observed with the vendor-style poll.
- Battery percentage: replace the IR-compensated OCV stopgap with the
  vendor qpnp-bms method (reimplemented, OCV from PMIC + CC + UUC).
- Sleep current: ~14 mA asleep with BT (day test) vs ~1.6 mA on AsteroidOS
  (with AOD). See POWER.md for the ranked fixes.
- USB attach doesn't wake the watch from cluster sleep (needs a VBUS / PHY
  wake source).

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
- 2026-10-26: M3 started. ADB device services + console written by an Opus
  agent with host tests (make test passes). USB bring-up on the watch stuck
  at TinyUSB's endpoint-count assert. Fable context exhausted; continued
  with Opus 5.5 as the main model.
- 2026-10-26: M3 DONE: wrong controller base fixed, adb shell/push/pull/
  reboot work, full edit-to-running loop 3.7 s.
- 2026-10-26: hardware I2C fixed by following the downstream vendor driver
  (Darrel asked whether I had checked it; I had only used lk's).

## GPU (M4 findings)

- Power: RPM 'clk2' id 1 (gfx3d core, rate in kHz via key 'KHz' 0x007a484b
  plus 'swen') and id 2 (OCMEM); OXILICX GDSC at MMSS+0x4034 (clear
  SW_COLLAPSE, EN_FEW_WAIT=2, wait bit 31), branches MMSS_MMSSNOC_AXI 0x506c,
  OXILICX_AHB 0x403c, OXILICX_AXI 0x4038, OXILI_GFX3D 0x4028. GPU MMIO
  0xfdb00000 (register index * 4). IRQ SPI 33.
- hw_init as mainline `a3xx_gpu.c` for a305b (VBIF limits, RBBM, CP_PROTECT,
  CP_DEBUG, QUEUE_THRESHOLDS 0x003e2008), PM4/PFP microcode (skip word 0),
  ME_INIT 17 dwords. The GPU reads and writes plain DDR physical addresses
  (no IOMMU setup needed): ring at 0x1e000000 (uncached window).
- RBBM_HW_VERSION 0x00070010; PM4 0x00330043, PFP 0x00330020 (identical to
  linux-firmware qcom/a330_*.fw). Self-test (PKT0 scratch write + CP_MEM_WRITE
  + WAIT_FOR_IDLE) completes in ~5 µs.
- Microcode ships in the code repo's firmware/ with LICENSE.qcom and is
  loaded from the boot image's ramdisk (not linked into the GPL binary):
  lk2nd puts the DTB at 0x01e00000 (r2) and the ramdisk at 0x02000000 and
  records it in /chosen linux,initrd-start/end. Keep firmware memory below
  0x01e00000.
- Shader toolchain: Mesa ir3 compiler being built on pc by an agent
  (IR3.md, tools/ir3c in this repo when done).
- First GPU draw (2026-10-26): sysmem/GMEM-bypass rendering into the linear
  XRGB8888 back buffer works; per-vertex-colour triangle over the CPU mesh,
  0.43 ms per draw incl. clean+invalidate of the 666 KB buffer. Render
  target pitch is in 32-pixel units (RB_RENDER_CONTROL BIN_WIDTH), so the
  framebuffers now use 416-pixel rows. Draw path written by an Opus agent
  from freedreno fd3_* (sysmem prep, restore state, program, draw); first
  run worked unmodified. Cache rule: CPU-cached framebuffer → clean+inv
  before the GPU writes, invalidate after.
- Build trap: make's dependency on firmware/*.fw did not rebuild an empty
  ramdisk.img (built while firmware/ was absent); the ramdisk is now
  regenerated every build and replaced only if different.
- GPU core clock: 320 MHz via RPM made ~1 in 3 boots hang right after the
  request (CPU stalled writing DRAM); 200 MHz: 11/11 clean, with or without
  an OCMEM vote. Probably the vdd_dig corner (Android pairs gfx3d rates with
  corners); not verified. OCMEM is not used.
- FlatMesh on the GPU (per-vertex-colour shaders, CPU-animated vertices,
  one 516-vertex triangle list): 1.1 ms/frame incl. vertex animation and
  cache maintenance vs 2.4 ms software; looks identical on the watch.

## UI toolkit: Slint (decided 2026-10-26)

Darrel picked Slint as closest to QML (declarative markup, bindings,
animations; GPLv3 licence fits). Bare metal it renders in software. Plan:
software first, GPU path planned.

GPU path options, cheapest first:
1. **Layer compositing (do first):** Slint renders the UI into its own
   XRGB/ARGB layer only when something changed (partial repaint,
   `RepaintBufferType::ReusedBuffer`), the GPU draws the animated background
   (FlatMesh already) and composites the UI layer with one textured,
   alpha-blended quad per frame. Needs textured quads + blending in
   src/gpu/draw.c (texture state, sampler, FS with a texture fetch via ir3c).
   Static UI then costs almost nothing per frame; animating UI still renders
   on the CPU.
2. **Slint GPU renderer on internals:** implement Slint's internal item
   renderer (what the software renderer implements: rectangles, borders,
   images, text, clipping, opacity layers) on the a3xx draw path: solid and
   rounded rects as quads with a SDF fragment shader, images as textures,
   text from a glyph atlas texture. Uses i-slint-core internals that are not
   a stable API: pin the Slint version, expect porting work on upgrades.
3. **OpenGL ES for Slint's femtovg/skia renderers:** not practical bare
   metal: they need std and a runtime GLSL compiler (or a lookup table of
   offline-compiled ir3 shaders for femtovg's fixed shader set) plus a GLES2
   implementation on our command stream. Only worth it if 2 proves too
   fragile.
- Slint 1.18.1 watchface running (2026-10-26): Rust staticlib in ui/ (agent-
  written), C API src/ui/ui.h, heap 0x06000000 64 MiB, full software
  repaint blended over the GPU mesh: 6.4 ms CPU per frame at 59 fps. Image
  925 KB text (Slint ~865 KB, 405 KB glyphs at 5 sizes). Next on this path:
  partial repaint into a UI layer + GPU compositing (option 1 above).
- Random boot hangs after linking Slint: Rust's compiler_builtins provides a
  weak __aeabi_uldivmod that the linker used for the whole firmware (the
  Rust lib came before -lgcc). It is ~2000x slower than libgcc's here:
  time_us() took ~300 us, init ran past the 3 s watchdog in most boots. Link
  -lgcc before the Rust library. (The GPU-stop-before-reboot theory was
  wrong.)
- UI layer compositing works: Slint partial repaint into a premultiplied
  RGBA layer at 0x0a000000, GPU blends it over the mesh (texture state,
  ONE/ONE_MINUS_SRC_ALPHA). Idle UI ~1 us CPU per frame; GPU 3.0 ms per frame
  for mesh + full-screen blended quad.

## Sleep (M6 tier 1, 2026-10-26)

- Battery current: PM8226 IADC 0x3600, external 9.7 mOhm sense resistor;
  gain channel 3, offset channel 5, signal channel 1; I = (raw-off)*17857 uV
  /(gain-off) / R. Unplugged: awake ~170 mA, asleep (panel off) ~131 mA,
  + GPU powered down ~127 mA. Charger USB-valid bit lags unplug by ~16 s;
  PON cable bit (Huawei driver's choice) never set here.
- CPU clock mux (APCS RCG 0xf9011050/54, 0x501 = A7 PLL undivided) and RPM
  bus/DDR votes survive a warm reset: a test that lowered them made later
  boots crawl into the watchdog. Firmware now sets both at boot.
- Staged measurement image (uncommitted): MDSS clock gating, touch sleep,
  low bus votes, CPU on XO; numbers pending.

Staged results (unplugged, asleep): MDSS clock gating, touch F01 sleep and
lower bus votes changed nothing; CPU on XO 124 -> 94 mA. CPU0 SAW + standalone
power collapse works (warm boot via register SCM call, QTimer frame 0 wake)
but saves nothing measurable (~96 mA). L2 does not keep dirty lines through
the collapse: clean all cache levels. Next: full APCS collapse (SUSPEND.md).

## 2026-10-30 evening

- Battery: vendor BMS method on main (POWER.md §10).
- GPU: sleeping waits, painter colour order fixed (GPU-UI.md §11).
- USB attach wake: branch `usbwake` (worktree ../asteroid-embedded-usbwake),
  uncommitted until a real plug test: USB_CHGPTH (0x1300) USBIN_VALID
  interrupt on both edges through the same SPMI summary IRQ as the power
  key; plugging in wakes the screen for 3 s as mce does
  (`MCE_DEFAULT_TK_EXCEPT_LEN_CHARGER` 3000). USBIN_VALID lags an unplug by
  ~16 s, so only the attach wakes.
- Steps and heart rate: branch `health` (SENSORS.md §8).
- AOD on main (8051e5e): on sleep (not palm) the face switches to ambient
  (time, date, battery, white on black), the GPU is suspended first so
  Slint renders on the CPU, `ui_render` blends it over black, one flip,
  then the vendor idle-on sequence (FE 00, NOP + 150 ms, 39; off: FE 00,
  38, from `qcom,mdss-dsi-idle-on-command`). Redrawn when the RTC minute
  changes; the sleep length is capped to the next minute. Wake: idle off,
  GPU back (1.1 ms). `aod on|off` (kv `aod`). Checked: buffer screenshots,
  one frame per minute while asleep, wake and the off path. Not checked:
  how the panel looks in idle mode (needs eyes) and the current (needs an
  unplugged run).

## M9 apps (2026-10-30, main 624cfa2..7ba0a4a)

- Layout as AsteroidOS: top quick settings, left notifications, right
  weather, bottom launcher (2 columns of round icons). Apps open on their
  own layer (panel 6, `UI_PANELS` 7) that slides in from the right, over
  the stack; a swipe right closes it; only right drags are gestures on an
  app, vertical moves go to the app (scrolling). When fully open only the
  app layer is composed.
- Settings: one kv key per byte (`brightness`, `bt`, `vibrate`, `aod`,
  `clock12`), applied at boot (brightness via DCS 0x51 x 255/100; BT
  start skipped when off; vibration gates notification buzz only).
- Alarm: kv `alarms` (count + 4 bytes each), checked once a second from
  the RTC (local time; weekday = (day + 4) % 7), once alarms turn off
  after ringing, snooze 600 s exact (checked every second), ring overlay
  with Snooze/Dismiss, vibrates 500/500 ms until dismissed or 5 min; going
  to sleep while ringing snoozes. Sleep length capped to the next alarm.
- Timer (default 5 min, +-1 min/10 s, 10 s..99 min) and stopwatch (tenths)
  run in main from time_ms, also with the app closed and asleep; timer end
  caps the sleep length and rings on the alarm overlay (Dismiss only).
- Gotchas: ios-add.svg is a 1 px cross at 28 px (use text); the submodule
  ios-play/ios-pause differ from the copies in ui/icons (keep ours);
  `make test` did not rebuild on ui.h changes (fixed, 6426f7d); stray
  pixels at the screen corners in shots are the known garbage outside the
  round panel (mesh does not cover the square buffer), not app bugs.
- health and usbwake branches still predate all of this; rebase before
  committing.

## AsteroidOS layout match (2026-10-30, main b12a245..fcea3e3)

Surveyed on the watch running AsteroidOS (screenshots and QML in the
session scratchpad `aos/`, launcher QML `aos/src/applauncher/`):
plus-shaped grid (top quick panel, left notifications, right Today,
bottom launcher), default face 000-default-digital, launcher
000-default-horizontal (6 other layouts installed: vertical, three-icons,
two-columns, turbo-list, 3x3, speed-dial; picked under Settings ->
Launcher with live previews), LPM brightness 45/255 = 18 % from
`[BrightnessLPM]` in meta-sturgeon 20als-defaults.ini (normal 114/255 on
the charger).

Done to match: AOD 18 %; default digital face (Roboto Medium/Light,
Raleway Light, nightstand ring of 50 segments generated as SVGs in
build.rs since Slint paths need std) with the old face as "Classic" and a
Settings watchface page; carousel launcher with per-app mesh colours
(blend by page position, fade in with the vertical offset, no dimming
towards the launcher); quick panel (lock, Settings, toggles 3/page, dots,
battery bar); Today screen, Weather as an app; apps fade in, left-edge
drag = back through app pages (Face.app-depth / back-count) then close to
the watchface, top-edge drag closes; edge chevrons; 50 % / flick snap in
100 ms. `set` console command for settings.

Open: Slint embeds every font at every size (SLINT_FONT_SIZES adds sizes
for computed font sizes), image grew 4.5 -> 11 MB; bold/semibold labels
(launcher names, battery %) use Noto Light for now; launcher variants and
their selector not implemented; indicator pop animation, burn-in shift on
the always-on face not done.

## Indicators, flicks and launcher layouts (2026-10-30, main 0d66e56..0a1e6fe)

- App close: apps carry their own FlatMesh in their colours (second mesh, clipped to a 64-gon
  round window), so closing shows two meshes as on AsteroidOS (f281b96, c034e24).
- Edge indicators (21720b3): qml-asteroid `Indicator.qml` diamonds, GPU-drawn from a 32 px
  texture in stack_compose, fixed on screen; pop on touch release and wake (300 ms out, 400 ms
  back). Left one kept out while notifications are pending, also CPU-drawn on the AOD face.
  The wake pop is timed from the first flipped frame (495e293); before, GPU/panel resume ate it.
- Palm to sleep used to skip the AOD face (4b1f159).
- Launcher flicks (b5cd260): Pager component, velocity from recent moves on animation-tick,
  Qt ListView physics (1500 px/s² deceleration, 2500 px/s cap), snap to nearest item.
- Seven launcher layouts (0a1e6fe), `set launcher n` / Settings → Launcher. Stack routing in
  `launcher_scroll`: horizontal layouts take sideways drags; vertical ones take vertical drags
  except down from their start (ui_launcher_edges bit 4) or the top 40 px; speed dial takes
  drags starting on its wheel ring (24–47 % of W from the centre). Turbo list and 3×3 keep the
  mesh grey, two columns keeps the first app's colours (as their QML does).
- Slint gotchas: colour literals are `#RRGGBBAA` (Qt's `#AARRGGBB` `#66000000` came out fully
  transparent: the speed dial band); the software renderer clips rectangles only, so the
  launcher previews hide items that don't fit the circle; `row`/`col` property names clash.
- Image grew to ~11.3 MB from the extra embedded font sizes (launchers, previews, turbo list
  in 4 px steps).
- Untested on AsteroidOS side by side: the six non-default layouts (no reference screenshots,
  built from QML only).

## Run-time fonts, review findings, alarm app (2026-10-30/31, main e2fee26..03d1545)

- Run-time fonts: third_party/slint vendors 5 Slint 1.18.1 crates (365e00e pristine) + PR 12367
  (9b3c992) + no_std systemfonts (a25005f) + optional complex-scripts (9945a42). da8871c
  registers the TTFs via `with_global_context` right after set_platform (registering in
  create_window_adapter fails: no context yet). Image 11.3 → 6.5 MB. Full repaints +15-30 %
  (GPU path face 4.2 → 5.6 ms, +0.7 ms more for the atlas checksum). Text layout needs
  52.6 KB stack (bitmap fonts: 15.5 KB) → svc stack 128 KiB. Plan for next steps (subset fonts
  → ~5.2 MB, cache tuning): FONTPLAN.md.
- 41bd6a0: paint atlas keyed by address broke with heap glyphs (freed/reused); heap texels now
  also matched by FNV-1a checksum.
- `uibench <p> 0` (CPU repaint) corrupts the on-screen layer (striped digits); not a renderer
  bug. GPU path: `uibench <p> 1`.
- Slint 1.19 not on crates.io yet (master bumped 2026-10-30); rebase the third_party patches then,
  drop PR 12367 if merged, drop the ring SVG hack (no_std Path).
- Hindsight reviews (Codex + Fable): keep Slint, stay in C. Done from them: INT_MIN printf
  (f706dfa), i2c length wrap (533eada), parser_test + ASan/UBSan (baaf053), ext4 scan_dir
  hang on corrupt dir size found by a deep fuzz run (220e109), typed ui_event/ui_alarm/
  ui_colors seam (9b8c121), ring buffer compiler barriers (a8038d0), rounded clips through
  the renderer (e1f0a41) and shader g (c7287fe), ui.h contract (03d1545). Not done: compositor
  mask post-pass for the speed dial (band and label share the layer; strips stay).
- Shader g: ir3c on pc; gl_FragCoord asserts in the standalone ir3_compiler, so the pixel
  position is a varying (VS c0 = to_px, c1 = rect centre; FS c0.zw = half size - r, c1.x = r).
- Quick settings toggles were dead since 2f0d1e1 (paging TouchArea on top); 87b0364.
- Alarm app now asteroid-alarmclock's layout (3bc5128, e431b7e): pager per alarm, CircularSpinner
  time picker, Repetition day buttons, 12 h AM/PM wheel.
- Licence review: keep GPL-3.0 (Darrel). Open: 4343A0.hcd has no redistribution licence;
  NOTICE.qcom missing.

## App fidelity rework (2026-10-31, main 03d1545..582d59f)

From APPS-AUDIT.md. Shared qml-asteroid ports in ui/ui/controls.slint (c014aaa). Plumbing a6f6577:
bt connected, RTC + notification time, timer-set / brightness-set events, stopwatch laps kept in
main. Pop-up (6c4993f), music (2688b35), timer (1e9865d), stopwatch (e17a750), weather (740be8d),
notifications one per page with stack routing via ui_notes_edges (32f3d29), settings list + pages
(52050bb), ringing + pairing screens (5a85ba4), console `media` (2542c34).
- Gotchas: an element with only height/width gets centred (give x/y); Flickable swallows
  horizontal drags once scrolled (notes uses one two-axis TouchArea under the pages);
  Slint arrays can't be appended in .slint (laps live in the firmware); timer spinners need a
  guard or turning them feeds back through timer-set.
- Noto Sans Bold added (same family, weight 700). Slint has no font-stretch, so condensed styles
  stay Light.
- Icons through component properties render at intrinsic size: tools/addicon.py makes our
  copies 160 px (11.0 → 7.1 MB, 582d59f). Note icons stay 40 px (579 of them), so the pop-up's
  80 px icon is soft.
- Not done: notification actions panel (snooze), Display extras (auto brightness, tilt/tap
  wake), nightstand brightness/delay, Time/Date/Language pages, launcher preview flipping.
- Vibration was turned off on the watch while testing (Darrel: avoid buzzing). Ringing still
  buzzes regardless of that setting.

## Consistency round 2 (2026-10-31, main 1810a8f..fdc115e)

Codex + Fable 5.1 consistency review against asteroid-launcher/qml-asteroid/asteroid-settings;
Darrel kept "back from an app's first page goes to the watchface" (AsteroidOS minimizes to the
launcher; considered a bug). Settings gap review (Fable) and an audio feasibility study (Fable).
- Back gesture peeks (d9acb53, 180c67b): Face.peek moves the top page, the page below kept and
  slid in from the left like LayerStack contentX. Pager settle time from distance and speed.
- Stack follows GestureFilterArea/PanelsGrid (d6c13fc): mean move per event locks at 1 % width
  (+8 px floor), switch past half (vertical only while moving that way) or > 10 px/event,
  linear 100 ms. Apps slide in, keep 5 s through sleep, close with ui_set_app(-1), left/top
  indicators 4.8 px (cdd2cd4). ui_set_screen → Face.screen (a40ca86).
- Condensed Noto styles (43c64db): fontique matches typographic family (name ID 16), so
  tools/notofont.py renames each style to its own family and subsets Latin/Greek/Cyrillic
  without hinting, ~136 KB each (6 styles, image 8.05 MB).
- Notifications: icon strip, actions panel above each page, snooze kept aside in notify.c
  (b4e6a13, f23c4ec). Quick panel: brightness 10/100 + hold-scrub, cinema, power off/reboot.
- Settings: tilt/tap wake gates, burn-in shift of the AOD face (per-face margin × 1/½/¼),
  nightstand brightness/delay/AOD (nightstand_on() keeps it for the delay after unplugging),
  Fahrenheit, Time/Date (RTC write), Power (PON PS_HOLD reset type 0x4 = shutdown; verified
  poff reason PS_HOLD, then USB_CHG power-on), About rows. ui_action codes moved to 32+.
- Unanswered alarms snooze after 30 s (16c73dc), verified with the motor disabled in a test build.
- Not committed: pairing confirm/cancel buttons (numeric comparison now waits for the user);
  needs a real pairing to test.
- Test gotchas: an `adb shell` helper that always slept 6 s made "cancel within 3 s" tests
  reboot the watch; adb stalled for a minute while two background `adb shell log` pollers ran.
  Corner pixels outside the round panel keep stale content (mesh only covers the circle).
- Audio (Fable): speaker is a TFA98xx on BLSP QUP3 (GPIO 10/11) fed by tertiary MI2S, mic on
  quaternary MI2S; no WCD codec, so playback needs the LPASS ADSP (PIL via TZ, APR, AFE/ADM/ASM),
  ~6–10 weeks, proprietary adsp blobs. Suggested first step: probe the amp's ID over I2C.

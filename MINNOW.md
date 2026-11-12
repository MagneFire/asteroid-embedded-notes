# Minnow (Moto 360 2014) port (2026-11-10, branch `minnow`, worktree `../asteroid-embedded-minnow`)

First watch that is not an APQ8026: TI OMAP3630. Nothing below has run bare-metal yet. Sources:
the vendor kernel in `../minnow/minnow-kernel` (branch android-omap-minnow-3.10-marshmallow-mr1-wear-release),
the eMMC dump in `../minnow/dump`, and AsteroidOS running on the bench unit (adb P027XY2LNL, hwrev 9
= P2-9 "Rev B+", bootloader MBM MINNOW0954). "Live" marks what was read from the running watch.

Rule for sessions: never reboot the watch. `fastboot boot` or `adb reboot bootloader` leaves it in
fastboot until Darrel starts it by hand.

## Decisions (Darrel, 2026-11-10)

- **Its own image**, `build/omap3/asteroid.img` (`make` builds both, `make SOC=omap3` this one). DRAM starts at 0x80000000, the A8 has no hardware divide and no VFPv4, and
  the whole SoC layer differs, so `make` builds `build/asteroid.img` for the APQ8026 watches as
  before and a second image for minnow from the same tree. The SoC layer is picked at build
  time; boards, apps, UI, Bluetooth host and storage are shared.
- **Frames composed on the CPU** with NEON. Only the Adreno path composites screen slides, the
  launcher, app panels and indicators today. DSS overlays (GFX, VID1, VID2 with per-pixel alpha)
  can take the busiest blends later.
- **SGX530 postponed until needed.** The kernel side (pvrsrvkm, DDK 1.x) is open and documents the
  host interface, but the microkernel, the USSE shader compiler and the PDS/TA stream builders are
  blobs in `/system` (`libsrv_init.so`, `libGLESv2_POWERVR_SGX530_125.so`, `libusc.so`,
  `libglslcompiler.so`). Bare-metal would mean capturing and replaying their output for a few
  fixed operations. 320x290 is about 93k pixels, and on AsteroidOS the SGX was the bottleneck
  (12-20 ms serialization per frame, see the minnow launcher work).
- **All code first, watch last**, in sessions Darrel runs.
- **Postmortem logs through AsteroidOS**, below.

## Postmortem logs

MBM has no `oem ramoops`. The vendor kernel has PSTORE_RAM and PSTORE_CONSOLE; live dmesg:
`ramoops: attached 0x20000@0x83000000, ecc: 0/0`. The tree gives buffer-start 0x83000000,
buffer-size 0x20000, console-size 0x1fc00, annotate-size 0x400, no record size. `fs/pstore/ram.c`
lays the zones out as dumps (none), console at 0x83000000, ftrace (none), then the annotation.
It rounds each size down to a power of two, so the console zone is 0x10000 and the annotation
(1 KiB) sits at 0x83010000, not 0x8301fc00. The local kernel tree (44dc41a, not what the watch
runs) changes the layout to seven 0x2000 dump records first: the constants in
`src/soc/omap3/soc.h` have to follow whichever kernel is installed.
Each zone is `{sig "DBGC", start, size}` plus data, which is what `src/log.c` writes already.
After a reset the kernel copies old zones to `/sys/fs/pstore/console-ramoops` and
`annotate-ramoops` before it reuses the region. AsteroidOS does not mount pstore; `mount -t pstore
pstore /sys/fs/pstore` does.

So the firmware keeps its log ring in the console zone and the fault record in the annotate zone
(1 KiB), and after a fault, a watchdog reset or a plain reboot it resets with scratchpad command 0:
MBM boots `boot`, which is AsteroidOS, and `tools/run.py` pulls the two files. Only
`adb reboot bootloader` asks for fastboot. Open: whether MBM leaves the region alone across a
warm reset (Motorola put ramoops there, so it should).

## Hardware

- **SoC:** OMAP3630, Cortex-A8 r3p2 (live cpuinfo: vfpv3 neon, no idiv), HS device. No GIC (INTC
  at 0x48200000), no generic timer (32 kHz sync counter, GPTIMERs). DRAM 512 MiB at 0x80000000;
  0x83000000-0x8303f000 reserved (ramoops and secure RAM).
- **PMIC:** TPS65912 on McSPI1 CS0 (15 MHz, CS active high), irq on SYS_NIRQ. DCDC1 VDD_MPU
  (OPPs 300/600/800/1000 MHz at 0.975/1.15/1.275/1.3375 V), DCDC4 VDD_CORE, DCDC2 3.0 V, DCDC3
  1.875 V. Power key on TPS GPIO3. Live: LDO3 2.95, LDO5 2.8, LDO8 2.8, LDO9 1.2, LDO10 2.5 on;
  LDO1, 2, 4, 6, 7 off. No RTC in it: the wall clock is the M4 hub's. `cpcap-minnow.c` is dead code.
- **I2C (400 kHz):** i2c1 mXT 0x4a (irq gpio 99, reset 164); i2c2 M4 hub 0x39 (irq 59, reset 129,
  wake 126, boot0 21, enable 28; firmware `m4sensorhub-p2_5_minnow.bin`, 151136 bytes; it also
  has the light sensor, heart rate, accel/gyro/compass); i2c3 LM3535 0x38 and MAX17050 0x36 (rsns
  10 mOhm, alert gpio 140).
- **Display:** DSS DSI1 (0x4804fc00), command mode, RGB888, to an SSD2848 bridge (320x320 frame
  memory) and an Orise OTM3201 panel, 320x290 at 45 Hz (bridge register 0x2010: 30/45/60). Panel
  reset gpio 14, bridge reset 23, vsync events 29, VDDIO enable 42, MEM_EN 87, bridge 1.2 V
  through gpio 86 on Rev B+ (LDO1 before), panel LDO7 2.85 V. 26 MHz clock enabled by gpio 177,
  shared with the USB PHY. External TE unused (`gpio_te` -2). Init tables in
  `drivers/video/omap2/displays/panel-minnow-common.h`, shared with the bootloader (data version
  0x081214). MBM leaves the logo on and passes `panel_minnow.panel_param=3#528916`.
- **USB:** MUSB OTG at 0x480ab000, ULPI, external TI TUSB PHY (irq gpio 142, resetn 15, cs 16,
  csn 27).
- **eMMC:** HSMMC2 at 0x480b4000, 8-bit. **MBR/EBR table, no GPT, no names.** p2 mbm, p5 cdt, p6
  pds, p7 utags, p8 logo, p9 boot, p10 recovery, p11 misc (empty), p14 system (squashfs 4.0, zlib,
  128 KiB blocks, firmware in `/etc/firmware`), p15 cache (ext4), p16 customize, p17 userdata
  (the AsteroidOS rootfs).
- **Bluetooth:** TI WL18xx on UART2 (0x4806c000), 3 Mbaud with flow control, HCILL, nShutdown
  gpio 83, RTS also as gpio 145, script `TIInit_11.8.32.bts` (73956 bytes). WiFi on MMC3 SDIO,
  1.8 V switch gpio 186: stays off.
- **Charging:** bq5105x Qi: gpio 176 is high while it charges, gpio 22 is pulsed while the
  watch is on the pad without charging (off the pad: both low, no pulse for 1.5 s), gpio 78
  high stops it (only healthd drives it; the tree's comment says 72, the pin is 78).
  factory-kill-disable gpio 182: the minnow kernel's mmi-factory only touches it with a factory
  cable and never drives it high, so the firmware leaves it alone too (unlike smelt). To check
  on the watch: unplug USB awake. Live under
  AsteroidOS on the dock at 100 %: gauge 53.4 C.
- **Vibrator:** LDO6 2.4 V switched on and off. **C55 DSP** (voice, UART1, McBSP4, W25Q80 on
  McSPI2, irqs gpio 76/81): unused, held off.
- **Reboot:** `'B'<<24 | 'M'<<16 | cmd` to the scratchpad word at 0x48002914 (cmd 'b' bootloader,
  'r' recovery, 'p' panic, 0 normal), then the PRM global software reset
  (`arch/arm/mach-omap2/omap3-restart.c`). **Power-off:** pad 0x142 to gpio, gpio 143 (the PMIC's
  watchdog input) high; with USB in the vendor waits 500 ms first
  (`drivers/power/reset/minnow-poweroff.c`).
- **Boot image:** Android boot image, 2048-byte pages. Stock headers say kernel 0x10008000,
  AsteroidOS's say 0x00008000 and both boot, so MBM ignores them; where it loads the kernel is
  not known (live: initrd at 0x85211000). zImage with the tree appended; MBM edits `/chosen`
  (bootargs with bootreason, `mmi,powerup_reason`, `linux,hwrev`).
- **Power management in the vendor kernel:** CORE retention only (`global_disable_off_mode = 1`
  in pm-debug.c although the tree enables off mode), no SmartReflex, wake-ups from the IO pads in
  `pad-wkup` (UART2, UART3, UART4, M4, touch, USB, bq5105x, gauge alert).

## Code facts that shape the port

- The APQ8026 image has about 380 `sdiv`/`udiv` and 73 VFPv4 `vfma` family instructions, half
  the divides in the Rust library: both sides need A8 flags.
- `start.S` sets ACTLR bit 6 (SMP on the A7). On the A8 that bit is IBE and ACTLR is secure-only
  on an HS device; L2EN goes through the ROM/PPA service.
- `display_init` reads back the bootloader's splash; smelt showed nothing because of that
  (SMELT.md), so DSS is programmed from scratch here.
- The CPU path of `frame.c` only blends the face and the overlay; `stack_compose` is GPU only.
- TinyUSB has `portable/mentor/musb`.
- The store writes raw to `cache`; firmware comes from ext4 `system` by name. Minnow needs
  partitions by number and a squashfs reader.

## State of the port (2026-11-10, nothing run on a watch)

Branch `minnow`: the SoC-neutral names and `src/soc/qcom/` first (the Qualcomm image stayed
byte-identical through the renames and the move), then `src/soc/omap3/` (start-up relocation,
INTC, GPTIMER2 time base and GPTIMER1 tick, WDT2 with a bark from the tick, PRCM, GPIO and pads,
I2C, McSPI + TPS65912, UART, HSMMC2, DSS/DSI, MPU retention), `display_minnow.c` (bridge and
panel from scratch, ULPS for the always-on face), the CPU compositor `src/gpu/soft.c`, MUSB with
TinyUSB's driver, the MBR/EBR scan with names from the board table, a squashfs reader for
`/etc/firmware`, the WiLink driver with HCILL, the hub's older firmware as a variant of
`hub_m4.c`, the gauge with minnow's two receiver lines, the motor on LDO6. Research digests the
drivers were written from: `hw/minnow/research-*.md`. Review: `ASTRA-MINNOW-2026-11-10.md`.

Never read `/sys/kernel/debug/pinctrl/*/pins` under AsteroidOS on minnow: the kernel dies
(panic_on_oops) and the watch drops off USB. The dumps in `hw/minnow/aos-*.txt` were read safely.

## First sessions on the watch

1. `fastboot getvar all` (max-download-size, hwrev), then `tools/run.py --soc omap3 --serial
   P027XY2LNL --adb-serial asteroid-minnow`. What to look for: any sign of life on the panel,
   `asteroid-minnow` on adb, the `clock:` line (CPU speed, ACTLR), `boot:` (bootreason,
   hwrev), `pmic:`, `display:` lines, `usb:` controller version.
2. If nothing: does the watch reset back (bootreason watchdog after 4 s means it ran)? Then
   boot AsteroidOS and `tools/run.py --pstore --soc omap3`: is the region kept across MBM, and
   across `fastboot boot` of the kernel?
3. `TEST=abort` and `TEST=hang` builds: record in pstore, where the watch lands (fastboot or
   the installed system).
4. Display: bridge register verify, TE (falls back to no TE after three misses), frame times,
   the flat tire, always-on at 30 Hz with the link in ULPS and back.
5. Touch, power key, haptics (LDO6), backlight curve (the vendor's dim step is code 0x03, ours
   is smelt's 0x26).
6. `emmc`, `part`, `ls /etc/firmware`, the store on `cache`.
7. Charging on the dock with the temperature watched: receiver lines (`gauge` status), stop at
   53 C, pulses on gpio 22; USB unplug awake and asleep (factory kill).
8. Hub: flash version, mark, start; clock from the hub; tilt (screen status 0 or 2?); light
   sensor values against the backlight; whether it crashes without the accelerometer as smelt's.
9. Bluetooth: script download, low energy, the BD address order, HCILL sleep and wake.
10. Sleep current against AsteroidOS, one matched ~15 min run each: MPU retention only so far;
    PER and CORE retention, pad wake-ups, off mode and a lower OPP are not written.

## First run on the watch (2026-11-11)

Booted with `fastboot boot build/omap3/asteroid.img` by Darrel (`build/asteroid.img` is the
Qualcomm image; MBM takes it and falls back to fastboot). Merged into main the same evening.

Working: display with the bootloader's picture kept, always-on face, touch, side button, eMMC
and the settings store, the hub with clock, steps and light sensor, Bluetooth LE (paired with a
phone, time set), vibrator, adb from the start, sleep and wake with adb staying up.

What the watch showed that reading had not:

- **DSS clock domain.** Reading DSS_SYSSTATUS, then DSI_SYSSTATUS, right after a soft reset
  gave a bus fault. After the DSS core reset DISPC is in force-idle, so a clock domain in
  automatic mode stops the clock. Linux holds the domain awake across the reset and writes
  DISPC_SYSCONFIG (0x2015) before letting it idle. We now write it straight after the reset
  and keep the domain forced awake while the display is on (the vendor runs automatic).
- **Pads.** MBM leaves most of the board's pins in safe mode: the touch reset (gpio 164,
  pad 0x16c) read 0x011f. The whole default pin table of the vendor tree is applied now.
- **SIM pin cells.** gpio 126-129 drive nothing until CONTROL_PBIAS_LITE (0x48002520) and
  CONTROL_WKUP_CTRL bit 6 (0x48002a5c) are set, `omap3_enable_usim_buffer` in the vendor's
  control.c. MBM leaves them 0x101 and 0. The hub's reset is gpio 129, so the hub never left
  reset: "m4 bootloader not answering".
- **Touch supply.** LDO8 (2.8 V, always-on in the vendor tree) is off after MBM. The
  controller answers on I2C without it but senses nothing. NV holds the r3 settings
  (T7 ff 10 00 02, threshold 70), so the snowflake sensor is fitted.
- **eMMC.** The card reads EXT_CSD BUS_WIDTH back as 0 after the switch to 8 bit.
- **Bluetooth.** The chip answers the LE enable command (0xFD5B) with status 1; LE works
  without it.
- **USB.** MUSB only attached after a VBUS cycle. The controller was reset with the PHY
  already up, so it had not heard the PHY's VBUS report, and SESSION was then written
  unconditionally. The vendor writes SESSION only without VBUS (`musb_core.c:938-950`). Now
  the PHY is restarted after the controller reset and DEVCTL reads 0x98 before the stack
  starts. TinyUSB's driver had no dcd_deinit, so a restart after a real unplug did nothing.
- **Bootloader's picture.** MBM passes `panel_minnow.panel_param=<type>#528916` (0x081214,
  the vendor's INIT_DATA_VERSION). With type 2 or 3 and that version the bridge and panel are
  left alone and only the DSI host is set up: display ready in 6 ms instead of 163.
- **60 Hz.** The vendor's dock rate (`20 10 00 F7 00 6C`) works as the awake rate: 61 fps
  when only compositing (8 ms a frame), 30-41 fps in seconds with repaints (7-23 ms each) or
  22 ms composites.
- **Clock.** The watch ran about 3 minutes fast once. Time came from GPT2 with its overflow
  (165 s) counted by interrupt; not caught in the act. The wall clock now counts from the
  32 kHz sync counter as the vendor's does.
- **CPU supply.** The vendor's PMIC set-up switches DCDC1 to the 0.7 V range (0x06 = 0x7f)
  and its kernel then sets the voltage over the VC bus. We wrote the range and nothing after.
  DCDC1_AVS read 0xbc before the set-up, which is 1.25 V in the lower range and 1.45 V in the
  0.7 V one. MBM's own range was not logged, so whether the watch ran at 1.45 V that evening
  is not known; the gauge's temperature went from 39 to 45 C. The range is left alone now and
  logged at start. PRM_VC registers read 0 under MBM.
- **Gauge on USB.** VCELL reads 4.6-4.9 V with USB in, as healthd logs on the vendor system.
  The gauge is now started over one second after USB goes, as the vendor does.
- **Postmortem.** A data abort resets into AsteroidOS and `tools/run.py --soc omap3 --pstore`
  shows the log and the record. A reboot by hand loses them.
- **USB proxy.** It keeps the last watch's serial for 60 s: an offline `P027XY2LNL` means no
  watch behind it. Its console log shows connects on the watch port.

Open: the hub does not answer some transfers (`i2c2: no answer to 39`) and reports firmware
0000; sleep current not measured; CORE retention, lower OPPs and DSS overlays not written.
Reviews and their open items: `hw/minnow/review-opus-2026-11-11.md`.

## Performance and scaling (2026-11-11 night)

Merged into main: the frame work below (f5f5297) and the clock and voltage scaling (2ccbde4,
merged 2026-11-12 after the soak).

- **Where a frame went.** The mesh took 7.1 of 8 ms: floating point divisions per row, and the
  Cortex-A8's VFP is slow at scalar arithmetic. In 16.16 integers with one division per edge it
  is 1.55 ms; a composite is 2.1-2.4 ms and swipes hold 61 fps at 60 Hz. The flip waits 12-14 ms
  for the previous frame to go out over DSI, which is what bounds the rate.
- **RunFast mode** (FPSCR FZ and DN) makes the vertex maths 30 % quicker and does nothing for
  repaints.
- **Repaints.** `prof <n>` samples the PC on the 1 ms tick; `tools/prof.py` names the functions.
  65 % of a face repaint was Slint's `draw_texture_line` and its blend. The paint hooks the GPU
  watches use now draw on the CPU with NEON: rectangles, textures (nearest scaling), rounded
  rectangles without a border, the rounded clip. Face 11.0 -> 6.0 ms, side pages 2.5 -> 1.2,
  top 5.4 -> 4.8, bottom 11.7 -> 10.0 (what is left there is the allocator and items made and
  dropped on every repaint). `uibench p 0` is Slint's own drawing, `uibench p 1` the hooks.
- **Rounded clip and rotate animation** were GPU-only before: the battery bar had square ends
  and the rotation snapped on minnow.
- **CPU supply.** DCDC1_OP holds the voltage (SELREG clear): 0x3e = 1.275 V in range 0, the
  vendor's 800 MHz value. So the images that wrote range 1 ran the CPU at 1.475 V. With reg
  0x26 bit 0 set the DCDC1 registers read 0 over SPI; 0x26 = 0x48 keeps them on SPI.
- **Scaling.** 200 MHz (M2 x 4) at 0.975 V (sel 0x26) asleep and awake after 300 ms without
  activity; 800 MHz at the bootloader's voltage otherwise, voltage first with a 200 us wait.
  Read back correctly, 93-100 % idle on the face, mesh steps 7.8 ms, swipes 49-59 fps.
  Soak 2026-11-12: 15 one-minute cycles (wake, four swipes, 10 s awake, 40 s asleep) with
  BT bonded and connected, 19 min up, no fault, 0 BT resets, 68-70 % of awake time at the
  slow clock, 30-32 C on USB. No current measured yet.
- **Gauge and pad** verified: `usb out, started over` gives 3760 mV where USB showed 4.8 V;
  `dock 1` two seconds after the pad; the charging animation runs. The percentage jumps after
  each restart (39, 35, 34, 66 that evening).
- **Clock at start.** 00:00 until 3.2 s: the hub is reset into its ROM bootloader (0.6 s) and
  given 2.5 s to start before the time is read. It does not answer before its reset (10 ms of
  tries at 0.06 s), so it is probably not running then; whether the bootloader or our own pin
  set-up at 1 ms stops it is not known. An untested patch that asks it every 100 ms while it
  starts is in `hw/minnow/hub-early-clock-untested.patch`. Parked.
- **`no answer to 39`** lines during normal running are first tries the hub driver's retry
  recovers (the error count stays 0): the hub seems to sleep through the first transfer.
- **`touch swipe`** did nothing on the mXT driver until the injection was added.
- **uibench** with hundreds of repaints tripped the watchdog before it fed it.
- **SGX530:** scoping study in `~/Downloads/AsteroidOS/minnow/sgx-study/`. Replay of the
  transfer queue looks feasible (fills, blends, scaling), triangles not; not started.
- **Clock after AsteroidOS.** After a night under AsteroidOS the M4 clock read 01:51 at 07:01
  (5 h 09 behind); AsteroidOS's own clock was about 4 h behind local time. The firmware keeps
  local time in the M4, Linux probably UTC. Likely AsteroidOS writes its (wrong) time into the
  M4; to check: `date; hwclock -r; cat /sys/class/rtc/rtc*/name` under AsteroidOS, then boot the
  firmware straight away and compare.
- **`set bt 1`** on the console only stores the value; the quick settings toggle starts BT.
  After AsteroidOS paired with the phone the old bond no longer matched and the phone paired
  again.

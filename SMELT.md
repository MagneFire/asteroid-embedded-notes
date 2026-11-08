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

## smelt-safety branch (2026-11-06)

Worktree ../asteroid-embedded-smelt2, 9 commits on main b4954a0, all build, 19 host tests pass.
Darrel checked on smelt: display, flat tire, palm, edge gestures, tilt to wake, AOD brightness,
rotation. Sturgeon: button, sleep, AOD. Tilt fix: gesture wake bit off with the screen on, as the
vendor's display notify does; the M4 otherwise only fired on lowering the wrist. AsteroidOS on
this watch showed the gesture rate at -1 in every state read, so how it drives this is not traced.

Open: crash on sleep (twice, no log, not since); charging after a stop needs lifting off the pad
on AsteroidOS, so the warm cycle may stop charging for good; 53 C stop not seen on the watch, 60 C
unvalidated, heat on the pad 37 to 49 C in minutes; chin details for indicator and speed dial;
second hub interrupt with status 0 after each gesture; codex fixes (full timer, tilt retry) not
yet booted on a watch.

## Merged into main (2026-11-06, f93f312, not pushed)

15 commits from smelt-safety. Every commit builds, 19 host tests pass. The final commits were never
booted, on any watch: the last boots had debug code on top, removed before committing. Shared
changes not rechecked on sturgeon or sparrow: polled I2C wait, recovery, palm cancel, wake log.

Crash record: logs-smelt-crash-2026-11-06.txt, watchdog bark at spm.c:180-183 from power_idle, 3 s
after a qup2 timeout. Late wake cause unknown. The stop at 53 C worked. Dock: 40 to 50 C in minutes, and it never
restarted in 15 min after a stop. Self-wake gone in one 15 min run. The BCR address is proved by
"qup2 recovered". Open: charge policy for this dock, late wake, chin details, sparrow.

## Polish round on main (2026-11-07, a7fd7f8..efc895c, not pushed, not booted)

Darrel's smelt report: vibration dead, tilt and tap wake unreliable, plus on every watch no list
overshoot, a black gap at boot, the face snapping size once, an open with fade but no slide, and
the speed dial name not swiping back. Nothing below has run on a watch.

- Slide missing: `stack_update` got the pass's `now`, read before `stack_open_app` set `app_t0`; the
  uint32 difference wrapped and ended the slide on its first frame. Clamped at 0, host test added.
- Black gap: `fbcon_init` presented a black frame before the GPU microcode read and hub upload,
  undoing b4dbb37. Removed; the console now only presents when written to (no-UI path).
- Size snap: `present_clock` ran after `frame_draw`, settings only from `start_run` at 2 s. Frame 1
  showed the face at full size before nightstand's 0.86. Settings now pushed in `app_init`, clock
  before each frame.
- Speed dial: Slint ignores drags from the name; the C ring test sent part of the name to Slint, so
  only presses inside the hole became a screen swipe. The name sets launcher-edges bit 5 and the
  stack treats such presses as not the wheel's.
- Overshoot: Pager rubber-bands (give min(0.3 item, 15 u), resist e*give/(e+2 give)) and a flick
  reaching an end with speed left (v^2 - 0.003 d) overshoots up to 0.6 give, held in `drag` while a
  Timer waits out the move, then 300 ms back. Settings' Flickables replaced by `Scroller`
  (SwipeGestureHandler, so children still get presses after FORWARD_DELAY); a press on a coasting
  list only grabs it on the first move. Not tuned on a watch.
- Tap wake: at the 100 ms asleep scan a quick tap comes as one T9 message with PRESS|RELEASE and no
  DETECT; since c28d144 that was dropped. Now pushed as down and up (vendor atmxt.c AOT path does
  the same). Palm cancels were already logged.
- Tilt wake: a failed gesture-bit write left the watch free to sleep with tilt off (Codex P2).
  hub_m4 tracks tilt_set, retries from m4_poll, and can_sleep waits for it. QUP2 timeouts that
  restart the M4 while asleep still lose gestures: not addressed.
- Vibration: smelt's vendor tree (dts/android-smelt, from googlesource SRCREV 49608c8, pc was down)
  enables qcom,vibrator@c000 with only vib-vtg-level 2300 mV over the mtp's 3100: manual mode, and
  its qpnp-vibrator.c (hw/smelt) writes VTG then EN bit 7 exactly as haptics_pmic.c does. No code
  cause found. pm8226_set now reads EN back and logs once if the write did not take; next step on
  the watch is `buzz 500` and that log line.

Not done, Darrel didn't pick them: chin layout (bottom indicator, speed dial bottom disc, page dots
under the 30 px flat tire) and rotation being on because the frame is 360x360. Round back/close
animation: Darrel thinks it may already be fixed, re-test only.

Sturgeon at efc895c (2026-11-07, Darrel): boot handover, no face resize, slide-in, overshoot (not
AsteroidOS's, kept as is) and the speed dial name swipe all fine. Smelt and sparrow not run yet.

Sparrow at efc895c: boots, `buzz 500` felt by Darrel, no "not taken" log, EN 0x1c046 back to 00.

## M4 wedged (2026-11-07)
Asleep on the dock, qup2 timed out about every 70 s after the M4's wake line rose (I2C status
041321c4 / 04138700: bus active, SDA high, SCL low, so the M4 holds the clock). Each one ended in
"failing on the bus" and a reset that brought firmware 0084 back, about 45 times, until 3417 s.
After that, the ROM bootloader stopped answering at all. A fresh firmware boot didn't fix it, and
neither did AsteroidOS's own driver ("Barker fail", -ENOTCONN on every try). GPIO 6/7 read high,
reset 62 is released, boot0 109 is high. The M4 needs a power cycle, which a reset doesn't give it.
Lost: tilt wake and rotation. Log: logs-smelt-m4-2026-11-07.txt.

Analysis, vendor comparison and the M4 image's own behaviour: SMELT-M4.md (2026-11-07).

## Firmware flashed to `boot` for the crash hunt (2026-11-07)

The asleep-on-USB deaths (SMELT-M4.md §8) rebooted into AsteroidOS, which sat on the record RAM,
and they take 10 min to hours to reproduce. So the firmware image (d4e693d plus one uncommitted
debug line in main.c that writes the fastboot cookie 0x77665500 to IMEM at boot) was flashed to
`boot` with `fastboot -s M987BW25ZV flash boot build/asteroid.img`. Every reset now comes back
into the firmware, which prints "previous boot ended with:" and keeps the 256 KiB console ring;
a reset that skips `reset_now` (watchdog bite, PMIC reset, long power press) parks in fastboot
because of the cookie, and `fastboot -s M987BW25ZV continue` boots the firmware from there.
Proved with `mem e0000000 1` over adb: data abort, back in the firmware in about 2 s,
`tools/run.py --attach --adb-serial asteroid-smelt` printed the record symbolized to `cmd_mem`.

Backups, checksums verified against `sha1sum` on the watch: `backup/smelt/` (boot-asteroidos.img
sha1 a90433e1, recovery-asteroidos.img, aboot.img). Partitions: boot mmcblk0p24, recovery p25,
aboot p3. Restore AsteroidOS with
`fastboot -s M987BW25ZV flash boot backup/smelt/boot-asteroidos.img`; `fastboot boot` of the backup
also runs it from RAM, but a Linux boot wipes the record region, so only after the evidence is out.
Reading a death: firmware back by itself = a recorded fault or bark; in fastboot = a reset without
`reset_now` (a bite whose bark could not run shows as "no fault record" after `continue`); hung =
long power press, but the KPDPWR S2 reset type is whatever AsteroidOS last set and may lose DRAM.
Never run `make run`/run.py without serials while smelt is attached.

First death with the firmware in `boot` (2026-11-07, about 400 s after the boot that followed the
`mem` test, asleep, usb 1 dock 0, 70 %, 33 C): the watch came back by a cold boot. No fault
record, the console ring empty (logs-smelt-crash2-2026-11-07.txt starts at the new boot), IMEM
cookie gone (no fastboot), and the PMIC says pon 02 (SMPL, sudden momentary power loss), warm
0000 (every warm boot today showed 0200 = PS_HOLD), poff 0020 (POFF_REASON2 bit 5 = UVLO). So the
PMIC lost its supply for a moment; not a firmware fault, and a different signature from the
"PS_HOLD warm reset" read off AsteroidOS for the two earlier deaths (if that reading was
PON_REASON1 = 0x02 it was SMPL as well). The firmware writes nothing to the SMBB on smelt
(no battery_pmic); CHG_CTRL reads 0, USB RT_STS 07, BAT_IF RT_STS 03. Dock detect was 0 for the
whole previous run and 1 right after the reboot, so the dock contact moved around the death.
PON regs: KPDPWR S2 type 01 (warm, DRAM survives a long press), KPDPWR+RESIN type 07 hard.
On the dock afterwards the gauge went 34 to 48.6 C in 6.5 min at 0 mA: the dock heats the watch
without charging it.
Follow-up the same evening (branch `attach`): the boot line names the PMIC reason bits (`pon 02
smpl warm 0200 ps-hold poff 0020 uvlo`), a cold boot logs "no log from the previous boot", and
events.c keeps boots and dock/USB changes with the RTC time in the kv store key `events`
(written on a change only; `kv` on the console shows it, the next boot logs it as "events before
this boot"). Flashed to smelt's `boot`. No smelt AsteroidOS dmesg exists in this repo, so the
earlier two deaths cannot be re-read.
Second cold death the same evening after a run of about 210 s (events history: previous boot
1793759560, next 1793759772), dock 0 usb 1 the whole run, no charger-line change recorded,
logs-smelt-crash3-2026-11-07.txt. Control run started: AsteroidOS backup booted from RAM on the
same USB setup at watch RTC about 1793760737 (unplugged a while before, 37 C). Its dmesg renders the
reasons as "Power-on reason: Triggered from SMPL (sudden momentary power loss) and 'warm' boot" and
"Power-off reason: Triggered from UVLO", so the two earlier deaths read as "PS_HOLD warm reset" were
almost certainly this line: all four deaths are supply losses. If AsteroidOS dies, the watch
cold-boots into the firmware (adb asteroid-smelt appears); if it survives an hour, the firmware's
sleep path with USB present is the suspect.

## Why smelt resets when USB is unplugged (2026-11-07 evening, root cause)

Darrel reproduced the "crash" at will: unplug the watch from the USB dock while it is awake. All
deaths were PMIC cold boots, pon SMPL (sudden momentary power loss) with poff UVLO, warm reason
0000, DRAM gone. Asleep unplugs survived (3 of 3); awake ones died (3 of 3). AsteroidOS, booted
from RAM on the same dock, survived every unplug, asleep only as tested.

Mechanism, measured with the new `vadc` command and `pmic` dumps (smelt-pmic-dump-2026-11-07.txt,
logs-smelt-pmic-session-2026-11-07.txt):
- With USB in, the PMIC passes VBUS straight to VPH_PWR: usb 5140 mV, vph 4971 mV. The PMIC's
  VBAT_SNS reads the same 4971 mV while the gauge has the cell at 4020 mV, so on this board the
  battery sense node is VPH_PWR, not the cell. The charger sees "battery over voltage" (buck RT
  0x1110 bit 1), keeps the battery FET open (BAT_IF RT 0x1210 bit 2 clear), ignores IUSB_MAX,
  VIN_MIN and VDD_MAX (pass-through), and the gauge reads 0 mA from the cell awake or asleep.
- Under AsteroidOS the same registers (every SMBB, PON, pin, regulator block diffed, all equal)
  but VPH_PWR sits at the cell (3.6 to 4.0 V), the cell delivers the whole load (-45 to -150 mA)
  and the buck is in the input current loop (0x1110 = 08). This state is stable: once the cell
  holds VPH_PWR below the OV threshold, the charger keeps the FET closed and, with charging
  disabled, feeds nothing from USB. AsteroidOS discharges on the dock.
- The flip happens electrically: Linux's quad-core boot sags VBUS through the dock, USB valid
  drops for a moment, the charger's hand-over closes the FET, and the state latches. The firmware
  never loads the dock that hard (even GPU + vibrator + full brightness moved VPH 120 mV with
  IUSB_MAX at 100 mA). Booting the firmware straight after a Linux run already shows 4971 mV at
  3.1 s: the bootloader or the reset puts the PMIC back into pass-through.
- The hand-over on a real unplug runs only after the USB valid debounce: USB_OVP_CTL 0x1342 = 21,
  bits 1:0 = 5 ms (0 none, 1 5 ms, 2 10 ms, 3 20 ms; vendor driver sets 20 ms on boards where the
  FET is already closed). Awake, VPH_PWR falls from 5 V to the lockout in about 2 ms; asleep in
  tens of ms. That is the awake/asleep split. USB_SUSP (0x1347) does not raise USB-invalid, so it
  collapses the rail without a hand-over: it killed the watch awake and asleep.

Tried live and useless: VREF_BAT_THM forced on (0x124a = c0, left in place, the vendor does it too),
BATFET out of LPM (0x1293 = 00, reset by cold boots), CHG_ON_BAT_FORCE (0x1049 bit 0), CHG_EN
(fast-charge status, 0 mA into the cell), IUSB_MAX 100 mA, VIN_MIN up to 5.5 V, VDD_MAX 3.6 V,
OVP threshold select 0, PMIC GPIO 1 and 2 configured as Linux has them, USB_ENUM_T_STOP.

Fix (branch `attach`, untested): `pmic_usb_valid_debounce(0)` in smelt's gauge init so the FET
closes as soon as USB valid drops. Test: flash, unplug awake several times, then asleep. If it
still dies awake, the FET's own turn-on is too slow and the remaining options are (a) make the
firmware enter the AsteroidOS state at boot by sagging VBUS (needs more than 100 mA of load, the
firmware cannot), (b) find whether the bootloader can be told to leave the FET closed, (c) accept it
and keep the watch asleep when lifting it off USB. Side finding: a long power press is a warm reset
on this watch (KPDPWR S2 type 1), so DRAM and the log survive it.

Astra review (ASTRA-SMELT-USB-2026-11-07.md) and corrections: buck RT bit 1 is VREF_OV, not
battery OV (VBAT_OV is bit 0 and clear), so the firmware's 0x42 is VDD loop plus VREF over-voltage;
Linux's 0x08 is VCHG_LOOP, the charger output voltage loop, not the input current loop. The
pass-through, the open FET and the idle cell stand on the ADC and gauge numbers; the latch and the
"FET closes after the 5 ms USB-valid debounce" are hypotheses the vendor driver neither confirms nor
denies (it only uses the debounce for a health check), and the 2 ms collapse is an estimate, not a
waveform. The extracted AsteroidOS tree marks the BMS "ok", but the kernel config has
CONFIG_QPNP_BMS and CONFIG_QPNP_CHARGER unset, so no BMS or charger driver runs there; only the IADC
is built. Debounce 0 (840074e) is therefore an experiment: if an awake unplug survives it, good; if
not, the failure does not by itself say the FET is slow. Astra's other points: Linux's unplugs were
tested asleep only; the "identical registers" dumps cannot exclude transient writes in Linux init;
debounce 0 may expose pogo-pin bounce as repeated USB valid edges (wake interrupts, power-path
switching). Code fixes from the review in the next commit: events retries a failed kv write, pmic
write rejects bad addresses and trailing text, boot voltages skip failed conversions.

### 2026-11-08 morning: debounce-0 build flashed, awaiting the awake unplug test

The watch ran the 8bf6a8c+ build for 11.2 h without a death. Event history from the kv store:
unplugged 1793765021 (cable 0 usb 0, asleep), docked without power 1793765045 (cable 1 usb 0),
unplugged 1793804921, replugged with power 1793804933, then 25 s of awake use on USB without a
death (nothing was unplugged awake). PMIC registers left modified by the live tests were back at
their defaults after the cold boots (VIN_MIN 0x1047 = 12, GPIO c040/c140 = 00).

Flashed `build/asteroid.img` (built from 840074e with 3890b21 uncommitted, build id 840074eba2+,
main.c fastboot cookie still in) to `boot`. First boot: USB_OVP_CTL 0x1342 = 0x20 (debounce 0,
the fix applied), pass-through state as before: 0x1210 = 03 (FET open), 0x1110 = 42, vadc 7 =
1674 mV (vph 5.02 V), vadc 6 = 1673 mV (vbat_sns 5.02 V), vadc 0 = 258 mV (usb 5.16 V).
Test to run: wake the watch, unplug, three times; then asleep three times. A death shows as a
cold boot line (pon smpl, poff uvlo) in `events before this boot`.

Side finding: from hour 3 of the 8bf6a8c+ run the display logged "lanes not in ULPS, status
00000f0e, not resting" at every sleep (~250 per hour), i.e. the panel never rested for 8 h.
Log saved as logs-smelt-8bf6a8c-run-2026-11-08.txt. Not investigated yet.

### 2026-11-08: the real cause, Motorola's factory kill (gpio 116)

The debounce-0 build died the same way ~2 min after boot (pon SMPL, poff UVLO, cold boot), so
the PMIC debounce idea was wrong and 840074e is reverted.

Smelt's DT (apq8026-smelt-common.dtsi) has `factory_support`, compatible
`mmi,factory-support-kungpow`: gpio 116 `factory_kill_disable` (out, init low), gpio 112
`factory_cable_detect` (in, active low), gpio 111 `factory_warn` (in). `&pm8226_chg` is
`status = "disabled"`; the cell is charged by the TI bq5105x Qi receiver-charger (gpio 53 term,
58 rate, 94 chg_n), the PMIC charger block does nothing on this board. drivers/misc/mmi-factory.c:
with no factory cable (gpio 112 high) and no DCP charger it logs "Disabling factory kill" and sets
gpio 116 high; low keeps the kill armed. Armed, the kill circuit disconnects the battery while
USB powers the watch, so unplugging cuts the power: exactly the PMIC-side picture (VPH at 5 V,
VBAT_SNS at VPH, 0 mA from the cell, "FET open") that I had blamed on the SMBB.

On the firmware gpio 116 read cfg 0x1 (input, pull-down) level 0: armed, as aboot left it.
Live test with the new `gpio` console command, USB in, no unplug: `gpio 116 = 1` moved vadc 7
(VPH) from 1667 mV (5.0 V) to 1332 mV (4.0 V = the gauge's cell voltage), vadc 6 the same,
buck RT 0x42 -> 0x08, the Linux state. Fix on branch `attach` (aed7434): `.kill_disable = 116`
in smelt's gauge pins, driven high in gauge_init. Flashed to `boot`; at boot gpio 116 reads
0x200/1 and VPH follows the cell (3873 vs gauge 3937 mV under load). Awake unplug test pending.
Why asleep unplugs survived before is not explained; unimportant now if the test passes.

The old `pmic_usb_valid_debounce` and its commit are gone (2cfe8c9). The console `gpio <pin>
[= 0|1]` command stays (265d4a5).

**Confirmed 2026-11-08 ~11:50:** Darrel unplugged and replugged the fix build repeatedly, awake;
uptime 3890 s, same boot, a dozen "usb: cable plugged in" lines and no reset. The USB unplug
reset is fixed by aed7434.

Merged into main as aed7434 on 2026-11-08 (fast-forward of `attach`) and pushed.

## Automatic brightness (2026-11-08, merged into main as 2780202, checked on smelt)

Light path on AsteroidOS: `tsl2584` kernel driver → `sensors.smelt.so` → sensorfw → mce. The hub's
own ALS (`m4sensorhub_als`, bank 6) exists in the vendor tree, but the HAL's light sensor path and
sensord's `als` powerstate point at `tsl2584`, so the direct sensor is the right one.

mce's display curve is `meta-smelt/.../mce/20als-defaults.ini`: 21 profiles of 21 steps, profile =
round((setting-1)*20/99), level = first step with lux < limit else 100, a tenth of a step of
hysteresis downwards, input median of 9 at 125 ms, 1 s fade. Default on (`als_enabled`,
`als_autobrightness` true). It filters every brightness including nightstand, and the flashlight
too. The firmware follows it except: median of 5 at 250 ms, flashlight keeps 255. The firmware
reports at least 2 lux, so steps 0 and 1 are never hit and 10 % bottoms at 6 %.

Decided 2026-11-08: watches without the sensor keep the plain brightness setting and get no switch; nightstand brightness follows the sensor as mce does, can change later.

To check on the watch: backlight leaking into the sensor (dark room, lux at 10 % against 100 %; the
log prints `light: N lux, brightness P`), the 49 ms stall when the gain changes around 100-200 lux,
the current of the held L18 rail while awake.

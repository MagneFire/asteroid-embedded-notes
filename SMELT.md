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

# Smelt M4 sensor hub: failure analysis (2026-11-07, offline research)

Why QUP2 times out about every 70 s with the watch asleep on the dock, why each timeout ends in
a bootloader restart of the M4, and what the vendor does differently. No watch was used; the
source material is the firmware (`src/sensors/hub_m4.c`, `src/soc/i2c_qup.c`), the vendor kernel
`android-msm-smelt-3.10-marshmallow-mr1-wear-release` (SRCREV 49608c8, pc:
`asteroid-wrynose/build/tmp/work-shared/smelt/kernel-source`), the HAL `sensors.smelt.so` and the M4
image `m4sensorhub-p0_dali.bin` (version 0x0084 at offset 0x200, same as the watch).

Copies: `~/Downloads/AsteroidOS/smelt/kernel-m4sensorhub/` (vendor mfd/misc/include/i2c sources),
`smelt/system/system/` (HAL, image), `smelt/m4-firmware-re/` (Ghidra 12.2 decompile of the whole
image, strings with referencing functions, objdump, scripts, README with the key functions).

## 1. What the log shows (logs-smelt-m4-2026-11-07.txt)

Each cycle starts with one `qup2 timeout`, I2C status `04138700`: bus active, the QUP is bus
master (bit 9), SDA high, SCL low. The M4 has been stretching the clock for the whole 20 ms the
firmware allows. The firmware resets the QUP mid-transfer (no STOP), bus-clears, and about 4 s
later every transfer errors with `041321c4` (bus error, SCL still low) until five failures trigger
the ROM-bootloader restart. The M4 comes back as firmware 0084, and the next timeout follows about
62 s after each `GO`. 45 cycles later the bootloader stopped answering (see §6).

## 2. What the M4 image does (Ghidra, addresses in smelt/m4-firmware-re/m4.c)

- I2C slave, `FUN_08020134` (EV ISR, NVIC priority 0): address 0x43, clock stretching enabled,
  WUPEN set (wake from Stop on address match). A register access is served inside the ISR: on the
  repeated-start read the data pointer is resolved and ADDR released; a write is applied or queued
  at the STOP. After every transaction the ISR spins up to 1,000,000 iterations waiting for BUSY
  to clear (or a new address) and calls panic(5) when the loop runs out; panic(6) when waiting for
  the STOP after the NACK of a read. The ER ISR (`FUN_080203cc`) panics with 5 on BERR/OVR/ARLO.
  A master that drops a transfer without a STOP leaves BUSY set in the STM32: our 20 ms abort
  makes the M4 panic a few seconds later. That is the 4 s gap in the log.
- Clocks: `FUN_08020b28` sets PWR CR1 to Stop1 plus low-power run, so the core runs at the LPR
  limit (2 MHz or less); SLEEPDEEP is cleared on ISR entry and set again once the bus is idle.
- Panic path: `FUN_0801d178(code)` divides by zero; the fault handlers (0x8042258..) save the
  registers and jump to 0x801cdd2, which disables the IRQ pins, pulses the wake line (low ~5 ms,
  then high), prints a long dump with interrupts off (any host access stretches meanwhile), then
  runs `FUN_0801d06a` forever: a polling slave that answers four zero bytes to bank 1 offsets
  0x14/0x18, 0x00 to other reads, and a 4-byte reply to bank 0xFF cmd 0xCD. The vendor's
  `m4sensorhub_panic_process` is built on exactly this.
- Panic codes: 1 accelerometer watchdog (750 ticks without an accel sample, `FUN_0801fd3e`, tick
  source not found), 2 RTC alarm register failures, 3 power-thread event flags, 4 the host read
  TOTALSTEPS (bank 3 offset 4) ten times with the same value while deviceState is 1
  (`FUN_0801fd8a`, keyed on the requested offset), 5/6 the I2C bus not released.
- Power manager (`FUN_08019038`, thread `FUN_080193e0`): LPM enabled at boot; BMI160 no-motion
  60 s at 50 mG → "Stable enter LPM" (sensor low-power hooks over the M4's I2C3, RTC wake timer
  off, deviceState 0); any-motion 20 s at 100 mG → "Motion exit LPM" (deviceState 1);
  stillModeTimeout 600 s (the vendor writes the same). 60 s after boot, motionless on the dock, the
  M4 enters LPM: that is the ~62 s period. Why the first host access around LPM entry stretches
  past 20 ms is not settled offline (LPM work at the 2 MHz clock, or the Stop wake path).
- Interrupt masks start at zero (banks allocated zeroed, `FUN_080182ca`); `HM_InterruptHost`
  (`FUN_0801e0aa`) raises the wake line only for enabled bits. With our gesture-only mask the
  line rises for a gesture or for a panic pulse. Reads of offset 0x14/0x18 clear the status and
  lower the line at the STOP of the read (`FUN_0801e06e`), so a level IRQ re-enabled before that
  can fire once more with status 0: benign, but indistinguishable from a panic without the probe.
- Pins on the M4: wake line GPIOB0, nowake PA15. gpio 62 is a real NRST (nothing reads BOOT0 or
  jumps to system memory), IWDG unused, no SYSMEM references.

## 3. Firmware vs vendor

| Topic | Vendor kernel | Firmware | Effect |
|---|---|---|---|
| I2C timeout with a stretching slave | `i2c-qup.c:1205-1227`: 32 ms, then while bus master a further 1 s | `TIMEOUT_MS 20` on every bus | aborts a legitimate stretch; the M4 then panics |
| Per-transfer retries | `m4sensorhub-reg.c`: 10, 20-50 us apart; 5 failed calls → M4 reboot | none; 5 counted fails → restart after 30 s | |
| Wake IRQ while suspended | deferred until resume | status read on the first poll after the cluster wakes | read lands in the LPM entry |
| IRQ enables at init | `irq_disable_all` zeroes both masks, then STILL, MOTION, GESTURE (display off only), PASSIVE... | gesture bit ORed in | |
| Still mode | timeout 600 s written at init, STILL/MOTION handled | nothing written | |
| Wake with status 0 | panic probe `FF CD` → 0xDEADBEEF → reboot and restore | ignored | panics unnoticed |
| Reboot test | bank 0 offset 0, 3 tries with growing waits | one VERSION read | |
| Bootloader attempts | 5 reset+barker rounds, each op retried 10x | one round | "not answering" after one NACK |
| BOOT0 after GO, reset pulse | high; boot0 high, reset low 10 ms, release, 600 ms | same | an M4 self-reset lands in the ROM bootloader |
| Pins | DTS scl 6, sda 7 (i2c_3 says scl 11, sda 10: likely a typo) | sda 6, scl 7 | only `bus_clear` cares; check on the watch |
| Bus clear | QUP `MASTER_BUS_CLR` 0x40c | GPIO bit-bang | equivalent |
| Touch during M4 boot | notifier exists, but smelt has `enable_at_boot = 1` | runs | not a difference |

The HAL only reads IIO devices and `download_status`; the kernel driver does everything.

Registers (vendor headers): GENERAL bank 1: UTC 0x00/4, VERSION 0x0a/2, NOWAKEINTENABLE 0x0c/4,
WAKEINTENABLE 0x10/4, NOWAKEINTSTATUS 0x14/4, WAKEINTSTATUS 0x18/4. POWER bank 11: version 0,
enable 1, stillModeTimeout 2/u16 s, motionDuration 4, motionThreshold 5, noMotionDuration 6,
noMotionThreshold 7, deviceState 8. Wake bits: STILL 0, MOTION 1, GESTURE 2, PASSIVE 3, AP_ALARM 4,
M4_READY 5, SIGNIFICANT_MOTION 6. Pedometer bank 3: enable 0, activity 2, TOTALSTEPS 4/u32.

## 4. Causal chain

1. ~60 s after boot with no motion the M4 enters LPM. A host access in that window (the 10 s
   step read, or a wake read) is stretched past 20 ms.
2. The firmware aborts: QUP reset, no STOP. The M4's ISR spins on BUSY for seconds, panics (5),
   pulses the wake line.
3. The firmware reads the status during the panic dump, fails, retries once a second into the
   panic slave, counts five failures, restarts the M4 through the bootloader.
4. 60 s later, again. Each restart is a chance for the final wedge.

## 5. Firmware changes (branch `m4`, 4 commits, fast-forwarded into main d4e693d on 2026-11-07, not pushed; 19 host tests pass, booted from RAM on smelt, see §8)

1. Per-bus I2C timeout: 1 s for the hub while the QUP is bus master and the bus active (the
   vendor's rule); 20 ms elsewhere. Always bus-clear with a STOP after a timeout.
2. Init parity: zero both enable masks, write stillModeTimeout 600, enable GESTURE, STILL,
   MOTION.
3. Panic probe on every wake with status 0; restart at once when it answers.
4. Steps read from pedometer offset 2 for 6 bytes, every 30 s, so the TOTALSTEPS stuck check
   never sees the request.
5. Retries: 3 per transfer, 3 barker rounds, 3 version reads; log gpio 5/6/7/62/109 when the
   bootloader is silent.
6. Console: `m4 pm 0|1`, `m4 rd <bank> <off> <n>`, `m4 wr <bank> <off> <bytes>` (hex); `hub`
   shows wakes, last status, crashes, restarts, power management and the hub's still/moving
   state.

Still open after the code: the first >20 ms stretch is tolerated, not explained; the `hub`
crash counter and the wake log ("m4 wake 00000001, N s after its start" for STILL) will show
whether the LPM entry still coincides with a slow answer.

## 6. Open

- The bootloader silence after 45 resets: a true NRST should always bring the ROM bootloader
  back, so the M4 was in a state only power-on clears, or the pulse on gpio 62 was not seen.
  The vendor's answer to a failed reboot is a kernel panic.
- The exact source of the first >20 ms stretch (see §2). On the watch: `m4 pm 0` as an A/B.
- The accelerometer-watchdog panic (code 1): who calls `FUN_0801fd3e` was not found.
- SDA/SCL naming of gpio 6/7 (which line is held low during a stretch).

## 7. On-watch checklist (after the code work)

Boot and `hub`: version 0084, enables 0x7, stillmode 600. Asleep on the dock 30 min: no `qup2
timeout`, STILL at ~600 s, MOTION when lifted. If timeouts persist: `m4 pm 0`, repeat. Tilt
wake and rotation still work. `m4 rd 1 18 4` while the wake line is high shows the pending bits.
Sturgeon and sparrow unaffected; 19 host tests pass.

## 8. On the watch (2026-11-07, branch m4 booted from RAM, USB cable, not the dock)

- Branch as committed (1 s stretch allowance, vendor start-up, STILL/MOTION/GESTURE enabled):
  still crashed. At 180.8 s `hub: m4 wake 00000001, 66 s after its start` (the STILL wake, read
  fine), then at 182.7 s a `qup2 timeout` after the full second of allowance, SCL low, errors every
  2 s, restart at 193 s. Same cycle at 103 s before. So the M4 is not slow: about a second after
  it reports the watch still it hangs (or crashes and prints its dump with interrupts off) and
  holds SCL until reset. The 20 ms vs 1 s question was a red herring for this failure.
- `m4 pm 0` (POWER enable 0) at 130 s did not stop the 180 s cycle. In the image that write makes
  the power thread terminate itself (`FUN_0801f4e8` is tx_thread_terminate), so "Stable enter LPM"
  cannot have run at 180 s: the crash follows the no-motion event, not the LPM entry.
- Writing the accelerometer rate (bank 0 offset 2, any value reads back as 20 ms) at 200 s:
  no STILL wake and no crash in the following 4 minutes, deviceState stays 1. The accelerometer
  feature blocks the hub's power management (FM_BlockLPM -> PM_DisableLPM turns the no-motion
  interrupt off), so the watch is never reported still. The crash itself is most likely the
  accelerometer watchdog in the image (750 ticks without a sample once the sensor is put to
  sleep), which a Wear OS host never sees because something always has the accelerometer on.
- Fix taken: the accelerometer is enabled on the hub whenever it is up and only read when wanted
  (fourth commit on the branch). Cost: the hub never enters its low power mode; sleep current
  to be measured off USB against AsteroidOS. Worth checking on AsteroidOS: `dmesg | grep -i
  "M4 panic"`, which would show the vendor driver quietly restarting the hub the same way.
- Soak with the fourth commit: 30 min asleep on the USB cable, 1762 cluster collapses, one tilt
  to wake by Darrel at 397 s (screen on, `wake: tilt`), hub counters 2 wakes, 0 crashes, 0
  restarts, 0 fails. The image before it failed at 103 s and 182 s. Gauge 43 -> 36 C over the run.
- Off USB (2026-11-07, AOD on both sides, watch lying still). Firmware: 17 min unplugged, `power:
  asleep` every minute reads a steady 6 mA gauge average (11 s filter, read right after the
  firmware's own one-minute wake), 2 wakeups a minute, level 73 -> 72 %, hub 0 wakes, 0 crashes,
  0 restarts. AsteroidOS: 64 min unplugged (a userspace `sleep` logger freezes in suspend, so
  the numbers come from healthd's battery lines in dmesg, logged at its 600 s alarm wakes):
  current_now -4 to -8 mA in 10 of 13 samples, -24 to -64 in the others when the 175 ms sample
  overlapped the resume; level 76 -> 72 %. No "M4 panic" in the AsteroidOS dmesg. The two
  methods differ (instantaneous register after a Linux resume vs the firmware's 11 s average),
  so the result is parity within about 1 mA: keeping the hub out of its low power mode does not
  cost anything visible. The AsteroidOS level drop (4 % in 64 min, about 14 mA) is larger than its
  samples suggest, but RepSOC was still correcting after the charge.
- Asleep-on-the-cable deaths, three in one evening, same image, separate from the M4 work:
  (1) right as the cable went back in after the unplugged run, (2) about 10 min after a replug,
  both rebooting into AsteroidOS by themselves (PMIC warm reset reason 0x02 = PS_HOLD,
  `bootreason=reboot`, so a firmware `reboot()` or a watchdog bite); (3) a hang 9 min after boot,
  asleep on the dock with a 1 Hz `adb shell log 600` poller running: adb stopped answering and
  nothing reset the watch for 8 min until Darrel forced fastboot. The next m4 boot said "no
  fault record from the previous boot" every time, which proves nothing: AsteroidOS boots in
  between and the record RAM at 0x1ef80000 (kernel ramoops is elsewhere, 0x1eae0000) is ordinary
  memory to it, and AsteroidOS has no /dev/mem to read it out. Last captured lines before (3): the
  usual minute pair of rpm clock votes, no wake, no hub or USB event, 2200 wakeups a minute from
  the poller's USB traffic (60 a minute without it). Common factor: asleep with USB connected and
  USB activity (enumeration at plug-in, adb). With USB connected the firmware does not use the
  cluster collapse and leaves the watchdog armed (power.c), so a reboot without a record means
  the bark IRQ could not run, and a hang without a reboot means the watchdog was not counting.
  The 30 min soak with a 20 s poller and the 74 min run without one both survived. Open; needs
  its own session: boot the m4 image, leave it asleep on the dock, once with and once without
  adb traffic, and get the previous log out (e.g. have the firmware print its previous log ring
  at boot, or dump 0x1ef80000 from the fastboot or a firmware `mem` command before Linux runs).

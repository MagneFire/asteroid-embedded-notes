# Smelt port, no watch attached (2026-11-05, branch `smelt`, worktree `../asteroid-embedded-smelt`)

Rationale and open questions for the `smelt` branch. Everything below was read from
`android-msm-smelt-3.10-marshmallow-mr1-wear-release` (kernel mirror on pc), `meta-smelt`,
`system-smelt-m.tar.gz` and lk2nd's `dev_tree.c`. Nothing has run on a watch.

## Corrections to SMELT.md

- Height is **330 (large) or 325 (small and sports)**, not just 330; 401 lines holds for both
  (back porch 50 vs 55). Panel: NT35350 large/small, NT35355 sports small.
- **Stock and AsteroidOS smelt images have no `dt` section**: `CONFIG_BUILD_ARM_APPENDED_DTB_IMAGE`,
  12 trees behind the zImage, `img_info` has no dt. QCDT on Moto aboot is untested by anyone.
  One image: `build/asteroid.img` has the QCDT table and also the smelt tree behind the firmware
  (zImage magic and end offset at 0x24/0x2c). Darrel: it has to stay a single image. Risk: a
  bootloader that sees a dt section and finds no match there fails instead of trying the appended
  tree, so if smelt refuses to boot, look at how its aboot matches the table entry first.
  LK reads the appended offset at 0x2c without checking the magic; `start.S` reserves the words.
- M4 cannot simply be released from reset: every vendor path resets with **boot0 high into the
  STM32 ROM bootloader** and sends GO to 0x08000000 after checking the barker at 0x0807fff8. The
  driver does the same with only read-memory and GO opcodes. `m4sensorhub_update_host_config` (which
  erases and writes a flash sector) is skipped.
- M4 wake line gpio 5 (MPM 5, level high), nowake 67 (MPM 31, unused), reset 62, boot0 109.
- BCM43430A1 patch is 41 characters; firmware name field is now 48.
- USB presence: `qpnp-usbdetect` reads the RT status of SMBB USB_IN (0x1310 bit 1) even though
  `pm8226_chg` is disabled. So reading it is what the vendor does; the interrupt setup is an SMBB
  write and is not done, the state is polled once a second.
- Charger line names: 53 WCHG_TERMINATE, 58 CHARGE_RATE, 54 WCHG_PAD_DET_N, 94
  CHARGER_STARTB_1P8_N, all only exported to user space by `bq5105x_ctrl`, which sets 53 and 58 low.
  We never touch them. If aboot leaves 53 high the watch would not charge; check it first on the pad.
- `lm3535,en_gpio` says unsupported but the driver hardcodes `LM3535_HWEN_GPIO 35`.
- gpio 37 is "LED I2C Select", only given a suspend config (out low), no driver uses it.

## Decisions

- **Gauge is read-only.** The vendor loads the cell model only on POR. Its `maxim,configuration`
  tables (FW3L 776 = 388 mAh, FW3S 564 = 282 mAh, keyed by `/chosen/batt-id`) are not ported: if the
  status shows POR, the percentage is the gauge's default model until stock has run once. The
  firmware logs this. Writing the model is future work and needs the batt-id, which aboot passes.
- **Three layers keep the PMIC charger off smelt:** the table has no `battery_pmic` (board_test
  asserts it), SMEM platform 0x41 and panel width beat a wrong tree, and `board_assumed` stops the
  charger setup of a guessed table. Remaining hole: SMEM not 0x41, MDP off, and aboot passing
  another watch's tree. Considered a gauge probe on QUP3 before charger setup: rejected, it would
  add I2C traffic on sturgeon at boot.
- `board_assumed` is a behaviour change on sturgeon and sparrow, but only where neither tree nor
  panel named the watch.
- **No idle DCS on smelt.** The three panels have different idle sequences and nothing in the data
  tells NT35350 small from NT35355 (both 325). Fix would be three trees/compatibles if idle pays.
- Backlight curve is the vendor's zone 0 (the ALS branch of `lm3535_configure` is compiled out, so
  `bright_zone` stays 0): level 10 -> 67, 45 -> 79, 255 -> 108. The AOD's 18 % gives code 79, where
  stock caps ambient at 36: AOD on smelt will be much brighter and hungrier than stock until tuned.
- Touch writes nothing; config is the chip's NVM (the vendor only rewrites it when the tdat CRC
  differs). No T7/AOT sleep, so touch runs at full rate asleep. T42 palm not wired. Single finger.
- `heart_rate` stays false; M4 has PPG but it is not in this driver. No accel, so no auto-rotate;
  rotation is off anyway on the non-square panel (`rotation_buffer` assumes square).
- Regulators: touch votes L28 2.8 V. L27, L14, L8, L19 are left as aboot set them, and nothing
  here turns the panel supplies (gpio 33, 25, L14/L27) down in sleep, unlike the vendor's
  `gpio-state-idle` for the OTE2005B.

## Open questions, only a watch can settle

See the final report for the order. Also: does `emmc_part_find("system")` and the store partition
name exist in Moto's GPT; does aboot's cont-splash use pipe RGB_0; orientation; the T9 y range
against 330/325 lines and flat tire; BT LPO clock; whether SMEM reads 0x41; restart reason for
fastboot; BT sleep-mode bytes (polarity from nitrous `host-wake-polarity = <0>`, and the gpiomux
pulls up, but AsteroidOS reverts nitrous and runs brcm_patchram defaults).

UI on a non-square panel was not looked at beyond not corrupting memory: Slint's Theme unit is the
short side, the mesh and rounded UI assume centre = half height.

The settings store writes raw to the `cache` partition, as on the other two watches: on smelt
that overwrites stock's cache filesystem if a partition of that name exists. Check the GPT with
`parts`-style output first if stock is to stay intact. No backups of a smelt exist in `backup/`.

# Sparrow battery data and charger limits

Research notes, 2026-10-31, for the ZenWatch 2 ("sparrow") port of
asteroid-embedded. Source comparison only; no watch access.

**Notation**: **[V]** verified in source (file:line), **[I]** inferred,
**[U]** unknown. Paths are in this repo (`dts/android-sparrow/...`)
unless they start with `FW:` (the sparrow worktree `src/`).

## 1. The two cells

| | C11N1540 (SPARROW_PR3, the bench unit) | C11N1502 (SPARROW_PR) |
|---|---|---|
| Data file | `dts/android-sparrow/sparrow-C11N1540_2229781_380mAh-batterydata.dtsi` | `dts/android-sparrow/sparrow-C11N1502-1901242-400mAh-batterydata.dtsi` |
| `fcc-mah` | 380 | 400 |
| `max-voltage-uv` | 4350000 | 4400000 |
| `v-cutoff-uv` | 3400000 | 3400000 |
| `chg-term-ua` | 20000 | 20000 |
| `flat-ocv-threshold-uv` | 3800000 | 3800000 |
| `default-rbatt-mohm` | 401 | 474 |
| `rbatt-capacitive-mohm` | 50 | 50 |
| `batt-id-kohm` | **75** | **75** |
| LUT temperature columns | **5**: -20 0 25 40 60 | **6**: -20 -10 0 25 40 60 |
| fcc-temp-lut | 382 384 384 384 384 | 403 404 404 404 404 404 |

**Correction to the task brief**: it is the C11N1502 (PR, 400 mAh) that has
the 6-column LUTs. The C11N1540 (PR3) is 5-column like sturgeon's
HB442528EBC, so `bms.c` takes its tables unchanged. **[V]**

Other facts:

- Both files say `batt-id-kohm = <75>` and `battery-type =
  "palladium_1500mah"` (copy-paste; the type string is wrong for both).
  **The ID resistor therefore cannot tell the two cells apart [V].** Only the
  1502 file is included by a board dts
  (`sparrow_pr_msm8226-720p-mtp.dtsi:381`, next to `batterydata-mtp-3000mah.dtsi`,
  which is not in the notes); nothing in the notes includes the 1540 file, so
  how the PR3 kernel picked it is **[U]**. The vendor kernel picks the node whose
  `batt-id-kohm` is closest to the measured one (tolerance not in the notes,
  **[U]**); a 75/75 tie means the first node wins.
- The data is the same shape as sturgeon's: `pc-temp-ocv-lut` has 31 rows
  (row legend `100 95 ... 11 | 10 ... 6 | 5 4 3 2 1 | 0`, one row of
  values per percentage, one value per temperature), identical to
  `lut_pc[31]` in sturgeon's `battery.h`. `fcc-temp-lut` is one row.
  `rbatt-sf-lut` has only **30 rows** (100 to 1 %); the firmware's tables have
  31, whose last row is twice the 1 % row (sturgeon's SCUD 14102 -> 28204,
  XWD 22938 -> 45877), so battery.h does the same.
- `bms.c` also needs `rbatt_sf[31][5]` per cell (`struct cell`,
  `FW:src/soc/bms.c:62-67`), inline in `cells[]`, with `id_kohm` and the default
  rbatt. That table comes from `qcom,rbatt-sf-lut` and is in battery.h as the
  `BATTERY_CELLS` macro.

## 2. battery.h

`FW:src/board/sparrow/battery.h` now holds the C11N1540 tables in
sturgeon's layout (`lut_temp[5]`, `lut_pc[31]`, `fcc_mah[5]`,
`ocv_mv[31][5]`, rows = percentages, columns = temperatures), the
`BATTERY_CELLS` macro (rbatt table) and, under `#if 0`, the C11N1502 tables
with the -10 column dropped. Spot checks against the dtsi (row, column):
100 % / 60 C = 4322 (row 1, 5th value); 25 % / 25 C = 3758 (16th row, 3rd
value `3745 3756 3758 3748 3735`); 2 % / 0 C = 3416 (29th row, 2nd value
`3373 3416 3418 3402 3380`). rbatt row 30 % = `2077 347 101 72 57`.

The batt-id arithmetic is in section 5.

### 2.1 The 5-column form of C11N1502 (the -10 column dropped)

```c
static const int8_t lut_temp[5] = { -20, 0, 25, 40, 60 };
static const uint8_t lut_pc[31] = { 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25,
				    20, 16, 13, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0 };
static const uint16_t fcc_mah[5] = { 403, 404, 404, 404, 404 };
static const uint16_t ocv_mv[31][5] = {
	{ 4396, 4392, 4384, 4378, 4372 }, { 4288, 4314, 4318, 4315, 4310 }, { 4220, 4254, 4258, 4256, 4250 },
	{ 4163, 4199, 4202, 4200, 4194 }, { 4108, 4147, 4147, 4144, 4140 }, { 4071, 4096, 4094, 4092, 4088 },
	{ 3964, 4050, 4052, 4048, 4038 }, { 3916, 3958, 3980, 3990, 3990 }, { 3878, 3920, 3944, 3947, 3945 },
	{ 3844, 3888, 3897, 3898, 3896 }, { 3824, 3856, 3862, 3862, 3860 }, { 3809, 3828, 3834, 3836, 3834 },
	{ 3796, 3807, 3814, 3813, 3811 }, { 3782, 3790, 3794, 3794, 3791 }, { 3768, 3778, 3777, 3774, 3766 },
	{ 3752, 3765, 3758, 3749, 3737 }, { 3735, 3746, 3736, 3726, 3714 }, { 3718, 3724, 3713, 3703, 3690 },
	{ 3702, 3708, 3694, 3686, 3674 }, { 3689, 3701, 3690, 3682, 3670 }, { 3680, 3698, 3690, 3682, 3670 },
	{ 3670, 3696, 3688, 3680, 3667 }, { 3655, 3692, 3684, 3676, 3662 }, { 3635, 3684, 3674, 3663, 3646 },
	{ 3604, 3662, 3649, 3635, 3614 }, { 3562, 3624, 3608, 3594, 3573 }, { 3502, 3574, 3560, 3546, 3524 },
	{ 3424, 3511, 3500, 3485, 3461 }, { 3328, 3432, 3418, 3399, 3370 }, { 3216, 3310, 3283, 3258, 3224 },
	{ 3000, 3000, 3000, 3000, 3000 },
};
```

### 2.2 The 6-column form of C11N1502 (native)

```c
static const int8_t lut_temp[6] = { -20, -10, 0, 25, 40, 60 };
static const uint8_t lut_pc[31] = { 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25,
				    20, 16, 13, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0 };
static const uint16_t fcc_mah[6] = { 403, 404, 404, 404, 404, 404 };
static const uint16_t ocv_mv[31][6] = {
	{ 4396, 4394, 4392, 4384, 4378, 4372 }, { 4288, 4308, 4314, 4318, 4315, 4310 },
	{ 4220, 4246, 4254, 4258, 4256, 4250 }, { 4163, 4190, 4199, 4202, 4200, 4194 },
	{ 4108, 4137, 4147, 4147, 4144, 4140 }, { 4071, 4089, 4096, 4094, 4092, 4088 },
	{ 3964, 4031, 4050, 4052, 4048, 4038 }, { 3916, 3940, 3958, 3980, 3990, 3990 },
	{ 3878, 3907, 3920, 3944, 3947, 3945 }, { 3844, 3875, 3888, 3897, 3898, 3896 },
	{ 3824, 3844, 3856, 3862, 3862, 3860 }, { 3809, 3818, 3828, 3834, 3836, 3834 },
	{ 3796, 3800, 3807, 3814, 3813, 3811 }, { 3782, 3788, 3790, 3794, 3794, 3791 },
	{ 3768, 3776, 3778, 3777, 3774, 3766 }, { 3752, 3760, 3765, 3758, 3749, 3737 },
	{ 3735, 3742, 3746, 3736, 3726, 3714 }, { 3718, 3725, 3724, 3713, 3703, 3690 },
	{ 3702, 3712, 3708, 3694, 3686, 3674 }, { 3689, 3704, 3701, 3690, 3682, 3670 },
	{ 3680, 3699, 3698, 3690, 3682, 3670 }, { 3670, 3694, 3696, 3688, 3680, 3667 },
	{ 3655, 3688, 3692, 3684, 3676, 3662 }, { 3635, 3676, 3684, 3674, 3663, 3646 },
	{ 3604, 3654, 3662, 3649, 3635, 3614 }, { 3562, 3618, 3624, 3608, 3594, 3573 },
	{ 3502, 3566, 3574, 3560, 3546, 3524 }, { 3424, 3501, 3511, 3500, 3485, 3461 },
	{ 3328, 3418, 3432, 3418, 3399, 3370 }, { 3216, 3298, 3310, 3283, 3258, 3224 },
	{ 3000, 3000, 3000, 3000, 3000, 3000 },
};
```

and its resistance table, 30 vendor rows plus the doubled 0 % row appended:

```c
		{ 1859, 726, 327, 100, 74, 61 }, { 1859, 726, 327, 100, 74, 61 },
		{ 1715, 718, 328, 101, 74, 61 }, { 1621, 709, 330, 103, 76, 62 },
		{ 1560, 713, 340, 107, 78, 65 }, { 1565, 725, 341, 112, 84, 67 },
		{ 1406, 722, 378, 124, 92, 70 }, { 1401, 627, 317, 126, 96, 73 },
		{ 1403, 642, 309, 128, 95, 75 }, { 1404, 650, 306, 106, 82, 67 },
		{ 1441, 650, 301, 99, 75, 63 }, { 1495, 660, 303, 100, 77, 64 },
		{ 1557, 688, 307, 103, 79, 67 }, { 1620, 732, 313, 106, 83, 70 },
		{ 1695, 783, 335, 107, 82, 68 }, { 1778, 845, 357, 102, 75, 63 },
		{ 1877, 914, 377, 101, 74, 62 }, { 1965, 981, 399, 101, 75, 62 },
		{ 2030, 1039, 414, 100, 74, 62 }, { 1966, 1018, 411, 101, 76, 64 },
		{ 1946, 1008, 417, 103, 77, 65 }, { 1997, 1043, 425, 105, 80, 66 },
		{ 2062, 1077, 438, 109, 81, 66 }, { 2174, 1110, 454, 110, 80, 66 },
		{ 2451, 1146, 461, 108, 80, 67 }, { 2837, 1188, 472, 112, 86, 74 },
		{ 3360, 1257, 503, 123, 98, 84 }, { 4207, 1350, 541, 138, 109, 92 },
		{ 6984, 1538, 592, 154, 119, 101 }, { 13968, 2859, 726, 211, 175, 192 },
		{ 27936, 5718, 1452, 422, 350, 384 },
```

(C11N1540 has no 6-column form; its dtsi has no -10 column. Interpolating
one in would invent data.)

### 2.3 bms.c patch (not applied)

Two independent hooks, 20 changed lines, tested with `cc -fsyntax-only`
against the sparrow and sturgeon headers (sturgeon unchanged, no
`BATTERY_TEMPS` or `BATTERY_CELLS` there; the default 5 lives in `bms.c`,
since sturgeon's `battery.h` is not touched), and against a 6-column header
with `BATTERY_TEMPS 6`:

- **`BATTERY_TEMPS`** (default 5): the `rbatt_sf` width, the `lut2()` parameter
  type, and the two hard-coded `4`s in `temp_cols()`. Needed only for a
  6-column cell (C11N1502 in native form); not for the C11N1540.
- **`BATTERY_CELLS`**: lets `battery.h` supply the `cells[]` table. `bms_init()`
  indexes `cells[1]`, so with a one-cell table it needs the `ARRAY_SIZE`
  guard. This one is needed for the C11N1540 to get its own resistance table;
  without it sparrow keeps sturgeon's SCUD/XWD resistances, which are wrong for
  this cell.

Two cells in one build cannot share `ocv_mv`, `lut_pc` and `fcc_mah` today
(the LUTs are file-scope, one per build); choosing between 1540 and 1502 at
run time would need those in `struct cell` too. With identical IDs there is
nothing to choose on anyway (section 5), so one cell per build (a
`BOARD_...` macro or board.mk switch picking the `#if` block) is the
simplest.

```diff
--- a/src/soc/bms.c	2026-10-31 20:40:22
+++ b/src/soc/bms.c	2026-10-31 20:40:22
@@ -58,14 +58,22 @@
 
 #include "battery.h"
 
+/* Temperatures in the battery tables; battery.h may say 6. */
+#ifndef BATTERY_TEMPS
+#define BATTERY_TEMPS 5
+#endif
+
 /* Two cell makers, told apart by the ID resistor in the pack; they share
  * the voltage table but not the internal resistance. */
 struct cell {
 	const char *name;
 	int id_kohm, rbatt_mohm;
-	uint16_t rbatt_sf[31][5];
+	uint16_t rbatt_sf[31][BATTERY_TEMPS];
 };
 
+#ifdef BATTERY_CELLS
+static const struct cell cells[] = { BATTERY_CELLS };
+#else
 static const struct cell cells[] = {
 	{ "SCUD", 10, 496, {
 		{ 1926, 401, 100, 65, 47 }, { 1916, 401, 100, 65, 47 }, { 1767, 405, 102, 67, 48 },
@@ -94,6 +102,7 @@
 		{ 45877, 5703, 688, 411, 255 },
 	} },
 };
+#endif
 
 /* Battery thermistor: 0.1 C against mV at the ADC input, with a 68 kOhm
  * pull-up to 1.8 V. */
@@ -165,9 +174,9 @@
 {
 	if (t < lut_temp[0] * 10)
 		t = lut_temp[0] * 10;
-	if (t > lut_temp[4] * 10)
-		t = lut_temp[4] * 10;
-	for (*j = 0; *j < 4 && t > lut_temp[*j] * 10; (*j)++)
+	if (t > lut_temp[BATTERY_TEMPS - 1] * 10)
+		t = lut_temp[BATTERY_TEMPS - 1] * 10;
+	for (*j = 0; *j < BATTERY_TEMPS - 1 && t > lut_temp[*j] * 10; (*j)++)
 		;
 	return t;
 }
@@ -194,7 +203,7 @@
 }
 
 /* A value of a percent x temperature table, interpolated in both. */
-static int lut2(const uint16_t lut[31][5], int t, int pc)
+static int lut2(const uint16_t lut[31][BATTERY_TEMPS], int t, int pc)
 {
 	int r1, r2, j;
 	pc_rows(pc, &r1, &r2);
@@ -823,7 +832,7 @@
 void bms_init(void)
 {
 	int ohm = ratiometric_mv(CHAN_BATT_ID), kohm = ohm > 0 && ohm < 1800 ? 68 * ohm / (1800 - ohm) : 0;
-	cell = iabs(cells[1].id_kohm - kohm) < iabs(cells[0].id_kohm - kohm) ? &cells[1] : &cells[0];
+	cell = ARRAY_SIZE(cells) > 1 && iabs(cells[1].id_kohm - kohm) < iabs(cells[0].id_kohm - kohm) ? &cells[1] : &cells[0];
 	uint8_t stored = pmic_read(BMS_SOC_STORAGE), iavg = pmic_read(BMS_IAVG_STORAGE);
 	int stored_soc = (stored >> 1) ? (stored >> 1) - 1 : NONE;
 	status = pmic_battery_status();
```

## 3. Charger limits

### 3.1 Downstream (vendor) charger node

`dts/android-sparrow/sparrow_pr_msm-pm8226.dtsi:77-104` (`pm8226_chg`, `qcom,qpnp-charger`),
status `disabled` there and switched on by
`sparrow_pr_msm8226-720p-mtp.dtsi:396-399` (which only adds
`qcom,battery-data`; the `//qcom,charging-disabled` line is commented out).
**[V]**

| Property | Value | Notes |
|---|---|---|
| `vddmax-mv` | 4400 | the max for the 1502; overridden by the battery data (4350 for the 1540) **[I]** |
| `vddsafe-mv` | 4430 | |
| `vinmin-mv` | 4400 | |
| `vbatdet-delta-mv` | 100 | resume 100 mV below vddmax |
| `ibatmax-ma` | 350 | |
| `ibatterm-ma` | 30 | batterydata `chg-term-ua` says 20 mA |
| `ibatsafe-ma` | 1500 | |
| `thermal-mitigation` | 1500 700 600 325 | |
| `resume-soc` | 99 | |
| `tchg-mins` | 150 | |
| `ibatmax-warm-ma` | 150 | above `warm-bat-decidegc` 450 |
| `warm-bat-mv` / `warmer-bat-mv` | 4100 / 4100 | |
| `ibatmax-cool-ma` | 150 | below `cool-bat-decidegc` 220 |
| `cool-bat-mv` | 4400 | |
| `use-external-rsense` | 1 | external sense resistor |

BMS node (`pm8226_bms`, same file, 195-224), for the fuel-gauge macros:
`r-sense-uohm` 10000, `v-cutoff-uv` 3400000, `max-voltage-uv` 4200000 (the
battery data replaces it **[I]**), `chg-term-ua` 100000 (battery data 20000),
`low-voltage-threshold` 3420000, `ocv-voltage-high/low-threshold-uv`
3750000/3650000, `low/high-ocv-correction-limit-uv` 100/250, `hold-soc-est` 3,
`shutdown-soc-valid-limit` 100, `adjust-soc-low-threshold` 15,
`calculate-soc-ms` 20000, `low-soc-calculate-soc-ms` 5000,
`low-voltage-calculate-soc-ms` 1000. External rsense **[V]**.

### 3.2 Mainline

`dts/mainline/qcom-apq8026-asus-sparrow.dts` has **no charger node** and
`dts/mainline/pm8226.dtsi:64-86` has `smbb: charger@1000`
(`qcom,pm8226-charger`) only with its interrupts and `status = "disabled"`
**[V]**. The "mainline charger 350 mA fast, 4.43 V safe, 4.4 V vin min" in
EMBEDDED.md's table (line 719) are the downstream values above, not anything in
the mainline tree. The mainline driver takes its limits from the
`monitored-battery` (simple-battery) node, which the sparrow dts also lacks
**[U]**.

### 3.3 Sturgeon (firmware, for comparison)

`FW:src/soc/pmic.c:263-273` (sparrow worktree; unchanged from sturgeon) and
`FW:src/soc/bms.c:31-36` **[V]**:

| Macro | Sturgeon | Sparrow vendor, C11N1540 | Sparrow vendor, C11N1502 |
|---|---|---|---|
| `VDDMAX_MV` | 4350 | 4350 (battery data) | 4400 |
| `VDDSAFE_MV` | max + 80 = 4430 | 4430 | 4430 |
| `VINMIN_MV` | 4370 | 4400 | 4400 |
| `IBATMAX_MA` | 300 (1.0 C of 300 mAh) | 350 (0.92 C) | 350 (0.88 C) |
| `IBATSAFE_MA` | 600 | 1500 | 1500 |
| `ITERM_MA` | 20 | 20 (battery data; node says 30) | 20 |
| `RESUME_DELTA_MV` | 100 | 100 | 100 |
| `TCHG_MINS` | 150 | 150 | 150 |
| `RESUME_PERCENT` | 99 | 99 | 99 |
| `USB_WALL_MA` | 500 | not in the node | |
| `V_CUTOFF_UV` (bms) | 3200000 | 3400000 | 3400000 |
| `V_MAX_UV` (bms) | 4350000 | 4350000 | 4400000 |
| `CHG_TERM_UA` (bms) | 20000 | 20000 | 20000 |
| `FLAT_OCV_UV` (bms) | 3800000 | 3800000 | 3800000 |
| `LOW_VOLTAGE_UV` (bms) | 3350000 | 3420000 | 3420000 |
| `RSENSE_UOHM` (bms) | 9700 | 10000 | 10000 |

The firmware has no warm/cool handling (`grep` for warm/cool in `pmic.c`
finds none, only PON warm reset), so the vendor's 150 mA at under 22 C or
over 45 C, and the 4100 mV warm cap, have no counterpart; `vddmax_adjust()`
trims the voltage at end of charge instead. Vin min register:
`0x0c + (mV - 4000) / 50` (`pmic.c:441`), so 4400 gives 0x14, a valid value.

## 4. Proposed BOARD_CHG_* macros

To live in `board.h` (sturgeon's values keep the current numbers, so its
build does not change); `pmic.c` and `bms.c` replace their local `#define`s
with `#ifndef`-defaults or these. Sparrow is shown for the C11N1540 (the bench
unit, PR3); the 1502 differences in the last column.

| Macro | sturgeon | sparrow PR3 (C11N1540) | sparrow PR (C11N1502) | Reason |
|---|---|---|---|---|
| `BOARD_CHG_VDDMAX_MV` | 4350 | 4350 | 4400 | cell max voltage |
| `BOARD_CHG_VDDSAFE_DELTA_MV` | 80 | 80 | 30 | vendor safe 4430 in both; `VDDSAFE_MV` is `VDDMAX_MV + delta` |
| `BOARD_CHG_VINMIN_MV` | 4370 | 4400 | 4400 | vendor |
| `BOARD_CHG_IBATMAX_MA` | 300 | 300 | 300 | below vendor 350, equal to sturgeon's proven 1 C; 350 is the vendor value and OK to raise once measured **[I]** |
| `BOARD_CHG_IBATSAFE_MA` | 600 | 600 | 600 | vendor 1500 is not a protection at 300 mAh; keep sturgeon's ceiling |
| `BOARD_CHG_ITERM_MA` | 20 | 20 | 20 | battery data `chg-term-ua` |
| `BOARD_CHG_RESUME_DELTA_MV` | 100 | 100 | 100 | vendor |
| `BOARD_CHG_TCHG_MINS` | 150 | 150 | 150 | vendor |
| `BOARD_CHG_RESUME_PERCENT` | 99 | 99 | 99 | vendor |
| `BOARD_CHG_USB_WALL_MA` | 500 | 500 | 500 | not in the node, keep |
| `BOARD_BAT_CUTOFF_UV` | 3200000 | 3400000 | 3400000 | vendor `v-cutoff-uv` |
| `BOARD_BAT_MAX_UV` | 4350000 | 4350000 | 4400000 | battery data |
| `BOARD_BAT_LOW_UV` | 3350000 | 3420000 | 3420000 | vendor `low-voltage-threshold` |
| `BOARD_BAT_RSENSE_UOHM` | 9700 | 10000 | 10000 | vendor `r-sense-uohm` (check the real shunt) **[U]** |

`VDDSAFE_MV` for the 1502: 4400 + 30 = 4430. The vendor's 4430 safe limit
equals the 1540's 4350 + 80, which is why the delta macro is per cell.
`CHG_TERM_UA`, `FLAT_OCV_UV` need no change (same values as sturgeon). The
vendor 3.40 V cutoff is a gauge setting, not a protection; the PM8226 does
not cut off by itself, so any value works as long as the shutdown logic
uses it **[I]**.

Not proposed (no firmware counterpart): warm/cool current and voltage
limits, thermal mitigation. If wanted later, from the vendor: warm >45 C
150 mA and 4100 mV, cool <22 C 150 mA.

## 5. Battery ID

- Vendor: VADC channel `batt_id`, **0x31**, ratiometric calibration,
  `scale-function 0`, `hw-settle-time 2`, no pre-divider
  (`dts/android-sparrow/sparrow_pr_msm8226.dtsi:1508-1517`) **[V]**. The firmware already reads
  the same channel: `CHAN_BATT_ID 0x31`, `ratiometric_mv()`, and
  `kohm = 68 * mv / (1800 - mv)` (`FW:src/soc/bms.c:30,825`), i.e. a 68 kOhm
  pull-up to 1.8 V as on sturgeon.
- The sparrow pull-up is **not** in the notes: the `rpull-up-kohm = <100>`
  at `sparrow_pr_msm8226-720p-mtp.dtsi:378` is in the battery-data node
  and, in this kernel family, is for the battery thermistor, not the ID
  **[I]**. The ID pull-up on sparrow is **[U]**; reading the raw millivolts
  once (the `bms: cell ... (id N kOhm)` log line would print a wrong kOhm if 68
  is wrong) would settle it.
- Both dtsi say 75 kOhm, so even a correct reading cannot distinguish
  C11N1540 from C11N1502 **[V]**. Recommendation: do not branch on the ID for
  now; pick the cell per build (PR3 = C11N1540) and log the measured kOhm
  (`bms_init` already does) to learn what each pack reads. If the two packs
  turn out to read differently, the table of cells, once it holds the
  per-cell LUTs (section 2.3), is where the nearest-ID choice already lives.

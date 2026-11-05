# Sleep power on sturgeon: where the 14 mA go

Research notes, 2026-10-29. Source comparison plus the 2026-10-29 day log;
no watch access, no code changes. Follows SUSPEND.md §8-9 (VDD min works,
~26 mA then) and L2OFF.md.

**Notation**

- `K:` vendor kernel `~/Downloads/AsteroidOS/minnow/sturgeon-kernel`
  (msm-3.10, HEAD 97abcf5b2468). `FW:` `~/Downloads/AsteroidOS/asteroid-embedded/src/`
  at c9f07f3 (main). `LOG:` the day log (`rc.txt`, 3241 lines).
- **[V]** verified in source (file:line), **[M]** measured on the watch
  (this log or an earlier note, cited), **[I]** inferred with reasoning,
  **[U]** unknown. Savings are expectations unless marked [M].

## 0. Summary

1. The firmware sleeps at exactly **1 Hz**: every wake is the 1 s CNTP tick
   (`FW:main.c:289`, `FW:spm.c:150-152`), and every tick is a full cluster
   power down with VDD min (10 wakeups and 10 cluster collapses per 10 s in
   2472 of 2569 samples). Linux in suspend has **no tick**: the vMPM wake is
   ~72.8 min out and only RTC alarms and MPM pins wake it (SUSPEND.md §2.4,
   `K:drivers/cpuidle/lpm-levels.c:339-346,484-493`). AsteroidOS wakes once
   a minute for the AOD clock (SUSPEND.md §8.2).
2. The average is `floor + (overhead per cycle) × 1 Hz`. The log cannot
   separate the two terms because the rate never varies. The earlier
   residency fit (SUSPEND.md §8.2: 86 % VDD-min residency at a 1 s tick,
   ~140 ms per cycle outside VDD min) and the log's own ~90 mA "awake but
   idle" level (§1.3) together suggest the **per-cycle overhead is most of
   the 14 mA**, with the floor in the low single digits [I]. One
   measurement (§6.0) settles it; the fix (no tick, §5 F1) is right either
   way because it is what the vendor does.
3. Of the three floor reductions measured on 2026-10-27 (USB PHY LPM
   -7 mA, DSI PLL/PHY off -2 mA, MDSS GDSC -1 mA, SUSPEND.md §8.1-8.2),
   **none is in the committed firmware** [V: no PHCD/ULPI/PLL/GDSC writes in
   `FW:usb/`, `FW:display/`; the only copy is `usb_phy_lpm()` in
   `patches/sleep-debug-harness.patch:180-187`]. They are the vendor's
   methods (§5 F3, F4) and worth ~10 mA if the 2026-10-27 deltas still hold
   at the new baseline.
4. Every BT host-wake costs ~90 mAs (23.0 vs 14.1 mA in the 10 s window,
   n=66) because the loop then spends two ticks at the core-only collapse
   level waiting for the 1 s BT_WAKE idle timer (§1.3, §5 F2). Rare in this
   log (1 per 6.5 min, ~0.2 mA average), but it becomes the dominant wake
   once the tick is gone.
5. The current measurement is the same PM8226 coulomb counter the vendor's
   BMS uses, with the same constants (§3). Comparisons against the
   AsteroidOS 1.6 mA figure are like for like.

## 1. What the day log says

### 1.1 Layout and span

`LOG` is two dumps concatenated: lines 1-691 are the tail (32390-37233 s),
lines 692-3242 the body (11327-32380 s). Reordered, it spans 11339 s to
37234 s = **7.2 h** (the first ~3 h of the 10.3 h run are not in this
file). The watch is unplugged throughout ("usb absent (charger gone)" at
11328 s) until 37185 s when USB is attached and it starts fast charging at
-280 mA.

### 1.2 Asleep samples

`power: asleep, W wakeups, C/CC/B collapses, I mA average` every 10 s
(`FW:main.c:345-350`).

| | value |
|---|---|
| samples | 2569 |
| clean samples (W=10, ΔCC=10, ΔB=0, previous sample 10 s earlier) | 2472 |
| clean mean / median / sd | **14.11 / 14.0 / 1.73 mA** |
| by hour from 11339 s | 15.2, 15.3, 14.6, 14.8, 14.7, 14.2, 13.0, (10.3 over the last 64 samples) |
| wakeup histogram | 10: 2481, 11: 68, 12-15: 7, 19-85: 12 |
| collapse deltas per 10 s (core, cluster, bailout) | (0,10,0): 2472, (3,8,0): 51, (2,9,0): 5, (1,9,0): 5, (0,11,0): 3, rest < 3 each |

So: one wake per second, each one a cluster collapse, and a steady
~14 mA. The slow decline over the night (15.2 → 13.0 mA) is unexplained
[U]; candidates are the phone's connection interval changing with its own
idle state, the cell voltage (3.89 V at 11328 s), or temperature. Worth
logging `bt: connection update` lines and the battery voltage next time.

### 1.3 The cost of an extra wake

Samples with 11 wakeups (n=66) average **23.0 mA (sd 3.8)** against 14.1,
i.e. one extra wake costs **~90 mAs**. The extra wakes coincide with BT
traffic (`nimble: GATT procedure initiated: notify; att_handle=56` lines,
and the (3,8,0) pattern: 3 core-only collapses, 8 cluster collapses).
Mechanism [V]:

- HOST_WAKE (gpio 64, MPM pin 28) wakes the cluster, the chip's data is
  read, `bt_tx_activity()` resets `tx_t` (`FW:bt/bcm.c:230-237`).
- `bt_can_sleep()` needs `!dev_awake` (`FW:bt/bcm.c:252-255`), and
  `dev_awake` only clears `DEV_WAKE_IDLE_MS` = 1000 ms after the last
  activity (`FW:bt/bcm.c:21,242-250`).
- Until then `cluster` is false (`FW:main.c:399`) and the loop does
  `spm_idle(false)`: core collapse only, L2 on, XO on, no RPM sleep set, all
  active-set votes in force, the whole SoC at its active corner, on the 1 s
  tick. That is the "72 mA core collapse" level of SUSPEND.md §8, now
  ~90 mA by this estimate: 2 ticks × ~1 s × ~45 mA above the sleeping
  average, or 1 s at ~90 mA; the two cannot be told apart from the log.

That ~90 mA is also the best available number for what each 1 Hz wake
costs per unit time outside VDD min (§2).

### 1.4 Awake

`power: awake` lines with the display on: **136-140 mA** instantaneous,
60 fps GPU FlatMesh, UI repainting every frame
(`ui: 59 of 59 frames repainted` while a notification is shown, else
1 of 60). Not the subject here, but the repaint-every-frame case doubles
the GPU work for nothing.

## 2. Cost model: overhead × rate + floor

Average current = `floor + E_cycle × f`, with f = 1 Hz. The log fixes
`floor + E_cycle ≈ 14 mA` and nothing else. Two anchors:

- SUSPEND.md §8.2 (2026-10-27, before the flag-1 fix): VDD-min residency
  86 % at a 1 s tick, 94 % at 2.5 s, i.e. ~140 ms per cycle not in VDD
  min, fitted as ~86 mA × 150 ms ≈ 13 mAs per cycle. At the time the CPU
  ran the sleep loop at 19.2 MHz; since 9c5d365/874f815 and fde97a9 the
  loop after a cluster wake runs on the A7 PLL (`FW:main.c:407-411`,
  `FW:soc/clock.c:47-75`), so the firmware part should be shorter now.
- The 90 mAs per BT wake (§1.3) says the non-VDD-min level is ~90 mA.

If the cycle still spends ~140 ms outside VDD min: E_cycle ≈ 12.6 mAs →
floor ≈ 1.5 mA, which is the AsteroidOS figure. If it spends 40 ms (a
plausible hardware minimum: Linux's own latency figure for this level is
12.7 ms, `K:arch/arm/boot/dts/qcom/msm8226-v2-pm.dtsi:160`, plus RPM
shutdown/bringup and our flush): E_cycle ≈ 3.6 mAs → floor ≈ 10 mA. Both
fit the log. **§6.0 is the measurement that decides**, and it is cheap.

What is in a cycle [V unless marked]:

| phase | what | where |
|---|---|---|
| wake | MPM timer → RPM bringup (XO start, PLLs, CX/MX up, DDR out of self-refresh) → SPI 171 | SUSPEND.md §2.4.6; durations readable at master stats +0x2c/+0x30 (§3.4) |
| wake | TZ warm boot, `cpu_resume`, GIC restore, `timer_resume` (TVAL=1 → immediate tick) | `FW:soc/suspend.S:63-112`, `FW:soc/spm.c:160-166`, `FW:soc/timer.c:47-52` |
| wake | A7 PLL re-enable (BYPASSNL, 10 us, RESET_N, lock wait ≤ 200 us, OUTCTRL), mux to PLL | `FW:soc/clock.c:67-80`, `:47-52` |
| loop | `wdt_feed`, `usb_poll` (tud_task + adb + console), `bt_poll`, charger poll 1/s (3 SPMI reads), `pmic_power_key()` = 1 SPMI read **every iteration**, touch poll, notify, every 10 s the CC read + `log_printf` | `FW:main.c:192-230, 345-350` |
| sleep | mux to XO, then `cpu_clock_park` (GPLL0 vote, mux GPLL0/2, PLL off), `bt_sleep`, `mpm_arm` (12 vMPM words + IPC), L2 SAW 0x1a1, QTimer, GIC save, handoff lock, **full L1+L2 clean+invalidate by set/way**, SMC | `FW:main.c:400-406`, `FW:soc/spm.c:137-170`, `FW:soc/suspend.S:26-58` |
| sleep | TZ flag-1 work (its own L2 flush), CPU SAW pc, L2 SAW pc (APC rail off over SPMI), RPM shutdown handshake, sleep set applied, XO off, VDD min | SUSPEND.md §2.4.5 [I] |

The SPMI reads cost ~10-50 us each [I]; the cache flush is the largest
firmware item on the way down; the RPM/XO work on the way up is outside
our control except through the rate.

## 3. How trustworthy is the current measurement

`pmic_battery_avg_ua()` (`FW:soc/pmic.c:635-646`) is the BMS coulomb
counter delta over elapsed `time_ms()`:

- Same hardware path as the vendor: BMS `CC_DATA0` 0x408a, 5 bytes, held
  via `CC_DATA_CTL` 0x4042 bit 0 (`K:drivers/power/qpnp-bms.c:55,79,524-548,787-798`).
- Same constants: 542535/100000 uV per LSB (`qpnp-bms.c:621-626`), 56
  ticks of a 32764 Hz clock per reading (`:1410-1411`), 9.7 mΩ external
  sense (`K:arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-pm.dtsi:104-106`,
  `qcom,use-external-rsense`). `cc × 542535 × 56 / 32764 × 10 / 9700` =
  0.956 µAs per count, identical to `cc_uv_to_pvh` / `r_sense_uohm`
  (`:1414-1426,1462-1465`). [V]
- Differences from the vendor: `calculate_cc` also applies the IADC gain
  trim (`cc_adjust_for_gain`, `:1459-1461`) and die-temperature
  compensation (`qpnp_iadc_comp_result`, `:1467`). SUSPEND.md §8.1 found
  the trim gain-offset 3267 vs the ideal 3291, i.e. ~0.7 %. Omitting both
  is a ≤1-2 % scale error [I].
- Resolution: 1 count ≈ 1 µAs, so a 10 s window resolves µA; the printed
  value is truncated to whole mA. The 1.7 mA sd between clean samples is
  therefore real variation plus ±0.5 mA quantisation, not counter noise.
  Use 60 s windows (sd ≈ 0.7 mA) or 5 min (≈ 0.3 mA) for A/B tests.
- Time base: CNTPCT keeps counting through VDD min and agrees with the
  MPM2 sleep counter within 1 % [M, SUSPEND.md §8.1].
- Caveats: the counter is frozen while USB power is present [M, §8]; sign
  is positive for discharge; the 36-bit counter cannot wrap in a day
  (2^35 counts ≈ 9 Ah). The AsteroidOS 1.6 mA reference was taken with the
  same counter on the same watch (§8.2), so the comparison is like for
  like.

The instantaneous `battery N mA` value (`pmic_battery_ua`, `:606-614`) is
a single IADC conversion without averaging; the vendor's `get_prop_batt_current`
path uses the same IADC with gain/offset channels but averages over its
fast-average setting. Only the CC average should be used for this work.

## 4. Wakeups: how many and why

- **Ours, asleep:** exactly 1.0/s from the CNTP tick: `timer_set_period(1000)`
  at sleep (`FW:main.c:289`), `tick_irq` reloads TVAL (`FW:soc/timer.c:39-43`),
  `spm_idle` turns the remaining TVAL into the vMPM wake time
  (`FW:soc/spm.c:150-152`). Plus BT host-wake (~66 in 7.2 h here), touch
  (none), power key (10 wake/sleep pairs). Every tick is an RPM-assisted
  cluster collapse; the 20 ms guard at `spm.c:150` never triggers at this
  period.
- **Why the tick exists:** nothing in the sleep loop needs it. The charger
  poll matters only with USB present (then `usb_connected()` already
  forbids cluster sleep), the power key and BT and touch are MPM wake pins
  (`spm.c:118`), the 10 s stats line is cosmetic, and NimBLE's host timers
  have an explicit next-deadline query (`bt_npl_next_ms()`,
  `FW:bt/npl.c:277-293`) that is not used by the sleep path. The watchdog
  (bark 3 s, bite 4 s, `FW:main.c:134`) is the one hard constraint: a tick
  longer than 3 s needs the vendor's suspend treatment (§5 F1).
- **Vendor, suspend (AsteroidOS idle with screen off):** no periodic
  timer. `lpm_suspend_enter` programs the vMPM with `~0` → ~72.8 min
  (SUSPEND.md §2.4.3), the arch timer PPIs and QTimer are MPM-bypassed
  (`msm8226-v2-pm.dtsi:223-289`), so only MPM pins and the PMIC RTC alarm
  wake it. The watchdog is stopped in device suspend
  (`K:drivers/soc/qcom/watchdog_v2.c:114-126`) and re-armed in resume
  (`:128-140`). AsteroidOS adds one wake a minute for the AOD clock
  (SUSPEND.md §8.2, the logger sees "each minute AOD wake"). BT host-wake
  behaves like ours: `nitrous` deasserts dev-wake 1 s after the last TX
  (`K:drivers/bluetooth/nitrous.c:39,186`), the wakelock keeps Linux in
  idle (gdhs / pc-no-rpm, SUSPEND.md §9) for that second.
- **Vendor, idle with screen on:** NO_HZ tickless; cpuidle picks gdhs or
  l2-cache-pc-no-rpm between events (SUSPEND.md §9 live lpm_stats).

So the structural difference is **1 wake/s vs ~1 wake/min**. Everything
else about our wake sources already matches the vendor.

## 5. Where the 14 mA can go, and the fixes, ranked

Each item: what we do, what the vendor does (file:line), evidence,
expected saving, confidence, how to measure. "Awake-part" means it only
costs during the non-VDD-min part of each cycle (so it scales with the
tick rate); "floor" means it costs for the whole sleep.

### F1. Drop the 1 Hz tick (awake-part, largest)

- **Ours:** `timer_set_period(1000)` (`FW:main.c:289`); the vMPM wake is
  always the next tick (`FW:soc/spm.c:150-152`).
- **Vendor:** no tick in suspend (§4); vMPM wake = next real deadline or
  ~72.8 min (`K:drivers/cpuidle/lpm-levels.c:339-346,484-493`,
  `K:drivers/soc/qcom/mpm-of.c:531-551`); watchdog stopped across the
  collapse (`K:drivers/soc/qcom/watchdog_v2.c:114-140`: `WDT0_RST=1`,
  `WDT0_EN=0` before, `EN=1, RST=1` after).
- **Change:** while asleep, compute the wake as the minimum of
  `bt_npl_next_ms()` (`FW:bt/npl.c:277`), the BT dev-wake idle expiry
  (F2), the haptics pattern step, and a long stats period (60 s, or none);
  program it into the vMPM via `spm_idle`'s TVAL path. Before the SMC:
  `wdt_stop()` (`FW:soc/wdt.c:28`); after resume: `wdt_arm` again. Keep
  the "wake < 20 ms ahead → core collapse" guard (SUSPEND.md §8).
  Whether the APCS WDT even counts with the APC rail off is [U]
  (L2OFF.md §5 E2 raised it); stopping it the vendor's way makes the
  question moot.
- **Risk:** a NimBLE callout that fires late is harmless for the link (the
  controller keeps the connection), but security/GATT timers must be
  honoured, which `bt_npl_next_ms()` gives. RTC-driven UI (minute clock)
  is not shown while asleep.
- **Saving:** `E_cycle × (1 − 1/60)`. If §6.0 confirms ~140 ms/cycle:
  **~10-12 mA**. If the cycle is ~40 ms: ~3.5 mA. Confidence that it is
  the largest single item: medium-high [I from §1.3 and §8.2]; the size
  needs §6.0.
- **Measure:** §6.0 first (residency vs tick), then A/B 5-min CC windows
  at 1 s vs 60 s vs no tick.

### F2. Shorten the BT wake tail (awake-part)

- **Ours:** after a host-wake, two ticks at core-only collapse (§1.3)
  because `bt_can_sleep()` waits for the 1 s idle timer and the tick is
  the only timer.
- **Vendor:** same 1 s rule (`nitrous.c:39`), but Linux spends that second
  in cpuidle, not at a fixed 1 s granularity.
- **Change:** when `bt_can_sleep()` is false only because `dev_awake`, set
  the wake time to `tx_t + DEV_WAKE_IDLE_MS` (not the tick) and use the
  core-only collapse until then; re-evaluate immediately after. Also stop
  deasserting/re-asserting BT_WAKE around the firmware's own 10 s log line
  if it ever sends (it does not today).
- **Saving:** ~90 mAs → ~20 mAs per event [I]; at this log's rate
  ~0.2 mA, more with a chatty phone. Confidence high on mechanism [V],
  low on magnitude.
- **Measure:** compare the 11-wakeup sample mean against the 10-wakeup
  mean before/after (the log already gives this split).

### F3. USB PHY low power mode (floor + awake-part)

- **Ours:** PHY left as the bootloader runs it, controller reset, pull-up
  connected (`FW:usb/usb.c:51-66,297-308`). No LPM anywhere.
- **Vendor `msm_otg_suspend`** (`K:drivers/usb/phy/phy-msm-usb.c:884-1141`)
  [V]: OTG comparators off `ulpi_write(OTG_COMP_DISABLE,
  ULPI_SET(ULPI_PWR_CLK_MNG_REG))` (`:616-617`); non-driving opmode when
  `ALLOW_VDD_MIN_WITH_RETENTION_DISABLED` (`:955-963`); `PORTSC |= PHCD`
  and poll (`:969-980`); `USBCMD |= ASYNC_INTR_CTRL | ULPI_STP_CTRL`
  (`:1005-1012`); `pclk`/`core_clk` off (`:1071-1073`); XO vote off
  (`:1077-1082`); PHY regulators off (`USB_PHY_REG_OFF`, `:1085-1088`) with
  `ALLOW_PHY_POWER_COLLAPSE`, else L20/L10 to 4 mA LPM loads
  (`:1089-1092`, loads `:65,70`, `msm_hsusb_ldo_enable` `:268-278`); bus
  vote 0 (`:1124`). 8226 gets `ALLOW_PHY_POWER_COLLAPSE | ALLOW_PHY_RETENTION`
  (`:4871`) and `ALLOW_LPM_ON_DEV_SUSPEND` from DT (`:4404,4882`; the
  sturgeon node has `qcom,hsusb-otg-lpm-on-dev-suspend`? not in
  `msm8226.dtsi:332-358` [V]; check the common MTP dtsi before relying on
  it). Resume is the mirror (`:1170-1280`).
- **Evidence:** `usb_phy_lpm()` (PHCD + USBCMD bits 29/30, plus the ULPI
  0x98 clear noted in SUSPEND.md §8.1) measured **-7 mA** within a run on
  2026-10-27 [M]. The regulator part (L20 3.075 V / L10 1.8 V off or LPM)
  was not measured separately ("L10/L20 off: no effect" at the 50 mA
  baseline, §8.1, inconclusive at that noise).
- **Wake on attach:** the vendor's path is the PMIC `usbin-valid`
  interrupt (`K:drivers/power/qpnp-charger.c:2103-2120,5784-5795`,
  `enable_irq_wake` `:707,757`) → MPM pin 62, which the firmware already
  wakes on for the power key (`FW:soc/pmic.c:62-86` does the same
  SET_TYPE/POLARITY/EN_SET dance for PON; repeat it for SMBB USB periph
  0x13). That also fixes "USB attach doesn't wake" (EMBEDDED.md).
- **Saving:** ~7 mA [M, 2026-10-27 baseline]. Confidence high that it is
  real, medium on the exact size at 14 mA.
- **Measure:** 5-min windows with/without `usb_phy_lpm()` on the sleep
  path, then add the L20/L10 `swen=0` / LPM step as a third arm.

### F4. DSI PHY/PLL off, DSI/MDP clocks off, MDSS GDSC (floor + awake-part)

- **Ours:** `display_sleep()` = DCS 0x28 + 0x10 only (`FW:display/display.c:139-144`).
  DSI PHY, DSI PLL, DSI/MDP clocks, MDSS GDSC and the panel rails L15
  (2.8 V "vdd"), L8 (1.8 V "vddio"), L4 (1.2 V "vdda") stay as the
  bootloader left them.
- **Vendor off path** `mdss_dsi_off` (`K:drivers/video/msm/mdss/mdss_dsi.c:518-565`)
  [V]: controller off, `mdss_dsi_phy_disable` (`K:.../msm_mdss_io_8974.c:48-80`),
  all DSI clocks off (`mdss_dsi.c:558`, PLL off via
  `dsi_pll_disable` → `GLB_CFG = 0` at `K:drivers/clk/qcom/mdss/mdss-dsi-pll-util.c:470-484`;
  that register is 0xfd922a20, the one the harness zeroed), then
  `mdss_dsi_panel_power_ctrl(OFF)` (`mdss_dsi.c:229-300`) → panel supplies
  disabled per `qcom,panel-supply-entries` / `ctrl-supply-entries`
  (`K:arch/arm/boot/dts/qcom/msm8226-mdss.dtsi:145-200`: vdda L4
  enable-load 100 mA / disable-load 100 µA, vdd L15, vddio L8). MDSS
  runtime suspend drops the footswitch (`mdss_mdp.c:2960-3030,3143-3157`,
  GDSC 0xfd8c2304 = `FW:soc/msm8226.h:33 MDP_GDSCR`).
- **Vendor low-power (AOD) path**, if we ever keep the panel on: command
  panels with `qcom,ulps-enabled` (the rm69080 has it,
  `dsi-panel-auo-rm69080-hvga-video.dtsi:45`) enter ULPS
  (`msm_mdss_io_8974.c:920-1000`, lane ULPS request at ctrl +0x0ac,
  status +0xa8), clocks off, supplies stay on at the `ulp-load` values.
- **Evidence:** DSI PLL + PHY power-down **-2 mA**, MDSS CBCRs gated and
  GDSC collapsed **-1 mA** [M, SUSPEND.md §8.2]. Rails off: not measured
  (the panel in sleep-in draws ~100s of µA [I]; the LDO quiescent is the
  real question, ~0.1-0.3 mA per LDO in NPM [I, PM8226 class figures]).
- **Cost:** a full DSI PHY/PLL/controller re-init and the panel on
  sequence (`dsi-panel-auo-rm69080-hvga-video.dtsi:46-61`, reset
  `:95`) on wake, which the firmware does not have yet; the harness only
  toggled PLL/PHY registers and relied on the bootloader's state
  surviving. Stage it: (a) PLL GLB_CFG + PHY power down and re-enable
  (measured path), (b) clocks + GDSC, (c) rails.
- **Saving:** ~3 mA [M] for (a)+(b); (c) [U].
- **Measure:** per stage, 5-min windows; verify the wake path with
  `display_timeouts()`.

### F5. eMMC: sleep the card and gate SDCC1 (floor, small; awake-part)

- **Ours:** `emmc_init` enables SDCC1 AHB + APPS clocks (RCG GPLL0/3 =
  200 MHz, `FW:storage/emmc.c:166-182`), wakes the card from the
  bootloader's CMD5 sleep (`:488-500`, the bootloader "puts it to sleep and
  turns HC mode off", `:5-6`), and leaves it in transfer state with the
  clocks on for the rest of the run.
- **Vendor:** suspend puts the card to sleep (`mmc_card_sleep` or
  deselect, `K:drivers/mmc/core/mmc.c:1857-1860`), power-off notification
  when supported (`:1732-1761`); host runtime PM gates clocks 200 ms after
  the last request (`K:drivers/mmc/host/sdhci-msm.c:194,3199`) and drops
  the bus vote (`:3470-3495`); `vdd` L17 is disabled and its load set to
  0 (`:1897-1918`), `vdd-io` L6 is always-on at 250 µA LPM
  (`:1919-1927`; DT `qcom,vdd-io-always-on`, `qcom,vdd-io-current-level =
  <250 154000>`, `qcom,vdd-current-level = <800 500000>`,
  `K:arch/arm/boot/dts/qcom/msm8226-720p-mtp.dtsi:134-141`).
- **Change:** after each store access, CMD5 sleep + gate both CBCRs
  (`store.c` already re-inits via `generation`/`emmc_card()->ready`);
  L17 `swen=0` while asleep is optional (the card must be re-identified
  after VCC off, which `emmc_init` can do).
- **Saving:** eMMC standby with clock running vs sleep: ~0.2-1 mA [I,
  datasheet class; "L17 off: no effect" at the 2026-10-27 noise level].
  Confidence low on size, high on direction.
- **Measure:** 5-min window with the card in CMD5 sleep and SDCC1 CBCRs
  off vs current.

### F6. Touch controller mode (floor, small)

- **Ours:** IC left in normal operation (`FW:input/touch.c:169-230`),
  default doze, L19 + LVS1 on, attention line as MPM pin 8.
- **Vendor:** `synaptics_rmi4_suspend` (`K:drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3834-3878`):
  with wake-gesture support (`WAKEUP_GESTURE` true, `:43`; set when F11
  query 27 / F12 ctrl 27 report it, `:1756,2055,2601-2604`) it switches the
  reporting mode to wake-gesture (`synaptics_rmi4_f11_wg`, `:3470-3500`)
  and keeps power and the IRQ as a wake source; otherwise IRQ off,
  `SENSOR_SLEEP` (`:3579-3600`) and `regulator_disable(pwr_reg)` (`:3871`).
  The real watch wakes from touch in AsteroidOS ("Resume caused by IRQ
  339, synaptics_dsx", `hw/sturgeon/dmesg.txt`), so it is the wake-gesture
  branch: IC powered, in gesture doze. `synaptics,is_wake` in the DT is
  unused by the driver [V grep]. Doze interval F01_CTRL02 = 3 (30 ms) both
  at init and resume (`:54,1640,3922,3725-3750`).
- **Saving:** full-report doze vs gesture doze: ~0.1-0.5 mA [I]; the
  2026-10-27 "touch F01 sleep: nothing" was at a 120 mA baseline.
  Confidence low.
- **Measure:** 5-min window with F01_CTRL00 = SENSOR_SLEEP (upper bound on
  what the IC costs), then the gesture mode if the bound is worth it.

### F7. Sensor-hub MCU handshake (floor, unknown size)

- **Ours (main):** gpio 108 (AP status) never driven; the MCU is on an
  unswitched rail (SENSORS.md §2) and runs whatever it does after reset.
  The sensors worktree drives 108 low during cluster sleep (`hub_sleep`,
  `asteroid-embedded-sensors/src/sensors/hub.c:239-243`) like the vendor.
- **Vendor:** `mcusleep_sleep_allow()` (`K:drivers/hwmcu/hwmcusleep.c:145-167`):
  108 low, gpio 65 wake IRQ, before suspend. What the MCU does with that
  is [U] (SENSORS.md §4).
- **Evidence:** contradictory at the old baseline: "MCU reset (-4 mA)" vs
  "MCU sleep handshake / MCU reset: no effect" (SUSPEND.md §8 vs §8.1).
- **Measure:** three 5-min windows: 108 floating (now), 108 low, NRST
  (gpio 87) held low. The last bounds the MCU + IMU share; the vendor only
  ever gets the middle one.

### F8. Regulator sleep set and LDO modes (floor, small each)

- **Ours:** active-set `swen=1` for L19 and LVS1 (`FW:input/touch.c:50-53`,
  `FW:soc/rpm.c:194-198`), no `ma`/`lsmd` keys; one sleep-set request
  (CXO Enab=0, `rpm.c:227-231`); bus votes active-set only (`rpm.c:213-219`).
  Whatever the bootloader enabled is unknown and stays on (SUSPEND.md
  §3.1 default rule).
- **Vendor:** sleep set only differs for `_ao` handles (`l8_ao`,
  `s1_corner_ao`, SUSPEND.md §3.2); LDO mode via `lsmd` and load via `ma`
  (`K:drivers/regulator/rpm-smd-regulator.c:113-129`, mode mapping
  `:1163-1164`), driven by each consumer's `regulator_set_optimum_mode`
  (USB `:268-278`, eMMC `sdhci-msm.c:1832-1930`, DSI supply entries).
- **Evidence:** "sleep-set bus 0 / CX ret / MX 750 mV / LDOs off: no
  effect" [M, 2026-10-27, noisy]. Since the RPM reaches VDD min every
  cycle (§8.2, §9), CX/MX and bus clocks are already at the vendor's
  sleep level; the remaining lever is which LDOs are on and in which mode
  (NPM vs LPM quiescent, [I] ~0.1-0.3 mA each).
- **Measure first, then fix:** dump every LDO/SMPS/VS `EN_CTL` (0x46) and
  `MODE_CTL` (0x45) at 0x1x00-0x1xFF/0x4x00 over SPMI once awake and once
  from the sleep loop, diff against the vendor's suspend set (L19, LVS1,
  L6 always-on, L8/L10/L20 LPM or off per F3/F5, L3 MX, S1 CX, S2 APC off
  by SAW, S3/S4 as rails for the others), and turn off or LPM the rest one
  at a time in 5-min windows.
- Items checked and already matching the vendor: BATFET LPM 0x40 when USB
  is absent (`FW:soc/pmic.c` `usb_changed`, vendor `qpnp-charger.c:1926-1946`);
  VREF_BAT_THM forced on (0xc0) is what the vendor does too
  (`qpnp-charger.c:6082-6086`), so the §8.2 candidate "0x124a 0xc0 → 0x80"
  is not a vendor method; S2 auto mode (`pmic.c:38`).

### F9. GPIO pulls (floor, tiny)

The vendor's suspended gpiomux configs (`K:arch/arm/mach-msm/board-8226-gpiomux.c`)
pull every unused line. We configure only the pins we use; the rest are
the bootloader's. A fighting pull costs V/R ≈ 20-100 µA each [I]. Only
worth a TLMM dump (117 × `GPIO_CFG`/`GPIO_IO`) diffed against the vendor
table once everything above is done.

### F10. Per-wake work, if any tick remains (awake-part)

Linux comes out of l2-cache-pc, handles the IRQ and goes back; it does
not read the PMIC or format text. Ours per wake: a SPMI read of
`PON_INT_RT_STS` every iteration (`FW:main.c:229`, `pmic.c:49-52`) that
the PON IRQ (`pmic.c:68-86`) already makes redundant; the charger poll
with USB absent (`main.c:202`); three clock-mux switches and a PLL re-lock
(`main.c:400-411`; the vendor leaves the mux on GPLL0 after
`ramp_down_last_cpu`, L2OFF.md §1.4.2, and runs no slower than 300 MHz,
`K:arch/arm/boot/dts/qcom/msm8226.dtsi:1048-1051`); `fbcon_puts` into the
text grid (cheap, `FW:display/fbcon.c:94-109`, no present while the overlay
is on). Saving: a few ms per wake; only matters at 1 Hz, zero after F1.

### F11. BT controller: connection parameters (floor, [U])

The host-wake rate is low, so the remaining BT cost is the controller's
own connection events. Interval and slave latency are set by the phone
and only logged at connect (`FW:bt/host.c:86-88`, `:99-100`); the log has
no such line, so the values during this run are [U]. A peripheral can
request latency (`ble_gap_update_params`); BlueZ on AsteroidOS advertises
its PPCP from `hci0` defaults (30-50 ms, latency 0) and whether the
AsteroidOS 1.6 mA figure had a phone connected is not recorded. BCM43430
BLE-connected idle at 30-50 ms is of order 0.5-1 mA [I, no local source].
Measure: 5-min windows BT off / connected / connected with latency 4.

### Not a problem, or the same as the vendor

- XO shutdown and VDD min happen every cycle (SUSPEND.md §8-9), so
  GCC/MMSS clocks, GDSCs on CX, BLSP/UART/QUP clocks and bus votes cost
  nothing during the sleep part; they matter only for the awake part
  (F10). `APCS_CLOCK_SLEEP_ENA_VOTE` (0xfc401488) is never written by the
  firmware; the vendor zeroes it at boot (`K:arch/arm/mach-msm/clock-8226.c:3597-3610`).
  Read it once; if nonzero, zero it (cheap, cannot hurt).
- Verify both RPM stat records (XO shutdown and VDD min, SUSPEND.md §3.4)
  increment, not only vmin; a stuck XO buffer vote (`clka`) would show
  there [I].
- GPU: GDSC collapsed and clocks gated at sleep (`FW:gpu/a3xx.c:257-270`).
- DDR self-refresh, PMIC own consumption, RPM: same hardware state as the
  vendor's suspend once VDD min is reached.

## 6. Measurement plan

All windows unplugged (the CC freezes with USB present), 5 min each,
CC average over the whole window, compared within one boot. The sd of a
5-min mean is ~0.3 mA (§3), so 0.5 mA effects are resolvable; the
2026-10-27 null results were 10 s samples at 50-60 mA and cannot rule
out anything below ~3 mA.

**6.0 Residency vs tick (decides how much F1 is worth).** Console
command that sets the sleep tick to 1, 2, 5, 10, 30 s. Per window read:
RPM VDD-min `accumulated` (0xfc19dbd0 + 0x18, 19.2 MHz ticks) and the MPM2
sleep counter (0xfc4a3000) at start and end → residency; the APSS master
stats shutdown/bringup durations (0xfc428150 + 0x2c/0x30) → the RPM part
of each cycle; the CC average. Fit `I = floor + E × f`. The watchdog must
be stopped across the collapse for ticks > 3 s (F1).

**6.1 Per-fix A/B.** F3 (PHY LPM, then + regulator step), F4 (a/b/c),
F5, F6, F7 (three arms), F8 (per LDO), F11 (three arms), each against the
immediately preceding baseline window, best at the longest tick from 6.0
so the floor dominates and the effect is not diluted by overhead.

**6.2 Bookkeeping in the log line.** Add to the 10 s line: VDD-min
residency % since the last line, XO-shutdown count delta, the BT
interval/latency (cached from the last `conn_update`), battery mV. That
turns every future day run into data for §1.2's unexplained drift.

## 7. Open points

- E_cycle today (§2): the one number that orders F1 against F3/F4.
- `qcom,hsusb-otg-lpm-on-dev-suspend` is absent from every sturgeon DT
  file (`msm8226.dtsi`, `msm8226-720p-mtp.dtsi`, `apq8026-v2.dtsi`,
  `apq8026-sturgeon/*`) [V grep], so the vendor does not enter USB LPM
  with a host attached and suspended; only the unplugged case (F3) is
  vendor-backed.
- What the MCU does while 108 is low (SENSORS.md §4 open point).
- The BT connection parameters during long sleeps and whether the
  AsteroidOS 1.6 mA reference had a phone connected.
- Whether the APCS watchdog counts through a cluster collapse (L2OFF.md
  §5 E2); F1 stops it either way.
  Moot since main c752d86: the dog is stopped across long sleeps, as
  the vendor kernel does in suspend, after two silent resets with it
  armed (EMBEDDED.md "Silent resets asleep").

## 9. F1 result 2026-10-30 (main efae487, combined test build)

101 min unplugged, display off, untouched:

- 1-7 wakeups per minute (was 60), one cluster collapse per minute.
- BT connected (first 13 min): 7, 6, 6, 6, 6, 7, 4, 4, 4, 4, 2, 1, 2, 3 mA
  per minute, still falling, so possibly the BMS settling after charging.
- BT disconnected (phone out of range, reason 0x08 supervision timeout),
  advertising: 0 +/- 1 mA for 85 min, i.e. below the counter's 1 mA
  truncation. Not comparable with the AsteroidOS 1.6 mA figure.
- One 1401 mA sample: counter read glitch, still to explain.
- Tilt wake from cluster sleep, notification wake, palm to sleep all
  seen in the same run.

## 10. Battery level: the vendor BMS method (2026-10-30, main adb84c5)

Reimplemented from `K:drivers/power/qpnp-bms.c` (GPL-2.0, not copied) with
the sturgeon DT values (`apq8026-sturgeon-pm.dtsi` bms node) and the
HB442528EBC profiles (`HB442528EBC-{SCUD,XWD}-4v35-300mah.dtsi`): FCC 322
mAh, cutoff 3.2 V (profile overrides the node's 3.4 V), max 4.35 V, chg
term 20 mA, flat OCV 3.8 V. The two makers share the OCV table and differ
in rbatt (496/487 mOhm and the SF table); picked by the ID resistor
(VADC 0x31, 68k pull-up): this watch is SCUD (10 kOhm).

- soc = (FCC*PC(OCV) - CC - UUC) / (FCC - UUC). OCV from BMS OCV_FOR_SOC
  (0x4090) when it changes, else the last one; CC from the main counter
  (0x408a), cleared after every read and summed in software; UUC from the
  16-sample average current and rbatt, moving 1%/min at most.
- Every boot here is a warm reset (PON warm reason 0x02 = PS_HOLD), so the
  vendor path estimates the OCV from V + I*rbatt(50%) and then forces it to
  the stored SOC (BMS 0x40b0 = (soc+1)<<1, 0x40b1 = iavg) if within 50%
  (Huawei: `estimate_new_ocv_flag` is always set, so the warm-reset limit
  50 applies, not the DT's 40).
- Kept: adjust_soc below 15% (OCV pulled towards V+I*R, limited per step),
  charging_adjustments in CV, clamp to 1% while V > cutoff, the Huawei
  cutoff (0% only after 5 readings with OCV estimate < 3.25 V), the
  "voltage < 3.25 V with USB" protection, report smoothing (1% per >= 5 s,
  rises only while charging, catch-up), and the charger driver's display
  hold (no drop < 6% while plugged, 10 s after unplug, only >= 50%).
  The charger resume now uses the BMS soc <= 99 as the vendor does.
- Left out: FCC learning (disabled in the DT), SOC wake thresholds (no
  suspend in that form), the low-voltage wake lock (no shutdown at 0% yet),
  battery insertion/removal, OCV dynamic settings (not in the DT).
- ADC corrections for PM8226 v2.2 (REVID 0x102/3 = 02 02, fab 0 = GF):
  VBAT_SNS -3.5 mV; PON OCV -6.8 mV and a temperature factor only at or
  below 25 C die temperature; current: internal-rsense path (the IADC node
  has no qcom,rsense), discharge only, x 1/(1 - 33*T[mC]/1e8). The IADC
  ATE gain trim (0x36f5 = 0xc9) applies only to the external path, so not
  here.
- Battery temperature: VADC 0x30 ratiometric over GND_REF/VDD_VADC, the
  vendor's 1.8 V / 68k table (sampled every 5 C). 29-30 C on the desk.
- The average current log (`pmic_battery_avg_ua`) now reads the shadow
  counter 0x40a8, which only software clears; the main counter is cleared
  by the gauge (and by the hardware at each new OCV, which may explain the
  odd 1401 mA sample in §9).

First run: boot estimate under charge gave 92% (charging current lowers
V + I*R), then a new hardware OCV (4.3765 V) at the end of the charge gave
100% at once (soc 100 is not rate limited, as in the vendor driver).

## 10. AOD / BT split, 2026-10-31 (main df6edb7 + temporary powertest)

Automated run, unplugged, untouched apart from one accidental wake, phone
connected nearby: 30 min settle, then 15 min arms; per-arm mean of the
asleep lines, dropping the first after each sleep entry (Fable review of
the method: the CC delta is per line, no BMS settling; order is the weak
point, BT-off arms last). Log: logs-powertest-2026-10-31.txt.

| arm | AOD | BT | mean | median | wakeups/min |
|---|---|---|---|---|---|
| 0 | off | connected | 9.3 | 10 | 3.0 |
| 1 | on | connected | 9.6 | 9 | 3.2 |
| 2 | on | chip off | 4.6 | 5 | 2.0 |
| 3 | off | chip off | 2.9 | 3 | 1.0 |

- BT (link + chip standby): 5.0-6.5 mA, the largest item. The vendor's
  bluesleep keeps the UART up 3 s + 0.5 s after traffic (TX_TIMER_INTERVAL
  3, bluesleep.c:126,293), longer than our 1 s tail, so the tail was not
  shortened.
- AOD (display_rest gating, minute redraws): 0.3 (arm1-arm0) to 1.8
  (arm2-arm3); arm 2 still falling 5.2 -> 4.1 over its halves.
- Floor with BT off and AOD off reads 2.9 mA vs 0 +/- 1 mA (BT
  advertising) on 2026-10-30 (§9): either a 2-3 mA regression since
  efae487 or not comparable (battery 87 %, 24 C). Next: same arm on
  efae487, and a reverse-order repeat.
- Awake with the 90 ms mesh step (df6edb7): ~140 mA with taps, no clear
  change from 136-140 mA.

## 11. Battery run 2026-11-01: the counter and the voltage disagree (main c752d86)

sturgeon, unplugged 09:08-16:42 (7.5 h; the log covers 7.3 h of it), worn,
phone connected nearly all the time (one drop and reconnect at 11:52,
media updates while the phone played video around 15:10), AOD on,
brightness 40, tilt and tap wake off. Watchdog off across long sleeps
(c752d86): no reset, no late wake. Steps kv: 584 total. Log and
kv dump: logs-battery-2026-11-01-sturgeon.txt.

| source | what it says | average |
|---|---|---|
| asleep lines (SW_CC delta per minute, 436 lines) | mean 3.2, median 2 mA; hourly 2.6, 2.0, 1.0, 0.7, 3.7, 1.1, 11.4 (media), 3.3 | 3.2 mA |
| BMS CC (CC_DATA, summed between OCVs, 183 OCVs) | 24.7 mAh | 3.4 mA |
| BMS hardware OCV | 4.264 V -> 3.904 V, 97% -> 58% of fcc 321 mAh = ~125 mAh | ~17 mA |
| awake 18 s, IADC instant vs CC | 105-137 mA vs 70-120 mA | CC ~0.65x |

Wakeups: 2/min in 316 of 436 minutes; 7.4/min mean. Long sleeps 1289,
collapses 27092 (core) / 390 (L2).

The two counters agree with each other and with the 1.6 mA AsteroidOS
reference's method (summary item 5 at the top), but the voltage says five times more
charge left the cell, and Darrel finds the battery life short against
AsteroidOS. Open, in order of what would settle it:

- **Cell capacity.** If the CC is right, 24.7 mAh moved the OCV by 39
  points: an effective capacity of ~65 mAh, a fifth of fcc. rbatt reads
  510-750 mOhm (§10: 496/487 mOhm in the table's SF); a ten-year-old cell
  may hold far less than the profile assumes, and then the % figure (and
  the 1-day feel) is the cell, not the firmware. Test: count the charge
  into the cell over a full charge from a low OCV (the CC is frozen with
  USB present, §3, so use the charger IADC or time x charge current), or
  run AsteroidOS for the same hours from the same OCV and compare the
  OCV drop.
- **Counter under-reading.** Awake, CC averaged ~0.65x the IADC instant
  current; a gain or offset error in `iadc_comp`/`sense_uv` that grows at
  low current would hide most of a ~15 mA load. Test: a fixed known load
  (screen on at 255, `awake on`) for 10 min, CC vs IADC vs OCV slope.
- **The AsteroidOS comparison has to be voltage based too.** The 1.6 mA
  reference used the same counter, so it carries the same error, if any.
  A like-for-like comparison is OCV (or %) drop per hour on each OS from
  the same start voltage, same AOD and BT state.

Sparrow ran the same build on battery in parallel; its run is in §12 once
it is back on USB.

## 12. Sparrow battery run 2026-11-01 (main 158ad1e)

sparrow (PR3, C11N1540 380 mAh, fcc 384000 uAh), unplugged 09:28-16:49
(7.4 h) in parallel with §11, mostly lying still, phone connected (three
drops with reason 0208, reconnected each time), AOD on. No reset, no late
wake. Steps kv: 432 total. Log: logs-battery-2026-11-01-sparrow.txt.

| source | what it says | average |
|---|---|---|
| asleep lines (441) | mean -5.9, median -7 mA | 5.9 mA, sign inverted |
| BMS CC | -124.2 mAh | 16 mA, sign inverted |
| BMS SOC | 100% (made up at the end of the charge, 4.335 V) -> 45% (one hardware OCV all run, 3.825 V at 23755 s) = ~211 mAh | ~30 mA, upper bound |

- **Not a sign error: the wrong sense resistor.** Awake on battery the
  counter read +100 mA against 120 mA instant, so only the low currents
  went negative. Register diff against sturgeon: `IADC1_BMS_ADC_CH_SEL_CTL`
  (0x3848) was 0 (internal rsense) on sparrow, 1 (external) on sturgeon;
  the vendor driver moves it to external at probe when
  `qcom,use-external-rsense` (both DTs) and clears both counters
  (qpnp-bms.c read_iadc_channel_select). Fixed in 0084d42; after it
  VSENSE_AVG reads -279 mA against -292 mA instant, charging. The rest of
  0x3800/0x4000 matches sturgeon apart from Android's leftover
  OCV_THR/SW_CC_THR wakeup thresholds.
- **Only one hardware OCV in 7.4 h** (sturgeon: one every ~2 min). The
  OCV timer and S1-S3 thresholds match sturgeon's, so the likely cause is
  the same internal channel (the S3 entry is decided on the sensed
  current); to check on the next run;
  the % comes from a made-up 100% start and a single reading, so the 30 mA
  is a bound, not a measurement.
- **IT7260 idle mode is never set on battery.** With 8ed1519 the attempts
  now come on time (sleep + 5 s, then 2 s retries, last at sleep + ~11 s),
  but every one gets -2 (no ACK): the chip has already put itself to sleep.
  Each wake sets the active mode at once (0, try 0). Whether the chip's own
  sleep is as cheap as the idle mode is not known.
- Hub: one wrist tilt, no restart, no fatal error.

Next for sparrow: repeat the battery run on 0084d42 and check the OCV
rate and the counter against the OCV drop.

### 12.1 sturgeon counter while charging (2026-11-01 evening)

Charging awake: instant -148 mA, CC average -149 mA; asleep, CC -158 mA
and iavg -159. From the 3.904 V OCV (58%) the CC counted 64.7 mAh in by
80% and the charge was still at ~150 mA, so the cell holds well over the
~65 mAh the §11 'cell capacity' reading needed: that explanation is out.
The counter is right at -150 mA and reads a fifth of the voltage drop
over a sleeping day, so the open question is what it misses while the
watch sleeps (a path around the sense resistor with the BATFET in LPM,
0x1293 bits 7:6 = 01 on unplug as the vendor charger does; or the BMS's
low-power sampling). Whatever it is applied to the 1.6 mA AsteroidOS
figure too, which came from the same counter. The full-charge count is in
the next entry.

### 12.2 sturgeon full-charge count (2026-11-01, 16:43-17:53)

From the 3.904 V OCV of the §11 run the CC counted 99.9 mAh in up to 95%
(gauge), when an adb reboot (another session flashing the rotate build)
restarted the counters; after it, from a 4.221 V OCV, 15.3 mAh more to the
end of charge (4341 mV, -19 mA). So 3.904 V to full took ~116 mAh. The
profile puts 3.904 V at ~58%, which makes the cell ~275 mAh (86% of the
321 mAh fcc): a usable cell, not a worn one.

The §11 discharge, 97% -> 58% on the same scale, is therefore ~105 mAh in
7.3 h, ~14 mA average, while the CC counted 24.7 mAh. **The CC is right
charging (and awake: -148 vs -149 mA) but misses about three quarters of
the charge while the watch sleeps on battery.** Every asleep figure in
§9-§11, and the 1.6 mA AsteroidOS reference, came from that counter.
Candidates: the BATFET LPM set on unplug (`pmic.c` usb_changed, 0x1293
bits 7:6 = 01), if part of the load then bypasses the external sense
resistor; or the BMS's low-power sampling losing low currents. Test:
unplugged, asleep for 30 min with 0x1293 left at 00, CC against OCV drop.

## 13. The asleep counter error was the IADC offset trim (2026-11-01, main 1c7378a)

- **BATFET LPM is not it.** 30 min arms on sturgeon, LPM on/off/on/off
  (0x1293 = 40/00): CC 1.9-2.3 mA in every arm, OCV slope 13-21 mA in
  every arm (the first arm, straight off the charger, is surface charge).
  Log: logs-batfet-lpm-2026-11-01-sturgeon.txt.
- **The trim was stale.** The BMS counters take their zero from the IADC
  offset trim at 0x36F2/F3, which the vendor's qpnp-adc-current.c
  (calibrate_for_trim) rewrites at probe and every 300 s from a shorted
  input conversion (channel 5). The firmware never wrote it. sturgeon:
  live offset 0xBBCA, stored 0xBBBF (11 counts, ~6 mA by the IADC
  scale, in the direction that hides discharge). sparrow: 0xBB08 against
  0xBB0A.
- **With the trim rewritten (1c7378a)** sturgeon's asleep lines read
  12-16 mA (30 min unplugged, phone connected, AOD on), against 2-3 mA
  before and the 13-21 mA OCV slopes: the counter and the voltage now
  agree. Log: logs-iadc-trim-2026-11-01-sturgeon.txt. That the effect is
  larger than the 6 mA estimate suggests the low-current (S2/S3)
  sampling depends on the trim more than the IADC scale does.
- So the real asleep current with AOD and a phone link is ~13 mA, not 3,
  and the 1.6 mA AsteroidOS figure (same counter, its own trim, in
  suspend) can't be compared until it is re-measured. Everything in
  §9-§11 that came from the counter is low by roughly 10 mA.

Sparrow under AsteroidOS (same session): 0x3848 = 1 (external rsense, as
0084d42 now sets), trim rewritten by the driver (0xBB02 -> 0xBB04 over the
run), BMS thresholds identical to ours, r_sense 10000 uOhm in its probe
log (83572ad makes that a board setting; the firmware used 9700). Its
OCV register did not change in a 32 min unplugged suspend either, so
sparrow's missing hardware OCVs are not a firmware bug. The run itself
gave no current: it went onto a wall charger halfway, and the charge
counter only has the two end points.

## 14. DSI PLL off between AOD frames (2026-11-02, branch aod-display-rest 1c686b1)

The AOD comparison with the vendor kernel (end of the 11-01 session):
between always-on frames `display_rest()` gated the DSI and MDP clocks
but left the DSI PLL, the MDSS AHB clock, the DSI PHY and the MDSS GDSC
on. Stage A (1c686b1) turns the PLL off (GLB_CFG 0xfd922a20 = 0) and gates
AHB at every rest, and the PHY (0xfd922c70 / 0xd98 = 0) only while the
panel sleeps, as the vendor keeps it on under ULPS for AOD.

- **PLL power-up:** the sequence must be msm8226's own,
  `dsi_vco_clk_8226` in `K:arch/arm/mach-msm/clock-mdss-8974.c:1652`
  (seq M x2 with 7 PWRGEN retries, D x2, F1, C, E). The 8974/28hpm one in
  `K:drivers/clk/qcom/mdss/` (not used on 8226) failed to lock about one
  redraw in three on both watches: byte/pclk stuck off, the frame lands
  offset on the panel. The PLL registers were not lost across the
  software reset. With the 8226 chain: no failure and no retry in 6.8 h.
- **Measurement (sturgeon):** overnight `powertest 15 25 dsi` (harness
  knob, ABBA, BT off, AOD on), 16 arms of 25 min, first 2 min trimmed.
  PLL off 8.71 ± 0.18 mA (n=8), PLL on 8.85 ± 0.20 mA (n=8): difference
  -0.14 mA, 2 SE 0.54, so **below the MDD**. OCV slopes ~-32 mV/h agree
  with ~9 mA. Log: logs-dsi-rest-2026-11-02-sturgeon.txt, analysis
  tools/powerlog.py.
- So the 10-27 "DSI PLL/PHY off -2 mA" (screen off, pre-trim counter)
  does not carry over to the AOD rest: in VDD min the PLL's reference
  is gone anyway. The AOD-off case (PHY off too) is not measured yet.
- Asleep total with AOD on and BT off: ~8.8 mA on sturgeon (vs the 12-16
  mA with a phone link in §13).
- **Sparrow:** functionally fine overnight (log ring kept arms 10-15
  only). Its counter reads -3..0 mA while the OCV falls ~30 mV/h, so the
  sparrow CC is still wrong. It did take 58 hardware OCVs overnight,
  unlike the 11-01 runs (§12/§13). Log: logs-dsi-rest-2026-11-02-sparrow.txt.

## 15. MDSS power collapse between frames (2026-11-02, aod-display-rest ac097aa)

Stage B (ac097aa) collapses the MDSS GDSC between frames as the vendor's
idle power collapse does (`K:mdss_mdp.c:2960` footswitch with
`idle_pc`, 50 ms autosuspend; msm8226-mdss.dtsi enables it).

- **What a collapse needs:** after the GDSC comes back, every MDSS register
  read hangs until TZ restores the display SMMU's secure config
  (buffer-based SCM, SVC_MP 0x0c cmd 2, device 1), with MDSS AHB and AXI
  on (calling it with the clocks off hangs too). A diff of the register
  space across a collapse showed ~150 registers reset (VBIF, MDP top/SMP/QoS,
  CTL0, RGB0, LM0, INTF1, PP0, DSI PLL, PHY, controller); `kept_regs` in
  display.c saves and rewrites them. For AOD the PHY is clamped (MMSS misc
  0xfd828014 bits 9/8/5/4 + 15, phy reset hold +0x108), which needs
  MMSS_MISC_AHB_CBCR on or the write hangs. Reading VBIF past ~0x580 hangs.
- **Measurement (sturgeon, AOD on, BT off):** day run, 24 arms of 25 min,
  mirrored collapse/pll/old/old/pll/collapse. Paired within 4 blocks:
  collapse - old -0.08 mA (2 SE 0.63), pll - old -0.26 mA (2 SE 0.74).
  Pooled: collapse 8.64, pll 8.64, old 8.90 mA. **Neither is above the
  MDD.** With the overnight PLL result (§14) the AOD rest's DSI/MDSS
  share is < ~0.5 mA. Log: logs-mdss-collapse-2026-11-02-sturgeon.txt.
- **Sparrow (AOD off):** 10 h without an error, but the arms compared
  nothing: with the screen off nothing redraws, and the harness only
  applied a new level at the next rest, so sparrow most likely stayed
  collapsed all day (Codex review). The harness now re-rests the display
  hardware on a level change (`display_set_rest_level`, console `rest`).
  Its counter is unusable as in §14 anyway. Log (arms 13-23):
  logs-mdss-collapse-2026-11-02-sparrow.txt.
- So the 10-27 "DSI PLL/PHY -2 mA, GDSC -1 mA" do not hold for the
  asleep state with a trustworthy counter. The asleep total with AOD and
  BT off is ~8.7-8.9 mA; the screen-off case on sturgeon is not measured.

Sparrow's counter (2026-11-02): Darrel sees the same wrong readings on
AsteroidOS, so it is not a firmware regression; power work continues on
sturgeon only.

## 16. Screen off: the floor is drawn in VDD-min (2026-11-02, aod-display-rest ac097aa + harness)

`powertest 15 25 dsi` with AOD off and BT off, one complete mirrored round
(arms 0-5; arm 6 cut short by the plug-in), with the rest level now
applied while resting (`display_set_rest_level`).

| rest | arms | CC mA (BMS cc, between OCV resets) |
|---|---|---|
| collapse | 0, 5 | 6.54, 7.46 |
| pll off | 1, 4 | 6.38, 6.31 |
| old | 2, 3 | 6.42, 7.50 |

- Paired in the round: collapse - old +0.04 mA, pll - old -0.62 mA. One
  round resolves ~0.6-0.8 mA, so neither is a detected effect.
- **RPM VDD-min residency 99.97% in every arm**, ~4 VDD-min entries a minute
  (new per-minute `power: vmin` line). The ~7 mA screen-off current is
  therefore almost all drawn while the SoC sits in VDD-min: wake overhead
  is negligible, and the remaining load is outside the APSS (peripherals,
  regulators, their sleep votes). That is what ASTRA-POWER.md's U/R/H/E/T
  experiments target.
- AOD costs ~1.9 mA (8.8 mA with AOD in §15 vs ~6.9 mA here, BT off both).
- Log: logs-screen-off-2026-11-02-sturgeon.txt.

## 17. Sleep measures, leave-one-out (2026-11-03 overnight, harness a909d0c)

`powertest 15 13 sleep`, AOD off, BT off, 13 min arms, 2 complete 14-arm
cycles plus 6 arms (7.6 h unplugged). Every arm applied what its label
says (want = have), VDD-min residency 99.9% in every arm. Shadow-counter
current, gap-free, 11 retained minutes per arm (tools/powerlog.py).

Saving of each measure with the other four on (mean of the two arms
without it minus the mean of the two all-on arms, per cycle):

| measure | saving | per cycle |
|---|---|---|
| U USB PHY low power (PHCD + STP) | **+4.2 mA** | +4.5, +3.9 |
| T touch sensor sleep (RMI4 F01) | +0.8 mA | +0.7, +0.8 |
| E eMMC sleep + SDCC1 clocks off | +0.7 mA | +1.0, +0.4 |
| R bus clock sleep votes (GCC vote already 0) | +0.5 mA | +0.5, +0.5 |
| H hub held in reset | -0.2 mA | +1.0, -1.3 |
| bundle: none - all | +3.7 mA | +3.5, +3.8 |

- All on: ~3-4 mA; none: ~7-9 mA (matching §16's ~7 mA screen-off floor).
- Two cycles only: the 2 SE from two values is not a real uncertainty. U is
  clearly large; T, E and R are probably real but small; H is unresolved.
- U alone exceeds the bundle, so the parts are not additive (the measures
  interact, or arm-to-arm noise of ~0.5-1 mA).
- RPM stats records (read 2026-11-03): 0xfc19dba0 is `xosd` (XO shutdown),
  0xfc19dbd0 `vmin`. The RPM counts the deepest mode entered, so `xosd`
  stays 0 while every sleep reaches `vmin`: not evidence of XO staying on.
- USB LPM still has no clean exit (the host does not re-enumerate); the
  harness reboots on plug-in. A real feature needs the vendor resume path
  (ASTRA-POWER-2.md §2).
- Log: logs-sleep-loo-2026-11-03-sturgeon.txt.

## 18. Rails on top of the sleep measures, and the trim noise (2026-11-03 day run)

`powertest 15 13 floor`, AOD off, BT off, 11.5 h unplugged; the log ring
kept arms 14-44 (one and a half cycles). B = the five sleep measures of
§17 (USB now rests through the real unplugged collapse in usb.c).

- **The counter follows the IADC trim: +0.52 mA per trim LSB, r = 0.94**
  over 160 baseline minutes. The firmware rewrites the trim every 5 min
  from one offset conversion, which wanders over ~bbce-bbdc (about ±5
  LSB), so the reading steps by up to ±2.5 mA at each rewrite. Raw
  baseline arms spread 2.4-7.6 mA; corrected to one trim (bbd3, the mean)
  their sd drops from 1.9 to 0.34 mA. This also explains the steps
  within arms noted in ASTRA-POWER-3.md. A fix belongs in the firmware
  (average several offset conversions, or filter the trim).
- Trim-corrected, each measure against its neighbouring B arms:

| measure | saving | per pair |
|---|---|---|
| V USB rails L10/L20 off | +0.24 mA | +0.34, +0.28, +0.10 |
| Q touch rail L19 off | +0.11 mA | +0.10, +0.07, +0.17 |
| M L4/L6 low-power sleep votes | -0.05 mA | -0.18, +0.07 |
| all three (ABBA) | -0.01 mA | -0.05, +0.03, 0.00 |

- So the rails add little: at most a few tenths of a mA, and the ABBA
  shows none. Baseline B is ~4.3 mA at trim bbd3; the absolute value
  moves 0.5 mA per LSB with whichever trim is right.
- Sleep-set low-power votes for L8 (also the CPU PLL supply) or L19 reset
  the chip with no record; M covers L4/L6 only. The TFA9895 is already
  powered down at idle (reg 0x09 = 0x0265, bit 0 set), so A was dropped.
- Log: logs-floor-2026-11-03-sturgeon.txt.

**Correction to §18 (ASTRA-POWER-4.md, checked):** `usb_next_ms()` in the
run's build returned 1 when no USB deadline was pending
(`(int32_t)UINT32_MAX < 0`), so the watch woke every second all day: 60
VDD-min entries a minute instead of ~5, residency 99.0% instead of 99.9%.
That inflates every arm alike (Astra estimates ~0.2-1 mA), so B ~4.3 mA is
not a sleep floor yet. With time-weighted trim correction the contrasts
shrink further: V +0.17, Q +0.02, M +0.07, all three ABBA +0.00 mA; only
the USB rails keep a small positive sign. The vendor IADC driver also
calibrates from one unaveraged conversion every 300 s (and, per its DT,
from channel 6, not 5), so there is no vendor filter to copy; the
measured slope within arms (0.551 mA/code) is close to the nominal 0.559.

## 19. Floor with the fixes in (2026-11-04 overnight, 2751917 + 1f29a3e + harness 62832a5)

`powertest 15 13 floor`, AOD off, BT off, 10 h unplugged, whole log kept
(settle + arms 0-44, 2.25 cycles). Gate first (ASTRA-POWER-4.md): a
1-minute rehearsal passed every transition. USB rests through the
committed unplugged collapse; no 1-second wakes (5-6 VDD-min entries a
minute, residency 99.8-99.9% in every arm); the trim now comes from 64
conversions and ranged bbd2-bbda asleep (time-weighted ~bbd7), rising as the
watch cooled.

- **Baseline B (the five sleep measures): 4.70 mA** over 23 arms, every
  arm 4.2-5.0 mA without any trim correction.
- Each added measure against its neighbouring B arms:

| measure | saving | 2 SE | per pair |
|---|---|---|---|
| V USB rails L10/L20 off | +0.09 mA | 0.18 | +0.21 +0.37 -0.06 -0.12 +0.06 |
| Q touch rail L19 off | -0.07 mA | 0.26 | +0.06 -0.02 +0.08 -0.57 +0.12 |
| M L4/L6 low-power sleep votes | -0.09 mA | 0.24 | -0.11 +0.01 -0.42 +0.14 |
| all three (ABBA) | +0.25 mA | 0.16 | +0.33 +0.04 +0.23 +0.41 |

- So none of the rail measures is worth implementing on its own; the
  remaining ~4.7 mA is elsewhere (ASTRA-POWER-4.md §4: the panel's full
  off sequence, the hub's sensors, CX/MX sleep votes, DDR).
- The absolute value rests on the asleep trim (bbd3); plugged in the trim
  reads ~bbc2-bbc5 (13-18 codes lower), so it is state dependent.
- Harness note: with no measures applied the harness keeps USB up, so
  during the settle USB was up; it rested when arm 0 applied U.
- Log: logs-floor2-2026-11-04-sturgeon.txt.

## 20. AsteroidOS on sturgeon, screen off, by the same counter (2026-11-04)

AsteroidOS booted with `fastboot boot backup/sturgeon/boot-asteroidos.img`;
`tools/aos-powerlog.sh` as a systemd unit, logging the BMS
`charge_counter_shadow` property (uAh, Linux's accumulated value) on every
USB change and every 600 s awake. This kernel's RTC has no wakealarm, so
the unplug and the replug are the samples. AOD off needs both dconf keys
(`/org/asteroidos/settings/always-on-display`,
`/desktop/asteroid/nightstand/always-on-display`) besides mce's low power
mode; BT off.

- Unplugged 3944 s at ~94-100%, 24 -> 17 C: shadow +2285 uAh, **2.1 mA**
  by the endpoints. VDD-min entries rose 32 -> 296.
- The samples in between do not add up: -29 uAh (14 min), -399 uAh
  (16 min, i.e. charging while unplugged), +2275 uAh (30 min, 4.5 mA),
  +438 uAh (6 min, 4.6 mA). Linux's trim moved bbce -> bbdb as the watch
  cooled; its accumulated counter is not a clean integral across that.
  So 2.1 mA is indicative, roughly +-1-2 mA.
- An earlier 8 min rehearsal with AOD on gave ~2.4 mA (first minutes after
  unplug).
- Compared with the firmware's 4.7 mA (§19, 18-20 C, trim bbd2-bbda): the
  gap is likely real, ~2-3 mA, but needs a longer AsteroidOS run to pin
  down. AsteroidOS does not wake every minute (the firmware's stats line,
  BMS calc every 20 s), worth ~0.1-0.2 mA of the gap.
- The firmware run shows the trim rising ~8 codes as the watch cooled
  overnight while the measured current stayed flat: the trim follows a
  real temperature-dependent offset.
- Log: logs-aos-screenoff-2026-11-04-sturgeon.txt.

**Correction to §20 (ASTRA-POWER-6.md):** the last 35.8 min of the AsteroidOS
run (after it had cooled) read **4.55 mA**, close to the firmware's 4.70; the
2.1 mA endpoint average is dragged down by the cooling stretch, so the
"likely 2-3 mA gap" is not supported. Linux's shadow property is still the
right value (accumulated plus raw, with gain/temperature compensation), but
offset error while cooling distorts short stretches. The RTC driver does
implement wake alarms (it only lacks the sysfs file), so a systemd timer
with WakeSystem=true should give periodic samples; to be rehearsed.

**AsteroidOS day run (2026-11-04, ASTRA-POWER-7.md):** 11.0 h unplugged, screen and
AOD off, BT off, tilt-to-wake off, systemd WakeSystem timer sampling every ~302 s
(works). Settled: 3.07 mA mean over 125 intervals (3.09 endpoint-integrated),
~4 VDD-min entries/min, 22.4 -> 18.5 C. Per Linux trim: bbd6 1.45, bbd9 2.80,
bbdc 4.33 mA (0.48 mA/code). Both write the same trim register, so at the
firmware's time-weighted trim (~bbd7.3) AsteroidOS reads ~2.0 mA against the
firmware's 4.70: an apparent gap of ~2.7 mA. Equal trim cancels the programmed
offset but not any state/temperature difference in the analogue zero, so this is
strong evidence, not proof. Snapshot (plugged in): panel rails L4, L8, L15
disabled with the screen off; touch doze_cycle 8, wake_gesture 1, L19 on.
Logs: logs-aos-2026-11-04/.
Battery state differs: the AsteroidOS day run went 96 -> 87% (4.25-4.30 V at
the start), the firmware §19 run 88 -> 80% (4.19 -> 4.03 V). Both logs carry
the percentage and voltage per sample; a higher battery voltage means slightly
less current through the regulators for the same load (a few percent, ~0.1 mA),
which favours AsteroidOS a little.

**Register diff, firmware vs AsteroidOS (2026-11-04, logs-aos-2026-11-04/fw-regs.txt
vs snap/aos-snap-1793824759.txt).** Firmware read plugged in, screen off, B
measures; AsteroidOS read after a timer resume, unplugged. All MMSS GDSCs are
collapsed on the firmware too, and the hub UART, LPASS AXI and USB PHY sleep
clocks are off, so the "bootloader-left domains" candidate is dead. LDOs on
under the firmware but off under Linux: L4 and L15 (panel, HPM), L20 (USB;
plugged here), and **L18 and L21 in HPM: the SDC2 (microSD) vdd and vdd-io
rails, whose controller sturgeon's DT disables** (apq8026-sturgeon-common.dtsi:80).
Something before the firmware (aboot or lk2nd) turns them on and nothing
turns them off. Linux has L11 on in LPM where the firmware has it off; L17 is
in LPM on the firmware (eMMC asleep) and HPM in the awake Linux read.

**Nightstand AOD in the earlier runs (2026-11-04).** The harness runs were armed
on the charger, and the watch went to sleep there: always-on was then picked
with nightstand.aod (1), not aod (0), and kept after the unplug (fixed in
84fbbe3). The floor runs (§19 and before) went to sleep plugged in and were
unplugged later without a wake, so they most likely ran with the AOD face on;
the frames are not logged, so this is inferred. The 4.70 mA "screen off" floor
and the 2.7 mA gap to AsteroidOS are therefore suspect. Rehearsal with AOD
really off (logs-night-rehearsal-2026-11-04.txt, 1-minute arms): B read 2.1-3.1
mA at trims bbc9-bbd0; every arm reached want = have, P entered and left deep
standby, S turned the hub services off. The night run re-measures the floor.

## 21. Night run with AOD really off (2026-11-05)

`powertest 15 30 night`, 8.6 h unplugged, B D D B B P P B B S S B B D D B B
(the schedule wraps), 99.94% VDD-min, no resets, want = have in every arm.
Logs: logs-night-2026-11-05-sturgeon.txt. First 3 minutes of each arm dropped.

| Arm | mA (mean of arms) | Trim-adjusted vs B |
|---|---|---|
| B, five measures | 2.74 (9 arms, 2.53-2.96) | - |
| D, SD rails L18/L21 off | 2.88 (4 arms) | +0.12 to +0.25 |
| P, panel deep standby | 2.72 (2 arms) | -0.20, +0.16 |
| S, hub running, services off | 2.54 (2 arms) | -0.33, -0.13 |

The floor is about 2.7 mA at trims bbd1-bbd9, not 4.70: §19 had the nightstand
AOD face on, so AOD costs about 2 mA. D and P save nothing measurable; S shows
a hub asleep with its services off costs no more than one held in reset.
Trim rose with cooling (27 -> 17.5 C) at only ~0.05 mA/code within this run, far
from the 0.5 mA/code seen across plug states, so that slope does not carry over
to a slow drift. BMS OCV fell 9.2 mV/h (§19: ~14, AsteroidOS: ~7).
Against AsteroidOS (3.07 mA raw) the gap is not established precisely: at this
run's trim (bbd6.1) the conditional 0.48 mA/code slope gives Linux ~1.4 mA, an
apparent ~1.3 mA gap (ASTRA-POWER-10.md); raw, the firmware reads lower. 2.7 mA is
also the BT-off, tap-off, hub-in-reset baseline, not a production floor. Goal:
the firmware must not use more than AsteroidOS, so this stays open.

**Rails the RPM does not know about (2026-11-05).** An off vote alone leaves
L4, L15 (and so likely L10, L20) on: the bootloader enabled them itself, so the
RPM sees no change. It only drops the mode (80 80 -> 00 80). Vote on, then off,
as Linux does; and give the voltage, or the RPM restores them at its minimum
(L4 1.15 V, L15 2.75 V instead of 1.2/2.8). So the earlier V results (rails add
nothing) probably never switched L10/L20 off. L18/L21 did go off with one vote.

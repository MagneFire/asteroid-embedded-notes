<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

Minnow's gauge, charger and thermal values are all in the vendor tree, but the factory-kill line and the USB path have open questions (items 5 and 4). A few places where I'm inferring are marked "uncertain". Nothing was modified and no device was touched.

## 1. Gauge models

**Mapping.** DT `tcompc0` is written to register 0x39, which is our `MAX17050_TEMPCO`, so it goes into our field `tempco`. The vendor reads DT properties `qrtbl00/10/20/30` into `qrtbl[0..3]`. Our register addresses (0x12, 0x22, 0x32, 0x42) match the vendor's.

**Where it lives.** `omap3-minnow.dtsi`, node `max17050@36` on `&i2c3`: default profile at 383, LG at 417, Lishen at 450, `temp-conv` at 483. Common to all three: version 0x0001, config 0x6254, full_soc_thresh 0x5F00, ichgt_term 0x0066, learn 0x2606, filter 0x87A4, tgain 0xE71C, toff 0x251A, fullcap and fullcapnom 662.

**Default profile** (`maxim,configuration`) and **LG** (`-SNN5951A`) differ only in `relax_cfg`. Both have `design_cap` 606 while fullcap is 662, copied exactly from the DT.

```c
#define MINNOW_CELL_LG 0x9cf0, 0xa310, 0xb180, 0xb360, 0xb6a0, 0xb6e0, 0xba10, 0xbb10, 0xbbd0, 0xbc10, 0xc200, 0xc250, \
  0xc7c0, 0xc820, 0xd050, 0xd710, 0x0140, 0x0110, 0x0210, 0x02c0, 0x1000, 0x0a00, 0x06c0, 0x31a0, \
  0x0af0, 0x1170, 0x0cb0, 0x08d0, 0x0aa0, 0x0880, 0x07b0, 0x07b0, 0x0100, 0x0100, 0x0100, 0x0100, \
  0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100, 0x0100

/* default: used when /chosen has no batt-id */
{ .config=0x6254,.learn_cfg=0x2606,.filter_cfg=0x87a4,.relax_cfg=0x043b,.full_soc_thresh=0x5f00,
  .design_cap=606,.fullcap=662,.fullcapnom=662,.ichgt_term=0x0066,.rcomp0=0x0052,.tempco=0x333a,
  .qrtbl={0x1b94,0x0e94,0x0594,0x0294},.tgain=0xe71c,.toff=0x251a,.version=1,.cell={MINNOW_CELL_LG} }
/* SNN5951A (LG): same, but .relax_cfg=0x203b */
```

**Lishen** (`-SNN5950A`):
```c
{ .config=0x6254,.learn_cfg=0x2606,.filter_cfg=0x87a4,.relax_cfg=0x203b,.full_soc_thresh=0x5f00,
  .design_cap=662,.fullcap=662,.fullcapnom=662,.ichgt_term=0x0066,.rcomp0=0x003c,.tempco=0x231c,
  .qrtbl={0x069a,0x0398,0x0298,0x0296},.tgain=0xe71c,.toff=0x251a,.version=1,
  .cell={ 0x9f80,0xa030,0xb220,0xb440,0xb890,0xb910, 0xba10,0xba40,0xbf10,0xbf60,0xc2d0,0xc5e0,
          0xc640,0xcc90,0xd520,0xd780,0x05d0,0x00e0, 0x01e0,0x03a0,0x08e0,0x1000,0x4000,0x1670,
          0x23d0,0x0df0,0x0a70,0x0aa0,0x06f0,0x0790, 0x06b0,0x06b0,
          0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100,0x0100 } }
```

**Compared with smelt:** config is 0x6254 here and 0x4254 on smelt (bit 13, the temperature sticky-alert enable, is the extra one). smelt's version is 0x0002 and minnow's is 0x0001.

**batt-id selection** (`max17042_battery.c:131-147`, `1052-1090`):
- The kernel reads the string property `batt-id` on `/chosen`, supplied by the bootloader.
- It looks for the child node `maxim,configuration-<batt-id>` with the string appended verbatim, so the values are exactly `SNN5951A` (LG) and `SNN5950A` (Lishen).
- If the property is absent, it uses `maxim,configuration`.
- If the property is present but names no node, config_data is NULL ("config data is missing") and no model is loaded at all. The `max17042_new_config_data()` check at 1365 would also dereference that NULL pointer.
- No example value is visible anywhere. In `boot_issue/wearos-dmesg.log:215-216` and `working-journal.log` the kernel prints "get_dts_batt_id: batt-id len <garbage>" and "using maxim,configuration profile". So on these units, with bootloader MINNOW0954, the property is absent and the default profile runs.
- I found no battery-ID resistor code in the kernel; the bootloader would do that.

## 2. temp-conv table

The table starts at -20 and has 84 entries (-20 to 63 °C). The result is in 0.1 °C.

```
-302,-271,-246,-222,-202,-180,-162,-147,-129,-114, -101,-86,-72,-59,-48,-35,-23,-12,-2,10,
22,32,42,51,62,72,82,91,99,110, 120,129,138,146,156,165,175,184,192,200,
210,220,230,238,247,256,266,275,285,294, 303,313,324,333,343,353,364,375,385,395,
407,419,430,441,453,466,479,492,505,520, 534,548,565,581,597,616,635,654,676,697, 721,747,775,800
```

This table is identical to the `temp_real[]` in our `src/soc/max17050.c`, so no change is needed. `max17050_decidegrees` also matches the vendor's `max17042_conv_temp` (`max17042_battery.c:197-221`):
- The input is `raw_s16*10/256` in 0.1 °C, truncated toward zero.
- The index is `t/10 - start`, minus one more if `t<0`.
- If the index is below 0, it returns `r[0]`. If it is at or above `n-1`, it returns `r[n-1]`, so the clamp ends are -30.2 °C and 80.0 °C.
- Otherwise it interpolates linearly: `r[i] + (r[i+1]-r[i])*dt/10` with `dt = t-(start+i)*10`, using integer division truncated toward zero.
- The temperature property is used by userspace healthd.
- Current: the vendor uses `raw*(1562500/rsns)`, which is 156 µA per count at 10 mΩ. We use 156.25. The difference is negligible.

## 3. Init and POR sequence versus `gauge_max17050.c`

**When init runs.** The vendor kernel (`max17042_battery.c`) runs it in four cases:
- At probe if STATUS.POR (bit 1) is set, or if register 0x20 (CONFIG_VER) differs from the profile's `version` (1493-1498).
- When the "malicious supply" `ac` goes offline (1281-1301, 865-884). `ac` is the TUSB PHY's power supply (`phy-tusb.c:367`, MAINS type, online equal to the level of the VBUS gpio 142). On USB removal it does a soft POR and then the full init again.
- From `max17042_perform_soft_POR` (536-580): lock the model, clear POR, check MLOCK1, then write 0x000F to register 0x60, wait 2-4 ms, and check POR is set (up to 8 retries).
- The vendor's lock check reads MLOCK2 twice and never checks STATUS, which looks like a vendor bug.

The soft POR on `ac` removal is the vendor's answer to the gauge being fed from the USB-powered rail. Healthd logs `v=4866` mV on USB in `wearos-dmesg.log:548`, above any Li-ion cell voltage, so the gauge's VCELL was probably not seeing the cell. Learned values from that period are discarded. Uncertain: that this is the actual rationale.

**Our code** only checks POR at init and every 30 s (`model_check`). It has no CONFIG_VER check and no re-init on USB removal. On minnow you probably want "VBUS fell, then soft POR, then `model_load`".

**The init sequence itself** (`max17042_battery.c:736-789`). Ours matches except where marked:

| Step | Vendor | Ours |
|---|---|---|
| Override block | Writes only non-zero fields: TGAIN, TOFF, CONFIG (valrt/talrt/salrt, cgain and the rest are zero in the DT and skipped) | Also writes 0x01=0xff00, 0x02=0x7f80, ICHGTERM, DESIGNCAP, LEARN, FILTER, RELAX, FULLCAP, FULLCAPNOM. Harmless extras. |
| Settle | msleep 500 | wait_ms 500 |
| Config registers | CONFIG, LEARN, FILTER, RELAX, FULLSOCTHR | Same |
| Model | Write 0x59/0xC4 to 0x62/0x63, write 48 words at 0x80, read back and compare, lock with 0/0 | Same. The vendor's `memcmp(...,size)` counts bytes, so only 24 words are really compared (line 476). Ours compares all 48. |
| Lock check | All 48 words must read 0, otherwise -EIO and no retry (`init_complete` stays 0 forever) | Same check; ours leaves POR set and retries at the next poll |
| Custom registers | RCOMP0, TEMPCO, ICHGTERM, QRTBL00/10/20/30, each write-verified with 8 retries | Same |
| Capacities | FullCAP verify; **DesignCap = fullcapnom**; FullCAPNom verify | Writes `design_cap` here. The last write is `design_cap` in both, so no net difference. |
| Wait | msleep 350 | wait_ms 350 |
| VFSOC0 | Read VFSOC (0xff), write 0x80 to 0x60, verify VFSOC0 (0x48), write 0 to 0x60 | Same |
| Cycles | 96 (0x17) for the 17047/50 | Same |
| Capacity seed | RemCap = (vfsoc>>8)*fullcapnom/100, RepCap the same, dQacc = fullcap/16, dPacc = 0x0C80, FullCAP, DesignCap = `design_cap`, FullCAPNom, RepSOC = vfsoc | Same |
| Finish | Clear STATUS bit 1, write CONFIG_VER (0x20) = version | Same |

**Alert setup (vendor only, `1468-1490`):**
- Write SALRT (0x03) = 0xFF00 and clear SMN/SMX in STATUS.
- Request the IRQ on a falling edge, with the handler using IRQF_ONESHOT.
- Set CONFIG bit 2 (ALRT enable), which 0x6254 already has.
- Program the SOC window to ±1%. The window is `(soc+1)<<8 | soc`.

Ours does none of this.

**Learned-value persistence:** the kernel does none. There is no save or restore of FullCAP, RCOMP or the cycle count. The only persistence is userspace healthd reading `battery_age` and `cycle_count` and keeping `/pds/battery/age.txt` and `previous-age.txt` for logging. Ours also persists nothing.

## 4. bq5105x

**Detect driver** (`drivers/misc/bq5105x_detect.c`): two input gpios, `GPIOF_IN|GPIOF_EXPORT`.

**Truth table** (header 41-44, new hardware; the DT does not set `old-hw`):

| Situation | gpio176 (chg) | gpio22 (det) |
|---|---|---|
| Docked, charging | high | high |
| Docked, not charging | low | periodic high pulses; may stay high for a while after charging stops |
| Not docked | low | low |

The DT flag 0x1 on detect-gpio is ignored, because `of_get_named_gpio` drops flags. The "active low" comment in `MINNOW.md:75` is misleading.

**Logic** (`269-362`):
- chg is edge-triggered on both edges; det is falling-edge only.
- chg high: immediately mark docked and disable the det irq. No debounce.
- chg low: enable the det irq. If det is low at that moment, start a 1500 ms alarm. If det is high, wait for a det falling edge.
- Each det falling edge cancels the alarm. If an alarm was pending, it reports docked. Either way it restarts the 1500 ms alarm.
- If the alarm expires, it reports undocked.
- So undock is reported only after about 1.5 s with no pulse while chg is low. The pulse period must be under 1.5 s (exact period unknown).

**Supplies.** The detect driver registers a power supply named `wireless`, type WIRELESS, with ONLINE equal to `reported_docked`. That means "on the pad", regardless of whether charging. It is supplied_to `max170xx_battery`. It also toggles a `dock` switch.

**USB.** USB is a separate supply, `ac` (MAINS), whose ONLINE is the raw level of gpio 142 (`tusb-irq`). The TUSB IRQ fires on both edges. Both can be online at once, and the battery STATUS is CHARGING if either is (`max17042_battery.c:391`). Nothing in the DT or kernel enables a USB charge path to the cell, and only the bq5105x charges, so whether "CHARGING on ac" is physically true is uncertain.

**`charge_terminate`** (`bq5105x_ctrl.c`): gpio 78 is requested output, init low, and exported with direction fixed. The kernel never drives it. Only userspace healthd writes `/sys/devices/0.bq5105x-ctrl/charge_terminate/value`. By analogy with smelt's `chg_term`, high stops charging and low allows it (inferred; not in the minnow source). The DT comment says "gpio-72", but gpio3 pin 14 is 78, and the live dump agrees.

**Mapping of our smelt fields:**
- `dock` (smelt gpio 54, low on the pad, falling-edge wake): there is no single equivalent. Docked = (176 high) OR (176 low and a falling edge on 22 within 1500 ms). Wake pads are 0x1a2 (176) and 0x5bc (22). Those are already in `minnow.c`.
- `charge_n` (smelt 94, low = charging): minnow's equivalent is gpio 176 with inverted polarity, high = charging.
- `charge_term`: gpio 78, as above.
- `charge_rate`: **does not exist in the minnow DT.** `init.minnow.rc:31` chowns `0.bq5105x-ctrl/charge_reduce/value`, but the DT has no such gpio and healthd has no `charge_reduce` string. Treat it as a leftover. Healthd does log "1/2C charging rate detected", but I found no gpio write for it. Uncertain.
- `kill_disable`: gpio 182 (see item 5).

**Bug if you reuse `gauge_max17050.c` unchanged:** `charge_lines()` calls `gpio_config` and `gpio_set` on `GPIO_CHARGE_RATE` unconditionally. With the field left as 0 it would drive gpio 0, which is the TPS65912 interrupt (`aos-gpio.txt:5`). Guard it with `if (GPIO_CHARGE_RATE)`.

**Behaviour to expect:** stopping the receiver makes chg drop low, but the pad stays "docked" via the pulses on gpio 22. A firmware dock detector that looks only at 176 will see "undocked" as soon as it terminates.

## 5. Factory kill on minnow

This is not the same as smelt. The minnow `mmi-factory.c` is a different, simpler driver.

- **Probe** (lines 42-55): it returns -ENODEV unless `/chosen` has the boolean `mmi,factory-cable`. It never touches the gpio otherwise.
- **If the cable is present**: `gpio_request_array` with flags 0 (DIR_OUT, init low) and exports the line to userspace with direction changeable (`gpio_export(...,1)`). So the kernel actively drives it low, and a factory tool can flip it.
- **There is no "Disabling factory kill" high-drive branch**, unlike smelt's `mmi,factory-support-kungpow` and its cable-detect gpio. Nothing in the minnow kernel ever sets gpio 182 high.
- **DT**: `factory_support` at line 151, `gpios = <&gpio6 22 0x0>` (gpio 182), `gpio-names = "factory_kill_disable"`.

So in the normal vendor case (no factory cable) the kernel leaves the line wherever the bootloader set it, and the stock watch runs that way. Whether minnow has the "kill while USB powers the watch" problem is not documented. The stock dmesg gives no evidence that unplugging USB resets the watch, but I did not check this explicitly. I would not default to driving 182 high. Leave `kill_disable = 0`, test unplugging USB while awake, and only then try driving it high.

**Reconciling the live dump** (`aos-gpio.txt:46`, "gpio-182 (factory_kill_disable) out lo" while running on the dock): the gpiolib label is set only by a request with that name. Under this driver that request happens only if `mmi,factory-cable` is in `/chosen`. So either the bootloader sets that property on the AsteroidOS boot path (for example when it boots with a cable attached), or the kernel running there differs from this tree. I cannot tell which from the files. A read-only check on the watch would be whether `/proc/device-tree/chosen/mmi,factory-cable` exists. Either way the line reads low, consistent with the code.

## 6. Charge and thermal policy

**Source.** It is entirely userspace (healthd.minnow, `/sbin/healthd` in `boot/initramfs`; `charger` is a symlink to it). The kernel has no termination or temperature logic, and `STATUS` is only CHARGING or DISCHARGING, never FULL.

The values come from the real boot log, `boot_issue/wearos-dmesg.log:445-461`, and match the format strings in the binary. Temperatures are in 0.1 °C:

- Monitor interval: 60 s charging, 600 s discharging, 60 s when warm.
- `thermal-boot-delay` 300 s.
- Periodic charge above 450 with hysteresis 30: 600 s on and 300 s off.
- Terminate (stop) at 530 with hysteresis 10.
- `charge-restart-level` 98.
- CPU throttle on at 500 and off at 430.
- Complete after 1800 s, or when `current_avg` is between 0 and 16000 µA for 5 counts.

These are the same values as smelt's `healthd.smelt` (`SMELT.md:46-56`), which is why our `charge_policy.c` constants apply unchanged. Healthd writes `charge_terminate` and reads `/sys/class/gpio/gpio176/value` (usage uncertain; probably the charging state).

I found no other thermal files (no thermal-engine or thermald conf) and no separate shutdown temperature in the healthd strings.

**What `charge_policy.c` implements (`src/soc/charge_policy.c`):**
- WARM 450/30, HOT 530/10, 600 s on and 300 s off, FULL_TIMEOUT 1800 s, FULL_MA 16, FULL_READINGS 5, RESTART_PERCENT 98.
- REDUCE_MV 4100 and RESTORE_MV 3900. This is smelt's `charge_rate` logic, which is absent on minnow.
- TEMP_MIN -200 and TEMP_MAX 800 (plausibility), and an invalid gauge gives stop plus reduced.
- `CHARGE_POWER_OFF_TEMP` 600 (`charge_policy.h`). This is our own limit; `ASTRA-SMELT-CHARGE.md:7` notes it is not from the vendor evidence.
- Unlike the vendor, the limits apply from boot with no 300 s delay (intentional per the file header).
- The polling interval is `POLL_MS` 30000 in the gauge file.

**Parametrize per board:**
- The charge_rate and reduce voltages (`REDUCE_MV`/`RESTORE_MV`).
- The gpio pins for dock, charge line and terminate.
- The polarities, because minnow's charge line is active high and smelt's is active low.
- The dock detect scheme (level versus pulse).
- The power-off temperature.

The rest can stay shared.

## 7. Low-battery and the alert line

- **Kernel:** no low-battery shutdown. `maxim,batt_undervoltage_zero_soc` is not set in the DT, so the VMN (undervoltage) flag is recorded but never acted on. VALRT, TALRT and V_empty are not programmed, so they stay at the gauge's POR defaults. I believe V_empty's default is 0xA561, but that is from memory of the datasheet and unverified.
- **Userspace:** charger mode in healthd has "ignore power-button press, battery level less than minimum" and "device unplugged: shutting down in %lld", with no threshold values visible in the strings. I could not decode the framework thresholds from `framework-res.apk` without aapt. Android's default is a shutdown at level 0 when unplugged. I did not confirm that for this build.
- **Gauge alert gpio 140** (`cc_alert_pin`, pad 0x13c with pull-up and off-mode wake): the IRQ is falling-edge and is a wake source in suspend.
  - On each alert (`max17042_battery.c:811-839`) it re-centres the SOC window to ±`alert_threshold` (default 1) and clears sticky bits.
  - It then calls `power_supply_changed`, so userspace re-reads the battery level.
  - The window is adjustable via `/sys/devices/ocp.2/i2c.8/i2c-2/2-0036/alert_threshold` (chowned to system in `init.minnow.rc:29`).
  - Nothing shuts the watch down from the alert.
- **Ours:** nothing uses the alert line yet. Only the pad config exists in `minnow.c:11`.

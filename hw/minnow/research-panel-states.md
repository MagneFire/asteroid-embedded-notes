<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

The digest below comes from reading the source only. Nothing was run and no files were changed. Panel paths are relative to `drivers/video/omap2/displays/`.

## 1. Display state machine

- **States.** The enum is at `panel-minnow.c:260`. It maps to the M4 values `SCREEN_STATUS_NORMAL_OFF=0, NORMAL_ON=1, AMBIENT_OFF=2, AMBIENT_ON=3`, defined in `include/linux/m4sensorhub/MemMapUserSettings.h:32`.
- **Config.** `CONFIG_HAS_AMBIENTMODE`, `CONFIG_WAKEUP_SOURCE_NOTIFY` and `CONFIG_ALS_WHILE_CHARGING` are all `=y` in `minnow_defconfig`.
- **`change_state_mlocked`** (`:3258`):
  - It does nothing if the state is unchanged. For AMBIENT_ON it only restarts the ambient alarm.
  - Otherwise it cancels the alarm, waits up to 500 ms for resume, runs the transition, sets `mpd->state`, and calls `sync_display_status`.
- **DISABLE.** If enabled, it calls `disable_mlocked`, which is a full power-off (see 6/7).
- **ENABLE.**
  - If the panel is off, it calls `enable_mlocked`, which is a full power-on.
  - If the previous state was AMBIENT_ON, it instead sets 45 Hz (`set_default_fps`).
- **AMBIENT_OFF.**
  - It is ignored if the state is DISABLE.
  - If smart ambient is enabled (`smart_ambient && !is_docked`, `:430`), it sets backlight 0 with `led_set_brightness(default_dev, 0)`, then calls `disable_mlocked`.
  - That is a full power-off of bridge, panel, VIO, clock and regulators.
  - The image is not kept anywhere.
- **AMBIENT_ON.**
  - It is ignored if the state is DISABLE.
  - Docked and in ENABLE: set 60 Hz only.
  - Smart ambient off: nothing happens beyond the state variable changing.
  - Otherwise: `enable_mlocked` if the panel is off, then 30 Hz, then `led_set_dim_brightness`, then start the ambient alarm.
- **What ambient mode is.** I found no panel partial mode, no separate bridge-memory path and no M4-drawn watch face in the panel driver.
  - Ambient ON is the normal pipeline, with the panel on.
  - The bridge refreshes at 30 Hz and the backlight is dimmed to a low ALS-derived code.
  - Host userspace (Android) draws the ambient face through the usual `update()` path.
  - Inference, not explicit in the source: the bridge scans the panel from its own URAM (DSITX video mode, burst). So the OMAP DSI can sit in ULPS after 250 ms without updates while the image stays up.
  - MEM_EN and the bridge stay powered the whole time the panel is enabled.
- **Smart-ambient fields.**
  - `support_smart_ambient` is a DT bool, set in `omap3-minnow.dtsi:104`. `ambient_timeout` is also from DT, and is 0 there, meaning never time out.
  - The sysfs files are `smartambient` (writable only while in NORMAL_ON) and `ambient_timeout`.
  - `minnow_panel_start_ambient_alarm` (`:616`) starts an ALARM_REALTIME timer only if `smart_ambient && ambient_timeout && !docked`. On expiry it goes to AMBIENT_OFF.
- **Events** (`omapdss_displayenable_notify`, `:482`):
  - POWERKEY, TOUCH and GESTURE queue early_init.
  - GESTURE_VIEWON and VIEWOFF set `is_gesture_view_on` and queue `ambient_wake_work` (`:583`). That work only acts while in AMBIENT_ON or AMBIENT_OFF, switching to AMBIENT_ON for view-on and AMBIENT_OFF for view-off.
  - DOCKON and DOCKOFF set `is_docked` and queue `dock_work` (`:557`). Dock-on moves AMBIENT_OFF to AMBIENT_ON. Dock-off while in AMBIENT_ON re-enters AMBIENT_ON to restart the timeout.
- **sysfs `interactivemode`** (`:1868`). Write 1 gives ENABLE. Write 0 gives AMBIENT_ON, unless the state is DISABLE. `omapdss enable()` (`:3476`) gives ENABLE, or AMBIENT_ON if `!interactive`. `omapdss disable()` gives DISABLE.
- **M4 sync** (`sync_display_status_mlocked`, `:3182`).
  - It writes the state to `M4SH_REG_USERSETTINGS_SCREENSTATUS` through `m4sensorhub_extern_set_display_status` (`drivers/mfd/m4sensorhub-extern.c:92`). That is a 1-byte I2C register write.
  - It is skipped if M4 is not in NORMALMODE.
  - While docked it reports ENABLE, which blocks wake gestures.
  - This runs after every transition, including no-ops.
- **Backlight in ambient.**
  - `led_set_dim_brightness` (`:3215`) reads `M4SH_REG_LIGHTSENSOR_SIGNAL`, a u16. The default is `DIM_BACKLIGHT_ALS=5` if the read fails.
  - It calls `led_set_brightness_raw_als`, which writes the LM3535 code directly. See 8.

## 2. Refresh rate (`:635`)

- The command is a 6-byte generic write to the bridge: `20 10 | den16 | num16`. That is VTCM Pixel Clock Frequency Ratio register 0x2010, with PCLKDEN then PCLKNUM.
- It is sent with `dsi_vc_generic_write` after `wake_up_locked`. No retransmit, so it goes to the bridge, not the panel.
- It is skipped if `panel_type < OTM3201_2_0`.

| Rate | Bytes | den/num | Used when |
|---|---|---|---|
| 30 Hz | `20 10 00 EF 00 34` | 239/52 | AMBIENT_ON (smart ambient) |
| 45 Hz | `20 10 00 5F 00 1F` | 95/31 | init-table default and ambient→ENABLE |
| 60 Hz | `20 10 00 F7 00 6C` | 247/108 | Docked ENABLE→AMBIENT_ON |

- The 45 Hz row matches the init table.
- The 60 Hz row equals the panel 1.0 override pixel clock.

## 3. ULPS

- **`ulps_timeout`** is hardcoded to 250 ms in `dt_init` (`:2413`). It is enabled by default, since `ulps_work` is queued after every `wake_up_locked` and every enable.
- **`ulps_work`** (`:3740`) takes the lock and, if the display is ACTIVE, calls `enter_ulps_locked`.
- **`enter_ulps_locked`** (`:1289`):
  - Cancel the ULPS work.
  - Send TEAR_OFF (`_enable_te(false)`), with one DSI-recovery retry on failure.
  - Disable the ext-TE IRQ if there is one.
  - Call `omapdss_dsi_display_disable(dssdev, disconnect_lanes=false, enter_ulps=true)`.
  - Set `ulps_enabled=true`.
  - Nothing else is switched: clkin, VIO, MEM_EN, resets and regulators all stay on.
- **`exit_ulps_locked`** (`:1331`):
  - Call `omapdss_dsi_display_enable`, then `vc_enable_hs(true)`, then re-send TEAR_ON.
  - On error it tries `dsi_recovery_locked` once, which is a fast DSI disable and enable.
  - Then it re-enables the TE IRQ, queues the ULPS work and clears `ulps_enabled`.
- **`wake_up_locked`** (`:1379`) exits ULPS if needed. Otherwise it re-arms the ULPS timer. It is called before `update`, the refresh-rate writes, the backlight, ESD and disable.
- **Suspend.** `minnow_panel_suspend` (`:3357`) forces ULPS and cancels ESD. Resume re-queues ESD after the remaining interval.
- **sysfs.** The `ulps` and `ulps_timeout` files exist.

## 4. ESD (`:3759`)

- The DT sets `esd_interval=8000` ms.
- The check runs only while enabled. It wakes from ULPS, turns HS off, then turns retransmit on. It reads DCS 0x0A (`GET_POWER_MODE`) from the panel through the bridge and turns retransmit off again (`check_panel_status`, `:2848`).
- Anything other than `DCS_POWER_MODE_NORMAL` is an error. A mode of 0x00 is tolerated up to 3 times in a row.
- On failure it calls `recovery_locked` (`:1276`): a fast `disable_locked`, `msleep(20)`, a full `enable_locked`, then a forced `update_locked`.
- Otherwise it re-enables HS, re-enters ULPS if `!interactive`, and re-queues itself.
- ESD is forced off for panel type 1.0.

## 5. `dt_init` and probe

- **Table defaults** for id_panel=2 (`:207-228`):

| Item | Value |
|---|---|
| Mode | command mode |
| Size | 320x290 (`PANEL_HEIGHT=290`; the bridge frame buffer is 320x320) |
| Pixel clock | `ceil(320*290*45/1000)` = 4176 kHz |
| Format | RGB888 |
| x/y offset | 0/0 |
| HS clock | 104,000,000 to 150,000,000 |
| LP clock | 7,000,000 to 9,000,000 |
| Panel reset | ACTIVE_LOW, 5 ms, wait 10 |
| Bridge reset | ACTIVE_LOW, 20 ms, wait 10 |

- **Caps:** MANUAL_UPDATE and TEAR_ELIM.
- **GPIOs and clock** come from the DT: `gpio_panel_reset` (gpio14), `gpio_bridge_reset` (gpio23), `gpio_vsync_events` (gpio29), `clk_in="periph_26mhz"` (gpio177), and the supplies ldo1 (bridge) and ldo7 (panel).
  - `gpio_vio_en` (gpio42) and `gpio_mem_en` (gpio87) are only in the board dts files. `gpio_mem_en` is only in `rev-b+`. Rev-a, p1b and p2 have no MEM_EN.
- **`gpio_te` is commented out** in the DT. The driver therefore uses the OMAP DSI-internal TE (`omapdss_dsi_enable_te`).
- **Pins.** Default `num_pins=4`, `pins={0,1,2,3}` (`:2420`). `omapdss_dsi_configure_pins` reads them as (dx,dy) pairs, so this is lane 1 = (0,1) and lane 2 = (2,3).
  - Polarity is encoded by the order inside each pair. The DT `pins` property is commented out.
  - The `pixel_clock`, `pixel_format`, `hs_clk` and `lp_clk` DT overrides are all commented out.
  - `panel_size_um` is `<39744 36020>`.
- **`panel_param`** is a module param that the bootloader passes (`:388`), in the form `"<type>#<ver>"`.
  - Parsing: `strtoul` on the type, then `'#'`, then `strtoul` on the version.
  - `3#528916` therefore means type 3 = `OTM3201_2_1` and version 528916 = 0x081214, which equals `INIT_DATA_VERSION` (0x081214, "MM/DD/YY" 08-12-14).
  - Type enum: -1 INIT, 0 DUMMY, 1 OTM_1_0, 2 OTM_2_0, 3 OTM_2_1.
  - Types 1 to 3 with a matching version set `skip_first_init=true`. Type 1 also turns off ESD and swaps in `panel_init_ssd2848_320x320_1` (45 Hz timings → 60 Hz-style non-burst, via `replace_cmdbuf`). A mismatched version only logs an error.
  - Types -1 and 0 mean no bootloader init, so the driver resets and initializes everything.
- **What `skip_first_init` changes:**
  - GPIO request initial levels (`:2599-2650`): VIO low (on) and MEM_EN high; reset lines in the inactive state.
  - In `power_on` for the first enable only: it sends a BTA instead of a hardware reset and init-table run, which keeps the boot logo.
  - It does not force an update on the first enable (`:3135`).
- **Type detection.** `detect_type` (`:1000`) runs during `verify_otm3201` only when `panel_type==PANEL_INIT`. It reads OTM register 0xB0:

| 0xB0 | Type |
|---|---|
| 0x12 | 1.0 |
| 0x1A | 2.0 |
| 0x1C or other | 2.1 |

  - For 1.0 it swaps the timing table and forces a reset retry.
- **SSD2848 verify** (`:1033`):
  - It runs when the table hits the `1, SSD2848_CMD, 0xFF` marker, and only if `need_verify`.
  - It turns retransmit off, then reads back every `SSD2848_CMD` entry before the marker.
  - Each read is `dsi_vc_set_max_rx_packet_size(4)` followed by `dsi_vc_generic_read_2(addr_hi, addr_lo, buf, 4)`. The packet size is then reset to 1.
  - The 4 bytes are compared with the 4 data bytes in the table.
  - Any mismatch makes the whole init fail and triggers a hardware reset and retry, up to 3 times. After that it retries once without verify, and with `PANEL_INIT` it falls back to the dummy panel.
- **OTM verify** (`:1089`): panel registers are read back one at a time through retransmit, using DCS read. A mismatching register is rewritten once (`rewrite_reg`).

## 6. Enable and disable order

**Screen on** (`enable_mlocked` `:3116`, `enable_locked` `:3034`, `power_on` `:2876`):

1. Take the wake lock and cancel ULPS and ESD.
2. Enable the ldo1 and ldo7 regulators.
3. Enable clkin (26 MHz).
4. Sleep 6.0 to 6.3 ms (hardware-bug workaround for the VIO dip).
5. `enable_vio`:
   - Select the pad pulldown state, wait 250 to 300 us, drive gpio42 low, select the output state.
   - Then set MEM_EN high.
6. `power_on`:
   - Configure the DSI pins, set the config, enable DSI and turn the video output off.
   - HS off.
   - `hw_reset`: assert both resets and wait the longer time (20 ms, `reset_ms=max`), release both, wait 10 ms (`release_ms=max`).
   - Run the init table with verify.
   - Panel power-mode check (3 retries on mode 0x00).
   - TEAR_ON.
   - On the first enable only, read the DA/DB/DC IDs.
   - `SET_DISPLAY_ON` to the bridge.
   - HS on and video output on.
7. ESD, then a forced `update_locked`, which sends the column/page window and starts a frame. The frame callback releases the DSI bus. Then queue ULPS and ESD again.

- If power_on fails, it cleans up with a fast disable.
- With retransmit on, `WAIT_MS > 100` ms (the 120 ms panel sleep-out wait) is replaced by `clear_bottom_line` (`:893`). That writes zeros to lines 290..319 and tops up the remaining delay.

**Screen off** (`disable_mlocked` `:3156`):

1. Cancel early_init, ULPS and ESD. Take the DSI bus lock.
2. Wake from ULPS. If that fails, do a fast disable.
3. `dsi_disable_video_output`.
4. Run the power-off table.
5. `omapdss_dsi_display_disable`.
6. State DISABLED.
7. `hw_active_reset`: both resets asserted, wait 20 ms.
8. clkin off.
9. MEM_EN low, VIO gpio high (off).
10. Regulators off.

- A fast power-off skips the table.

**Early init** (`:511`): on powerkey, touch or gesture it runs `change_state(ENABLE)`.
- It saves `last_state` as AMBIENT_OFF if that was the state, otherwise DISABLE.
- It arms a 500 ms timeout.
- If userspace has not called `enable()` or `interactivemode` by then, or the kernel suspends first, it reverts to `last_state`.
- `omapdss enable()` and the interactivemode store clear the pending revert.

## 7. Power-off table (`panel-minnow-common.h`, `panel_off_ssd2848_320x320`)

- Retransmit on: `DISPLAY_OFF` (sync), then `ENTER_SLEEP` (nosync).
- Retransmit off, to the bridge: `DISPLAY_OFF` (sync), wait 50 ms, `ENTER_SLEEP` (nosync), wait 20 ms.
- Then a generic write nosync, `10 28 00 00 00 01`, to MIPIRX Power Cut register 0x1028 (PWC=1), and wait 5 ms.
- The comment says PWC "will enable power cut to the whole chip and only global reset can restore the power supply to the chip".
- So before the bridge can be used again, the reset line must be toggled (gpio23 active-low 20 ms, then a 10 ms wait). The driver does this at every next power-on in `_minnow_panel_hw_reset`.

## 8. LM3535 (`drivers/leds/leds-lm3535.c`)

- **Bus.** I2C3 address 0x38 per the DT. The driver falls back to 0x36 if the first read fails.
- **Enable pin.** HWEN is hardcoded as gpio 98 (`:77`, a plain `gpio_request`/`direction_output` on gpio 98).
  - Probe sets it high, then `msleep(1)`.
- **Probe and `setup`** (`:1000` onward):
  1. Read reg 0x50 for the revision: 0xFF→0, 0xF0→1, 0x02→2, 0x00→3, else 4.
  2. `configure`: write `CONFIG(0x20)=0`, then `ALS_RESISTOR(0x51)=0`. Only this `#if 1` branch is built, so the zone boundaries and `ALS_CTRL` are never written.
  3. `enable(1)`: HWEN=1, 1 ms, then `ENABLE(0x10)=0x07`. For revisions 2 and 3 also `TRIM(0xD0)=0x68`.
  4. `BRIGHT_A(0xA0)=87`.
- **Interrupt.** The DT has no irq, so there is no ALS interrupt. The `bright_zone` atomic stays 0, and brightness always uses the zone-0 curve.
- **`brightness_set`** (`:693`):
  - Values 1..4 become 0 (off). Values 5..9 become 1 (dim). Value 255 and the rest use the curve.
  - On `value==0` and already disabled, it returns.
  - It calls `set_ramp(do_ramp, |Δcode|)`, which writes `OPTIONS(0x30)`. The step time is chosen so the total ramp is about 200 ms (`ramp_time=200000` us). The no-ramp device `lcd-nr-backlight` (name contains "nr") writes `OPTIONS=0`.
  - Then `A(0xA0)=code`. For value 0 it waits out the ramp, writes `ENABLE=0` and drives HWEN low.
- **"nr"** means "no ramp". It is not night or ambient.
- **Curve.**
  - Value 1 (dim) gives code 0x03 (`dim_values[0]`).
  - Otherwise `code = (24 v³ − 15295 v² + 4123276 v + 634967215) / 10^7`. My arithmetic: v=10 gives about 67, v=255 gives 108 (0x6C). Max code is about 0x6C, so there is no clamp at 0x7F.
- **M4 ALS floor** (`CONFIG_WAKEUP_SOURCE_NOTIFY`, `alsstatus` defaults to 1):
  - When M4 is in NORMALMODE, `convert_value` reads `M4SH_REG_LIGHTSENSOR_SIGNAL` at most every 500 ms.
  - It sets `code = max(code, abs_als_to_backlight(als))`, capped at 36 (`MAX_AMBIENT_BACKLIGHT`).
  - `abs_als_to_backlight` is a quadratic piecewise fit by ALS value, with a quirk: ALS 86 and 87 fall through to the third branch.
  - Example: ALS=5 gives code 5.
  - While docked, the code is at least 36 (`MIN_DOCK_BVALUE`).
- **Ambient path.** `lm3535_brightness_set_raw_als` (`:675`) writes the ALS-derived code (at most 36) straight to `A`. There is no ramp and no zone curve. It enables the chip first if needed.
- **Suspend/resume.** The suspend and resume hooks are compiled out under `HAS_AMBIENTMODE`. `lm3535_pm_suspend` only cancels the ALS delayed work.

**Comparison with `src/display/backlight_lm3535.c` and `lm3535.h`:**

- **Dim step.** Firmware uses `LM3535_DIM=0x26` for levels 5..9. The vendor minnow uses `dim_values[0]=0x03`. The vendor code of 0x03 is much dimmer.
- **Curve.** The zone-0 cubic matches. The code is clamped at 0x7F, which the vendor never reaches.
- **ALS floor and dock minimum.** Firmware has neither. Vendor: up to 36 from the M4 ALS, and at least 36 when docked.
- **Ambient direct codes.** Firmware has `set_code`, so ambient dimming could be done with a code of 2..36.
- **Ramp.** Vendor writes `OPTIONS` before each brightness change. Firmware writes `OPTIONS=0` once at init, so it is always instant, which is fine.
- **Registers.** CONFIG=0, ALS_RES=0, ENABLE=0x07, TRIM=0x68 on revisions 0x02 and 0x00, and A=code all match. Vendor also writes A=87 after init (not needed).
- **I2C speed.** DT says 400 kHz; firmware uses 200 kHz (`BUS_HZ`). Not important.
- **HWEN.** Vendor gpio 98 is high at probe and low on off. I could not check firmware's `board->backlight_pins.enable`.

## 9. M4 display driver (`drivers/misc/m4sensorhub_display.c`)

- This is a different feature from the panel driver: an M4 "timepiece" (clock face) driver. The M4 can draw the clock face itself over MIPI with the host asleep.
  - `m4_display_sync_state` (`:267`): to hand over, it syncs clock, timezone and daily-step offsets to the M4, sets `gpio_mipi_mux` to 1, enables regulator "vcsi", and writes `M4SH_REG_TIMEPIECE_ENABLE=1`. The inverse waits 2 ms, disables the regulator and puts the mux back to 0.
  - The ioctls are `SET_TIMEZONE_OFFSET`, `SET_DAILYSTEP_OFFSET` and `LOCK_CLOCKFACE`.
  - `m4sensorhub_set_display_control(m4_ctrl, mux_gpio)` is exported, but I found no callers anywhere in this tree. The DT has no mux gpio either.
- In this tree, minnow ambient mode is entirely the host-driven path in section 1. The M4's only role in the panel path is the SCREEN_STATUS register (gesture/wake gating) and the ALS value.
- **Uncertain:** whether the shipped M4 firmware actually uses the mux. The mux path looks unused on minnow, which is a conclusion from the source.

Bridge register values for power-on are in `panel-minnow-common.h:62-210` (the 0x0008 PLL for 216.6 MHz, DSITX timings, and the OTM3201 gamma set). I did not repeat them here.

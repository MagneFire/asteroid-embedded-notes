# Codex (gpt-6-astra) power round 4, 2026-11-03

On POWER.md §18: the trim noise, the absolute floor, USB rest readiness, the remaining ~4.3 mA. Claude confirmed in the code that usb_next_ms() returns 1 when there is no deadline.

**The trim mechanism is real, but 4.3 mA is still a normalized reading, not a calibrated floor. The USB rest feature is not ready to commit unchanged: its deadline handling introduces a sleep regression, and the 10-second charger classification is unsound.**

This is a read-only sturgeon report. I read §18 first, reviewed the earlier reports, current firmware and relevant vendor sources, and recalculated statistics from the day log using an in-memory script. No files were changed, no device commands were run, and no commit was made.

**1. Trim noise: your interpretation is substantially right.**

The firmware performs one channel-5 external-offset conversion, then writes that result directly to `0x36f2/f3`. Its conversion uses `DIG_PARAM=0`, `HW_SETTLE=0`, and `FAST_AVG_CTL=0`. `bms_poll()` invokes the trim operation every 300 seconds. The log records the requested value only when it changes; it does **not** read back and verify the stored trim. [FW pmic.c:625](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:625), [trim:655](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:655), [bms.c:842](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/bms.c:842).

A useful model is:

\[
I_{\rm reported}=I_{\rm true}+k(T_{\rm stored}-T_{\rm true})
\]

Here, \(T_{\rm true}\) means the offset code that correctly zeros this measurement path under the current conditions. A noisy upward trim rewrite therefore increases reported discharge.

The nominal scale supports this interpretation: **5.42535 µV/code ÷ 9.7 mΩ = 0.5593 mA/code**. The firmware’s shadow-counter conversion uses that voltage scale and sturgeon’s 9700 µΩ resistor. [FW pmic.c:697](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:697), [board setting:104](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/board/sturgeon.c:104).

My reconstruction retained intervals wholly inside each arm after two minutes of settling, excluding attachment. It gives:

| Baseline analysis | Slope, mA/LSB | Correlation |
|---|---:|---:|
| Assign the minute’s **ending trim** to the entire interval | 0.5186 | 0.9373 |
| Weight each trim by its time within the interval | 0.5375 | 0.9584 |
| Exclude intervals crossing a trim change | 0.5377 | 0.9619 |
| Within-arm slope, using those non-crossing intervals | **0.5510** | — |

The first row reproduces §18. The last is especially persuasive: removing between-arm level differences brings the slope very close to the nominal **0.5593**.

This establishes a strong calibration-induced component. It does not prove every variation in the offset conversions is random noise: genuine die-temperature drift, conversion-state dependence and interference remain possible.

**The vendor does not show an ordinary averaging/filtering solution—and its calibration-channel selection needs correcting in our earlier interpretation.**

| Vendor behavior | What the source actually does |
|---|---|
| Calibration conversion | One gain conversion on channel 3, then one selected offset conversion; writes that offset directly to the trim registers. No ordinary median, sample average, hysteresis or change threshold. [qpnp-adc-current.c:911](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:911) |
| Offset-channel selection | Channel **5** when `iadc->external_rsense` is true; otherwise channel **6**, except for a specified PM8941 BATFET workaround. [954](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:954) |
| How external rsense is selected | The **IADC node’s `qcom,rsense` property** sets `external_rsense`. It is not controlled by the BMS node’s `qcom,use-external-rsense`. [1497](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:1497) |
| Sturgeon DT discrepancy | The BMS declares external rsense and 9700 µΩ, but I found **no `qcom,rsense` on the inherited sturgeon IADC node**. Therefore this source configuration selects **channel 6 for trim calibration**, while BMS measures external rsense. [sturgeon-pm.dtsi:111](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-pm.dtsi:111), [msm-pm8226.dtsi:423](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:423) |
| Decimation/averaging | The configure function writes `amux_prop->decimation << 3`, settling and fast-average settings. Those properties are zero-initialized; this IADC driver contains no channel-to-`amux_prop` assignment, and the relevant DT channel settings are also zero. Thus the reviewed path writes **0/0/0**, like firmware. [configure:764](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:764), [allocation:1549](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-common.c:1549) |
| Recalibration frequency | At probe, then delayed work every **300000 ms**. An IADC read also checks PMIC die temperature and recalibrates after a change exceeding **5000 m°C**, unless automatic calibration is suppressed. This is not a temperature-only policy. [periodic work:1037](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:1037), [temperature check:1138](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:1138), [probe:1548](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:1548) |

**That channel discrepancy corrects my earlier blanket statement that sturgeon’s vendor calibrates the same external-offset channel.** It is a source-level finding; the running AsteroidOS DT might differ. Inspect its actual IADC node and calibration channel before treating a vendor trim value as a reference. Do not switch firmware to channel 6 merely to imitate this apparent mismatch.

The BMS has additional calibration calls:

- Both SOC recalculation paths call `calibrate_for_trim(..., false)` when BATFET is open. [qpnp-bms.c:3173](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3173), [3231](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3231).
- Its BATFET-open workaround repeatedly calibrates until measured current is sufficiently small, waiting **20 ms** after each calibration because BMS uses the new trim on its next VSENSE sample. This is a special coupling workaround, not normal averaging. [3837](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3837).
- On affected revisions, BATFET transitions suppress automatic calibration while open, then recalibrate and resume it when closed. [3966](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:3966).

**Does Linux compensate the counter? Yes for gain and modeled errors; no for the observed trim-history error.** `calculate_cc()` applies gain correction using `gain_raw-offset_raw`, converts using rsense, and calls IADC compensation. That compensation is multiplicative and revision/fabrication dependent. There is no integration of historical trim changes that subtracts the additive error you measured. [qpnp-bms.c:1441](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1441), [qpnp-adc-current.c:617](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:617).

Consequently, there is no basis for saying “the vendor already avoids this noise.” Long integration and different actual calibration timing/channel may make its observed result different. Its scheduled work is also not a five-minute wake alarm guaranteeing a rewrite during uninterrupted suspend.

**Concrete firmware fix I would implement first:**

1. Keep channel 5 for the external measurement path.
2. Replace the single conversion with a **64-conversion batch** at the currently understood hardware settings. Preserve full precision while accumulating; round once when producing the trim code.
3. Initially log the ordinary mean, median, spread and a mean with the four highest/lowest samples removed. Select the ordinary mean unless the batch data establishes outliers; do not assume a median fixes a systematic bias.
4. Retain the previous trim if collection fails. Check SPMI read/write results, perform both protected writes, and verify both bytes afterward.
5. Keep the existing five-minute opportunity initially, but skip unchanged writes. Log every calibration attempt, including unchanged results, actual readback, channel, die temperature and conversion settings.
6. Once batch behavior is known, consider a slow filter or temperature-triggered refresh. **Do not begin with wide hysteresis or temperature-only updates:** these can preserve a wrong zero and make an inaccurate meter look stable.

Sixty-four independent samples reduce standard error by eight, but independence must be measured. Spread sampling across a bounded collection period if adjacent conversions are correlated.

Hardware averaging is a sensible second step. The vendor header defines fast-average codes **4 = 16 samples**, **6 = 64 samples**, and decimation codes 0–3 as 512–4096. However, higher settings need conversion-time and actual-effect validation; the present firmware timeout is only about 10 ms. Also, the vendor’s used decimation shift and its other register definitions are inconsistent enough that I would not blindly transplant a nonzero setting. [ADC enums:154](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/qpnp/qpnp-adc.h:154), [fast averaging:280](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/qpnp/qpnp-adc.h:280), [used shift:776](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:776).

**Validation using existing logs:** reconstruct a piecewise-constant trim history and integrate it over every CC interval:

\[
I_{\rm ref}=I_{\rm measured}
-k\left(\frac{\sum_j T_j\Delta t_j}{\Delta t}-T_{\rm ref}\right)
\]

Use non-crossing intervals as a cross-check, fit within unchanged arms, and estimate uncertainty by calibration epoch/arm rather than treating every minute as independent. Compare results with \(k=0.519,\ 0.537,\ 0.559\). Hold out some arms when estimating the slope.

These logs can validate the mechanism and show what slower filtering of the recorded sequence would predict. **They cannot establish the noise reduction of 64 back-to-back conversions**, because those samples were never collected. Future acceptance should require stable raw CC at fixed load, verified trim readback and consistent zero estimates—not merely a reduced scatter after fitting away the same data.

**2. The absolute floor is not identifiable from this run alone.**

`bbd3` is a reference coordinate. Neither its being near the mean nor a vendor having written it makes it the correct zero.

Using the equation above:

\[
I_{\rm true}\approx4.3+0.52(T_{\rm true}-\texttt{bbd3})\ {\rm mA}
\]

For illustration, a correct trim three codes lower would imply approximately **2.7 mA**; three codes higher would imply **5.9 mA**. Those are sensitivity examples, not confidence limits.

Moreover, the retained baseline intervals have a time-weighted mean trim approximately **1.11 codes above bbd3**. “bbd3, the mean” is therefore not exact for this retained baseline population. An unbiased mean of repeated, correctly configured offset conversions is a reasonable estimator; the mean of this mixed, changed-only log is not an absolute standard.

A stable stored trim also does not eliminate gain error, external/internal calibration-path mismatch or sampling-state dependence. Firmware’s raw shadow path lacks the gain/temperature processing used by its main BMS calculation. [FW pmic.c:721](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:721), [bms.c:312](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/bms.c:312).

**The OCV audit supports the scale, but cannot choose the correct trim code.** For the retained day-log portion, approximately 16967–41531 seconds, I obtain:

| Audit | Result |
|---|---:|
| OCV endpoints | 4.23657 → 4.12203 V |
| Fitted OCV slope | −17.62 mV/hour |
| Temperature-interpolated profile slope | −1.589 percentage points/hour |
| Equivalent current using 321 mAh | **5.10 mA** |
| Equivalent current using 275 mAh | **4.37 mA** |

These are whole retained-session estimates, not isolated B-arm measurements. The capacity sensitivity alone is approximately **0.73 mA**, larger than one trim code. The interpolation uses the firmware’s temperature/OCV table. [Profile:49](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/board/sturgeon.c:49), [log start:4](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:4), [late OCV:2586](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:2586).

The earlier audit was useful for exposing a gross discrepancy between approximately 3 mA CC and much faster voltage loss. Its agreement after trim updates did not calibrate the meter to sub-mA accuracy. Cell capacity, profile mismatch, relaxation and hardware OCV qualification remain confounders. [POWER.md:618](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:618), [trim audit:739](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/POWER.md:739).

To establish an absolute floor, use a calibrated external battery-current measurement or a validated zero-current calibration under conditions known to match the BMS path. A matched Linux run is valuable comparative evidence, but its counter shares this uncertainty.

**3. USB rest: improved substantially, but not ready unchanged.**

The bypass correction, explicit CDC detach, checked PHY override writes, disconnected failure state and retry path are real improvements. A failed PHCD entry now leaves clocks enabled. The log demonstrates a successful restore in **103 ms**, followed by high-speed configuration. [FW usb.c:394](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:394), [restore:429](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:429), [successful replug:2590](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:2590).

The remaining findings, in priority order:

| Priority | Finding | Consequence / concrete correction |
|---|---|---|
| **Before commit** | `usb_next_ms()` initializes `next=UINT32_MAX`, then casts it to signed and returns **1**. | “No deadline” becomes an immediate deadline. Preserve the sentinel explicitly. |
| **Before commit** | `gone_t` remains set after collapse, and its deadline is still considered while down. | An expired unplug deadline continues constraining sleep. Clear it or evaluate it only while removal debounce is pending. |
| **Before commit** | Ten seconds without `tud_mounted()` permanently classifies the source as a charger. | A slow/disabled host or later deconfiguration can strand USB until replug. Elapsed enumeration time is not BC1.2 classification. |
| **Before commit** | DCD timeouts still report success or continue using endpoint state. | Bounded loops prevent infinite waits, but do not establish successful reset/flush/EP0 priming. Propagate failure and enter controlled recovery. |
| **Follow through** | Initialization/connection ordering and some clock/reset error handling remain incomplete. | Defer connection/IRQ delivery until final PHY/session setup succeeds; use the same checked path at boot. |
| **Follow through** | `cdc_out()` still has an unbounded connected-host backpressure loop. | A host that stops accepting data can prevent main-loop cable handling. Add a bounded/nonblocking output policy. |

The **deadline bug is observable in the day run**. `usb_next_ms()` constrains `app_next`; `power_idle()` only programs a long timer when `next > 1000`. A returned 1 therefore leaves the ordinary one-second timer in use, explaining the observed cadence rather than producing 1000 wakes per second. [usb.c:534](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:534), [main.c:885](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:885), [power.c:241](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/power.c:241).

Fix deadline calculation per candidate using wrap-safe elapsed-time comparisons, then take the minimum. Also include the **next PMIC cable poll while USB is up**: merely adding debounce/retry deadlines does not schedule the initial removal detection. Once successfully down on battery, PMIC attach wake should allow long sleep without perpetual cable polling. [main.c:556](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:556).

The DCD problems remain concrete:

- `dcd_init()` returns true even if reset stays asserted.
- `bus_reset()` clears/reuses queue memory after a potentially unsuccessful prime/flush wait.
- The newly bounded EP0 setup wait still primes the endpoint after expiry; `dcd_edpt_xfer()` returns true.
- `dcd_deinit()` returns true after a potentially failed flush.

[Reset/init:187](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:187), [deinit:256](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:256), [EP0:481](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:481).

The outer restore’s checked `tusb_init()` therefore cannot currently detect all controller failures. Its ignored PHCD-exit timeout is defensible **if the subsequent full reset is reliably checked**; that distinction matters.

`controller_init()` also re-enables clocks after block reset without checking their running state, and proceeds to PHY selection even after detecting reset failure. Boot-time `usb_init()` ignores both its result and final `phy_select()` failure. TinyUSB still enables the interrupt before `usb_restore()` performs its final disconnect/select/connect sequence. [usb.c:61](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:61), [boot initialization:548](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:548), [TinyUSB usbd.c:595](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/device/usbd.c:595).

CDC detach now addresses the teardown issue, but it does not fix the output loop that can prevent teardown from being reached. [usb.c:261](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:261).

**Charger behavior needs a distinction between clock suspension and analog PHY collapse.**

The vendor **does suspend the USB block for a DCP**. It first detects DCP, enables `VDP_SRC` with ULPI register `0x85`, then runtime-suspends. Its suspend path can assert PHCD/STP and gate clocks, while explicitly excluding DCP from PHY retention, rail collapse and regulator-LPM paths. [Detection/result:2673](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:2673), [DCP restrictions:1014](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1014), [clock/supply policy:1065](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1065).

Therefore:

- **Clock-resting an identified DCP can be acceptable.**
- **The current “not configured after 10 s” path is not an adequate DCP implementation.**
- For the first feature commit, keep USB available whenever VBUS is present, and retain the tested unplugged rest path.
- Later add BC1.2 classification and a DCP-specific suspend state preserving the required analog source and supplies. That need not keep the controller clocks running continuously.

The PMIC needs a software-established charging policy: source-appropriate input-current limit, input suspend cleared, charger enabled, and normal voltage/thermal limits. Linux passes detected-source current through the USB power supply, then the charger programs IUSB_MAX. Sturgeon caps USB input at **1100 mA** and separately limits battery charging to **300 mA**. [Notification:1420](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1420), [charger policy:3400](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:3400), [input-limit programming:1138](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1138), [board limits:84](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-pm.dtsi:84).

Firmware currently stops the enumeration timer and writes **500 mA for every detected VBUS source**. The PMIC does not learn “DCP” from `tud_mounted()==false`. The relevant controls are `USB_IMAX=0x1344`, `USB_SUSP=0x1347`, and `USB_ENUM_T_STOP=0x134e`. [FW pmic.c:242](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:242), [attach policy:341](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:341).

Your successful unplug/replug tests support the normal path. They do not cover delayed enumeration, stalled CDC output, injected reset/flush failures or DCP behavior.

**4. Remaining consumption: first recover the lost long sleeps, then investigate persistent loads.**

The day-run retained intervals average **99.0304% VDD-min residency**, with **60 entries per minute**. A representative interval contains 59.503 seconds of VDD-min in 60.085 seconds. This is materially different from the previous 99.9–99.97% results. [Day log:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:21).

At an illustrative 90 mA outside VDD-min, the excess above a roughly 4 mA sleeping load would be approximately **0.8 mA**. That is an estimate, not a measured correction; transition current is unknown. It makes the USB scheduling fix the highest-priority experiment before calling 4.3 mA a sleep floor.

The following ranges are **engineering guesses in battery mA**, except where explicitly described as measured. They overlap and must not be summed.

| Rank | Candidate | Plausible opportunity | Discriminating read/experiment |
|---|---|---:|---|
| **0** | Extra one-second wakes | Roughly **0.2–1 mA** | Fix USB deadlines; repeat unchanged B with stable trim. Compare current and time outside VDD-min. |
| **1** | Panel’s full-off commands and supplies | **0–1.5 mA** | Compare present sleep-in against complete RM69080 full-off, then panel-owned supply shutdown with proven cold recovery. |
| **2** | Hub and independently powered sensors | **0–1 mA**, potentially more if a sensor remains active | Compare services disabled with MCU alive/asleep against reset; identify physical supplies before switching them. |
| **3** | CX/MX requests and inherited shared-rail policy | **0–1+ mA** recoverable, poorly constrained | Capture Linux and firmware active/sleep requests; distinguish AP requests from final RPM aggregate voltages. |
| **4** | DDR/platform retention | Potentially a substantial part of the remaining few mA | Compare retention configuration, memory clock requests and temperature behavior. No verified per-component current yet. |
| **5** | eMMC supplies beyond CMD5 sleep | **0–0.5 mA** | Compare sleep against L17 power-off only after full card reinitialization works. L6 LPM alone does not test this. |
| **6** | GPIO contention/back-power | **0–0.5 mA** ordinarily; larger fault possible | Audit pins crossing into reset/unpowered devices; change one driver-owned pin group at a time. |
| **7** | PMIC auxiliary blocks/regulator overhead | **0–0.3 mA** ordinary excess; larger if an output is active | Compare subtype-decoded enables/modes against Linux; retain measurement and charger protection functions. |
| **8** | BCM shutdown/supplies | Expected **<0.1 mA** excess if shutdown is sound | Verify REG_ON, wake/UART pins and actual supply current; separate a shutdown input from physical rail removal. |
| **9** | External 32 kHz outputs | Likely small normally; wiring faults can change that | Establish output/consumer mapping, then test only unused outputs. Preserve RTC/MPM timekeeping. |

**Panel: there is a more specific omission than rail policy.** Firmware sends only `28` and `10`. The sturgeon AUO RM69080 vendor off sequence additionally waits after sleep-in, sends a delayed `00 00`, and sends **`4F 01`**. That is a concrete untested difference; its current effect is unknown. [FW display.c:449](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:449), [RM69080 off sequence:57](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/dsi-panel-auo-rm69080-hvga-video.dtsi:57).

Treat that full-off sequence as potentially requiring cold recovery. Do not append `4F 01` and assume the existing sleep-out wake path remains sufficient.

For the configured RM69080 panel, cold recovery needs:

- Supply/controller restoration with the vendor delays.
- Panel enable GPIO78 and reset GPIO25; reset sequence **low 5 ms, high 10 ms**.
- The panel’s complete initialization commands, including page selection, `18 66`, `07 6D`, TE enable, sleep-out, orientation and display-on, preserving packet types and delays.
- Brightness, address/window state and framebuffer repaint restoration.

The file’s “video” name is misleading: it specifies **command mode**, matching firmware. Sturgeon also includes alternative EDO panels, so confirm the actual panel before generalizing this sequence. [Panel selection:13](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-panel.dtsi:13), [commands:46](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/dsi-panel-auo-rm69080-hvga-video.dtsi:46), [reset:95](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/dsi-panel-auo-rm69080-hvga-video.dtsi:95).

The relevant supplies are **L15 2.8 V**, **L8 1.8 V**, **L4 1.2 V**. Inspect bases `0x014e00`, `0x014700`, `0x014300`. Linux full-off releases supply consumers; lowering L4’s mode is not equivalent to removing its load. **L8 also supplies the CPU PLL through an active-only consumer**, so preserve that requirement and leave the crashing L8 experiment out of routine runs. [Supply definitions:127](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-mdss.dtsi:127), [vendor power-off:64](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_dsi.c:64), [PLL consumer:1005](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226.dtsi:1005).

**Hub reset does not account for the hub/sensor supply current.** H lowers AP-status, asserts reset and stops UART. It neither removes the STM32 supply nor establishes that attached sensors have stopped autonomous operation. The vendor MCU binding provides handshake GPIOs and UART wiring, but no verified regulator mapping. [FW hub.c:459](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:459), [MCU DT:34](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-mcu.dtsi:34).

A useful comparison is: explicitly disable heart-rate/accelerometer/step/tilt services, allow normal MCU sleep, then compare with reset. Reset can leave downstream sensor configuration intact or prevent the MCU from completing shutdown. Supply isolation requires a schematic, board tracing or an established net map; I still cannot give a defensible hub-supply SPMI address.

**Linux CX/MX policy can now be stated more precisely.**

- **CX is S1, `smpa/1`.** GCC’s ordinary digital supply uses the both-set corner handle; CPU PLL digital uses an active-only handle. Clock levels map to NONE/SVS/NORMAL/SUPER_TURBO. Linux does not encode one universal “CX sleep = X µV” value here. [Regulator handles:129](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:129), [clock levels:166](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/clock-8226.c:166).
- USB’s DT levels are `<1 5 7>`. Its low-power request selects 1; the corner driver subtracts `CORNER_NONE`, making that a **raw RPM `corn=0` contribution**, not a request for a literal voltage. Other consumers can dominate. [USB levels:337](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226.dtsi:337), [corner translation:708](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:708).
- **MX is L3, `ldoa/3`.** CPR uses the active-only handle. The sleep-only handle seeds **750000 µV**. That is more than an unused-looking DT label: probe marks the initial voltage modified, and later aggregation includes every registered sleep-set handle. A higher both-set consumer can still raise the aggregate. [MX handles:207](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:207), [initial request:1486](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:1486), [aggregation:503](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:503).

Thus **750 mV is a real Linux MX sleep contribution**, but I cannot establish the final running aggregate or physical voltage from DT alone. Capture the driver’s complete request logging (`debug_mask` supports this), including `swen`, `uv`, `corn`, `vfc`, mode and load keys. Compare S1 base `0x011400` and L3 base `0x014200`, remembering that an AP-side read after waking normally sees restored active voltage. [Request logging:279](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:279).

**DDR remains an allocation question, not a demonstrated defect.** VDD-min residency does not identify DDR refresh current or prove identical Linux/firmware retention policy. Start with BIMC sleep requests and the CX/MX audit. I have not established a trustworthy sturgeon DDR self-refresh status register or DRAM supply map in this review; assigning a precise DDR current would be invented.

**GPIO and BCM checks remain useful despite small expected normal currents.** Read TLMM configuration and I/O state for touch GPIO16–19, hub UART0–3 and handshake pins, BT UART12–15/wake63–64/REG_ON67, and amplifier I²S pins. Touch’s L19-off experiment leaves LVS1 pull-ups powered and does not establish pin isolation, so a null Q result is not proof of zero remaining touch-related current. [Touch power:43](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch.c:43), [rail-off:374](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch.c:374).

BT-off already stops UART and lowers chip power control. The vendor likewise exposes GPIO67 rather than a verified physical rail switch. I found no source-backed BCM supply mapping that justifies naming a PMIC rail to remove. [FW bcm.c:212](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:212), [BCM DT:40](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-bcm.dtsi:40).

**PMIC/clock inventory:** inspect ordinary ADC enable controls, unused LPG/WLED/vibrator outputs, and regulator mode/enable state. Verify DRV2605 mode register `0x01` bit 6 at QUP2/`0x5a`: firmware requests standby, but the final write is unchecked. The powered-down TFA9895 should move down the list, rather than retaining an assumed mA-scale active-amplifier budget. [DRV2605 initialization:75](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/haptics_drv2605.c:75).

For regulator snapshots, capture type/subtype `+04/+05`, status `+08`, voltage `+40/+41`, mode `+45`, enable/hardware-follow `+46`, and pull-down `+48`. Do not infer sleep votes from these alone.

For 32 kHz, the USB sleep-clock branch is a concrete inspectable item, but I still lack a verified PM8226 external-output/net mapping for sturgeon. An enabled branch is not itself evidence of a significant load, and XO shutdown does not imply external sleep clocks are off. Keep RTC/MPM clocks intact.

**Measuring AsteroidOS by the same method requires handling its counter resets.**

A suitable future run would:

1. Use this same sturgeon, similar voltage and temperature, screen fully off and BT off. Record touch gesture and sensor-service settings; firmware’s reset-held hub is not functionally equivalent to ordinary Linux suspend.
2. Start logging locally before unplugging, retain data in RAM, and avoid an attached ADB session during measurement.
3. Record monotonic/boottime timestamps, shadow charge, raw OCV, battery and PMIC temperatures, calibration channel/settings, every trim write/readback, and 64-bit RPM residency/count deltas.
4. Perform both sparse long-suspend measurements and a controlled one-minute logging run, so logger wake overhead is measurable.
5. Apply the same interval exclusions and time-weighted trim normalization; report raw and normalized results together.

**Do not simply subtract two raw `0x40a8` values across Linux operation.** Linux’s BMS reads and resets the shadow counter during SOC calculation, accumulating it in software. Its `CHARGE_COUNTER_SHADOW` property returns the software accumulation plus the current raw contribution. Either use that property with its corrections documented, or instrument every raw read/reset and reconstruct a common raw-unit total. [Shadow property:1768](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1768), [reset during calculation:1847](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1847).

Linux cancels SOC calculation work during suspend while preserving hardware measurement. Capture actual calibration timing rather than assuming five-minute writes continue through sleep. [BMS suspend:5332](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:5332).

The target should be a matched Linux measurement with a trim/OCV audit. The historical 1.6 mA number remains an uncalibrated reference.

**5. Corrections and anomalies in §18 and the log.**

The important corrections are:

- **Residency is 99.03%, not 99.9%, for this day run.** Its one-second wake cadence is consistent with the USB deadline bugs above.
- **The observed trim range includes `bbcb`**, not just `bbce..bbdc`. Relative to bbd3, the retained range reaches −8 to +9 codes. At `bbcb`, the counter approaches zero and the main BMS counter briefly goes negative despite the unplugged state. [Log:2116](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:2116).
- **The quoted 1.9→0.34 mA scatter mixes populations.** I reproduce 1.907 mA as the raw **minute-sample** SD and 0.336 mA as the corrected **arm-mean** SD. With ending-trim correction, minute SD becomes 0.665 mA; raw arm-mean SD is 1.532 mA. With time-weighted trim and the same 0.519 coefficient, those corrected SDs are 0.548 and 0.296 mA.
- **A residual drift remains:** corrected early B arms average about 4.54 mA, late B arms about 4.01 mA using time-weighted trim and \(k=0.519\). Voltage, true offset drift and other state changes remain candidates.

The small-effect table changes when trim transitions are integrated correctly:

| Added measure | §18 saving | Time-weighted trim, \(k=0.519\) | Time-weighted trim, fitted \(k=0.5375\) |
|---|---:|---:|---:|
| USB L10/L20 off | +0.24 mA | **+0.167 mA** | **+0.145 mA** |
| Touch L19 off | +0.11 mA | **+0.021 mA** | **+0.005 mA** |
| L4/L6 LPM | −0.05 mA | **+0.069 mA** | **+0.050 mA** |
| Combined ABBA | −0.01 mA | **+0.004 mA** | **+0.024 mA** |

Positive means saving. These use neighboring B arms, full post-settling intervals, and the three complete ABBA blocks. They are not narrow-confidence estimates. USB rails retain a small positive indication; **touch, L4/L6 and the combined bundle remain unresolved around zero**. The data does not support adding the individual point estimates into a guaranteed saving.

Two harness issues should remain separate from the feature review:

- **Partial USB-rail failure can leave incorrect state.** L10 can change successfully while L20 fails; `usb_rails_off` then does not describe the mixed state, and a later “on” request can return early. `usb_restore()` also ignores the rail-restore result. Track and restore each rail independently. [usb.c:325](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:325).
- **LDO baseline restoration leaves the sleep `ma=1` key behind.** The “off” path sends only `lsmd`, so it does not restore the prior request dictionary. That may be immaterial with forced HPM, but “as active” overstates what was restored. [rpm.c:288](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:288).

I checked the **112 retained, recognizable RPM acknowledgements**: their returned message IDs match the logged requests. Thus I found no evidence that mismatched acknowledgements caused this run’s results, although the transport still does not enforce that match.

The L8/L19 resets are evidence against those experimental profiles, not proof of a particular electrical cause. Preserve the existing early PON/warm-reset/power-off reason capture when investigating them; missing retained logs alone cannot distinguish a supply failure from every other reset mechanism. [FW pmic.c:25](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:25).

Finally, reattachment produces BT advertising/IRK errors before recovery. They occur after the sleep measurement and do not explain its baseline, but should be tracked as harness restoration defects. [Log:2617](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor-2026-11-03-sturgeon.txt:2617).

My recommended next order is **USB deadline repair and unplugged-only feature cleanup; averaged, verified trim calibration; a fresh long-sleep baseline; then complete panel-off and matched AsteroidOS measurements**.
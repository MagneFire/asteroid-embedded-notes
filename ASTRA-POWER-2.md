# Codex (gpt-6-astra) power follow-up, 2026-11-03

Follow-up to ASTRA-POWER.md after the screen-off VDD-min result (POWER.md §16), the USB recovery failure and the 1-minute functional cycle. Not yet checked against hardware: the RPM record names, rail states and the USB recovery sequence are proposals.

The new residency result shifts the investigation decisively toward persistent peripheral and supply load. **I would prioritize a recoverable USB shutdown, then explicit regulator policy—especially USB and display supplies.** I would retain PLL/GDSC rest for vendor parity, without assigning it a measured saving.

This report covers Sturgeon only. I read the working tree, notes, functional log, analysis script, and relevant vendor sources. No files were changed, no commits were made, and nothing was run on a device. Current hardware states that are not logged remain unknown.

**1. The zero “XO” counter does not establish that XO stays on.**

The vendor’s 8226 DT selects sleep-statistics version 2 at `0xfc19dba0`; its driver reads **two records**, each **48 bytes**. Their layout is:

| Offset | Field |
|---|---|
| `+0x00` | `u32 stat_type`: four ASCII mode-name bytes |
| `+0x04` | `u32 count` |
| `+0x08` | `u64 last_entered_at` |
| `+0x10` | `u64 last_exited_at` |
| `+0x18` | `u64 accumulated` |
| `+0x20` | `u32 client_votes` |
| `+0x24` | Three reserved words |

Thus the two bases really are `0xfc19dba0` and `0xfc19dbd0`. Timestamps use the 19.2 MHz architectural counter. The kernel obtains the displayed name from `stat_type`; **it does not identify the first record as XO shutdown by its address**. See [DT:361](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-v2-pm.dtsi:361), [layout:61](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/soc/qcom/rpm_stats.c:61), [name decoding:92](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/soc/qcom/rpm_stats.c:92), and [record count:286](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/soc/qcom/rpm_stats.c:286).

**My working interpretation is that these are `vlow` and `vmin` mode records, and the watch spends its sleep time in the latter.** Upstream Qualcomm statistics code explicitly identifies `vlow` and `vmin` as RPM mode names. That supports the interpretation, but does not prove this watch’s record order or RPM accounting semantics. [Upstream implementation](https://android.googlesource.com/kernel/common.git/+/ee5814dddefbaa181cb247a75676dd5103775db1/drivers/soc/qcom/qcom_stats.c).

The next diagnostic should read both names:

- `readl(0xfc19dba0)`: expected `0x776f6c76` if `"vlow"`.
- `readl(0xfc19dbd0)`: expected `0x6e696d76` if `"vmin"`.
- Also record both `client_votes` words and entry/exit timestamps.

The current harness never reads these names; its `xo` and `vmin` labels are hardcoded. [Firmware main.c:823](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:823).

**Do not require both counters to increment.** Separate mode counters need not be cumulative counters for nested hardware conditions. Entering a deeper mode can leave a shallower mode’s count unchanged. Conversely, the Linux reader alone cannot prove “this particular RPM’s VDD-min always turns off every XO output.” That requires RPM implementation documentation or independent clock evidence.

My conclusion is therefore:

- **Zero in record 0 is not evidence of a stuck XO.**
- **VDD-min with XO shut down is the leading interpretation**, pending name verification.
- My earlier suggestion that both records must increment was too strong.
- VDD-min residency does **not** establish that all peripheral rails or exact CX/MX voltages match Linux.

At 99.97% residency, an illustrative 90 mA non-VDD-min current contributes only approximately `0.0003 × 90 = 0.027 mA`. The previous 0.4 mA wake-budget estimate is superseded by this measurement. Transition energy is not independently measured, but it is no longer the leading explanation of 7 mA.

**2. USB should enter low power while unplugged; recovery should establish a fresh attachment.**

The vendor explicitly supports this case. Sturgeon inherits peripheral mode, PMIC OTG control, L10/L20 supplies, and manual D+ pull-up control. Its board override also **removes `disable-reset`**, allowing the vendor reset path. [USB DT:332](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226.dtsi:332), [Sturgeon override:29](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-common.dtsi:29).

On cable removal, the vendor stops the peripheral and moves to `B_IDLE`. Its ChipIdea disconnect callback clears the same two ULPI external-VBUS bits that the harness clears. This is a gadget disconnect transition, not just a PHY clock operation. [OTG removal:2822](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:2822), [ChipIdea disconnect:60](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/chipidea/ci13xxx_msm.c:60).

The subsequent unplugged suspend path:

1. Masks the main USB IRQ.
2. Sets and polls PHCD.
3. Asserts STP; asynchronous interrupt enable is conditional and unnecessary for ordinary unplugged PMIC-controlled operation.
4. Enters PHY retention where supported.
5. Gates core/interface clocks and releases its XO vote.
6. **Disables L10 and L20**, releasing their load requests.
7. Lowers its digital/CX requirement and drops its bus-performance vote.

The PMIC-control capability selection enables PHY collapse. [Capabilities:4868](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:4868), [suspend:965](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:965), [clocks/supplies:1065](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1065), [regulator disable:242](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:242).

`msm_otg_resume()` reverses the resources actually removed: bus vote, XO, clocks, analog supplies, CX and retention/clamps. It then clears asynchronous-enable/STP, clears PHCD and polls it, and finally restores interrupt handling. A PHCD timeout invokes PHY/link reset. It does **not** unconditionally reset the controller on every successful resume. [Resume:1147](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1147), [PHCD recovery:1229](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1229), [IRQ restoration:1319](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1319).

The harness currently performs only part of that lifecycle. Its exit does not reject a PHCD-clear timeout, `phy_select()` discards ULPI errors, and neither controller endpoints nor TinyUSB/application state are rebuilt. [usb.c:312](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:312), [phy_select:48](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:48).

**Why enumeration fails remains a diagnosis, not a proven root cause.** `0x88000205` reports connected/enabled and PHCD clear; it proves neither functioning EP0 nor correct address, descriptors, interrupts, or software queues. Plausible failures include:

- PHY/link state survives the bit-level exit incorrectly.
- Manual disconnect/reconnect was not accompanied by a matching stack lifecycle.
- A bus-reset/port-change event was missed or mishandled.
- Stale ADB transfer state keeps `usb_busy()` true after transport failure.

That last possibility fits the spin: `usb_busy()` combines PORTSC connectivity with queued events, `adb_tx_busy`, or pending ADB work, and `power_idle()` returns immediately when busy. It is **not enough evidence to call this an IRQ storm**. [usb_busy:386](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:386), [power_idle:219](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/power.c:219).

The DCD deserves particular scrutiny: reset interrupts are disabled, and reset handling is reached through a port-change interrupt followed by inspection of the reset status bit. Log raw `USBSTS`, `USBINTR`, `DEVICEADDR`, endpoint status and the three busy reasons before changing this behavior. [DCD initialization:243](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:243), [interrupt handler:606](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:606).

**Concrete recovery sequence I recommend implementing and validating:**

1. **On confirmed removal, while registers remain accessible:** stop accepting transfers, detach the console, reset ADB transport state, disconnect and deinitialize TinyUSB. Mask the USB IRQ. Clear manual pull-up/session assertion. Then enter PHCD/STP and, separately, resource collapse. Keep PMIC attach wake armed.

2. **On PMIC attachment:** process recovery before any ordinary USB polling or connectivity-register access. Restore required bus/XO votes, clocks and any disabled supplies; restore CX before releasing retention. Clear STP/async-enable and clear PHCD with a bounded wait. Read a ULPI identification register to distinguish “PHCD cleared” from a working PHY interface.

3. **For this unplugged-recovery feature, initially use a full reset on each attachment.** Mirror the vendor sequence:
   - Clear AHB bypass before asynchronous block reset.
   - Gate the relevant clocks, assert `GCC_USB_HS_BCR` at `0xfc400480`, hold approximately 1 ms, deassert, then restore clocks.
   - Select ULPI and issue a bounded USBCMD controller reset.
   - Restore AHB burst/mode configuration.
   - Follow the vendor’s settling/POR sequence: its full reset waits 100 ms, pulses PHY POR, writes the PHY tuning overrides, then pulses POR again.
   - Sturgeon overrides are register/value pairs `80=44`, `81=68`, `82=3c`, `83=f3`.

   The primary PHY control register is USB base `+0x240`, hence `0xf9a55240`; POR is bit 0. Preserve unrelated bits. [Block reset:426](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:426), [full reset:551](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:551), [POR definitions:100](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/usb/msm_hsusb_hw.h:100).

4. **Reinitialize TinyUSB and the DCD coherently.** Calling `tusb_init()` again without deinitialization is insufficient: the device initialization returns immediately when already initialized. Deinit clears the device state and event queue, but the custom ADB driver has an empty init and no deinit callback, so explicitly clear `adb_open`, `adb_tx_busy`, `adb_rx_queued`, and call `adb_reset()`. [TinyUSB guard:538](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/device/usbd.c:538), [deinit:604](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/device/usbd.c:604), [ADB reset:193](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:193).

5. **Keep attachment and IRQ delivery deferred until initialization is complete.** Currently DCD init starts RUN/STOP and TinyUSB init unmasks the IRQ. A recovery path should defer those actions until the final controller reset, endpoint-list setup, PHY tuning and session wiring are complete. Reapply reset-sensitive settings after the final reset. Clear stale W1C interrupt/endpoint status while quiescent, then assert manual session-valid, issue a barrier, connect and unmask. The vendor explicitly places a barrier after manual-connect writes. [Vendor connect:91](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/chipidea/ci13xxx_msm.c:91).

6. **Bound every recovery wait**, including DCD `ENDPTPRIME`, `ENDPTFLUSH` and reset loops. A dead controller must not hang inside `tud_deinit()`. Failure should leave USB disconnected, interrupts masked, application queues cleared, and a delayed retry available. Recovery deadlines must participate in the main-loop sleep deadline.

This is a concrete proposed implementation, **not a tested recovery guarantee**. A simple disconnect/connect is a useful first diagnostic, but here it only toggles RUN/STOP; it does not rebuild endpoints or stack state. A generic ULPI function-reset command also should not be treated as equivalent to the vendor’s block-reset/POR/tuning sequence. [DCD disconnect/deinit:256](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:256).

Unplugged collapse and attached host-bus suspend should be distinct states. Start with unplugged collapse; attached suspend has remote-wakeup and resume requirements that this sequence intentionally does not attempt to preserve.

**3. Persistent-load candidates and the state reads that would distinguish them.**

The estimates below are **investigation ranges in battery mA**, not measurements or an additive budget. Vendor load requests in µA select regulator operating modes; they are not measured consumption.

First, establish a regulator inventory. Firmware SPMI addresses encode `SID << 16 | peripheral << 8 | offset`. For the SID1 regulators, read `base+0x04/+0x05` for type/subtype, `+0x08` status where applicable, `+0x40/+0x41` voltage range/code, `+0x45` mode, `+0x46` enable and `+0x48` pull-down. Enable bit 7 and HPM bit 7 are defined by the vendor; mode interpretation must respect regulator subtype and hardware-follow bits. [SPMI encoding:1](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/spmi.c:1), [register definitions:115](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/qpnp-regulator.c:115).

**An AP-side dump taken “in the sleep loop” still runs while the AP is awake.** It can establish persistent peripheral settings, but generally cannot observe the RPM’s live collapse-time CX/MX state: waking to read it may already restore active settings. Likewise, SPMI hardware registers do not reveal separate active/sleep vote dictionaries.

For those dictionaries, retain/log the firmware’s requests and acknowledgements. The current RPM client supplies no generic resource-state read API. The relevant keys are `swen`, `uv`, `ma`, `lsmd`, `ssmd`, `corn`, and `vfc`; LDO `lsmd=0` is IPEAK and `1` HPM. **Absent a sleep request, the active request remains effective during RPM-assisted collapse.** The contrary comment at firmware `rpm.c:205` remains incorrect. [Vendor keys:113](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:113), [default rule:192](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:192).

| Priority | Candidate and expected size | Read from firmware | Vendor comparison and interpretation |
|---|---|---|---|
| **1** | **USB analog supplies remaining after U:** perhaps **0.1–1 mA additional** beyond PHCD/STP; several mA possible if PHY shutdown is incomplete | L10 `0x014900`, L20 `0x015300`; RPM `ldoa/10`, `ldoa/20`. Also PHY control, ULPI and clock registers | Vendor disables both on unplugged collapse. Active loads are 50,000 µA each; fallback regulator-LPM loads are 4,000 µA, but unplugged PMIC control takes the collapse path. Board voltages are 1.8 V and 3.075 V. [Supply implementation:187](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:187), [L20 configuration:405](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:405). |
| **2** | **Panel/DSI supplies with screen off:** **0.2–1.5 mA** | L15 `0x014e00`, L8 `0x014700`, L4 `0x014300`; RPM `ldoa/15,8,4`. Read panel enable GPIO78 and reset GPIO25 | Firmware sends DCS display-off/sleep-in but no rail shutdown. Vendor full-off releases supplies; AOD/ULP separately lowers loads. [Firmware:449](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:449), [vendor off:64](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_dsi.c:64). |
| **3** | **Other inherited regulator enables/HPM modes:** **0.1–1 mA aggregate**, potentially more with an active attached load | Inventory all implemented SID1 LDOs, SMPS control blocks and LVS1. LDO bases follow `0x014000 + 0x100×(n−1)` for implemented LDO numbers; do not assume missing numbers exist | The vendor explicitly manages consumers; firmware inherits much of this state. An enabled rail is a candidate, not proof of waste. The PMIC map identifies implemented blocks. [Map:611](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:611). |
| **4** | **eMMC supplies beyond E:** **0.05–0.5 mA** additional; card awake-versus-sleep can be larger | L17 `0x015000`, L6 `0x014500`; RPM `ldoa/17,6`; card sleep state and SDCC clocks | E sleeps the card and gates clocks, leaving supplies untouched. Vendor permits disabling L17; L6 is always-on. **L6 LPM is conditional**, discussed below. [E implementation:604](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/emmc.c:604), [MMC DT:133](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-720p-mtp.dtsi:133). |
| **5** | **Touch supplies beyond T:** **0.05–0.5 mA** additional | L19 `0x015200`, LVS1 `0x018000`; RPM `ldoa/19`, `vsa/1`; RMI F01 control and attention pin | Firmware explicitly enables both without load/mode requests. T changes sensor mode only. Vendor gesture suspend keeps touch available; non-gesture suspend sleeps it and disables `pwr_reg`. [Firmware power:43](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/touch.c:43), [vendor suspend:3851](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3851). |
| **6** | **Sensor hub and sensors:** **0.1–3 mA total candidate**, with no defensible estimate for residual after H | GPIO87 reset; GPIO108 AP status, GPIO62 wake request, GPIO65 wake indication, UART1 state. **Supply-to-PMIC mapping not established** | H holds the STM32 in reset; that does not prove its supply or attached sensors are off. Vendor suspend lowers AP status and enables MCU wake, preserving sensor service. The MCU DT has GPIO/UART wiring but no regulator phandle. [MCU DT:34](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-mcu.dtsi:34), [vendor sleep:145](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmcu/hwmcusleep.c:145). |
| **7** | **GPIO contention/back-power:** typically **0.02–0.1 mA per opposing weak pull**, aggregate **0–0.5 mA**; hard back-power can exceed this | `GPIO_CFG(n)=0xfd511000+0x10n`, `GPIO_IO(n)=0xfd511004+0x10n`; inspect mux, pull, direction, input/output level | Vendor has suspended pin tables, e.g. BT I²S GPIO/pulldown/2 mA. Audit actual board pins and powered-down peripherals before applying them. [Firmware map:83](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/msm8226.h:83), [vendor example:605](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:605). |
| **8** | **BT chip with BT off:** expected **well below 0.1 mA incremental**, unless shutdown/back-power is faulty | GPIO67 REG_ON low; UART4 stopped; GPIO12–15 and wake pins63/64. **External supply mapping not established** | Firmware stops UART and drops chip enable; vendor rfkill also drops its power GPIO. A GPIO named “power” does not prove the external rail is disconnected. [Firmware:212](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:212), [vendor:304](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/bluetooth/nitrous.c:304). |

Three qualifications materially affect those rankings:

- **Display loads are independent of PLL/GDSC rest.** Vendor active requests are 100,000 µA on each supply; ULP requests are L4 **1,000 µA**, L15/L8 **100 µA** each. Full-off releases the supplies. The absence of a PLL/GDSC saving says nothing about this untested policy. L8 also supplies clock PLL consumers, including an active-only handle, so “panel off → L8 off everywhere” is wrong. [Display loads:163](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-mdss.dtsi:163), [L8 handles:278](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:278), [PLL consumer:1006](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226.dtsi:1006).
- **L6’s 250 µA request is not established Sturgeon sleep behavior.** The driver applies it only with `qcom,vdd-io-lpm-sup`; I did not find that property in the inherited Sturgeon configuration. Its presence in the current-level pair alone is insufficient. [Property parsing:1303](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1303), [conditional LPM:1919](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1919).
- **LVS1 is shared.** Sturgeon’s audio DT also names it, and the board PM file places an always-on declaration on its resource node. That placement alone does not establish how the child regulator constraints are parsed, but it reinforces that touch is not its only concern. [Audio supply:42](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-sound.dtsi:42), [board declaration:143](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-pm.dtsi:143).

The PMIC and retention candidates need a separate treatment:

| Candidate | State reads and vendor policy | Expected opportunity |
|---|---|---|
| **Charger/BATIF** | Read SID0 charger status `0x001010`, control `0x001049`, USB status `0x001310`, BATIF thermal reference `0x00124a`, and relevant BATFET control. Vendor deliberately keeps thermal reference forced on. Its BATFET LPM register selection depends on SMBB subtype; do not transplant one address across types. [Firmware register map:211](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:211), [vendor BATFET:1926](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1926), [thermal reference:6082](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:6082). | **Low priority, 0–0.2 mA guessed excess** absent an abnormal setting. Your existing BATFET experiment is stronger evidence than generic speculation. |
| **BMS/IADC/VADC** | BMS at `0x004000`, BMS-IADC `0x003800`, ordinary IADC `0x003600`, VADC `0x003100`. Firmware clears VADC enable after conversion. Vendor BMS suspend cancels software work but preserves hardware measurement. [VADC cleanup:180](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:180), [BMS suspend:5332](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:5332). | **Tens to hundreds of µA order-of-magnitude**, not a sourced PM8226 specification. Do not disable the meter to obtain a lower reading. |
| **LPG/WLED/PMIC vibrator** | SID1 LPG bases `0x01b100`–`0x01b600`; inspect channel enable/control and output routing. WLED `0x01d800`; PMIC vibrator enable `0x01c046`. Sturgeon disables the WLED node; PMIC vibrator is disabled in the base DT. Disabled Linux nodes do not prove bootloader hardware is off. [PMIC blocks:786](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:786), [Sturgeon WLED:86](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-common.dtsi:86). | **Near zero expected** when unused; potentially mA if an output/boost remains enabled. |
| **Actual Sturgeon vibrator: DRV2605** | QUP2, I²C `0x5a`, mode register `0x01`, GO `0x0c`, enable GPIO60. Firmware already enters standby; vendor also returns it to standby. [Firmware:118](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/haptics_drv2605.c:118), [vendor:984](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/haptics/drv2605.c:984). | **Below 0.1 mA guessed** in correct standby; check failed initialization paths if the mode differs. |
| **CX/MX and memory/platform retention** | CX S1 control base `0x011400`, RPM `smpa/1` with corner/floor keys; MX L3 `0x014200`, RPM `ldoa/3`. Vendor defines both-set and active-only CX handles, active-only MX for CPR, and a sleep-only MX handle initialized to 750 mV. Definition does not prove a live 750 mV sleep request or final aggregate voltage. [CX:121](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:121), [MX:207](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:207). | Allow **roughly 1–3 mA as an unallocated platform-floor hypothesis**, not a measured intrinsic floor or recoverable saving. Audit requests before attempting voltage changes. |

I cannot honestly give a sensor-hub or BCM supply SPMI address from the files reviewed: their board bindings expose control signals, not a verified physical supply net. That needs a schematic, board tracing, or an already-known net map.

One additional candidate is the **TFA9895 speaker amplifier**. Firmware’s current speaker code only probes its revision; it does not establish a shutdown state. I would inspect that after the named rail inventory, rather than assign it a current without a verified power-control register map. [speaker.c:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/audio/speaker.c:21).

**4. Predictions for the overnight leave-one-out and the next decision.**

My provisional expectation is **all-on around 3–4 mA, settled none around 7–9 mA, and a bundle saving around 3–6 mA**. Those are forecasts, not confidence intervals. A settled none result near 11 mA would require explaining the difference from the earlier 7 mA baseline.

I would expect U to be a leading contributor, H potentially substantial, and R comparatively small given the residency and zero GCC vote. E and T remain credible contributors, but the one-minute cycle is too mixed to allocate their savings reliably.

For example, arm 6 starts at 524.778 s; its sample at 566.843 s covers the preceding 60.005 s, including the previous arm and hub initialization. It reports only 50.828 s in VDD-min. The following none interval reports 10.919 mA with 59.924 s in VDD-min, so hub boot does not explain every high reading. [Functional log:137](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-functional-2026-11-02-sturgeon.txt:137).

Use the analysis script’s complete mirrored cycles, trim and mismatch filtering. Its reported part savings are **conditional savings with the other four measures enabled**, not standalone savings. [powerlog.py:129](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:129).

| Overnight outcome | Interpretation and next step |
|---|---|
| **U is large** | Implement the USB lifecycle above first. Then compare PHCD/STP alone against added clocks/retention/L10/L20 collapse. Validate repeated attach, removal, charger-only attachment and failed enumeration. |
| **H is large** | Separate sensor-service load from UART load and reset effects. Compare normal sensor configuration, services disabled with MCU alive, UART idle, and reset. Permanent reset sacrifices steps/tilt and is not ordinary vendor suspend. |
| **E is large** | Promote card sleep and clock gating to storage-owned runtime idle. Keep rail removal as a separate experiment requiring full card power-cycle support. |
| **T is large** | Add a real RMI sleep/gesture policy. Preserve the intended wake behavior; deep sensor sleep cannot silently replace touch-to-wake. Test L19 mode/off separately. |
| **R is large despite unchanged residency** | Investigate which bus vote matters and whether it changes retention policy or peripheral behavior. Verify the `vmin` label. VDD-min residency alone does not reveal every clock/rail state. |
| **Bundle large, all conditional parts small** | Test single measures against none, then targeted pairs. This is consistent with overlapping/redundant savings: several measures may each remove the same load, so removing one from all-on changes little. Also rule out state carryover. |
| **Conditional parts sum to more than bundle** | Complementarity is plausible: multiple measures may be jointly necessary for a low-power condition. Prioritize U×R, H×E and relevant pin/rail interactions. |
| **Strong order dependence or negative savings** | Check restoration, asynchronous hub startup, eMMC re-wakes, temperature/voltage drift and sampling windows before accepting a physical explanation. |
| **All-on remains near 7 mA** | The functional low readings did not reproduce. Move to USB rail collapse and the persistent rail inventory; retain no claimed bundle saving. |
| **All-on reproducibly reaches 2–3 mA** | Stop treating 7 mA as an intrinsic platform floor. Preserve that state as the reference and price back required functionality individually. |

Also inspect within-arm trends and retained intervals, not only cycle means. A full shadow interval should lie after the settling cutoff when comparing sensitivity to trimming; the script currently filters by the sample’s ending timestamp. [powerlog.py:81](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:81).

**5. Shape of a production implementation.**

The firmware already has the right broad separation: board data describes wiring, drivers own hardware operations, `power_update()` handles user-visible power transitions, and `power_idle()` decides when the cluster may sleep. Preserve that structure.

- **USB:** a driver-owned state machine such as attached, detached, collapsed, recovering and fault. Use PMIC VBUS as cable truth. Make `usb_poll()`, `usb_busy()` and `usb_connected()` safe while collapsed; avoid MMIO into gated hardware. Process attach recovery before polling. Keep disconnect/session state, IRQ state and resource ownership explicit.

- **RPM policy:** board/platform tables for active and sleep requirements, with acknowledged desired/applied state. Aggregate shared consumers before sending votes. Initialize explicit sleep policy at boot because warm-reset inheritance is already a concern. Match acknowledgements to requests and propagate failures. Avoid sending unchanged votes on every idle pass.

- **eMMC:** retain the existing transfer-time wake in `xfer()`, and sleep after a quiet interval when no operation is pending. Flush and wait for card readiness before CMD5; preserve the selected clock rate. Reapply idle after calibration or settings I/O naturally through the storage policy. Risks are data integrity, timeout recovery and unnoticed background I/O. [Transfer-time wake:644](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/emmc.c:644).

- **Touch:** board/driver-supported active, gesture and deep-sleep modes, selected on display/user-policy transitions. Deep sleep should mask attention wake; resume should restore controller state and drain pending status before unmasking. Rail removal requires reset/reinitialization and protection against I²C back-power.

- **Hub:** retain AP-status/wake handshake for ordinary sleep. Add explicit service configuration and UART idle management. Use reset/off only for a deliberate sensors-disabled mode. Holding reset as the default would lose the functionality the MCU exists to preserve. The existing sleep callback also sends a step flush after each cluster wake, which can recreate UART work. [hub.c:488](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:488).

- **Display:** keep active, AOD and full-off supply profiles distinct. First implement ULP load policy without removing panel power. Full-off rail shutdown needs a complete cold panel initialization path; the current wake operation is only sleep-out, 120 ms delay and display-on. Shared L8 ownership and board-specific panel-enable/reset sequencing are the main risks. [display_wake:458](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:458).

- **Pins and unused peripherals:** add small board pin-state tables applied by the owning driver when a peripheral stops. Preserve wake inputs and avoid driving into an unpowered chip. A global blanket pulldown operation would obscure ownership and can introduce the very leakage being investigated.

The immediate sequence I would choose is **analyze the overnight cycles, verify the RPM mode names, implement recoverable unplugged USB LPM, then measure USB and display supply policy separately**. The unresolved hardware facts are the actual inherited rail modes, live collapse-time CX/MX settings, and the hub/BCM physical supply mapping.
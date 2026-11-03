# Codex (gpt-6-astra) power round 3, 2026-11-03

Review of the USB unplugged-collapse code and of the remaining 3-4 mA floor after the leave-one-out run (POWER.md §17). Proposals, not yet checked on hardware.

**The next targets should be USB analog power, panel supply policy, and explicit regulator sleep votes. But first fix the USB reset bug and instrument the current-meter drift.** The overnight run supports a large U saving; it does not yet establish a stable 3–4 mA floor.

This is a read-only Sturgeon report. I inspected the working tree, earlier reports, vendor sources and overnight log, and reran the local analysis script. I changed no files, made no commit, and ran nothing on a device. References below distinguish firmware **FW**, vendor kernel **K**, and notes **N**.

**1. USB review: the lifecycle is substantially improved, but recovery still has concrete failure paths.**

The highest-priority findings are:

| Priority | Finding | Consequence |
|---|---|---|
| **Fix first** | AHB2AHB bypass uses the wrong bit | The asynchronous-reset workaround is ineffective when bypass is enabled |
| **Fix first** | Recovery continues after failed clocks, resets and ULPI writes | Can access unavailable hardware, connect a broken controller, and permanently suppress retry |
| **Fix first** | EP0 still contains an unbounded wait | Enumeration can hang the main loop |
| **Fix next** | DCD starts the controller and enables IRQ delivery before final PHY/session setup | Host events can arrive during incomplete recovery |
| **Fix next** | CDC console is not explicitly detached | Console callbacks can survive stack teardown |
| **Fix next** | USB deadlines do not participate in idle scheduling | “Two seconds unplugged” is not a bounded two-second deadline |
| **Missing feature** | VBUS presence is treated as data-host attachment | Charger-only attachment keeps USB up indefinitely |

**The bypass mask is definitely wrong.** Firmware clears `BIT(2)` at `USB_AHB_MODE`, address `0xf9a55098`. The vendor defines `AHB2AHB_BYPASS` and its mask as **`BIT(31)`**, and clears that bit before asserting asynchronous block reset. This matters only when bit 31 is set, so successful replug tests would not invalidate the finding. [FW usb.c:390](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:390), [K msm_hsusb_hw.h:55](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/include/linux/usb/msm_hsusb_hw.h:55), [K phy-msm-usb.c:460](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:460).

**The teardown/reinitialization API pairing is correct in this TinyUSB checkout.** `tud_deinit(0)` disables the DCD interrupt, disconnects, deinitializes the controller/classes, deletes the event queue and resets `_usbd_rhport` to invalid. A subsequent explicit `tusb_init(0, &rh)` reaches `tud_rhport_init()` and rebuilds the device stack. The remaining top-level role assignment does not block this. Explicit ADB cleanup is necessary because its class driver has an empty init and no deinit callback; the new clearing of the three ADB flags plus `adb_reset()` addresses that. [TinyUSB usbd.c:604](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/device/usbd.c:604), [TinyUSB tusb.c:112](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/tusb.c:112), [FW usb.c:196](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:196).

There are nevertheless several error-handling problems:

- `controller_init()` silently continues after its reset timeout.
- `phy_select()` discards the ULPI result.
- All four override writes discard their results.
- `usb_collapse()` gates clocks even when PHCD failed, then records `usb_down=true`.
- `usb_restore()` accesses `USB_AHB_MODE` even if `clock_on()` failed. Its `&&` also skips enabling the system clock if AHB failed.
- Recovery sets `usb_down=false` before TinyUSB initialization succeeds, and calls disconnect/select/connect even after `tusb_init()` fails.
- With VBUS still present and `usb_down=false`, later `usb_cable(true)` calls do not retry.

Thus the current `ok` flag is diagnostic text, not a recovery policy. A failed PHCD exit followed by a successful full reset could legitimately recover; a failed clock or final reset cannot simply be ignored. Recovery needs a final validated result and a disconnected fault state with a scheduled retry. [FW usb.c:59](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:59), [FW usb.c:362](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:362).

**The loops are only partly bounded.** The newly bounded DCD reset/prime/flush loops neither report timeout nor stop subsequent operations. For example, `bus_reset()` can clear/reuse queue-head memory even though flush never completed, and `dcd_init()` still returns success after reset fails. Their million-iteration limits are CPU-speed-dependent, not elapsed-time deadlines.

Two unbounded loops remain:

- `qhd_start_xfer()` waits forever for EP0 `ENDPTSETUPSTAT` to clear. This is on the enumeration path.
- `dcd_edpt_iso_activate()` waits forever for flush. It is dormant for the present CDC/ADB descriptors, but the blanket claim that flush waits are bounded is incorrect.

[FW dcd_ci_hs_msm.c:187](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:187), [FW dcd_ci_hs_msm.c:218](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:218), [FW dcd_ci_hs_msm.c:455](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:455), [FW dcd_ci_hs_msm.c:492](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:492).

**The POR/override order is right.** The vendor performs block reset, link reset/AHB setup, waits 100 ms, pulses PHY POR, applies the override sequence, then pulses POR again. The new 15 µs pulse meets its stated minimum 10 µs. Sturgeon’s `80=44, 81=68, 82=3c, 83=f3` values match its DT override. [K phy-msm-usb.c:528](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:528), [K phy-msm-usb.c:573](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:573), [K sturgeon-common.dtsi:29](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-common.dtsi:29).

Two ordering differences remain important:

1. `controller_init()` calls `phy_select()`, which asserts external session-valid before the rest of recovery.
2. TinyUSB subsequently performs another controller reset; DCD init starts RUN/STOP, and TinyUSB immediately unmasks the IRQ. Only afterward does firmware disconnect, reapply `phy_select()`, and reconnect.

Defer RUN/STOP and IRQ unmasking until endpoint setup, reset-sensitive AHB/session configuration and PHY configuration are complete. Include a barrier before final attachment: the vendor explicitly requires one after manual-connect writes. Do not assume the second controller reset preserves every setting programmed before it; verify/reapply AHB configuration after the last reset. [FW dcd_ci_hs_msm.c:243](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/dcd_ci_hs_msm.c:243), [TinyUSB usbd.c:595](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/third_party/tinyusb/src/device/usbd.c:595), [K ci13xxx_msm.c:91](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/chipidea/ci13xxx_msm.c:91).

Other vendor differences worth preserving:

- Suspend masks IRQ, obtains PHCD, asserts STP, handles retention, executes a barrier, then removes clocks/resources. PHCD failure triggers reset/retry or failure—not unconditional success.
- Resume restores bus/XO/clocks, analog supplies and CX/retention state before clearing STP/PHCD.
- Vendor clears both STP and asynchronous-enable on resume. Firmware clears only STP.
- PMIC-controlled reset disables the PHY’s OTG comparator through ULPI `0x88`’s set alias. Firmware does not establish that state.
- L10/L20 removal, CX release and a USB-owned bus vote are still absent.

These are parity differences; the existing 99.9% VDD-min result means they should not all be described as proven residency blockers. [K phy-msm-usb.c:965](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:965), [K phy-msm-usb.c:1065](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1065), [K phy-msm-usb.c:1173](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1173), [K phy-msm-usb.c:615](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:615).

**Main-loop behavior while down is mostly sound.** `usb_poll()` returns immediately; `usb_connected()` avoids gated MMIO; `usb_busy()` short-circuits through that false result. Consequently, these functions do not themselves keep `power_idle()` spinning while `usb_down` is true. Collapse/recovery run synchronously in the main loop, and `tud_deinit()` already masks the GIC interrupt through the DCD hook. [FW usb.c:304](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:304), [FW usb.c:461](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:461), [FW power.c:219](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/power.c:219).

The remaining integration problems are:

- **CDC teardown:** ADB reset detaches an ADB shell, but does not guarantee detachment of a CDC terminal. `tud_umount_cb()` only logs, and CDC deinit does not call the line-state callback. Explicitly detach/cancel USB-owned console work before deinit. `cdc_out()` also has no elapsed-time limit while waiting for a connected host; cable processing cannot run while it is trapped there. [FW usb.c:256](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/usb.c:256), [FW adb.c:135](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/usb/adb.c:135).
- **Polling description:** the code polls PMIC VBUS at most once per second, not each pass. Its check occurs after `usb_poll()` and `console_poll()`. Neither that polling deadline nor `gone_t+2000` limits `app_next`. With falling-edge wake disabled, removal detection and collapse can wait until a later scheduled wake. Add a USB deadline; avoid imposing perpetual 1 Hz wakeups once safely down. [FW main.c:556](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:556), [FW main.c:885](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:885), [FW pmic.c:405](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:405).
- **Attach during teardown:** recheck VBUS before final clock/rail removal, and process a latched attach before another long sleep.
- **Harness semantics changed:** U now permits automatic collapse rather than immediately applying PHCD/STP. `usb_phy_lpm()` always returns true; `usb_phy_in_lpm()` reports a software flag even after PHCD failure. “Have U” therefore needs hardware-success semantics before it remains trustworthy experimental evidence.

**Charger-only attach needs a distinct state.** PMIC VBUS proves a source is present; it does not identify SDP/CDP/DCP or prove enumeration. Present firmware restores USB for every source and never collapses while VBUS remains present. Add source classification, enumeration timeout/recovery, appropriate charging-current policy, and charger-specific USB suspend.

The vendor detects charger type before starting the peripheral. For DCP it enables `VDP_SRC` using ULPI `0x85`, then runtime-suspends; its suspend explicitly forbids PHY retention/power-collapse while that source is required. Therefore “VBUS present but no enumeration → remove L10/L20” is not a faithful charger-only implementation. [K phy-msm-usb.c:2673](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:2673), [K phy-msm-usb.c:1014](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:1014).

**2. The remaining current: rank recoverable peripheral load before core voltage changes.**

My previous `vlow` guess was wrong: the watch establishes **`xosd` and `vmin`**. Zero `xosd` alongside almost continuous `vmin` is not evidence of a stuck XO. It also does not establish exact CX/MX voltages, every clock-output state, or peripheral shutdown.

The following sizes are **investigation ranges in battery mA**, not measured component currents or additive savings. Except for the DRV2605 figures identified below, they are engineering guesses.

| Investigation priority | Candidate | Plausible additional saving / interpretation |
|---|---|---|
| **1** | USB L10/L20 and remaining PHY policy | **0.1–1 mA** after successful PHCD/STP; more if shutdown is incomplete |
| **2** | Panel/DSI supplies L15/L8/L4 | **0.2–1.5 mA** from rail/load policy |
| **3** | Inherited HPM modes and apps sleep requests | **0.1–1 mA aggregate**; overlaps the named rails |
| **4** | TFA9895 state | Near zero if already powered down; **mA-scale possible** if active. High-value read, uncertain probability |
| **5** | Hub and independently powered sensors | **0–1 mA working residual range**, with a **several-mA failure case**; H does not establish shutdown |
| **6** | Touch L19, shared LVS1 | **0.05–0.5 mA** beyond sensor sleep |
| **7** | eMMC L17 and retained interface supply | **0.05–0.5 mA** beyond CMD5 sleep |
| **8** | TLMM contention/back-power | **0–0.5 mA aggregate** ordinarily; hard back-power can exceed this |
| **9** | Charger/BMS/unused PMIC blocks | **0–0.2 mA guessed excess** in normal configuration; enabled output/boost could be much larger |
| **10** | BT shutdown, DRV2605 standby, external sleep-clock loads | Normally µA to tens-of-µA class individually; inspect abnormal states |
| Separate floor | CX/MX, DDR retention, RPM and essential PMIC operation | Potentially **order 1–3 mA combined**, but this is an unallocated hypothesis, not an established irreducible floor |

The old **1.6 mA AsteroidOS result included AOD**, making it a useful target, but it used its own charge-counter measurement and lacks this run’s matched OCV/trim audit. It is not yet a calibrated reference from which to allocate a precise remaining gap. [N SUSPEND.md:834](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/SUSPEND.md:834).

For regulator reads, firmware addresses encode `SID<<16 | peripheral<<8 | offset`. At each listed regulator base, capture:

- `+0x04/+0x05`: type/subtype.
- `+0x08`: status, interpreted for that subtype.
- `+0x40/+0x41`: voltage range/code.
- `+0x45`: operating mode.
- `+0x46`: enable and hardware-follow controls.
- `+0x48`: pull-down configuration.

Enable bit 7 and HPM bit 7 are useful, but decode hardware-follow/subtype fields too. A software-enable read alone is insufficient. [K qpnp-regulator.c:115](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/qpnp-regulator.c:115).

| Candidate | Concrete reads | What vendor suspend does—and what remains unproven |
|---|---|---|
| **USB** | L10 base **`0x014900`**, L20 **`0x015300`**; RPM `ldoa/10,20`. PHY control **`0xf9a55240`**, PORTSC **`0xf9a55184`**, USBCMD **`0xf9a55140`**. Clock branches **`0xfc400484/488`** | Unplugged PMIC-controlled collapse disables both analog supplies and releases load requests. Firmware does neither. Read USB registers before gating, not through a down block. [K supply-off:242](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/usb/phy/phy-msm-usb.c:242) |
| **Panel** | L15 **`0x014e00`**, L8 **`0x014700`**, L4 **`0x014300`**; RPM `ldoa/15,8,4`; GPIO78 enable and GPIO25 reset | Full panel-off disables supply consumers; ULP instead reduces load requests. Firmware only sends display-off/sleep-in. **L8 also supplies the CPU PLL through an active-only consumer:** retain its awake requirement. [FW display.c:449](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:449), [K mdss_dsi.c:64](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/video/msm/mdss/mdss_dsi.c:64), [K PLL supply:1005](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226.dtsi:1005) |
| **Touch** | L19 **`0x015200`**, LVS1 **`0x018000`**; RPM `ldoa/19`, `vsa/1`; QUP5/I²C `0x20`, dynamically discovered F01 control; GPIO16–19 | Non-gesture suspend disables `pwr_reg`, mapped to L19. Gesture suspend takes a different path. **The suspend code does not disable `bus_reg`/LVS1.** LVS1 also supplies microphone circuitry. [K touch suspend:3851](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3851), [K mapping:24](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/synaptics-dsx.dtsi:24), [K audio:42](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-sound.dtsi:42) |
| **eMMC** | L17 **`0x015000`**, L6 **`0x014500`**; RPM `ldoa/17,6`; SDCC branches **`0xfc4004c4/4c8`**, pad control **`0xfd512044`** | Host power-off can disable L17; L6 is always-on. L6’s low-load request is conditional on `lpm_sup`, not established merely by the DT’s `<250 154000>` pair. Firmware E preserves both rails. [K MMC DT:133](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-720p-mtp.dtsi:133), [K regulator handling:1897](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1897) |
| **Hub/sensors** | GPIO87 reset, 108 AP-status, 62 wake-MCU, 65 MCU-wake, UART GPIO0–3, boot/status GPIO106/111/114 | Vendor permits MCU sleep and preserves wake/service operation. H asserts reset and stops UART; it does not switch off sensor supplies or prove minimum STM32 current. **I found no verified physical supply-to-SPMI mapping.** [FW hub.c:459](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/sensors/hub.c:459), [K hwmcusleep.c:145](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmcu/hwmcusleep.c:145) |
| **BT** | GPIO67 REG_ON, GPIO63/64 wake lines, GPIO12–15 UART; check actual output and mux/pull state | Firmware already stops UART and lowers chip power. No demonstrated additional vendor shutdown saving for these BT-off arms. External rail and shutdown-pin back-power remain unverified. [FW bcm.c:212](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:212) |

**TFA9895 deserves a real state read now.** Firmware only probes revision. Read QUP3/I²C `0x34`, 16-bit big-endian registers **`0x00` status and `0x09` system control**, optionally `0x04` I²S and `0x07` boost. Upstream identifies `0x09` bit 0 as power-down, bit 2 DSP enable, bit 3 amplifier enable and bit 4 boost enable. That provides a concrete diagnostic absent from my previous report. I did not establish that this vendor/AsteroidOS userspace actually powers it down, nor its current on this board. [FW speaker.c:21](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/audio/speaker.c:21), [upstream TFA989x driver](https://raw.githubusercontent.com/torvalds/linux/master/sound/soc/codecs/tfa989x.c).

**DRV2605 is unlikely to explain the gap if standby succeeded.** Read QUP2/I²C `0x5a`, **mode `0x01` bit 6**, GO `0x0c`, and GPIO60 enable. TI specifies approximately **1.9 µA typical standby**, versus **0.6 mA typical awake with no signal** under its stated test conditions. Firmware and vendor both request standby. However, firmware initialization can return early after enabling the chip, and its final standby write is unchecked: an error path could leave a meaningful load. [FW haptics_drv2605.c:75](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/input/haptics_drv2605.c:75), [K drv2605.c:984](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/haptics/drv2605.c:984), [TI electrical characteristics](https://www.ti.com/lit/ds/symlink/drv2605.pdf).

**CX/MX and apps votes require a request audit, not an arbitrary voltage reduction.**

- CX: S1 control base **`0x011400`**, RPM **`smpa/1`**, especially `corn`, `vfc`, `uv`, `swen`, `ssmd`, `ma`.
- MX: L3 base **`0x014200`**, RPM **`ldoa/3`**, especially `uv`, `swen`, `lsmd`, `ma`.
- Bus requests: `clk1/0,1,2,3` and `clk2/0`; record active and sleep `KHz`.
- XO: `clk0/0`, `Enab`.
- GCC sleep vote: **`0xfc401488`**, already zero in the experiment.

There is no implemented generic RPM resource-state read interface here. Log the transmitted active/sleep dictionaries and match acknowledgements to message IDs. The existing transport accepts a response based on its request tag without validating the returned message ID; that is too weak for claiming a newly applied regulator profile. [FW rpm.c:165](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/rpm.c:165).

The misleading comment at `rpm.c:205` remains: **without a sleep request, an existing active regulator request remains effective in sleep.** Linux has active-only CX/MX consumers, but a sleep-only MX handle initialized to 750 mV does not prove that handle is used or that final MX is 750 mV. Reading SPMI after wake generally observes restored active voltage, not collapse-time voltage. [K request semantics:192](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:192), [K CX/MX definitions:121](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-regulator.dtsi:121).

**PMIC blocks to inventory:**

| Block | Addresses/state | Interpretation |
|---|---|---|
| Charger/BATIF | Status **`0x001010`**, charge control **`0x001049`**, USB status **`0x001310`**, thermal-reference **`0x00124a`**, firmware’s BATFET CTRL4 **`0x001293`** | Compare subtype-specific controls. Retain charge/temperature protections; prior BATFET results outweigh generic guesses |
| BMS | Control **`0x004042/43`**, main CC **`0x00408a`**, OCV **`0x004090`**, VSENSE **`0x004098`**, shadow CC **`0x0040a8`** | Vendor preserves hardware measurement; suspend cancels software calculation work |
| ADCs | VADC **`0x003100`**, IADC **`0x003600`**, BMS-IADC **`0x003800`**; enable controls at relevant `+0x46`, stored IADC trim **`0x0036f2/f3`** | Confirm ordinary conversions leave their ADC disabled; preserve BMS operation |
| LPG | Bases **`0x01b100`–`0x01b600`**, controls including `+0x46` | Check output enables, clock selection and routing |
| WLED | **`0x01d846`** module control; channel controls starting **`0x01d860`** | Sturgeon disables the Linux WLED node; that alone does not reset inherited hardware |
| PMIC vibrator | **`0x01c046`** | Unused on Sturgeon; actual vibrator is DRV2605 |

The BMS suspend path specifically cancels calculation work rather than disabling the meter. [K qpnp-bms.c:5332](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:5332). PMIC block mappings and the Sturgeon WLED override are in [K msm-pm8226.dtsi:786](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm-pm8226.dtsi:786) and [K sturgeon-common.dtsi:86](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/apq8026-sturgeon/apq8026-sturgeon-common.dtsi:86).

**GPIO/TLMM:** read `CFG(n)=0xfd511000+0x10n` and `IO(n)=0xfd511004+0x10n`. Prioritize every signal crossing into a reset or unpowered peripheral, including touch I²C/reset, hub handshake/UART, BT wake/UART and amplifier I²S. Opposed weak pulls can cost tens of µA each; a driven-high pin feeding an unpowered device through protection structures can cost much more. Linux’s suspended pin configurations are a real policy difference, but blanket pulldowns are not a safe substitute for per-net ownership.

**32 kHz outputs:** keep these separate from the `clka` XO-buffer family. The known USB PHY sleep-clock branch is **`0xfc4004ac`**; inspect it, but an enabled branch is not proof of an expensive running load. The essential MPM sleep counter is **`0xfc4a3000`**. I did **not** establish the PM8226 external 32 kHz output-control addresses or Sturgeon consumer wiring from the reviewed sources, so I will not invent them or claim Linux disables them. Preserve the RTC/MPM timebase. External clock-load/back-power testing needs a verified net map first. [K clock-8226.c:367](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/clock-8226.c:367), [K sleep-clock branch:1474](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/clock-8226.c:1474).

**DDR self-refresh:** DDR remains powered in both systems. Excellent VDD-min residency supports successful platform sleep, but does not quantify DDR refresh current or establish identical memory policy. Inspect the BIMC sleep request and MX state first. I have no verified Sturgeon DDR self-refresh status-register address from this review; an AP read after wake would also disturb the state being tested. Do not treat DDR rail removal or reduced retention voltage as a reversible overnight measure.

**3. One overnight run: retain URHET and screen additional policies against nearby baselines.**

Define **B = existing URHET all on, AOD off, BT off**, with the new USB implementation fixed and validated. This is a new baseline: the overnight U implementation and current U implementation are not identical, so measure B before importing an absolute current.

I would add these independent mask bits:

| Bit | Measure | Entry and reversible exit |
|---|---|---|
| `0x20` **V** | USB L10/L20 off | Only after successful unplugged teardown/PHCD/STP. Apply explicit active and sleep disable policy. Restore voltages/load/enables and settle before PHY access/recovery |
| `0x40` **P** | Full-off panel supply policy | Finish display DMA; send panel sleep-in and honor its delay; apply panel reset/enable and safe pin state; remove panel-owned L15/L4 votes. Handle shared L8 with an active requirement and explicit sleep policy |
| `0x80` **Q** | Touch L19 off | T first; suppress polling and IRQ/MPM wake; establish safe reset/I²C pins; remove L19. Restore supply, delays, reset, function discovery/configuration and attention handling |
| `0x100` **E2** | eMMC L17 off, **only if power-cycle recovery is proven** | Flush/finish writes, block storage users, CMD5/clock stop, safe pads, remove L17. Restore supply and perform full card/controller initialization before serving I/O |
| `0x200` **M** | LDO sleep-mode/load profile | Keep voltages/enables fixed; use a reviewed peripheral-rail whitelist with explicit sleep `lsmd`/`ma`, preserving adequate active requirements |
| `0x400` **A** | TFA9895 explicit power-down | Save relevant state; with audio idle, set verified power-down policy and read back. Restore saved state on exit; avoid resetting/reprogramming calibration |

Several qualifications are essential to making those reversible:

- **P needs a cold panel initialization path.** Existing `display_wake()` is just sleep-out, delay and display-on. That is insufficient after removing panel power. Use the detected panel’s initialization/reset sequence, not another panel’s similarly named DT file. [FW display.c:458](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/display/display.c:458).
- **Q should initially leave LVS1 enabled.** L19-only is the clean vendor-backed comparison. LVS1 removal is a separate shared-supply experiment requiring touch/audio ownership and pin isolation; label it separately if later added.
- **E2 cannot reuse the current CMD5 wake path.** Power loss invalidates card/controller assumptions. The current transfer path only wakes a sleeping card; it does not reinitialize a power-cycled one. If full recovery is not ready, omit E2 rather than scheduling a rail-off arm with an optimistic restore. [FW emmc.c:604](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/storage/emmc.c:604).
- **M is not “all LDOs to LPM.”** Exclude CX/MX and unidentified/shared essential rails. Review permitted current and settling for each candidate. LDO mode and load votes interact; changing only `lsmd` while retaining an overriding high `ma` may do nothing.
- **V/P/Q/E2 need driver-owned states.** Temporary I/O must restore the resource before access and invalidate/reapply the experimental state afterward. Do not let normal polling silently access a powered-off device.
- Establish explicit **baseline active and sleep requests at startup**. Restoring a hardware register does not restore RPM dictionaries, and “return to unspecified” is not a reliable inverse after sending sleep requests.

The scheduler currently assumes five bits and an 8-bit arm table. Extend its enum, mask validation, table width, labels and actual-state reporting. Reapply in dependency order, with teardown reversed on restore; USB restoration must not cause unrelated rail restoration to be skipped. [FW console.c:942](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:942), [FW console.c:1240](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:1240).

**Recommended arm schedule, assuming all six additions pass a short recovery check beforehand:**

```text
15 min settle

13 min per arm:
B, B+V, B, B+P, B, B+Q, B, B+E2, B, B+M, B, B+A, B, F

Then the exact reverse order.

Finally, 30 min each:
B, F, F, B

F = B plus every validated new measure.
```

Total: **8 h 19 min**. Omitting unready E2 gives **7 h 27 min**.

This deliberately brackets each individual test with nearby B arms. Estimate each saving as the interpolated adjacent-B current minus test current. The reverse block checks direction/carryover; the final ABBA comparison estimates the combined saving over longer windows. It provides two individual repetitions, so small effects still need restraint, but it is less exposed to the three-hour drift of the original mirrored cycle.

The existing parser/`arm_stats()` can support this, but **`leave_one_out()` cannot be used unchanged**: it hardcodes five-character URHET labels, fourteen positions, and cycle arithmetic. Add a separate profile/arm manifest and bracketed contrasts. If retaining literal leave-one-out instead, map new factors independently while forcing old `0x1f` on in every arm; never reinterpret the existing labels silently. [N powerlog.py:131](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:131).

For every arm:

- Start the settling interval **after successful application**, not before lengthy restoration.
- Retain only current intervals whose **entire interval** lies after settling and before arm end.
- Record intended/applied mask, transition errors, rail status, active/sleep request dictionaries and matched acknowledgements.
- Record raw shadow CC, elapsed time, both full RPM records, temperature, OCV and every IADC trim update/readback.
- Keep hardware current monitoring unchanged across arms.
- Keep logs in RAM while testing eMMC-off; do not create background storage traffic.
- Abort and restore on attach or user wake. Mark the interrupted arm invalid.
- Mark failed restoration invalid too: missing “have” bits alone do not detect a rail that remains off when it should have returned.

I would not add unverified hub-supply shutdown or CX/MX undervolting to this same run. They need facts the current source review does not provide.

**4. Overnight data: the reported conditional savings reproduce, but the absolute floor and small effects need more caution.**

Using the current script with its default two-minute trim:

| Arm type | Cycle 0 pair, mA | Cycle 1 pair, mA |
|---|---:|---:|
| All URHET | **2.95, 4.35** | **3.96, 5.32** |
| Without U | 8.27, 8.11 | 10.23, 6.91 |
| Without R | 4.50, 3.84 | 5.30, 5.04 |
| Without H | 5.89, 3.31 | 2.70, 4.05 |
| Without E | 6.15, 3.13 | 4.11, 6.04 |
| Without T | 4.85, 3.90 | 4.64, 6.27 |
| None | 6.84, 7.53 | 9.09, 7.69 |

The four complete-cycle all-on arms average **4.14 mA**, with cycle baselines **3.65 and 4.64 mA**. The later incomplete cycle’s all-on arm is **4.53 mA**. Thus “~3–4 mA” is a useful rough description, but **2.95–5.32 mA** is the actual complete-cycle spread. [N overnight log, arm 0:93](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-loo-2026-11-03-sturgeon.txt:93), [arm 13:782](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-loo-2026-11-03-sturgeon.txt:782), [arm 27:1506](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-loo-2026-11-03-sturgeon.txt:1506).

Specific issues:

1. **Arm 0 has physically suspicious current readings.** Unplugged samples include **−16, −123 and −339 µA**, before later settling around 3.6–4.5 mA with the same measure mask and residency. These negative readings cannot represent sustained battery charging in the reported unplugged state. They strongly warrant an offset/sampling audit; they do not prove which mechanism is wrong. [N log:96](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-loo-2026-11-03-sturgeon.txt:96).

2. **Large steps occur inside unchanged arms.** Arm 8 changes from roughly **5.5–5.7 mA to 2.8–3.0 mA**, with essentially unchanged VDD-min residency. Firmware recalibrates IADC every five minutes but does not log the trim values. Correlate these steps with trim updates before attributing them to peripheral state. The shadow and resettable counters share the analog measurement chain, so agreement between them is not independent validation. [N log:527](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-sleep-loo-2026-11-03-sturgeon.txt:527), [FW bms.c:842](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/bms.c:842), [FW pmic.c:647](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:647).

3. **OCV is not an arm-scale meter here.** Arm 8’s fitted slope is **+36.0 mV/h**, while CC reports discharge. Its OCV readings jump both upward and downward by several millivolts. Relaxation after preceding higher-load arms and measurement behavior can explain why this is not a reliable short-window energy estimate. The overall fall from approximately **4.227 to 4.076 V** supports net discharge, but does not independently validate a particular all-on mA figure.

4. **The trim filter includes partly untrimmed intervals.** `powerlog.py` accepts a shadow sample based on its ending timestamp. Require `end − duration >= arm_start + trim`. For arm 0, doing that changes its mean from **2.95 to 3.25 mA**. That is already material relative to R/E/T. [N powerlog.py:83](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/powerlog.py:83).

5. **U is robust to ordinary trimming changes; H is not.** Increasing the script trim from two to four minutes changes U **4.24→4.04 mA**, R **0.53→0.55**, E **0.72→0.74**, T **0.77→0.75**, H **−0.15→−0.31**, and bundle **3.65→3.55**. This strengthens the qualitative ranking, but does not resolve calibration drift or establish narrow uncertainties.

6. **Conditional effects are not additive.** Their sum is about **6.10 mA**, versus the **3.65 mA** bundle. Complementarity is possible, but so are nonlinear temporal drift and state carryover. The mirrored design cancels approximately linear drift; it cannot cancel arbitrary within-arm steps. H’s positive/negative cycle results remain unresolved.

7. **Residency is persuasive but not a component allocation.** Typical samples show about 59.92 s of VDD-min per 60 s. At an illustrative 90 mA outside that mode, the ordinary non-VDD-min contribution is only around **0.1 mA**. That makes a multi-mA wake-work explanation unlikely. Five RPM entries versus two logged firmware wakeups is not inherently inconsistent: these counters count different events. Current firmware now reads 64-bit accumulated statistics, addressing the earlier low-word wrap concern. [FW main.c:823](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/main.c:823).

The most actionable combination is therefore **fix USB recovery, record the meter’s trim behavior, then test V/P/Q and explicit LDO sleep policy against nearby all-on baselines**. The sources support those omissions; the data does not yet justify treating the remaining current as an intrinsic Sturgeon floor.
**Confidence is high that firmware requests the vendor’s BT-off state; confidence in electrical shutdown and sleep-power parity is still incomplete.** GPIO67 has not been read back off, and GPIO110 matters because the combo shares internal regulators. READ below means source/log evidence; INFER means interpretation. No edits, commits or device access.

**1. Claims a–e**

- **a — READ: holds in code.** `bt_stop()` drives GPIO67 low, GPIO/output/pulldown/2 mA, matching vendor rfkill blocked. The night harness calls it before arm 0. This proves the requested configuration, not its physical level. [bcm.c:48](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/bt/bcm.c:48), [console.c:1374](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/console/console.c:1374), [board-8226-rfkill.c:178](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-rfkill.c:178)
- **b — partly holds. READ:** neither BT shutdown path switches an external supply. **INFER:** “supplies stay up” must distinguish external VBAT/VDDIO from internal rails. The related CYW4343W datasheet says **both REG_ON inputs low disable internal regulators**, with VDDIO retained; that is a shutdown mechanism, not merely a running core held in reset. Applying this to Sturgeon’s exact BCM4343S revision remains a family-level inference. [Manufacturer datasheet, §2.5–2.6](https://www.mouser.com/datasheet/2/196/Infineon_CYW4334WKUBGT_DataSheet_v11_00_EN-3361216.pdf)
- **c — configuration holds after BT initialization; current estimate is unproved. READ:** UART stop makes GPIO12–15 GPIO inputs/pulldown/2 mA; HOST_WAKE retains its initialization pulldown; DEV_WAKE retains its last output. Stop does not establish all these states if UART/BT never initialized. Linux captured five high inputs, but TX/RTS are normally **AP outputs**, so those highs do not establish five chip-driven highs after shutdown. **INFER:** 60 µA assumes roughly 30 kΩ at 1.8 V; neither resistance nor off-state contention is measured. Five such paths mean 0.54 mW at that rail, not automatically 0.3 mA battery current. [uart_dm.c:327](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/uart_dm.c:327), [snapshot:925](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/snap/aos-snap-1793824759.txt:925)
- **d — only partly established. READ:** the journal records hardware rfkill unblocking, and the snapshot has GPIO67 high. Thus that capture is not hardware-off. The supplied captures do **not** establish `bluetoothctl` causation or continued `brcm_patchram_plus` process presence. [journal.txt:3404](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-aos-2026-11-04/journal.txt:3404)
- **e — mostly holds, with a crucial correction. READ:** Linux captured GPIO110 low; I found no firmware WLAN pin setup. WLAN power is in **board-8026-wifi.c**, not board-8226.c. Its `batfet` vote disables/enables **battery-FET low-power mode**, not a dedicated WLAN rail. Firmware also selects LPM on unplug; effective state still needs readback. The earlier BATFET experiment therefore did not test WLAN supply removal. [board-8026-wifi.c:204](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8026-wifi.c:204), [qpnp-charger.c:1926](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-charger.c:1926), [pmic.c:348](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:348)

**2. Vendor pin targets — WLAN off in both columns**

| Lines | BT hardware-off | BT on, sleeping idle |
|---|---|---|
| GPIO67 BT_REG_ON | Output low, PD, 2 mA | Output high, PD, 2 mA |
| GPIO12–15 UART | Vendor retains function 2, no pull, 8 mA; rfkill does not remux | Same; UART controls directions/levels |
| GPIO63 DEV_WAKE | Vendor bluesleep teardown drives low | High permits sleep; low requests wake |
| GPIO64 HOST_WAKE | Input, PD, 2 mA | Same; high idle, low requests host |
| GPIO110 WL_REG_ON | Output low, PD, 2 mA | Same |
| GPIO66 WL_HOST_WAKE | Input, PD, 2 mA | Same |
| GPIO68–71 BT audio | Unused/suspended: GPIO input, PD, 2 mA | Same when audio unused |

**READ:** these board gpiomux entries have suspended configurations; UART and wake/control settings are identical active/suspended. GPIO63’s runtime level overrides its default-low declaration. [gpiomux:236](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:236), [gpiomux:469](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:469), [bluesleep.c:419](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/bluetooth/bluesleep.c:419)

**READ: SDC3 has competing definitions.** GPIO39/40/41/42/43/44 are DAT3/DAT2/DAT1/DAT0/CMD/CLK. Board gpiomux suspend specifies GPIO inputs, 2 mA, PD except **DAT1 PU**. DT pinctrl instead keeps function 2, 2 mA, **CMD/all data PU, CLK no pull**; SDHCI prefers pinctrl when acquired. Capture Linux raw registers before choosing a “vendor-equivalent” firmware configuration. [gpiomux:650](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/mach-msm/board-8226-gpiomux.c:650), [pinctrl.dtsi:140](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/arch/arm/boot/dts/qcom/msm8226-pinctrl.dtsi:140), [sdhci-msm.c:1219](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/mmc/host/sdhci-msm.c:1219)

**INFER:** UART pulldowns are reasonable if the peer is truly high-impedance, but are neither vendor parity nor demonstrated optimal. Removing them can leave AP inputs floating. Remaining unknowns are board-level LPO routing, external pulls, CLK_REQ/strap connections and BT VDDIO wiring. Mainline identifies **L6 as SDC3 VQMMC**, not proof that every combo VDDIO pin uses L6; L18/L21 experiments concern SDC2. The family supports internal/external LPO, but absence of driver clock setup proves neither choice. [mainline DTS:307](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/dts/mainline/qcom-apq8026-huawei-sturgeon.dts:307), [datasheet §3.3](https://www.mouser.com/datasheet/2/196/Infineon_CYW4334WKUBGT_DataSheet_v11_00_EN-3361216.pdf)

**3. Exact read-only console commands**

```text
mem fd5110c0 16
mem fd511270 24
mem fd5113f0 20
mem fd5116e0 2
mem fd511440 16
```

Each four-word GPIO record is **CFG, IN_OUT, interrupt config, interrupt status**.

| GPIOs, in order | CFG addresses, in order |
|---|---|
| 12–15 | `fd5110c0`, `fd5110d0`, `fd5110e0`, `fd5110f0` |
| 39–44 | `fd511270`, `fd511280`, `fd511290`, `fd5112a0`, `fd5112b0`, `fd5112c0` |
| 63, 64, 66, 67 | `fd5113f0`, `fd511400`, `fd511420`, `fd511430` |
| 110 | `fd5116e0` |
| 68–71, additional audio audit | `fd511440`, `fd511450`, `fd511460`, `fd511470` |

**READ:** IN_OUT is CFG address +4. CFG pull=`v&3`: none/down/keeper/up = 0/1/2/3; function=`(v>>2)&15`; drive=`2×(((v>>6)&7)+1)` mA; bit9 is GPIO output-enable. Alternate-function direction belongs to the peripheral. IN_OUT bit0 is sampled input; bit1 is output latch. Expected firmware GPIO67 off: **CFG `201`, latch 0, sampled low**; stopped UART CFG `001`; running UART `0c8`. [msm8226.h:83](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/msm8226.h:83), [tlmm.c:5](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/tlmm.c:5)

Read after shutdown and at arm boundaries; USB console access wakes the system, so these are not direct asleep measurements.

**4. One extra arm — INFER/proposed experiment**

Define **P = V with only GPIO12–15 and GPIO64 pull bits changed PD→none**, retaining GPIO-input mode, clock gating, DEV_WAKE, both REG_ON levels, WLAN pins and every rail policy. Restore original pulls on exit. Keep `V A A V / A V V A`; add `V P P V / P V V P`, equal durations. This tests the five-pin pull group, not individual pins or full vendor parity.

Log CFG/IN_OUT once per transition; retain identical calibration/wake cadence and discard the same settling interval—three minutes as before. Compare paired charge-counter rates alongside temperature, trim and VDD-min residency. **A null result bounds only what this noisy measurement can resolve.** Floating inputs may increase current; restore on anomalies. Do not combine forcing GPIO110 low with this arm: if initially high, that changes WLAN power state and destroys attribution. Never float either REG_ON.

**5. AsteroidOS rfkill comparison**

**INFER: valid as a whole-system hardware-off baseline, not a chip-only subtraction.** Block the rfkill entry named `brcm_Bluetooth_rfkill`, rather than only `hci0`. **READ:** the kernel lowers GPIO67; upstream `bluetooth_rfkill_event` handles hardware block by killing the attach process. HCI unregister then invokes the AsteroidOS bluesleep teardown: DEV_WAKE low, wake-IRQ/timer changes, UART clock handling and a temporary wakelock. [daemon:874,1253](https://github.com/mer-hybris/bluetooth-rfkill-event/blob/master/bluetooth-rfkill-event/bluetooth_rfkill_event.c#L874), [AsteroidOS patch:126](/Users/darrel/Downloads/AsteroidOS/meta-smartwatch/meta-sturgeon/recipes-kernel/linux/linux-sturgeon/0009-bluesleep-Use-kernel-s-HCI-events-instead-of-proc-bl.patch:126)

Verify actual GPIO67 low, attach-process exit and settled suspend behavior before measuring. Preserve both Linux baselines—BlueZ-off and hardware-blocked. Neither source inspection nor the existing counter captures yet establishes that firmware draws no more asleep than AsteroidOS.

# Bluetooth on sturgeon (M7): hardware, bring-up, sleep, host stack

Research notes and the plan for the first watch session. Written 2026-10-28,
offline (no watch): the code in the `bt` worktree builds but has never run.
The NimBLE host integration (§7.1-§7.7, §8, §9 steps 9-19) was added the same
day, also offline: it builds and links, nothing of it has executed.

**Sources and notation**

- `D:` downstream kernel `android-msm-sturgeon-3.10-marshmallow-dr1-wear-release`
  @ 97abcf5b (local copy `~/Downloads/AsteroidOS/minnow/sturgeon-kernel`), the
  tree AsteroidOS builds for sturgeon.
- `A:` AsteroidOS layers: `meta-smartwatch/meta-sturgeon` (kernel patches,
  `bcm4343.conf`), `meta-asteroid` (`bluetooth-rfkill-event`, `brcm-patchram-plus`).
- `P:` `AsteroidOS/brcm-patchram-plus` @ 8b4a2d84 (the recipe's SRCREV),
  `src/main.c`. `R:` `mer-hybris/bluetooth-rfkill-event` @ d64fbb2f
  (recipe SRCREV) plus the meta-asteroid patches.
- `ML:` mainline Linux master fetched 2026-10-28 (`drivers/bluetooth/btbcm.c`,
  `hci_bcm.c`), plus the mainline DTS copies in `dts/mainline/`.
- `N:` Apache NimBLE `nimble_1_10_0_tag` (a7a156f2), `third_party/nimble`.
  `S:` `asteroid-btsyncd` 2.1 snapshot (`~/Downloads/AsteroidOS/2.1/
  asteroid-btsyncd`), `Sy:` AsteroidOSSync @ e9784e7, `B:` meta-asteroid's
  `bluez5` bbappend and patch.
- **[V]** verified in source (file given). **[I]** inferred, reasoning given.
  **[U]** unverified: a choice or guess that needs the watch.

## 1. Hardware facts

| Item | Value | Source |
|---|---|---|
| Chip | Broadcom BCM43430A0 (BT part of the BCM4343S combo), HCI H4 over UART | EMBEDDED.md; `ML` sturgeon dts `brcm,bcm43430a0-bt` [V] |
| UART | BLSP1 UART4, UARTDM v1.4 core at **0xf9920000** | `D:apq8026-sturgeon-bcm.dtsi` (`hserial:serial@f9920000`, `qcom,msm-hsuart-v14`), `ML:qcom-msm8226.dtsi:601` [V] |
| UART IRQ | **SPI 110** (GIC 142), level high | both DTs [V] |
| BAM | 0xf9904000, IRQ SPI 238, pipes 6 (TX) / 7 (RX); not used here | `D` dtsi [V] |
| Pins | gpio 12 RX, 13 TX, 14 RFR (our RTS), 15 CTS; **function 2**, 8 mA, no pull | `D:board-8226-gpiomux.c:236-266` (`gpio_uart_config`), `ML` `blsp1_uart4_default_state` [V] |
| Naming | downstream comments and msm-bus call it "blsp1_uart3" (0-based), mainline and the GCC clock names say UART4 | `D:clock-8226.c:3244-3245` maps `f9920000.serial` to `gcc_blsp1_uart4_apps_clk` [V] |
| REG_ON | **gpio 67**, output, pull-down, 2 mA; power-on = low 30 ms then high, off = low | `D:board-8226-rfkill.c` (git history, before 4a3675d3; `bluetooth_set_power`), gpiomux `msm_bt_regon_configs` [V] |
| BT_WAKE (dev-wake) | **gpio 63**, output, default low, pull-down, 2 mA; **low = wake** | `D:board-8226-gpiomux.c` (`gpio_wakeup_peripheral_irq_config`), `D:bluesleep.c` (ext_wake 0 = awake) [V] |
| HOST_WAKE | **gpio 64**, input, pull-down, 2 mA; **low = BT wants the host** (falling-edge IRQ) | `D:bluesleep.c:622,631` (`POLARITY_LOW`, `IRQF_TRIGGER_FALLING`), gpiomux `gpio_wakeup_ap_irq_config` [V] |
| HOST_WAKE wake source | MPM pin 28 = gpio 64 | `D:msm8226-v2-pm.dtsi:317`, SUSPEND.md §MPM [V] |
| Supplies | none switched by the BT driver; WLAN toggles a `batfet` regulator, BT does not | `D:board-8226-rfkill.c`, `D:board-8026-wifi.c` [V] |
| LPO (32 kHz) | not configured by any BT/WLAN code in `D` | [U] whether the chip has an external sleep clock or uses its internal LPO |
| Patch file | `4343A0.hcd`, 39973 bytes, 209 `0xFC4C` Write RAM records (max 204 data bytes) + 1 `0xFC4E` Launch RAM (`ff ff ff ff`) | parsed locally [V]; on AsteroidOS it is `/vendor/firmware/4343A0.hcd` (`A:bcm4343.conf`) |

Downstream sturgeon used Google's `nitrous` driver; AsteroidOS reverts that
(`A:linux-sturgeon/0002`, `0003`) and uses `bluesleep` with the DT node
`qcom,bluesleep { host-wake-gpio = 64; ext-wake-gpio = 63; tx-timer-interval
= <1>; }`, plus `qcom,rx-char-to-inject = <0xFD>` on the UART [V].

### Clocks (GCC 0xfc400000)

| Register | Offset | Use |
|---|---|---|
| `APCS_GPLL_ENA_VOTE` | 0x1480 bit 0 | GPLL0 (600 MHz) vote; status `GPLL0_STATUS` 0x001c bit 17 |
| `APCS_CLOCK_BRANCH_ENA_VOTE` | 0x1484 bit 17 | BLSP1 AHB (already set by the I2C driver) |
| `BLSP1_UART4_APPS_CBCR` | 0x0804 | branch enable bit 0, off bit 31 |
| `BLSP1_UART4_APPS_CMD_RCGR` | 0x080c | update bit 0; CFG +4, M +8, N +0xc, D +0x10 |

Sources: `D:arch/arm/mach-msm/clock-8226.c:387-413,427-475,1012-1020,1205`,
RCG programming `D:drivers/clk/qcom/clock-local2.c:48-71,126-149` [V].
CFG = `(2*div-1) | src<<8 | (n ? 2<<12 : 0)`, src 1 = GPLL0, 0 = XO; M = m,
N = ~(n-m), D = ~n.

Vendor frequency table `ftbl_gcc_blsp1_uart1_6_apps_clk` (`clock-8226.c:682`)
and how `msm_serial_hs.c:819-945` uses it [V]:

| Baud | UART clock | RCG (div, m/n) | CSR |
|---|---|---|---|
| 115200 | 7.3728 MHz | GPLL0 /1, 192/15625 | 0xcc |
| 230400 | 7.3728 MHz | same | 0xee |
| 460800 | 7.3728 MHz | same | 0xff |
| 921600 | 14.7456 MHz | GPLL0 /1, 384/15625 | 0xff |
| 1000000 | 16 MHz | GPLL0 /5, 2/15 | 0xff |
| 1500000 | 24 MHz | GPLL0 /5, 1/5 | 0xff |
| 2000000 | 32 MHz | GPLL0 /1, 4/75 | 0xff |
| **3000000** | **48 MHz** | GPLL0 /12.5 (div field 24), no M/N | 0xff |

Above 460800 the driver sets the clock to 16 x baud with CSR 0xff. The RCG
has `VDD_DIG_FMAX_MAP2(LOW, 31.58 MHz, NOMINAL, 63.16 MHz)`: 48 MHz needs the
**NOMINAL vdd_dig corner** [V]. The firmware does not vote a corner; it relies
on whatever the RPM currently holds [U] (same open question as the GPU clock in
EMBEDDED.md).

### UARTDM register use (FIFO mode)

Offsets from `D:drivers/tty/serial/msm_serial_hs_hwreg.h` [V]: MR1 0x00, MR2
0x04, IPR 0x18, TFWR 0x1c, RFWR 0x20, DMRX 0x34, DMEN 0x3c, NCF_TX 0x40, BADR
0x44, CSR 0xa0, SR 0xa4, CR 0xa8, MISR 0xac, IMR 0xb0, ISR 0xb4,
RX_TOTAL_SNAP 0xbc, TF 0x100, RF 0x140.

Init as `msm_hs_startup`/`msm_hs_set_termios` (`msm_serial_hs.c:1094-1187,
2680-2822`) minus BAM, receive path as mainline `msm_serial.c`
(`msm_handle_rx_dm`, from memory of mainline, not re-fetched) [V/I]:

- MR1 = auto-RFR level 48 (`(48 & 0x3f) | ((48 << 2) & 0xffffff00)`) |
  CTS_CTL (bit 6) | RX_RDY_CTL (bit 7) = hardware RTS/CTS.
- MR2 = 8N1 (0x34) | ERROR_MODE (0x40) | RX_ZERO/ERROR_CHAR_OFF (0x300).
- BADR = 64 (vendor value: TX/RX FIFO split), IPR = 31 (stale timeout, the
  vendor value for >= 115200), DMEN = 0 (no BAM).
- CR: PROTECTION_EN 0x100, RESET_RX 0x10, RESET_TX 0x20, RESET_ERR 0x30,
  RESET_BREAK 0x40, RESET_STALE 0x80, RESET_CTS 0x70, SET_RFR 0xd0, enable
  RX|TX (bits 0, 2), DMRX = 0xffffff, STALE_EVENT_ENABLE 0x500.
- RX: IMR = RXLEV (bit 4) | RXSTALE (bit 3), RFWR = 16 words. RXLEV: read
  16 whole words. RXSTALE: `RX_TOTAL_SNAP - bytes already taken` bytes, 4
  per word, then RESET_STALE, DMRX, STALE_EVENT_ENABLE again.
- TX (polled): wait SR.TXEMT or ISR.TX_READY, CR 0x300 (clear TX_READY),
  NCF_TX = byte count, then words into TF whenever SR.TXRDY.
- Baud change: wait TXEMT, disable RX/TX, CSR + RCG, full reset/re-enable
  (vendor resets TX/RX after every rate change).

[U]: the RX FIFO size (BADR 64 assumes a 128-word RAM; lk2nd's `uart_dm.c`
comment says the RAM is 128 entries on its targets), whether RFWR counts words,
and whether auto-RFR at 48 words leaves enough headroom at 3 Mbaud (16 words =
~210 us of interrupt latency).

## 2. HCI bring-up sequence

AsteroidOS runs, via `bluetooth-rfkill-event` (`A:bcm4343.conf`: `lpm = true`,
`reg_hci = true`, `baud_rate = 3000000`, `fw_patch =
/vendor/firmware/4343A0.hcd`, `uart_dev = /dev/ttyHS0`) [V]:

```
brcm_patchram_plus --use_baudrate_for_download --no2bytes --enable_lpm \
    --enable_hci --baudrate 3000000 --patchram /vendor/firmware/4343A0.hcd \
    --bd_addr <stored address> /dev/ttyHS0
```

(`R:bluetooth_rfkill_event.c:847-885`; `--bd_addr` comes from the stored file,
§4) [V]. With those flags `P:main.c:927-984` does [V]:

1. UART raw, CRTSCTS, **115200**.
2. `HCI_Reset` `01 03 0c 00`; wait for the event (re-sent every 4 s on timeout).
3. `--use_baudrate_for_download`: Update UART Baud Rate `01 18 fc 06 00 00
   <baud LE32>`, wait for the event, then switch the host to 3000000.
4. Download Minidriver `01 2e fc 00`, wait for the event. `--no2bytes`: no
   2-byte wait (needed only by old chips).
5. Each `.hcd` record is `opcode LE16, len, data`: sent as `01 <record>`,
   one event awaited per record. The last record is `0xFC4E` Launch RAM;
   patchram sends no separate launch command.
6. Host back to **115200** (the patched firmware restarts at the default
   rate), `HCI_Reset` again.
7. Update Baud Rate to 3000000 again, host follows.
8. Write BD_ADDR `01 01 fc 06 <addr, little endian>`.
9. Write Sleep Mode `01 27 fc 0c` + 12 bytes (§3).
10. `--enable_hci`: hand the tty to the kernel H4 line discipline.

The firmware's `bt_start()` (`src/bt/bcm.c`) does the same, plus two delays
from mainline `btbcm_patchram` (`ML:btbcm.c:223-268`): **50 ms** after the
minidriver command and **250 ms** after Launch RAM (patchram has none; the
reset retry covers it there). It also waits 100 ms after REG_ON before the
first reset (`ML:hci_bcm.c:301`, "wait for device to power on") and retries the
reset 3x with 1 s timeouts. Then it reads Local Version (0x1001), BD_ADDR
(0x1009) and Local Name (0x0c14).

Expected values [I]: manufacturer 15 (Broadcom); `ML:btbcm.c:505` lists LMP
subversion **0x2122 = "BCM4343A0"** (that table is consulted before the
patch; the value after the patch is [U]); unprogrammed BD_ADDR
**43:43:A0:12:1F:AC** (`ML:btbcm.c:27,119`, `BDADDR_BCM43430A0`).

Timing estimate [I]: 210 records at 3 Mbaud (~0.15 s of wire time) plus one
command/event round trip each; the full bring-up should be well under 1 s
plus the fixed 400 ms of delays. The console command blocks the main loop
for that long (the watchdog is fed in every wait).

## 3. BT sleep (LPM) protocol

### Write Sleep Mode (0xFC27) parameters AsteroidOS sends on sturgeon

`P:main.c` with `-DLPM_STURGEON` (`A:meta-sturgeon/.../brcm-patchram-plus_git.bbappend`) [V]:

| Byte | Field | Sturgeon | Meaning (`ML:btbcm.h` field names, `hci_bcm.c` comments) |
|---|---|---|---|
| 0 | sleep_mode | 0x01 | UART sleep mode (H4 + BT_WAKE/HOST_WAKE) |
| 1 | idle_threshold_host | 0x18 | host idle threshold; "in 300 ms" per `ML:hci_bcm.c`, so 7.2 s [U units] |
| 2 | idle_threshold_hc | 0x18 | controller idle threshold, same units [U] |
| 3 | bt_wake_polarity | 0x00 | BT_WAKE active **low** |
| 4 | host_wake_polarity | 0x00 | HOST_WAKE active **low** |
| 5 | allow_host_sleep_during_sco | 0x01 | |
| 6 | combine_sleep_mode_and_lpm | 0x01 | |
| 7 | enable_uart_txd_tri_state | 0x00 | |
| 8-11 | usb_auto_sleep, usb_resume_timeout, break_to_host, pulsed_host_wake | 0 | **level** host-wake (mainline hci_bcm sends pulsed = 1) |

The firmware sends exactly these bytes (`sleep_mode[]` in `src/bt/bcm.c`).

### Host side as bluesleep does it (AsteroidOS patch 0009) [V]

- **TX**: before sending, the host asserts BT_WAKE (gpio 63 **low**) and turns
  the UART clock on with RFR asserted (`hsuart_power(1)`:
  `msm_hs_request_clock_on` + `set_mctrl(TIOCM_RTS)`). A TX timer (DT
  `tx-timer-interval = <1>`, so **1 s**) deasserts BT_WAKE (gpio 63 **high**)
  when no data went out in the last period.
- **RX**: the chip pulls HOST_WAKE (gpio 64) **low** when it has data and
  keeps it low while it wants the host awake (level mode, pulsed = 0).
  The falling-edge IRQ schedules the sleep work, which turns the UART on.
- **Sleep**: when BT_WAKE is deasserted *and* HOST_WAKE is high *and* the TX
  FIFO is empty, the host deasserts RFR (`set_mctrl(0)`) and only then gates
  the UART clock (`msm_hs_request_clock_off`); a 500 ms wakelock covers the
  clock-off.
- Patch 0009 hooks this to HCI traffic (`HCI_DEV_WRITE` from
  `hci_uart_send_frame`) instead of the `/proc/bluetooth/sleep` interface.

### What that means for the superloop and M6 sleep [I]

- Awake (current code): gpio 63 held low, so the chip never enters LPM; the
  UART clock stays on. Safe for bring-up, costs BT idle current.
- To let the chip sleep: after ~1 s without TX, drive gpio 63 high. Before
  every TX, drive it low again (the chip's wake latency after BT_WAKE is
  unknown [U]; bluesleep sends immediately and relies on CTS flow control,
  which our TX path honours).
- Before the host gates its own clocks (M6 tier 1 already switches the CPU
  to XO; GPLL0 must stay up while the UART runs from it): deassert RFR (clear
  MR1.RX_RDY_CTL, CR 0xe0 RESET_RFR), wait TXEMT, then stop the UART clock. The
  chip then cannot send; it signals with HOST_WAKE low instead.
- HOST_WAKE as a wake source: TLMM summary interrupt (SPI 208) for WFI sleep;
  MPM pin 28 for the deeper tiers (SUSPEND.md). On wake: UART clock on, RFR
  asserted (auto-RFR back on), then the chip sends.
- A BLE connection keeps the controller busy at the connection interval; the
  host only wakes when there is HCI traffic (data, notifications, events), so
  connection parameters chosen by the phone decide the host wake rate, not
  the link itself [I].

### Mainline uses opposite wake polarities

`ML` sturgeon dts: `device-wakeup-gpios = <&tlmm 63 GPIO_ACTIVE_HIGH>`,
`host-wakeup-gpios = <&tlmm 64 GPIO_ACTIVE_HIGH>`; `hci_bcm` always sends
`bt_wake_active = 1` and derives `host_wake_active` from the IRQ polarity [V].
Both setups are self-consistent because the host tells the chip the polarity
in 0xFC27. The firmware follows AsteroidOS (active low everywhere). The chip's
behaviour *before* 0xFC27 arrives is [U] (sleep mode presumably disabled by
default, so BT_WAKE should not matter during the patch download).

## 4. BD_ADDR on sturgeon

- The chip has no programmed address as far as AsteroidOS is concerned:
  `bluetooth-rfkill-event` reads `/var/lib/bluetooth-rfkill-event/
  bluetooth_address` (meta-asteroid patch 0002 replaced the upstream
  `/factory/bluetooth_address`); if missing or malformed it generates a random
  one from `/dev/random` (`random_default_bdaddr`, avoiding the reserved LAP
  9E:8B:00-3F) and **saves it**, so each watch keeps one random public address
  across reboots [V: `R:bluetooth_rfkill_event.c:265-305`, patch 0002].
- Where the stock Wear OS image kept the factory address (Huawei `oeminfo`,
  `/persist`, a property `ro.bt.bdaddr_path`) is [U]; `P` only reads
  `ro.bt.bdaddr_path` on Android builds.
- Without 0xFC01 the chip reports the default 43:43:A0:12:1F:AC (`ML:btbcm.c`)
  [I: expected].
- AsteroidOSSync stores the watch's MAC (`PREFS_DEFAULT_MAC_ADDR`) and later
  connects with `getRemoteDevice(mac)` + `createBond()`, so the address must
  be **stable across boots**, and a public address is the safe choice (a static
  random address may not survive Android's address-type cache) [I].
- Plan: until the firmware has persistent storage, `adb shell bt <addr>`
  writes an address given on the command line. The real fix: read the address
  the watch already uses under AsteroidOS (`cat
  /var/lib/bluetooth-rfkill-event/bluetooth_address` on an AsteroidOS boot) so
  an existing phone pairing keeps working, and store it with the bonding keys.

## 5. What AsteroidOSSync needs from the watch

From `AsteroidOSSync` @ e9784e7 and `asteroid-btsyncd` (2.1 snapshot @ 4d261a7) [V]:

- Advertising: service UUID `00000000-0000-0000-0000-00a57e401d05` (scan
  filter in `MainActivity.java:149`).
- Services (base `xxxxxxxx-0000-0000-0000-00a57e401d05`):
  time 5071 (5001 set: authenticated write + notify), screenshot 6071 (6001
  request: auth write; 6002 content: auth read + notify), media 7071
  (7001-7004, 7006: auth write; 7005 commands: notify), weather 8071 (8001
  city: auth write + notify; 8002-8004: auth write), notification 9071 (9001
  update: auth write; 9002 feedback: notify), Battery 180F / 2A19
  (encrypt-authenticated read + notify; Sync requires NOTIFY).
- **Bonding and MITM encryption are required**: Sync calls
  `device.createBond()` before connecting, and almost every characteristic is
  `encrypt-authenticated-*` in btsyncd. The watch's BlueZ agent registers
  `DisplayYesNo` (`asteroid-launcher/lipstick/src/bluetoothagent.cpp:26`), so
  against a phone (KeyboardDisplay) pairing is LE Secure Connections numeric
  comparison, or legacy passkey entry with the watch displaying the passkey.
  Either way the watch needs a yes/no or passkey UI and SMP with MITM.
- MTU: Sync requests 256 (`AsteroidBleManager.java:167`); writes are split at
  `min(MTU-3, 512)`; long writes are reassembled by the watch per
  characteristic. The BCM43430A0 is a 4.1-era controller [I], so no LE Data
  Length Extension: 27-byte LL payloads, L2CAP fragmentation in the host.
- Bond keys (LTK, IRK, peer identity) must survive reboots, so persistent
  storage is a prerequisite for M7's exit criterion regardless of the stack.

## 6. Host stack recommendation

Licences checked 2026-10-28:

- **BTstack** (bluekitchen, `LICENSE` on master): BSD-3-style text **plus
  clause 4: "Any redistribution, use, or modification is done solely for
  personal benefit and not for any commercial purpose or for monetary gain"**,
  commercial use by separate licence. That is not MIT/BSD/Apache and not
  OSI-approved: **ruled out**, which reverses the 2026-10-25 "BTstack
  preferred" note in EMBEDDED.md.
- **Apache NimBLE** (`apache/mynewt-nimble`, latest tag `nimble_1_10_0`):
  Apache-2.0; bundled pieces are BSD-3 (`queue.h`, `os_mbuf.c`) or
  permissive. SMP crypto: up to 1.8 the bundled tinycrypt (BSD-3); since 1.9
  the Linux port links **Mbed TLS** (Apache-2.0 OR GPL-2.0-or-later) [V:
  `porting/nimble/Makefile.mbedtls`, `ext/` listing]. Porting: an NPL
  layer (event queues, callouts on our timer, no-op mutex/semaphores;
  `porting/npl/dummy/` is a skeleton) and a transport glue from the host's
  HCI buffers to `src/bt/hci.c`. Host-only build, no controller.
- **Own minimal host**: L2CAP LE fixed channels (ATT 0x0004, SMP 0x0006,
  signalling 0x0005), a static ATT/GATT table, notifications, prepared/long
  writes, SMP with LE SC numeric comparison (P-256 ECDH, AES-CMAC f4/f5/f6/g2)
  plus legacy fallback, key storage. Smallest code, but SMP and interop with
  many Android versions is where the bugs would be.

**Decision (Darrel, 2026-10-28): NimBLE host (Apache-2.0), pinned to a release tag, with a
small superloop NPL port and our H4 transport; SMP crypto via a permissive
library (Mbed TLS under Apache-2.0, or tinycrypt as in 1.8).** It already
does what Sync needs (bonding with LE SC + MITM, GATT server, MTU exchange,
notifications, key store callbacks) and runs fine without an RTOS when every
callout and event runs from the main loop. Keep the own-host option as the
fallback if the port proves heavier than the protocol work. Vendored
2026-10-28: NimBLE 1.10.0 + Mbed TLS 3.6.7, see §7.1.

## 7. Code (committed on main 5f912fb..977e31e, 2026-10-28)

- `src/soc/uart_dm.c`: BLSP UARTDM driver (clock + baud table, pins, init,
  IRQ RX ring 4 KiB, polled TX, runtime baud change, stop releases the pins).
- `src/bt/hci.c`: H4 parser over the ring, `hci_send`, blocking
  `hci_cmd(opcode, params, rsp, timeout)` matching Command Complete/Status.
- `src/bt/bcm.c`: power and wake gpios, patchram loader, `bt_start()`.
- `src/bt/npl.c`: NimBLE porting layer for the superloop (§7.2), plus
  `__assert_func` and the `malloc`/`free`/`realloc` NimBLE's GATT server needs.
- `src/bt/transport.c`: NimBLE's controller-side transport over `hci.c` (§7.3).
- `src/bt/host.c`: host start/stop, `bt_poll()`, GAP (advertising, connection,
  pairing), status (§7.4).
- `src/bt/gatt.c`: the AsteroidOS GATT services (§7.4).
- `src/bt/store.c`: `ble_store` callbacks on RAM tables, key/value backend
  for bonds and the BD_ADDR (§7.5).
- `src/bt/port/syscfg/syscfg.h`, `src/bt/port/nimble/nimble_npl_os*.h`,
  `src/bt/port/bt_mbedtls_config.h`: our NimBLE and Mbed TLS configuration.
- `src/civil.c`: `epoch_from_civil()` (inverse of `civil_from_epoch`, round
  trip checked on the host for 1970, 2000-02-29, 2024-02-29, 2099-12-31).
- `src/main.c`: `bt_poll()` every loop iteration; no cluster collapse while
  the chip is up (§7.6).
- `src/console/console.c`: `bt` (bring up the chip, then start the host),
  `bt <aa:bb:cc:dd:ee:ff>` (store the address, then the same), `bt status`,
  `bt off`. Nothing in the boot path calls BT.
- `firmware/4343A0.hcd` copied from `hw/sturgeon/firmware/`; the Makefile
  packs `firmware/*.hcd` into the ramdisk next to the GPU microcode
  (`boot_blob("4343A0.hcd")`). Its redistribution terms are unknown (Broadcom
  blob from the watch's `/vendor`): **decide before committing it**; the
  build works without it (`bt` then reports the missing file).
- Host tests: `make test` did not link before this change either (missing
  stubs for `cpu_clock_*`, `pmic_read`, `power_request`); the bt stubs were
  added to `tests/stubs.c`, and the link still fails on exactly those four
  symbols, no new ones.

### 7.1 Third-party code, pins, build

| Submodule | Pin | Licence | Why this version |
|---|---|---|---|
| `third_party/nimble` (`apache/mynewt-nimble`) | `nimble_1_10_0_tag`, a7a156f2 (2026-07-10) | Apache-2.0; `queue.h` and `os_mbuf.c` BSD-3 (its `LICENSE`/`NOTICE`) | latest `nimble_1_x` release tag on 2026-10-28 (`git ls-remote`) |
| `third_party/mbedtls` (`Mbed-TLS/mbedtls`) | `mbedtls-3.6.7`, 068ff080 (2026-07-01) | Apache-2.0 OR GPL-2.0-or-later, used under Apache-2.0 | latest 3.6 LTS; see below |

Crypto choice [V unless marked]: NimBLE 1.10.0 **removed tinycrypt**
(`N:RELEASE_NOTES.md`, "Removal of Tinycrypt support"; no `ext/tinycrypt`);
`nimble/host/src/ble_sm_alg.c` calls Mbed TLS directly (AES-ECB, AES-CMAC,
P-256 `mbedtls_ecp_gen_key` / `mbedtls_ecdh_compute_shared`). So with this
NimBLE it is Mbed TLS or patching NimBLE; Mbed TLS it is. 3.6 rather than
4.x: NimBLE's own CI builds against `mbedtls-3.6.5`
(`N:.github/workflows/build_ports.yml`), and 4.x moved the legacy
`mbedtls_ecp_*`/`mbedtls_ecdh_*` API out of the public interface into
TF-PSA-Crypto [I: from the 4.0 release announcements, not re-checked
against the 4.x tree]. The nested `framework` submodule of Mbed TLS is not
needed (`git submodule update --init`, not `--recursive`, is enough).

Build integration (`Makefile`):

- NimBLE host only: `nimble/host/src/*.c` minus `ble_gatts_lcl.c` (debug
  table printer that needs `console_printf`), the GAP and GATT services,
  `nimble/transport/src/transport.c` (buffer pools), and from
  `porting/nimble/src` only `endian.c mem.c nimble_port.c os_mbuf.c
  os_mempool.c os_msys.c`. No controller, no `hal_timer`/`os_cputime`, no
  `porting/npl/*` (ours replaces it), no `store/config` (ours replaces it).
- Mbed TLS: 13 files of `library/` (AES, CMAC, cipher, bignum, ECP, ECDH,
  constant time, platform, `memory_buffer_alloc`).
- Configuration: `-Isrc/bt/port` comes before the NimBLE include paths, so
  `syscfg/syscfg.h` resolves to ours; it defines our values and then
  includes NimBLE's generated `porting/nimble/include/syscfg/syscfg.h`, whose
  entries are all `#ifndef` guarded. Ours: transport LL = custom, HS = native,
  peripheral + broadcaster only, 1 connection, SM legacy + SC + bonding +
  MITM, IO DisplayYesNo, key distribution ENC|ID both ways, 4 bonds, 16
  CCCDs, preferred MTU 256, 32 msys blocks, event buffers 257 bytes, device
  name `sturgeon`. `BLE_VERSION` stays 50: NimBLE only accepts 50-63 there
  (`hci_common.h` `#error`); the controller minimum checked at run time is
  HCI 4.0. Mbed TLS: `-DMBEDTLS_CONFIG_FILE='"bt_mbedtls_config.h"'` (the
  file must not be called `mbedtls_config.h`: the quoted include in
  `build_info.h` would find the library's own default first).
- Warnings: NimBLE and Mbed TLS headers come in with `-isystem`, and their
  sources get `THIRD_PARTY_CFLAGS` (default `-w`); our files keep `-Wall
  -Wextra`. At the pinned tags both build without a single warning under
  our flags (`make THIRD_PARTY_CFLAGS=` after removing their objects), so
  `-w` only guards future bumps.
- Heap: one 32 KiB static buffer (`crypto_heap` in `host.c`) under Mbed TLS's
  `memory_buffer_alloc`; NimBLE's `malloc`/`free`/`realloc` (GATT/ATT tables
  at host start, three `realloc`s at service registration) wrap it with a
  size header. Peak use is [U] (P-256 with `MBEDTLS_ECP_NIST_OPTIM` and the
  default fixed-point comb table should stay well under 16 KiB [I]).

Size (`arm-none-eabi-size`, clean build): before text 928428, data 1392, bss
699648; after text 1047484, data 1728, bss 761088: **+119.1 KB code/rodata**,
+0.3 KB data, +60 KB bss (32 KiB crypto heap, NimBLE pools, key tables).
`asteroid.bin` is 1049216 bytes.

### 7.2 NPL port for the superloop

- **Single context.** No NimBLE function runs in an interrupt handler. The
  UART RX IRQ only fills the 4 KiB ring; `hci_poll()` parses it from the main
  loop.
- **Event queues**: singly linked lists (head/tail, `queued` flag) in the
  event struct itself; `ble_npl_eventq_put` ignores an already queued event
  like Mynewt does. `bt_poll()` drains the default queue, at most 32 events
  per call.
- **Callouts**: a list of active callouts with an absolute `time_ms()`
  expiry (ticks = ms, wrap-safe with signed differences). `bt_npl_expire()`
  moves expired ones to their queue at the start of every `bt_poll()`.
  Stop/reset also pull a still-queued expiry event, as Mynewt's does.
  `bt_npl_next_ms()` (and `bt_idle_ms()`, which also returns 0 while events
  are queued) give the time to the next deadline.
- **Mutex**: a depth counter. **Semaphore**: a token count; `sem_pend` with
  no tokens polls `hci_poll()` (set by the transport through
  `bt_npl_set_wait`) and feeds the watchdog until a token arrives or the
  timeout passes. This is what makes the host's blocking HCI commands work:
  `ble_hs_hci_cmd_tx` waits on `ble_hs_hci_sem`, and the Command Complete is
  handed to the host synchronously from the parser (`ble_hs_hci_rx_evt`
  releases the semaphore; everything else is queued for later). Nothing in
  that path sends, so the parser is never re-entered.
- **Critical sections** only count nesting and mask nothing: nothing that
  touches NimBLE state runs in IRQ context.
- `ble_npl_os_started()` is true, `ble_npl_get_current_task_id()` a constant.
- **Logging**: NimBLE INFO, WARN, ERROR and CRITICAL go to `log_printf` as
  `nimble: ...` lines (fragments buffered until the newline); DEBUG is
  compiled out (it uses `%llu`, which our `vsnprintf` does not do). Levels:
  `BT_NPL_LOG_*` in `src/bt/port/nimble/nimble_npl_os_log.h`.
- `assert()` (NimBLE uses it, including `SYSINIT_PANIC_ASSERT`): logs,
  writes a fault record (`log_record`) and reboots, like the crash path.

### 7.3 HCI glue

- Bring-up is unchanged: `bt_start()` powers the chip, downloads the patch,
  writes the BD_ADDR and sleep mode with the blocking `hci_cmd()`.
- `bt_host_start()` then swaps the parser's handler to the transport
  (`bt_transport_attach`): events are copied into NimBLE's event buffers
  (LE Advertising Reports into the discardable pool), ACL packets into
  `acl_from_ll` mbufs (header included, as `hci_h4.c` does), and handed to
  `ble_transport_to_hs_evt/acl`. Commands and ACL from the host go out with
  `hci_send()` (ACL mbuf chains linearised first).
- **Flow control is NimBLE's**: at sync it reads LE Read Buffer Size (falling
  back to Read Buffer Size if the LE value is 0) and counts Number of
  Completed Packets (`ble_hs_hci_avail_pkts`); the transport only moves
  packets. UART-level flow is hardware RTS/CTS as before.
- The host's sync starts with its own HCI_Reset. AsteroidOS does the same
  (patchram writes BD_ADDR/sleep mode, then the kernel's HCI init resets),
  so the baud rate, BD_ADDR and sleep mode should survive it [I]; if every
  command after the host's reset times out, suspect the baud rate first [U].
- A host that has not synced 10 s after `bt` stops itself (state "failed to
  sync"): with a dead controller each sync attempt blocks the main loop for
  NimBLE's 2 s command timeout, every 100 ms.

### 7.4 GAP, GATT, SMP

- **Name** `sturgeon`: AsteroidOS's hostname is `${MACHINE}` (oe-core
  `base-files` `hostname = "${MACHINE}"` [V]) and BlueZ's adapter name follows
  the hostname [I]; it is also the GAP Device Name characteristic.
- **Advertising data** as `B:0001-Advertise-hostname-in-BLE-ad-payload...`
  plus `S:advertisement.cpp` produce it [V for the fields, I for the order and
  flags value]: Flags 0x06 (LE General Discoverable, BR/EDR not supported;
  `main.conf` has `ControllerMode = le`), Complete Local Name = the first 8
  bytes of the hostname, Complete List of 128-bit UUIDs =
  `00000000-0000-0000-0000-00a57e401d05`. 3 + 10 + 18 = 31 bytes, exactly
  full. No TX power, no scan response data. Sync's scanner filters on that
  UUID (`Sy:MainActivity.java:149`). Connectable undirected, 100-150 ms
  interval (BlueZ's default would be 1.28 s, `hdev->le_adv_*_interval =
  0x0800` [I: from memory of Linux `hci_core.c`]; faster for the first tests).
  Advertising restarts after every disconnect.
- **Services** (`src/bt/gatt.c`), UUIDs and properties as `S:` registers
  them; "auth" = NimBLE `*_ENC | *_AUTHEN` (encrypted, MITM-authenticated
  link, BlueZ's `encrypt-authenticated-*`):

  | Service | Characteristic | Properties | Firmware |
  |---|---|---|---|
  | Time 5071 | 5001 set | auth write, notify | **sets the PMIC RTC** |
  | Screenshot 6071 | 6001 request | auth write | logged |
  | | 6002 content | auth read, notify | reads empty, never notifies |
  | Media 7071 | 7001 title, 7002 album, 7003 artist, 7004 playing, 7006 volume | auth write | logged |
  | | 7005 commands | notify | never notifies |
  | Weather 8071 | 8001 city | auth write, notify | logged |
  | | 8002 ids, 8004 max, 8003 min | auth write | logged |
  | Notification 9071 | 9001 update | auth write | **logged** (length + printable text) |
  | | 9002 feedback | notify | never notifies |
  | Battery 180F | 2A19 level | auth read, notify | **real %** (`pmic_battery_percent`), notified on change, checked once a minute while connected |

  Plus NimBLE's GAP (1800) and GATT (1801) services.
- **Time payload** (`Sy:TimeService.java:94-102`, `S:timeservice.cpp`) [V]: 6
  bytes, year-1900, month 0-11, day, hour, minute, second of the **phone's
  local time**; btsyncd interprets them in the watch's timezone. The firmware
  has no timezone and shows the RTC as is, so it writes
  `epoch_from_civil(local time)` to the RTC: the watch shows phone local time.
- **Notification payload**: Sync splits each XML message into writes of at
  most `min(MTU-3, 512)` bytes (`Sy:AsteroidBleManager.java:47-64`); btsyncd
  feeds them to an XML reader until a write ends with `</insert>`
  (`S:notificationservice.cpp`). The firmware logs each write; reassembly and
  parsing are the next step.
- **SMP**: LE Secure Connections + legacy fallback, bonding, MITM, IO
  capability DisplayYesNo (as `asteroid-launcher/lipstick/src/
  bluetoothagent.cpp:26`), key distribution ENC|ID both ways. Numeric
  comparison: the number is logged and **auto-accepted by
  `pairing_accept()` at the top of `src/bt/host.c`** (the one place to wire
  a yes/no UI; auto-accept means no MITM protection in practice). Legacy
  passkey display: a random passkey from LE Rand, logged. Repeat pairing
  from a known peer deletes the old bond and retries.
- P-256 key generation and DHKey run inside host events. Measured cost on
  the A7 is [U]; at 19.2 MHz (XO, display asleep) it could approach the 3 s
  watchdog bark, so `bt_poll()` switches the CPU to the PLL while it runs
  queued host work and back to XO afterwards.

### 7.5 Key store and BD_ADDR

- `ble_hs_cfg.store_read/write/delete_cb` work on RAM tables (our/peer
  security material, 4 each; 16 CCCDs) with the semantics of NimBLE's
  `ble_store_config` (BLE_ADDR_ANY = any peer, `idx` skips matches, overflow
  through `ble_store_util_status_rr`, which drops the oldest peer).
- Every change saves the whole table set as one blob (`"bt.bonds"`, magic +
  size checked on load) through `struct bt_kv { name, load(key, buf, len),
  save(key, buf, len) }`. The BD_ADDR is key `"bt.addr"` (6 bytes, display
  order); `bt <addr>` saves it and a plain `bt` loads it.
- The only backend today is RAM (`"ram"`): nothing survives a reboot. The
  eMMC key/value store plugs in with `bt_kv_set_backend()` before `bt` runs;
  the blob layout is the raw NimBLE structs, so it is tied to the NimBLE pin
  and our syscfg (bump the magic when either changes).

### 7.6 Sleep interaction

- `main.c` calls `bt_poll()` every iteration (a no-op until `bt` started the
  host). While the display is on the loop does not sleep, so callouts run
  within one frame.
- With the display asleep the loop sleeps in `spm_idle()` between timer
  ticks (100 ms period). Wakes: the tick, and the UART RX interrupt for HCI
  traffic (SPI 110 through the GIC; core power collapse wakes on it [I]).
  So host callouts run up to ~100 ms late while asleep. That is harmless for
  what NimBLE times (sync retry, GAP/SM/ATT timeouts of seconds) [I]; for a
  tighter bound main.c can program the next tick from `bt_idle_ms()` (0 =
  work queued, `UINT32_MAX` = nothing pending).
- **No cluster collapse while the chip is up** (`spm_idle(... &&
  !bt_running())`): the UART interrupt is not an MPM wake source, and
  HOST_WAKE (MPM pin 28) is not armed yet. Core-only collapse stays allowed.
- BT_WAKE stays low (chip never enters its LPM), the UART clock stays on:
  idle current with BT up is the cost until the §3 sleep protocol is wired.

### 7.7 What is stubbed or missing

- Screenshot, media, weather: writes logged, no notifications, 6002 reads
  empty. Notification 9001 logged per write, no reassembly, no parser, no
  9002 feedback, no UI.
- Pairing confirmation auto-accepts (`pairing_accept()`); passkey only logged.
- Keys and BD_ADDR in RAM only (lost on reboot; the phone keeps its bond, so
  after a watch reboot the phone must forget the watch and pair again).
- No BT LPM (BT_WAKE/HOST_WAKE), no deeper sleep with BT up.
- No privacy (public address only), no Data Length Extension (the 4.1-era
  controller [I]), one connection.
- `bt off` does not disconnect over the air; it cuts power. Starting again
  resets the host (`ble_hs_sched_reset`), which forgets the old connection.

## 8. What Sync needs vs what the firmware does

| Sync needs (§5) | Firmware now |
|---|---|
| Advertising with the AsteroidOS UUID, connectable | yes, same fields as btsyncd/BlueZ (§7.4) [U on air] |
| A recognisable name | `sturgeon` in advertising and GAP |
| Stable public address across boots | only if `bt <addr>` is given after each boot (RAM kv) |
| Bonding, LE SC/MITM encryption for every auth characteristic | yes; confirmation auto-accepted |
| Bond keys across reboots | **no** (RAM key store) |
| MTU 256 | preferred MTU 256 |
| All six services with btsyncd's UUIDs/properties | yes (§7.4 table) |
| Battery read + notify | yes, real percentage |
| Time set | yes, writes the RTC |
| Notifications shown, feedback 9002 | logged only |
| Media, weather, screenshot | logged / empty |

## 9. First watch session: test plan

Ordered so each step isolates one layer. Logs: `adb shell log 80`.

1. `make run`; `adb shell help` lists `bt`. Boot unaffected (BT never runs
   unless asked).
2. `adb shell bt`. Success prints up-time, HCI/LMP versions, manufacturer,
   BD_ADDR, name. Record: total and patch ms, LMP subversion, BD_ADDR (expect
   43:43:a0:12:1f:ac), the `uart rx/tx/errors` and `hci packets/errors`
   counters in the log (errors should be 0; failures log the same counters
   plus CTS and host-wake). Since the NimBLE integration `bt` goes on to
   start the host (last line `bt: host starting ...`); steps 1-7 only look at
   the bring-up lines before it.
3. If it fails, by stage:
   - `uart failed`: clock. `adb shell mem fc400804 1` (CBCR, bit 31 = off),
     `mem fc40080c 5` (RCG cmd/cfg/M/N/D), `mem fc40001c 1` (GPLL0 status bit 17).
   - `reset failed (-1)`: TX timed out, so CTS never asserted. Check the log's
     `cts` after power-on; `mem fd511430 2` (gpio 67 cfg/io: expect output,
     io bit 1 set), `mem fd5110c0 16` (gpio 12-15 cfg: function 2 = 0x8 in
     bits 5:2). Try MR1 without CTS_CTL to separate flow control from wiring.
   - `reset failed (-2)`: sent but no event. RX path: `mem f99200a4 1` (SR),
     `mem f99200b4 1` (ISR), `mem f99200bc 1` (RX_TOTAL_SNAP), the uart rx
     counter. Maybe the chip is not out of reset after 100 ms: retry `bt`.
   - `baud rate for the download failed`: the 48 MHz clock or the vdd_dig
     corner [U]. Change `BAUD_FAST` to 1000000 / 2000000 / 115200 to bisect.
   - `patch download failed` with a record number: compare against the hcd
     parse (record 0 = 70 data bytes, RAM address 0x00210750); check uart error counters
     (overrun would point at the RX FIFO/RFR settings [U]).
   - `reset after the patch failed`: increase the 250 ms delay, or check
     whether the patched firmware comes up at 3 Mbaud instead of 115200 [U].
4. `adb shell bt off`, then `bt` again (repeatability; REG_ON low resets the
   chip fully [U]).
5. Watch gpio 64 (host-wake) in the log before and after; with BT_WAKE held
   low the chip should stay awake, host-wake level after 0xFC27 is [U].
6. Current: battery mA in the `power:` log line with BT off vs on (no LPM;
   "on" now includes 100-150 ms advertising) to size the M6 impact.
7. Read the address AsteroidOS uses: boot AsteroidOS once and `cat
   /var/lib/bluetooth-rfkill-event/bluetooth_address`; then `adb shell bt
   <that address>` and confirm Read BD_ADDR returns it.
8. Before the firmware session, or on the same day: boot AsteroidOS and
   scan the watch with nRF Connect; save its raw advertising data (and scan
   response, if any) as the reference for step 11.

NimBLE host (needs steps 1-7 to pass):

9. `adb shell bt`, then `adb shell log 40`. Expect in order: `bt: key store
   "ram", 0 bonds`, `bt: host synced, address <BD_ADDR> (type 0)`, `bt:
   advertising as "sturgeon"`. `adb shell bt status`: host advertising
   (synced), hci commands and events counting, 0 dropped, 0 tx errors.
10. If it does not sync (`failed to sync` after 10 s, or `nimble:` error
    lines):
    - all host commands time out right after its first command: the host's
      HCI_Reset changed the UART rate [U]; test by sending a raw `hci_cmd`
      Reset + Read Local Version at 115200 after `bt` (temporary code).
    - one command fails: read the opcode from the `nimble:` line; the
      BCM43430A0's answers to LE Set Event Mask, LE Read Buffer Size and LE
      Read Local Supported Features are the likely suspects [U]. `dropped` >
      0 means an event did not fit the transport buffers.
    - assert: the fault record names the NimBLE file and line.
11. Phone scanner (nRF Connect): the watch shows as `sturgeon`, connectable,
    flags 0x06, 128-bit UUID 00000000-0000-0000-0000-00a57e401d05. Compare
    the raw bytes with step 8's AsteroidOS capture; any difference other than
    the address is a finding (§7.4 marks the order and flags as [I]).
12. nRF Connect connect without bonding: services 1800, 1801, 5071, 6071,
    7071, 8071, 9071, 180F with the §7.4 properties. Read Battery Level: the
    phone must start pairing (auth read). Log: `pairing, compare NNNNNN:
    accepted` with the same number as the phone, then `encryption 0:
    encrypted 1, authenticated 1, bonded 1, key size 16`. The value equals
    `pmic_battery_percent` of the `tick` line's mV. Record how long pairing
    took (log timestamps; covers the P-256 work, §7.4).
13. `bt status`: connected, bonded peers 1, mtu as negotiated. Disconnect and
    reconnect from the phone: no new pairing (keys in RAM), encryption
    restored with the stored LTK.
14. Repeat step 12-13 with the display asleep (power key): pairing must still
    complete (CPU boost in `bt_poll`), the `power:` line shows 0 cluster
    collapses while BT is up, notifications/reads still answered.
15. AsteroidOSSync: forget the watch in Android's Bluetooth settings first.
    Sync's scan lists `sturgeon`; select it: `createBond()` pairs (numeric
    comparison on the phone), log shows `mtu 256` (or what Android picks) and
    `subscribe handle ...` lines for the notify characteristics Sync enables
    (at least Battery Level, which Sync requires; the full list is [U]).
16. Sync's time sync: log `bt: time set to <phone local time>`; `adb shell
    rtc` and the watch face show it.
17. Phone notification: `bt: notification, N bytes` lines, payload chunks of
    at most MTU-3 bytes ending with `</insert>`. Weather refresh and media
    playback: logged writes on 8001-8004 and 7001-7006.
18. Battery: Sync shows the watch's percentage; let it change (charger) and
    confirm a notification within a minute.
19. `bt off`, `bt` again: host resets (`host reset, reason ...`, `bt status`
    resets 1), re-syncs and advertises; Sync reconnects. Then reboot the
    watch: bonds are gone (RAM), so the phone's reconnect fails encryption
    (expect a key-missing/PIN-or-key-missing disconnect reason [U]); forget
    and pair again. This is the expected behaviour until the eMMC store
    backs `bt_kv`.

## 10. Open questions ([U] summary)

1. Whole UART path untested: FIFO size/BADR, RFWR units, auto-RFR level.
2. 3 Mbaud needs the 48 MHz clock at vdd_dig NOMINAL; no corner vote yet.
3. Chip boot time after REG_ON (100 ms chosen), launch delay (250 ms chosen).
4. Whether the patched firmware restarts at 115200 (patchram assumes so).
5. Sleep threshold units of 0xFC27 bytes 1-2; chip wake latency on BT_WAKE.
6. LPO/sleep clock source of the BCM43430.
7. Factory BD_ADDR location on sturgeon, if any.
8. Licence of `4343A0.hcd`.
9. Whether HCI_Reset (the host's first command at sync) keeps the 3 Mbaud
   rate, BD_ADDR and sleep mode on the patched BCM43430A0 (§7.3).
10. Whether the BCM43430A0 accepts NimBLE's startup sequence (event masks,
    LE buffer size, LE features) unchanged.
11. P-256 key generation / DHKey time on the A7 at PLL and at XO; Mbed TLS
    heap peak (32 KiB reserved).
12. Advertising field order and flags value BlueZ actually puts on air on
    AsteroidOS (compare with step 8).
13. Whether the UART RX interrupt wakes a power-collapsed core reliably
    (§7.6), and callout lateness while asleep.
14. Android's behaviour when the watch lost its bond (RAM key store).

## 11. First watch session results (2026-10-28)

All verified on sturgeon with nRF Connect on an S23:

- Bring-up works first try: chip up in 628 ms (patch 220 ms), LMP
  subversion 0x2122, default BD_ADDR 43:43:a0:12:1f:ac, name "BCM4343A0
  UART 37.4 MHz wlbga_e". 3 Mbaud works without extra vdd_dig votes.
- NimBLE syncs, advertises as "sturgeon"; the AsteroidOS GATT table is
  visible; battery read works (81%).
- The S23 uses LE legacy pairing (Passkey Entry, watch displays). The
  passkey is only logged for now (`adb shell log 6 passkey`), so the UI
  must show it before Sync can pair without adb.
- Bonding and reconnect with the stored LTK work; CCCDs are restored.

Bugs found and fixed:

1. UART TX: TX_READY must be cleared right after writing NCF_TX for every
   transfer (as lk's uart_dm.c does). Clearing it only after waiting left
   a stale TX_READY, so the next write could program NCF_TX while the
   previous transfer was still in the FIFO. Symptom: an HCI command
   (LE Rand right after an ACL burst) never answered, then the chip
   stopped answering anything (its H4 framing broke).
2. GIC: lk2nd leaves every SPI edge-triggered (ICFGR 0xffffffff), our
   gic_init never changed it. The UART line stayed high (MISR 0x18,
   SR.RXRDY 1) with no new edge, so RX stopped for good after a burst.
   gic_init now sets all SPIs level (ICFGR reads 0x55555555); the MPM
   wake (SPI 171) is still set edge by spm_init. Committed separately on
   main (9217a14) since it affects every driver; touch, USB and cluster
   sleep re-tested.
3. RPA: the BCM4343A0 rejects LE Set Address Resolution Enable (0x202d,
   status 0x01) and NimBLE 1.10 has no host-side resolution, so the LTK
   lookup used the phone's RPA and NACKed (0x201b) on reconnect. The
   transport now resolves the LE Connection Complete peer address against
   stored IRKs (ah() checked against the Core spec sample) and rewrites
   it to the identity address.
4. A host reset storm (chip silent) blocked the main loop 2 s per reset
   forever; on_reset no longer restarts the 10 s sync timeout.

Debug lesson: `adb shell log N` in a 0.4 s loop trips the watchdog in
log_tail; use `log N <pattern>` and poll at 1.5 s, or ramoops after
`adb reboot` (`tools/run.py --no-boot --tail 8000`).

Next: passkey on screen, persistent bonds (eMMC store), AsteroidOSSync
end to end (time, notifications), BT sleep (dev-wake/host-wake) so
cluster collapse can stay on with BT up.

## 12. Persistence, pairing UI, address (2026-10-28)

- Bonds and the BD_ADDR key live in the eMMC key/value store (`cache`
  partition, first 1 MiB); bond reconnect after a watch reboot verified.
  `bt forget` clears them.
- The passkey is shown full-screen over the watchface (display woken),
  cleared on encryption change or disconnect. Verified with the S23.
- BD_ADDR: Darrel chose the simplest option, the chip default
  43:43:a0:12:1f:ac (no `bt.addr` key written). It is the same on every
  BCM4343A0, so two such watches near each other would clash; fine for one
  personal watch. AsteroidOS uses a random address per install
  (`/var/lib/bluetooth-rfkill-event/bluetooth_address`), so adopting it
  was rejected; `btinfo` can still read it and the BlueZ bonds.

## 13. Gadgetbridge and notifications (2026-10-28)

Darrel uses Gadgetbridge (AsteroidOS support) instead of AsteroidOSSync.
Verified: bond reconnect, battery level, time sync, notifications.
Notifications follow asteroid-btsyncd's format: writes to 9001 are
collected until they end in `</insert>` or `</removed>`; fields pn, id,
an, ai, su, bo, vb (none/normal/strong/ringtone). btsyncd never
implemented the 9002 feedback (TODO upstream), so a tap only dismisses
locally. src/notify keeps the last 20; the newest is shown over the
watchface and wakes the display. Gadgetbridge's test notification is a
call notification that it removes again after a few seconds.

Next: vibration (DRV2605 on blsp1_i2c2 at 0x5a), a notification list,
media/weather, BT low-power mode so cluster collapse stays on with BT up.

## 14. Media, weather, screenshot, notification list (M7, 2026-10-29)

Written offline (watch not available): builds, untested on hardware.
Formats from `S:mediaservice.cpp`, `S:weatherservice.cpp`,
`S:screenshotservice.cpp` and the matching `Sy:connectivity/*Service.java`.

### 14.1 Formats

- **Media 7071** [V from source]: 7001 title, 7002 album, 7003 artist are
  raw UTF-8 (Sync sends a single 0 byte for a missing field, so the
  firmware stops at the first NUL); 7004 playing = byte 0 != 0; 7006
  volume = byte 0, 0-100. 7005 (notify, watch to phone): one byte
  `0` previous, `1` next, `2` play, `3` pause; volume is `4` plus a second
  byte with the absolute new volume 0-100 (`m_value[1] = volume*100`).
  btsyncd's play/pause button sends 2 or 3 depending on the playing state;
  stop also sends 3. Sync acts on byte 0 and, for 4, `data[1]`. The
  firmware's volume up/down steps the last known volume by 10 (50 if the
  phone never sent one) and updates it locally, since the phone may not
  echo it.
- **Weather 8071** [V]: 8001 city UTF-8; 8002 ids, 8003 min, 8004 max are
  five big-endian 16-bit values, day 0 = today. btsyncd reads exactly 5;
  the firmware takes `min(len/2, 5)` (the count comes from the ids write).
  Ids are OpenWeatherMap condition codes. Temperatures are **kelvin**:
  Sync sends OWM's default unit rounded (`Math.round(getTemp())`, no
  `units=` parameter), and asteroid-weather/launcher show `kelvin - 273`.
  btsyncd stores `time(NULL)` as `timestamp-day0` on the ids write; the
  firmware stores the RTC (phone local time) there. Today's index: Asteroid
  uses `round((now - day0) / 24 h)`; the firmware uses calendar days of the
  RTC (`now/86400 - day0/86400`), which does not show yesterday's forecast
  as today in the morning. Sync's write order is city, ids, max, min.
  Gadgetbridge's order/day count is [U].
- **Screenshot 6071** [V]: any write to 6001 triggers it (Sync writes one
  zero byte). btsyncd asks lipstick for `/tmp/btsyncd-screenshot.jpg`, then
  notifies 6002 with the file size as 4 bytes **little-endian**, then the
  file in **20-byte** chunks (the last one shorter), one notification each.
  If the file cannot be opened it notifies `QByteArray::number(0)`, the
  ASCII byte `'0'`. Reads of 6002 return the last value sent. Sync's
  receiver treats the first 4-byte notification after a request as the
  size and appends everything after it until `size` bytes, then decodes
  with `BitmapFactory` and saves `Screenshot_<time>.jpg`. Chunks stay at 20
  bytes as btsyncd does (fits the minimum MTU; a larger MTU is not used).

### 14.2 Firmware

- `src/media/media.c/.h`: state (title/album/artist 96 bytes each,
  playing, volume or -1), `media_write`, `media_command` (UI action ->
  7005 bytes via `bt_gatt_media_command`, only if 7005 is subscribed).
- `src/weather/weather.c/.h`: state (city 64 bytes, day-0 time, days,
  ids/min/max in K), saved with `kv_set("weather", 100 bytes)` 3 s after
  the last write (main loop, not inside the GATT callback); loaded at
  `BT_START_MS` together with the BT start (no eMMC access earlier in boot).
- `src/screenshot/screenshot.c/.h`: on a request (and 6002 subscribed)
  copies the front buffer (`fb.buf[fb.back ^ 1]`: the frame the MDP scans,
  mesh + UI layer as the GPU composed it, XRGB8888, stride 416, rows
  upright as the user sees them because the pipe does the vertical flip) to
  0x0b000000, then encodes it to a JPEG at 0x0b000000 + 666 KB (2 MiB
  region, write-back cached), MCU rows until 4 ms are spent per main loop
  iteration (CPU taken off XO while encoding). The idle path does not sleep
  while encoding. With the display asleep it sends the last frame shown
  (which is the watchface, see 14.3) [I: lipstick probably behaves alike].
- `src/screenshot/jpeg.c/.h`: our own baseline JPEG encoder (GPL like the
  rest; no third-party code): JFIF, YCbCr 4:2:0, AAN float DCT, the example
  quantisation and Huffman tables of T.81 Annex K, IJG quality scaling,
  quality 75. Host-checked: decodes with macOS ImageIO (sips); the UI
  screens come out at 14-16 KB (about 750 notifications).
- `src/bt/gatt.c`: routes 7001-7006 / 8001-8004 writes to the modules;
  tracks subscriptions from `BLE_GAP_EVENT_SUBSCRIBE` (`bt_gatt_subscribe`,
  called from `host.c`; TERM on disconnect clears them and aborts a
  transfer); `bt_gatt_poll()` (end of `bt_poll`) sends up to 16 screenshot
  chunks per call while more than 12 of the 32 msys blocks are free;
  NimBLE queues on the connection when the controller is out of ACL
  buffers, so the msys count is the back-pressure. `BLE_HS_ENOMEM` = retry
  next poll, other errors abort.

### 14.3 UI (Slint, `ui/ui/watchface.slint`, `ui/src/watch.rs`)

Layout follows asteroid-launcher's `MainScreen.qml` PanelsGrid: the
notifications panel is at (-1, 0), left of the watchface, so **swipe right**
opens it; Today (weather) is at (1, 0), **swipe left**; the app launcher is
at (0, 1), **swipe up**. Music is an app in AsteroidOS, so the music screen
takes the launcher's place below the watchface (swipe up). The quick
settings slot (swipe down) is unused. Back is the opposite swipe; screens
slide in 250 ms.

- Gestures are recognised in `ui_touch`: a move past 40 px becomes a swipe
  unless it is vertical on the notification list (that goes to the
  Flickable); a swipe cancels the press by releasing at (-10000, -10000) so
  no TouchArea clicks (host-checked). A swipe while a popup is shown closes
  the popup (the notification stays in the list); the pairing code ignores
  swipes.
- **Notification list**: newest first, app + summary per row; tap a row to
  open it in the existing full-screen view, tap that view to dismiss
  (`notify_dismiss`); the x on each row dismisses directly. New
  notifications still pop up (and vibrate, wake) as before, but only the
  new one: dismissing it no longer shows the next older one, those are in
  the list. A popup whose notification is removed by the phone closes.
- **Weather screen**: city, ionicon for today's id (AsteroidOS's
  `weathericons` mapping: 2xx thunderstorm, 3xx drizzle, 511 snow, 5xx
  rain, 6xx snow, 7xx cloudy, 800 sunny, 801 partly sunny, 802-804 cloudy,
  else alert), condition text, max/min in degrees C, then the next days
  (weekday, icon, max/min). The watchface shows a compact line at the top
  ("Partly cloudy  13° / 7°") when there is a forecast for today.
- **Music screen**: title (two lines), artist - album, previous /
  play-pause / next, volume down / volume % / volume up.
- **Sleep**: going to sleep calls `ui_home()` (watchface, popup closed,
  no animation), so waking always shows the watchface.
- Icons: ionicons from `asteroid-icons-ion` (MIT), copied to `ui/icons/`
  with their size set in the SVG; Slint rasterises them at build time to
  alpha maps (about 46 KB). Font sizes reuse the existing ones only (each
  new size costs a full glyph set, 20-30 KB).
- Size: `asteroid.bin` 1262336 -> 1416176 bytes (+150 KB: Slint generated
  code ~75 KB, icons ~46 KB, C ~16 KB).

### 14.4 Open points [U]

1. Whether Gadgetbridge subscribes to 7005 and 6002, its weather write
   order/day count, and whether it implements AsteroidOS screenshots at
   all (AsteroidOSSync does).
2. Real screenshot encode time on the A7 (host: 1 ms; expect tens of ms in
   4 ms slices) and transfer time (about 750 notifications; depends on the
   connection interval and packets per event).
3. Whether lipstick's screenshot with the screen off is the last frame too.
4. Swipe threshold (40 px) and Flickable interaction on the real touch
   controller.

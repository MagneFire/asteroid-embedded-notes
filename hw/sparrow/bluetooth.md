# Sparrow (ZenWatch 2) Bluetooth: what bcm.c must change for the BCM4343A1

Written 2026-10-31 from reading only; nothing here has run on a sparrow.
Compared: `src/bt/bcm.c`, `hci.c`, `transport.c`, `src/soc/uart_dm.c`,
`src/storage/firmware.c`, `src/board/{sturgeon,sparrow}/board.h` (worktree
`asteroid-embedded-sparrow`) against the downstream kernel
(`android-msm-sparrow-3.10-marshmallow-mr1-wear-release` @ 3d2fa521; copies in this
directory: `bluesleep.c`, `rfkill.c`, `msm8226-v2-pm.dtsi`, `firmware/`), the mainline
`dts/mainline/qcom-apq8026-asus-sparrow.dts`, and the AsteroidOS `meta-sparrow` layer
(`recipes-android/brcm-patchram-plus/`) plus `brcm-patchram-plus` main.c (checked out
under `asteroid-walnascar-5/build/tmp/work/sprat-.../brcm-patchram-plus/4.1.1+git/git/src/main.c`).

## Summary

The bring-up sequence itself carries over unchanged. **The wake-line polarity does
not**: sparrow is active **high** on both lines where sturgeon is active low, and bcm.c
hard-codes active low in four places plus the 0xFC27 bytes. Everything else is a board
constant or a note. Without the polarity change the chip comes up and talks (LPM is off
until 0xFC27), but the sleep handshake would be inverted: the host would tell the chip
"low = awake" while bluesleep-style wiring wants "high = awake", and `bt_can_sleep()`
would never be true or the chip would sleep with the host sending.

## 1. Patchram flow vs brcm_patchram_plus

Vendor invocation (meta-sparrow `patchram.service`, `-DLPM_SPARROW` in the bbappend):

```
rfkill unblock bluetooth
brcm_patchram_plus --baudrate 3000000 --enable_lpm --enable_hci --no2bytes \
  --patchram /system/etc/firmware/bt/BCM4343A1_001.002.009.0053.0240.hcd /dev/ttyHS0
```

Note: **no `--use_baudrate_for_download`**, unlike sturgeon. main.c order for sparrow:
reset at 115200, minidriver 0xFC2E, every .hcd record, reset, Update Baud 0xFC18 to
3000000 (host follows), BD_ADDR (only if given), Write Sleep Mode 0xFC27, then hand the
tty to the kernel. So the vendor never downloaded the 4343A1 patch at 3 Mbaud, and the
chip's behaviour with a 3 Mbaud minidriver + download is **[U]** (it works on the
4343A0 with `--use_baudrate_for_download`; the A1 ROM is a different mask).

Same as sturgeon, so no change:
- 0xFC2E with empty parameters, one Command Complete awaited. `--no2bytes` only skips
  a 2-byte read after it; bcm.c waits the event and sleeps 50 ms (bcm.c:87-90), fine.
- Records sent as `opcode LE16, len, data`, one event per record, the last record
  (0xFC4E Launch RAM, `ff ff ff ff`) is part of the file; bcm.c breaks after it
  (bcm.c:105).
- 0xFC18 parameters `00 00 <baud LE32>` (bcm.c:78 = patchram's `hci_update_baud_rate`).
- After Launch RAM the firmware restarts at 115200 (the host goes back to 115200,
  bcm.c:157, then waits 250 ms and resets). Vendor has no delay there, relies on a
  reset retry every 4 s. bcm.c's 250 ms + 3 resets x 1 s is more tolerant. Keep.

**.hcd format**: identical container. Parsed locally:
- sparrow `BCM4343A1_001.002.009.0053.0240.hcd`, 36099 bytes: 142 x 0xFC4C Write RAM
  (first record 70 bytes, the rest up to **255**) + 1 x 0xFC4E Launch RAM. Embeds the
  string "BCM4343WA1 37.4MHz Murata Type-1DX_AsusZen BT4.1 PCM_S-0053".
- sturgeon `4343A0.hcd`, 39973 bytes: 209 x 0xFC4C (max 204 bytes) + 1 x 0xFC4E.
- Record limit 255 is the HCI maximum; `hci_cmd()` takes `uint8_t plen`, buffers are
  `c[3 + 255]` (hci.c:125) and `txbuf[1 + 1028]` (hci.c:12): fits. `patchram()` bounds
  check (bcm.c:96) is fine. **No change.**
- Both use a 37.4 MHz crystal, so the 0xFC18 baud divisor path is the same.

**Sleep mode (0xFC27)**: the sparrow vendor bytes come from `LPM_SPARROW` in main.c:

| byte | field | sturgeon (bcm.c:35) | sparrow |
|---|---|---|---|
| 0 | sleep_mode | 1 | 1 |
| 1 | idle_threshold_host | 0x18 | **0x01** (default; LPM_SPARROW sets only the polarities) |
| 2 | idle_threshold_hc | 0x18 | **0x01** |
| 3 | bt_wake_polarity | 0 (active low) | **1 (active high)** |
| 4 | host_wake_polarity | 0 (active low) | **1 (active high)** |
| 5 | allow_host_sleep_during_sco | 1 | 1 |
| 6 | combine_sleep_mode_and_lpm | 1 | 1 |
| 7 | txd_tri_state | 0 | 0 |
| 8-11 | usb/break/pulsed | 0 | 0 (level host-wake) |

sparrow array: `{ 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0 }`. The threshold unit is 300 ms
(`ML:hci_bcm.c` comment), so sparrow lets the controller sleep after 0.3 s of idle where
sturgeon waits 7.2 s [U units]; the host side in bcm.c keeps its own 1 s idle timer
(`DEV_WAKE_IDLE_MS`, matching bluesleep's 1 s TX timer), no change needed there. (`LPM_WREN`, sparrow's sibling, has the same 1/1.) Mainline
`hci_bcm` also sends bt_wake_active = 1 and the sparrow DTS declares both gpios
`GPIO_ACTIVE_HIGH` (`qcom-apq8026-asus-sparrow.dts:79-80`), so three sources agree.

Wait after Launch RAM: nothing A1-specific found. Mainline `btbcm_patchram` uses 250 ms
for all chips. If the first reset after the patch times out on the bench, raise
bcm.c:158 to 500 ms before anything else.

## 2. GPIO polarity and timing

`bluesleep.c` (sparrow, host-wake gpio 48 = `GPIO_BT_WAKE_UP_HOST`, dev-wake gpio 61 =
`GPIO_HOST_WAKE_UP_BT_SR`, `board.h:31-33`; EVB uses 45 instead of 61, not the product):

- **Dev-wake (gpio 61) active HIGH.** Probe drives it 1 (`bluesleep.c:690`); `bluesleep_start`
  asserts `1` (`:428-429`); wakeup sets 1 (`:203-204`, `:247-248`); the TX-idle timer
  sets **0** ("set host_wakeup_bt high" comment is backwards, the code writes 0 on idle)
  (`:304-305`); stop sets 0 (`:467`). bcm.c does the opposite: 0 = awake (bcm.c:236),
  1 = idle (bcm.c:246), initial 0 (bcm.c:53).
- **Host-wake (gpio 48) active HIGH, rising edge.** `board-8226.c:94-99` registers the IRQ
  resource with flags `IORESOURCE_IRQ` only, no `IORESOURCE_IRQ_LOWEDGE`, so
  `bluesleep.c:717-720` picks `POLARITY_HIGH` and `:730` requests `IRQF_TRIGGER_RISING`.
  `bluesleep_can_sleep()` is "host_wake != polarity" i.e. host-wake low
  (`bluesleep.c:188`). bcm.c: falling edge (bcm.c:205), `!bt_host_wake()` = chip wants
  host (bcm.c:243), `bt_host_wake()` true = idle (bcm.c:261). All inverted for sparrow.
- Pad config: downstream muxes both as gpio inputs, **no pull** (`pr_gpio_pinmux.h`
  `bt_wakup_host_*`, `host_wakup_bt_*` in `gpio_pinmux_setting.h:163-186`); mainline also
  `bias-disable` (dts:268-273). bcm.c uses pull-down on both and on REG_ON: harmless for
  active-high lines (pull-down = deasserted), no change required. 8 mA drive matches.

`rfkill.c` (REG_ON = **gpio 34**, `GPIO_BT_REGEN`): on = drive low, `usleep(300)` (300 us),
drive high (`:42-46`); off = drive low (`:52-53`). `GPIO_BT_RESET` 36 is only touched on
the EVB (`g_ASUS_hwID == SPARROW_EVB`); the product has no second reset line. REG_ON is
active high like sturgeon's gpio 67. bcm.c holds it low 30 ms then high (bcm.c:49-57),
100 ms before the first reset (bcm.c:143): both far above the vendor's 300 us. No
change. (Vendor has no explicit post-REG_ON delay either; the 4 s reset retry covers it.)
Unknown **[U]**: how the 32 kHz LPO clock reaches the chip. The vendor rfkill only toggles
gpio 34 and mainline lists no clock, so nothing more is expected, but if the chip never
answers the first reset, check WL_REG_ON (gpio 35, `wlan_regulator` in the mainline DTS)
and the RF clock.

## 3. UART: BLSP1 UART1, gpio 0-3, function 2

- Mainline DTS: `&blsp1_uart1` with `pins = "gpio0".."gpio3"; function = "blsp_uart1"`
  (`qcom-apq8026-asus-sparrow.dts:66-70, 261-266`), 8 mA, no bias. `bluetooth` child with
  `max-speed = <3000000>`, compatible `brcm,bcm43430a1-bt`.
- Downstream: `sparrow_{pr,pr3,er}_gpio_pinmux.h` mux gpio 0 "BT Uart Tx", 1 "Rx",
  2 "**CTS**", 3 "**RTS**" with `gpio_uart_config` = `GPIOMUX_FUNC_2`, 8 mA, no pull
  (`gpio_pinmux_setting.h:157-161`). So function 2 is right, and the pin order is
  TX, RX, CTS, RFR at gpio 0, 1, 2, 3 (same order `uart_dm_init` assumes for
  `first_gpio + i`, uart_dm.c:254-255). `BOARD_BT_GPIO 0`, `BOARD_BT_FUNC 2`: **no change**.
- Controller: downstream node `serial@f991d000` (`qcom,msm-hsuart-v14`, SPI 107, BAM
  pipes 0/1), i.e. UART1 at 0xf991d000. `uart_dm_init` computes base
  `0xf991d000 + (uart-1)*0x1000` and IRQ `32 + 107 + uart - 1` (uart_dm.c:238,258), so
  UART1 gives 0xf991d000 and GIC 139: **no change**. The vendor uses BAM, we use the
  FIFO/IRQ path as on sturgeon (UART4); the 3 Mbaud clock path (`find_baud`/`set_clock`)
  is per-port identical (GCC_UART_APPS_CBCR(uart)); only whether UART1's RCG register
  offsets are in the table is worth a glance on first boot (the log prints
  "baud clock rcg stuck" if not).
- Note, not a change: sturgeon's sensor hub already uses UART1 (gpio 0-3, `hub.c`), so
  hub.c and bcm.c must never be linked for the same board; sparrow has the BT chip there
  and `board.mk` lists no hub driver.

## 4. Firmware pool

`firmware.c` `POOL_SIZE` = 128 KiB = 131072 B, entries aligned to 64.

| file | bytes | pool after |
|---|---|---|
| a330_pfp.fw | 2212 | 2240 |
| a330_pm4.fw | 9220 | 11520 |
| BCM4343A1_...hcd | 36099 | 47680 |

47680 of 131072 used (36%), 83392 free: **fits** (sturgeon: 51520). Even all six
`MAX_FILES` files on sparrow (add em7184.fw 22028, it7260.fw 31104, it7260.cfg 512)
total 101376 B and still fit with 29696 spare; the file *count* is then exactly at the
limit of 6.

Name length: `BCM4343A1_001.002.009.0053.0240.hcd` is **35 characters**. The committed
`firmware.c` stored names in `char name[24]` and rejected `len >= 24` with a silent
`return NULL` (no log), so `bt_start()` would fail with "patch file ..." and nothing
else. The sparrow worktree already carries an uncommitted fix (`name[40]` and the
`BOARD_FIRMWARE_DIRS` search list `"/vendor/firmware/", "/etc/firmware/bt/",
"/etc/firmware/"`), which is also needed because the patch lives in
`/system/etc/firmware/bt/`, not `/vendor/firmware/`. 35 < 40 so it is fine; commit it
with the sparrow BT change. (A log line for the length rejection would be a small extra.)

## 5. MPM pin for gpio 48

`msm8226-v2-pm.dtsi` `qcom,gpio-map` (`<mpm_pin gpio>` pairs), line 309: `<20 48>`.
**MPM pin 20 = gpio 48: confirmed.** The same table has `<28 64>` (sturgeon's host wake),
`<8 17>` (touch, valid for sparrow's irq gpio 17 too) and `<54 111>` (sparrow hub irq).
The worktree's `board.h` already has `BOARD_BT_MPM 20` (uncommitted change from the
committed 28). Wake polarity: `spm_wake_pin(pin, on, high)` third argument is the MPM
polarity bit; sparrow's host-wake is active **high**, so it must be `true`
(bcm.c:207 passes `false`, correct for sturgeon only).

## 6. Other chip assumptions in bcm.c / hci.c

- No expected-version check anywhere: `bt_start()` reads Local Version, BD_ADDR and Local
  Name only to fill `struct bt_info` (bcm.c:176-195); `console.c:401-404` prints them.
  Nothing compares against 0x2122 or a name. **No change.** Expect a different LMP
  subversion after the patch than sturgeon's (A1 rather than A0); record it, but the
  value is **[U]** (mainline btbcm lists A1 as 0x2209 from memory, unchecked here).
- hci.c and transport.c: chip-independent (H4 framing, command waiting). Timeouts are
  1000 ms per command; the A1 patch has 143 records vs 210, so patch time shrinks
  (~100 ms of wire time at 3 Mbaud). **No change.**
- Strings: bcm.c:1 header comment says BCM43430A0 / UART4 / gpio 12-15, 63, 64, 67; update
  to be board-neutral. BLUETOOTH.md still describes sturgeon only.
- Default BD_ADDR of an unprogrammed A1 is not the A0's `43:43:A0:12:1F:AC`; irrelevant,
  because bt_start writes the stored address when one is given (bcm.c:167-173). The
  vendor image also writes one (`ro.bt.bdaddr_path` on Android).
- `power()` (bcm.c:49-56) does `tlmm_config(..., 2 mA)` on the control pins; vendor
  uses 8 mA active for the wake pins. Not functionally relevant at these speeds.

## Concrete change list

| where | change |
|---|---|
| `src/board/sparrow/board.h` | add `BOARD_BT_DEV_WAKE_ACTIVE 1`, `BOARD_BT_HOST_WAKE_ACTIVE 1`, `BOARD_BT_SLEEP_MODE { 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0 }`, optional `BOARD_BT_DL_BAUD`; `BOARD_BT_MPM 20` (done in worktree, uncommitted) |
| `src/board/sturgeon/board.h` (38-46) | add the same three macros with sturgeon's values: `0`, `0`, `{ 1, 0x18, 0x18, 0, 0, 1, 1, 0, 0, 0, 0, 0 }` so sturgeon's behaviour is byte-identical |
| `src/bt/bcm.c:35` | `sleep_mode[12]` initialiser from `BOARD_BT_SLEEP_MODE` |
| `src/bt/bcm.c:53` | drive dev-wake to its *asserted* level in `power()` (`DEV_WAKE_ACTIVE`: 1 on sparrow, 0 on sturgeon as now); the level does not matter before 0xFC27, it only has to match what `bt_tx_activity()` assumes afterwards |
| `src/bt/bcm.c:236` | `tlmm_set(GPIO_BT_DEV_WAKE, DEV_WAKE_ACTIVE)` (awake) |
| `src/bt/bcm.c:246` | `tlmm_set(GPIO_BT_DEV_WAKE, !DEV_WAKE_ACTIVE)` (idle) |
| `src/bt/bcm.c:243` | chip wants host: `bt_host_wake()` compared to `HOST_WAKE_ACTIVE` (helper `host_wake_asserted()`) |
| `src/bt/bcm.c:261` | `bt_can_sleep()`: host wake **not** asserted (idle level) |
| `src/bt/bcm.c:205` | IRQ edge: `TLMM_IRQ_EDGE_RISING` for active high, `EDGE_FALLING` for active low |
| `src/bt/bcm.c:207,213` | `spm_wake_pin(MPM_PIN_HOST_WAKE, ..., HOST_WAKE_ACTIVE)` (third arg true on sparrow) |
| `src/bt/bcm.c:226-229` | `bt_host_wake()` is a raw level getter, used by `fail()` (bcm.c:120) too; leave it raw and add the polarity compare at the callers above, or document it as raw |
| `src/bt/bcm.c:151` (and `:157`) | **[U]** keep download at 3 Mbaud as sturgeon (works if the A1 ROM matches); if "patch download" fails or hangs, make the download baud a board macro and use 115200 for the download like the vendor flow (3.2 s wire time for 36 KB at 115200, still acceptable for bring-up) |
| `src/bt/bcm.c:1-9` | reword the header to BCM4343 family, board-neutral |
| `src/storage/firmware.c` | `name[40]` and `BOARD_FIRMWARE_DIRS` (already in worktree, uncommitted); the 35-char name needs it |
| `src/bt/hci.c`, `src/bt/transport.c`, `src/soc/uart_dm.c` | none |
| `.hcd` handling (`patchram()` bcm.c:85-110) | none |
| REG_ON timing (bcm.c:49-57, 143) | none |
| UART pins/function (`BOARD_BT_GPIO 0`, `BOARD_BT_FUNC 2`) | none |
| Pool size | none (47680 of 131072 B) |

First-boot checks on the bench (not run): the console `bt` log lines "bt: powered, cts N,
host wake N" (host wake should be low before 0xFC27 on an active-high line; if it reads
high before any patch the polarity assumption above is wrong), then the same after
0xFC27 with the dev-wake line held asserted (1).

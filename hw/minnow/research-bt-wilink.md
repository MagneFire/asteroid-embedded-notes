<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

The research is done and nothing was modified. I ran no device commands, only `python3 -I` on the .bts and `objdump` on `uim-sysfs`. Items I couldn't confirm are marked **[U]**. Kernel paths below are relative to `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel`.

## 1. Power-up as the vendor stack does it

`board-minnow.c:45-53` sets the kim platform data to nshutdown gpio 83, `/dev/ttyO1` (port_index 1), flow_cntrl 1 and baud 3000000. It sets no `chip_enable`, `chip_disable`, `chip_awake` or `chip_asleep`, and `suspend`/`resume` are empty stubs (`board-minnow.c:74-83`). The rts gpio hack is not in the board file at all (see section 3).

The sequence has two halves, userspace `uim-sysfs` and the kernel `st_kim.c`:

1. **kim probe** (`st_kim.c` ~806-815): `gpio_request(83)` and `gpio_direction_output(83, 0)`, so the chip starts in shutdown.
2. **`st_kim_start`** (`st_kim.c:459-512`), per attempt:
   - nshutdown LOW, `mdelay(5)`, nshutdown HIGH, `msleep(100)` (lines 475-478).
   - Notify uim through the sysfs `install` file and wait up to `LDISC_TIME` = 1000 ms for the line discipline.
   - Retry up to `POR_RETRY_COUNT` = 5 (`ti_wilink_st.h:239`).
3. **uim-sysfs** (`dump/extracted_data/system/bin/uim-sysfs`). Mostly inferred from strings plus a disassembly spot-check:
   - It reads `/sys/devices/platform/kim/{dev_name,baud_rate,flow_cntrl}` and opens `/dev/ttyO1`.
   - It first sets the host port to 115200. Whether CRTSCTS is on at this stage is **[U]**.
   - It writes the 8-byte packet `01 36 FF 04 <baud u32 LE>`. The disassembly at 0x14f0-0x1514 shows plen = 4, and `movw r1,#0xff36` is the opcode for the response check.
   - For 3 Mbaud that packet is `01 36 FF 04 C0 C6 2D 00`.
   - It waits for the command-complete (CCE) at 115200. Only then does it switch the host UART to 3000000 with flow control, ioctl 0x5401 (TCGETS) then the set call, and installs `N_TI_WL`.
   - `0xFC06` (write BD_ADDR) also appears in uim (0x1726, 0x176c). The string "Usage: uim <bd address>" suggests it is only sent when argv carries an address. The `.rc` file starts `uim` with no arguments, so I believe the stock flow does not write a BD address **[U]**.
4. **`read_local_version`** (`st_kim.c:216-259`):
   - It sends `01 01 10 00` (HCI Read_Local_Version, 0x1001), now at 3 Mbaud.
   - It waits up to `CMD_RESP_TIME` = 800 ms.
   - The response bytes (without the 0x04 type byte) are: [0]=0x0e, [1]=len, [2]=ncmds, [3..4]=opcode, [5]=status, [6]=HCI ver, [7..8]=HCI rev, [9]=LMP ver, [10..11]=manufacturer, [12..13]=LMP subversion.
   - `v = data[12] | data[13]<<8`, so `chip = (v&0x7C00)>>10`, `maj = (v&0x0380)>>7`, plus 8 if `v&0x8000`, and `min = v&0x7F`. The name is `TIInit_%d.%d.%d.bts`.
   - For 11.8.32: v = 0x8000|0x2C00|0x0020 = **0xAC20** (derived, not observed).
   - The script's own comments list the post-patch subversions: 185x `ac7f`, 189x `b07f`.
   - A 189x part (chip 12) would load `TIInit_12.8.32.bts` instead.
5. **`download_firmware`** (`st_kim.c:286-422`) skips the 32-byte header and walks the records. See section 2.
6. **`st_kim_stop`** (`st_kim.c:559-567`): nshutdown LOW, 1 ms, HIGH, 1 ms, LOW. That 1 ms glitch pulse is a possible hazard.

**Baud handling.** The script has no `0xFF36` command and no `ACTION_SERIAL`, so the kernel's `skip_change_remote_baud` (`st_kim.c:261-279`, `:328-337`) never fires for this file. Baud change is done entirely by uim, before the ldisc is installed.

## 2. BTS format and the real file

**Structures** (`ti_wilink_st.h:310-358`):
- **Header, 32 bytes:** `u32 magic`, `u32 version`, `u8 future[24]`.
- **Action record:** `u16 type`, `u16 size`, then `size` bytes of data.
- **SEND (1):** data is a full H4 command packet starting with `0x01`.
- **WAIT (2):** `u32 msec`, `u32 size`, then the expected bytes.
- **SERIAL (3):** `u32 baud`, `u32 flow`.
- **DELAY (4):** `u32 ms`.
- **RUN_SCRIPT (5)** and **REMARKS (6)** carry strings.

**Kernel handling:**
- SEND is written to the UART. The command with opcode `0xFF36` is skipped together with its following WAIT.
- WAIT only waits for any response, up to 800 ms, ignoring the record's own timeout and expected bytes. `validate_firmware_response` (`st_kim.c:68-97`) frees the response and keeps waiting if status byte `data[5] != 0`.
- DELAY calls `msleep`.
- Types 3, 5 and 6 fall through the switch and are ignored.

**Parsed `TIInit_11.8.32.bts`** (73956 bytes, parsed by `python3 -I`):
- **Header:** magic bytes `42 54 53 42` ("BTSB", u32 0x42534254), version 1, 24 reserved zero bytes. The first record is at offset 32.
- **Records:** 763 in total, and the file ends exactly at the last record's end.
  - SEND 297, WAIT 297, REMARKS 169.
  - SERIAL, DELAY and RUN_SCRIPT: none.
- **WAIT records:** all 297 are `timeout 5000 ms, size 7`, expecting `04 0e 04 00 <op lo> <op hi> 00`. The ncmds byte in the expected data is 0x00, which is irrelevant to the kernel but matters if you match literally.
- **Distinct opcodes:**
  - `0xFF05` ×255 (patch memory writes, payload up to 255 bytes)
  - `0xFF03` ×32
  - `0xFD06`, `0xFD0C`, `0xFD1C`, `0xFD2B`, `0xFD55`, `0xFDCF`, `0xFDFB`, `0xFE37`, `0xFE38`, `0xFF01` ×1 each (10 total)
  - Total 297. There is no `0xFF36`, no `0xFC06` and no `0xFD5B`.
- **Largest command:** 259 bytes of record data, which is 1 type byte + 3 header bytes + 255 payload bytes. All length bytes match the record sizes.
- **First command:** `01 37 FE 02 08 20`.

**Tail section** (record number, file offset):

| Rec | Offset | Opcode | Bytes | Meaning |
|---|---|---|---|---|
| 708 | 72138 | `0xFE38` | `01 38 FE 00` | one-shot calibration step, per the script comment |
| 716 | 72459 | `0xFDCF` | `01 CF FD 07 0C 01 FF FF FF FF FF` | the "3V switch control" customization |
| 720 | 72534 | `0xFDFB` | `01 FB FD 06 00 F1 1B 02 00 01` | calibration, **[U]** |
| 747 | 73609 | `0xFD06` | `01 06 FD 22 00 02 00 40 1F …` (34 B) | PCM codec config, 16 bit, 8 kHz sync, 512 kHz clock |
| 750 | 73675 | `0xFD1C` | `01 1C FD 13 FF 88 13 00 00 D0 FF FF FF FF FF FF FA 00 00 00 00 00` | board-specific, **[U]** |
| 753 | 73726 | `0xFD55` | `01 55 FD 09 48 46 02 07 02 01 01 FF FF` | not decoded |
| 757 | 73837 | `0xFD2B` | `01 2B FD 05 1C 00 20 00 70` | HCILL parameters, section 3 |
| 761 | 73920 | `0xFD0C` | `01 0C FD 09 01 01 00 FF FF FF FF 00 00` | sleep mode config, section 3 |

The script ends with the `0xFD0C` command and its WAIT, `04 0e 04 01 0c fd 00` (note ncmds 0x01 in this final WAIT's expected bytes). Nothing further is needed. The firmware directory has no BLE add-on `.bts` file.

## 3. HCILL (`st_ll.c`, `st_core.c`)

**Bytes** (`ti_wilink_st.h:390-393`): `0x30` GO_TO_SLEEP_IND, `0x31` GO_TO_SLEEP_ACK, `0x32` WAKE_UP_IND, `0x33` WAKE_UP_ACK. Each is a single byte, sent as a bare byte between packets.

**States:** ASLEEP 0, ASLEEP_TO_AWAKE 1, AWAKE 2, AWAKE_TO_ASLEEP 3, INVALID 4. `st_ll_enable` sets AWAKE and takes a PM reference.

**Chip initiates sleep:**
- The chip sends 0x30 after its inactivity timeout.
- The host replies 0x31, sets ASLEEP, and drops the PM reference so the UART can autosuspend (`st_ll.c:73-94`, `:49-53`).
- The host never sends 0x30.
- After sending 0x31 the host must not transmit until a wake exchange.

**Host wakes the chip:**
- To send while ASLEEP, `st_int_enqueue` (`st_core.c:~660-700`) parks the packet in `tx_waitq`.
- It sends 0x32, sets ASLEEP_TO_AWAKE and takes a PM reference (`st_ll.c:174-189`).
- There is no timeout or retry in this code.
- On receiving 0x33 (`st_core.c:585`, `st_wakeup_ack`), the host moves `tx_waitq` to `txq`, sets AWAKE and transmits.
- In ASLEEP_TO_AWAKE the host queues the packet and waits for the 0x33.

**Chip wakes host:**
- The chip sends 0x32.
- From ASLEEP the host replies 0x33 immediately and goes AWAKE.
- A 0x32 received while already AWAKE or ASLEEP_TO_AWAKE counts as a collision.
  - The host logs an error and re-sends 0x33 without taking a second PM reference (`resend_ll_wake_ack`, `st_ll.c:65-71`).
  - It forces AWAKE.
  - `st_core.c:573-580` then moves `tx_waitq` to `txq` ("assume chip awake"), so a crossed wake does not deadlock.
- A 0x32 in AWAKE_TO_ASLEEP is logged and not answered.

**Pad wake on OMAP** (`omap3-minnow.dtsi`):
- `ti,pad_irq = <0x144 89 1>` maps the UART2 CTS pad, whose mux value is `0x4100` (probably wake-up enable plus input), to IRQ 89.
- The `&uart2` node has `wakeup-capable`, `autosuspend-delay = <100>`, `timed-wakelock = <150>` and `rx_trig = <32>`.
- `omap-serial.c:1805` sets `SCR[4]` (RX_CTS_WU_EN) at runtime suspend, and `:1826` clears it at resume.
- `WER = 0x7F` is written at startup (`:798`).
- So the wake-up trigger is the chip's RTS (our CTS) or RX activity.

**RTS gpio 145 hack:**
- The `&uart2` node has `gpios = <&gpio5 17 2>` (`dtsi:985`).
- `uart_pinctrl_state_init` (`omap-serial.c:1510-1545`) requests the gpio and drives it high.
- The idle pinmux (`dtsi:860-866`) puts the RTS pad `0x146` in mode 4 (gpio), so RTS reads high ("not ready") while the UART is runtime-suspended.
- Default pinmux restores hardware RTS on resume (`omap-serial.c:1795-1830`).
- The effect is to stop the chip streaming into a clock-gated UART. This is my reading of the mux, not stated in a comment **[U]**.

**HCILL config in the script:**
- `0xFD2B` params `1C 00 20 00 70`.
  - The script comment says "35 msec inactivity". 0x1C = 28, so 28 × 1.25 ms = 35 ms is plausible **[U]**.
  - The rest are probably retransmit timeout 0x0020 and RTS pulse width 0x70 **[U]**.
- `0xFD0C` params `01 01 00 FF FF FF FF 00 00`, commented "Sleep enable with hcill hardware option". The field breakdown is **[U]**.

**Consequence for us:**
- HCILL is already enabled by the script, so the chip will send 0x30 after about 35 ms idle.
- Either implement the state machine above, or skip the last two script commands (`0xFD2B` and `0xFD0C`) so the chip never sleeps. I haven't verified that the second option avoids HCILL traffic entirely **[U]**.

## 4. OMAP3 UART2 (0x4806c000), 48 MHz functional clock

**Register offsets** (regshift 2, 16-bit accesses via `readw`/`writew`; offsets from `serial_reg.h` shifted left by 2):

| Offset | Register | Offset | Register |
|---|---|---|---|
| 0x00 | RHR/THR/DLL | 0x20 | MDR1 |
| 0x04 | IER/DLH | 0x40 | SCR |
| 0x08 | IIR/FCR/EFR | 0x44 | SSR |
| 0x0C | LCR | 0x54 | SYSC |
| 0x10 | MCR | 0x58 | SYSS |
| 0x14 | LSR | 0x5C | WER |
| 0x18 | MSR/TCR | 0x1C | SPR/TLR |

**Baud:**
- `serial_omap_baud_is_mode16` (`omap-serial.c:318-330`) picks 13x only if its error is strictly smaller than 16x.
- 3000000: 13x gives 48M/(13·1)=3.69M, 16x gives exactly 3M, so **MDR1 = 0 (16x), DLL = 1, DLH = 0**.
- 115200: both modes give 115384 (equal error), so the driver chooses **13x (MDR1 = 3), divisor 32 (DLL = 0x20)**. 16x with divisor 26 gives the same rate.

**MDR1 values:** 0 = 16x, 3 = 13x, 7 = disabled. The sequence is `MDR1 = 7` while changing DLL/DLH (set under LCR = 0x80 or 0xBF), then write the final mode. Details are at `:893-1037`.

**FIFO and flow control** (`:956-1100`):
- LCR = 0xBF (mode B) and `EFR |= ECB (bit 4)` to unlock enhanced registers.
- LCR = 0x80, `MCR |= TCRTLR (bit 6)`.
- `FCR = 0x31` (FIFO enable plus TX trigger 24).
- `TLR = 0x80`. RX trigger is 8×4 = 32 bytes, from `rx_trig = 32`; TX bits are 0 so FCR applies.
- `SCR = 0`, restore MCR, then program the divisor.
- **Auto RTS/CTS:** `EFR[6] = RTS`, `EFR[7] = CTS`, with `MCR[1]` (RTS) asserted. `TCR = 0x0F` (halt/resume thresholds) and `ECB` is cleared at the end.
- The enable-FIFO and clear-FIFO sequence is at `:293-296`.

**Reset:** write `SYSC` bit 1 (SOFTRESET), then poll `SYSS` bit 0 (RESETDONE). The bit positions come from the OMAP TRM, not from this driver, which I did not check for them **[U]**.

**Status and interrupts:**
- LSR bits: 0 = RX data ready, 1 = OE, 2 = PE, 3 = FE, 4 = BI, 5 = THR/TX FIFO empty, 6 = TSR empty, 7 = FIFO error.
- IER bits: bit 0 = RHR/RX, bit 1 = THR empty, bit 2 = line status, bit 3 = modem status.
- The vendor driver runs with `IER = 0x05`.
- Pad wake: the `WER` bits are CTS, DSR, RI, DCD, RX, RHR, RLS and TX; `0x7F` covers bits 0-6.

## 5. Mapping to our driver

**Callers outside `src/bt/`:**
- `bt_start` and `bt_stop`: `actions.c:15`, `actions.c:70`, `console.c:479`, `console.c:495`.
- `bt_can_sleep`, `bt_sleep`, `bt_lpm_next_ms`: `power.c:400-447`.
- `bt_running`: `console.c:448`.
- `bt_lpm_poll`: `host.c:275`.
- `hci_poll`: set as the NPL wait function at `transport.c:54`.
- `hci_send`: `transport.c:77`, `transport.c:92`.

**Uses in `bcm.c`:**
- `BT_UART` at lines 83, 116, 145, 158, 161, 199, 252, 268, 274.
- `board->bt` fields: `uart` through the `BT_UART` macro; `gpio` (14), `func` (15), `dev_wake` (16), `host_wake` (17), `reg_on` (18), `mpm` (19), `dev_wake_active` (20), `host_wake_active` (21), `patch` (25), `sleep_mode[12]` (175).

**Uses in `hci.c`:** `uart_read` at 108, `uart_write` at 120, and `bt_tx_activity()` at 117.

**Generic, shareable with `bcm.c`:**
- All of `hci.c` except the H4 parser hook described below, and all of `host.c`, `npl.c` and `transport.c`.
- `bt_running` and the `bt_info` readout block (`bcm.c:177-196`: read local version, BD_ADDR, name).
- `reset()`, `fail()`, `sleep_ms()` and `log_packet()`.
- A shared `bt_common.c` could take the readout block, and opcodes `0x0C03`, `0x1001`, `0x1009` and `0x0C14`.

**Chip-specific, to write in `ti.c`:**
- **`power()`:** nshutdown 83 LOW for 5 ms, HIGH for 100 ms.
- **`set_baud()`:** `0xFF36` with a u32 LE baud, expecting its CCE at 115200 before `uart_set_baud(3000000)`.
- **Script loader:** replaces `patchram`. Walk the SEND/WAIT records from offset 32, send each H4 command, wait for its CCE and require status 0. Do not skip anything: the script contains no `0xFF36`.
- **BD address:** write via `0xFC06`, 6 bytes in LSB-first order, as in `bcm.c`'s reversal at lines 168-174.
- **LPM:** an HCILL state machine replacing the dev-wake/host-wake gpio protocol in `bt_lpm_poll`, `bt_lpm_next_ms`, `bt_can_sleep`, `bt_tx_activity` and `bt_sleep`.
  - Sending 0x32 and waiting for 0x33 before TX replaces `bt_tx_activity`'s gpio set.
  - `bt_can_sleep` = state ASLEEP and `uart_idle`.
  - `bt_sleep(true)` = `uart_hold_rx` plus RTS gpio 145 high.
  - `bt_host_wake` has no gpio, so return false or read the RX/CTS line.

**H4 parser change:** `hci.c:63-68` counts any non-1..4 type byte as an error and ignores it. For TI, add a hook before that check so 0x30-0x33 go to `ti.c` when `!type`. Put it in `hci.c` behind a weak function or callback.

**Board fields for TI:**
- `uart` (UART2 index, 1 or 2 depending on our numbering, **[U]**).
- `nshutdown` gpio (83).
- `rts_gpio` (145) and RTS pad / UART pad mux values (`0x144`, `0x146`, `0x148`, `0x14a`).
- Script blob name `TIInit_11.8.32.bts` (or a pointer to it).
- `baud` 3000000.
- Optionally `hcill` on/off, and the `0xFD2B`/`0xFD0C` bytes if you replace the script's own.

Today's `board->bt` has `dev_wake`, `host_wake`, `reg_on`, `mpm`, `patch` and `sleep_mode[12]`. The TI port doesn't use all of those, so either make it a union by chip or add a `ti` sub-struct.

**BLE and NimBLE:**
- The chip is an 18xx part with BT 4.x dual mode. This is plausible rather than proven. The Moto stock image ships `android.hardware.bluetooth_le.xml` and `/system/etc/bluetooth/ble_stack.conf`.
- `system/etc/firmware/wl1851_LE.bin` is 6 bytes, `01 5B FD 02 01 01`: an H4 command for opcode `0xFD5B` (HCI_VS_LE_Enable) with two parameter bytes.
- The main script does not contain `0xFD5B`, so LE enable looks like a separate step after the script. The 6 byte file is the likely source.
- What loads it in the stock OS is **[U]**: `libbt-vendor.so` only opens `/dev/hci_tty`, and the `bluetooth.default.so`/`libbluetooth_jni.so` strings don't mention it.
- Practical plan: after the script, send `01 5B FD 02 01 01` and check for a successful CCE. If LE commands (such as LE_Set_Event_Mask) fail without it, it is required.
- The BD address source is `/pds/bluetooth/bdaddr.txt` = `5c:31:3e:eb:d5:24`, referenced by `build.prop:49` (`ro.bt.bdaddr_path`). `bt_config.conf` has the same address. Neither the script nor the kernel writes the address. The bluedroid stack reading the property file and issuing `0xFC06` is **[U]**.

## BT-reset notes (`dump/bt-reset-2026-08-29`), in 5 lines

1. Eight boots were captured in `bt-matrix`. `cycles.log` shows 19 clean off/on cycles, then cycle 20 began at about 1224 s and the watchdog fired.
2. Boot-0008 is a real kernel panic: "Bluetooth: Unable to push skb to HCI core(-6)", then a NULL dereference in `__sk_free` and `skb_queue_tail`. That matches the double-free that `st_core_fix.patch` fixes (a `kfree_skb` after `->recv` fails).
3. Three other boots show "software restart" (bootreason `reboot`) with `reboot_vs_nshutdown = before-nshutdown-toggle` and a teardown event of `tty_close_exit` or `bt_open_exit`. The reset came before the chip power toggle, so the nshutdown pulse itself isn't implicated.
4. Boot-0012 shows bootreason `watchdog` and `reset_source` 0x0 (none), with `last_teardown_event = bt_open_exit`; the verdict file says `undetermined`. I found no brownout or PMIC cause.
5. No `.md` analysis file sits beside the dump, so I can't tell whether the patch was applied or whether the "reboot" boots were deliberate. Mark the conclusion as unproven.

Files:
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/drivers/misc/ti-st/st_kim.c`
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/drivers/misc/ti-st/st_ll.c`
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/drivers/misc/ti-st/st_core.c`
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/drivers/tty/serial/omap-serial.c`
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/arch/arm/mach-omap2/board-minnow.c`
- `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/arch/arm/boot/dts/omap3-minnow.dtsi`
- `/Users/darrel/Downloads/AsteroidOS/minnow/dump/extracted_data/system/etc/firmware/TIInit_11.8.32.bts`
- `/Users/darrel/Downloads/AsteroidOS/minnow/dump/extracted_data/system/etc/firmware/wl1851_LE.bin`
- `/Users/darrel/Downloads/AsteroidOS/minnow/dump/extracted_data/system/bin/uim-sysfs`
- `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-minnow/src/bt/bcm.c`
- `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-minnow/src/bt/hci.c`

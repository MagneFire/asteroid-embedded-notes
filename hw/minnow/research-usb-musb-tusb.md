<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

I read all of `phy-tusb.c`, `omap2430.c/.h`, the relevant parts of `musb_core.c`, `musb_gadget.c` and `musb_regs.h`, the hwmod data, both dts files, and the tinyusb musb sources. Abbreviations: K = `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel`, T = `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-minnow/third_party/tinyusb/src`.

**Key findings**
- **The kernel never reads the PHY over ULPI.** Cable presence is just the level of gpio142.
- **PHY power is controlled only by gpios.** Moto also power-cycles the PHY before every connect; that was their fix for "consecutive fastboot/adb fails".
- **The 26 MHz clock (gpio177) is shared with the display bridge.** USB must not turn it off on its own.
- **`dcd_musb.c` needs a few small edits.** A new port header alone is not enough.

## 1. OMAP wrapper (0x480ab400) and clocks

Registers, from `K/drivers/usb/musb/omap2430.h:19-50`:
- `OTG_REVISION` 0x400.
- `OTG_SYSCONFIG` 0x404:
  - MIDLEMODE [13:12]: 0 force, 1 no, 2 smart.
  - SIDLEMODE [4:3]: 0 force, 1 no, 2 smart.
  - ENABLEWAKEUP bit2, SOFTRST bit1, AUTOIDLE bit0.
- `OTG_SYSSTATUS` 0x408: RESETDONE bit0.
- `OTG_INTERFSEL` 0x40c: PHYSEL [1:0] (0 = UTMI 8-bit, **1 = ULPI 12-pin**, 2 = ULPI 8-pin). EXTCP is bit2.
- `OTG_SIMENABLE` 0x410: TM1 bit0. The kernel only prints it (`omap2430.c:373`); don't use it.
- `OTG_FORCESTDBY` 0x414: ENABLEFORCE bit0.

What the vendor kernel actually does:
- **The glue never writes SYSCONFIG.** The hwmod layer does it. `omap_hwmod_3xxx_data.c:1675-1728` sets `HWMOD_NO_OCP_AUTOIDLE | HWMOD_SWSUP_SIDLE | HWMOD_FORCE_MSTANDBY`. The comment cites erratum i479, and says any MIDLEMODE other than force stops `core_pwrdm` idling on 3630.
- **Enable** (`omap_hwmod.c:1359-1410`): SIDLE = no-idle, MIDLE = force, AUTOIDLE = 0, ENAWAKEUP not set. So **`OTG_SYSCONFIG = 0x0008`**.
- **Idle** (`omap_hwmod.c:1443-1460`): SIDLE = force, MIDLE = force, so **0x0000**. Then the interface clock is gated.
- **Boot reset:** the hwmod has no NO_RESET flag, so at setup it writes SOFTRST (bit1) and polls SYSSTATUS bit0.
- **Init** (`omap2430_musb_init`, `omap2430.c:318-387`): `INTERFSEL |= ULPI_12PIN` (1), because the dts has `interface-type = <0>` (ULPI). That is the only wrapper write.
- **Runtime suspend/resume** (`omap2430.c:590-617`): save `INTERFSEL` on suspend and restore it on resume. `usb_phy_set_suspend` is a no-op for this PHY. `musb_core.c` also saves/restores the full core context because the block loses state in off-mode (commit f7fc70e: "enumeration fails after offmode").
- **`OTG_FORCESTDBY` is never written.** Commit 876578127261 removed `omap2430_low_level_init/exit`, which cleared ENABLEFORCE on resume and set it on suspend: "Disabling force standby causes the HSOTG clock to stick on after USB is resumed." So it stays at whatever MBM left or its reset value (I don't know the reset value). The kernel is PIO-only (`minnow_defconfig:2048 CONFIG_MUSB_PIO_ONLY=y`), so the module's DMA master port is unused. Leaving ENABLEFORCE = 1 should be safe for PIO, but that is my inference.

Clocks:
- Only the interface clock: `hsotgusb_ick` = **`CM_ICLKEN1_CORE` (0x48004A10) bit4**. There is no functional clock; the 60 MHz ULPI clock comes from the PHY.
- Wait on **`CM_IDLEST1_CORE` (0x48004A20) bit5** (ST_HSOTGUSB_IDLE, 0 = accessible). Bit4 is STDBY (`clock34xx.c:115-126`, `prcm-common.h:282-285`).
- Autoidle is `CM_AUTOIDLE1_CORE` (0x48004A30) bit4. I assume the kernel's clock autoidle setup enables it (unverified).
- Clock domain: `core_l3_clkdm`.

What this means for bare metal:
- Run with SYSCONFIG = 0x0008.
- When resting, write SYSCONFIG = 0x0000, clear ICLKEN bit4, and wait for IDLEST bit5 = 1.
- Re-write `INTERFSEL` = 1 on restore.
- Expect to redo the whole core configuration if CORE went to OFF.
- **Uncertain:** SOFTRST may never complete unless the PHY is powered and supplying ULPI CLK. Power the PHY first and use a timeout.

## 2. The TUSB PHY

**Which chip:** the driver only says "TI TUSB transceiver" (`phy-tusb.c:1-2`), compatible `ti,tusb-usb`. The ULPI wiring plus CS/RESETN pins suggest a TUSB1210 or TUSB1211, but nothing confirms it. You can identify it by reading ULPI vendor ID 0x00/0x01 (expect 0x0451) and product ID 0x02/0x03 (0x1507 or 0x1508). I don't know what "csn" (gpio27) drives; it may be a second chip-select or an analog switch on D+/D-.

**Gpios** (`omap3-minnow.dtsi:136-149`; flags are used raw as GPIOF, where `DIR_IN` = 1 and `INIT_HIGH` = 2):

| Signal | Gpio | Pad | Default (off) | On |
|---|---|---|---|---|
| tusb-irq | 142, input | 0x140 = 0x4104 (mode4, input, OFFWAKEUP) | n/a | n/a |
| resetn | 15 | 0x5ae | low | high |
| cs | 16 | 0x5b0 | low | high |
| csn | 27 | 0x5c6 | high | low |

Pads are listed at `:776-783`. The 26 MHz clock is the `periph_26mhz` gpio-clock on gpio177, active high (`:75-82`). The comment there says it feeds "both Display Bridge and USB", and the display also uses it (`:96`), so reference-count it.

**Power-up** (`tusb_enable`, `phy-tusb.c:121-150`):
- Clock on first.
- Then each output gets `enable XOR default`, in list order: resetn=1, cs=1, csn=0.
- No delays inside the function.

**Power-down:** resetn=0, cs=0, csn=1, then clock off. `gpio_request_array` at probe drives the "off" levels.

**What gpio142 means:**
- It is **VBUS presence, active high**. It is used directly as `power_supply "ac".online` (`:63-77`, type MAINS) and for both enable and reset decisions (`:156`, `:181`).
- The interrupt is requested on both edges with `enable_irq_wake` (`:407-434`). The ISR only queues work (`:217-224`).
- The work handler (`:177-215`):
  - High: `omap_musb_mailbox(VBUS_VALID)`, then PHY on.
  - Low: `omap_musb_mailbox(VBUS_OFF)`, then PHY off.
  - There is a `factory_override` sysfs flag that forces the PHY on.
- The board pad-wake table lists pad 0x140 as "USB", IRQ 254 = gpio142 (`:291`).

Things the driver does not do:
- No ULPI register access, no charger-type detection, no host vs wall-charger distinction (any VBUS counts as "ac").
- The wireless dock is a separate driver (`bq5105x-detect`: detect gpio22, charge gpio176, `:248-264`). Whether wireless charging also raises gpio142 is unknown; it probably doesn't.

**Quirk (commits b2f0b362, 4b915d5a):**
- `musb_pullup(on)` calls `usb_phy_reset(0)`, waits 10 ms, calls `usb_phy_reset(1)`, then sets SOFTCONN (`musb_gadget.c:1610-1630`).
- `tusb_phy_reset` does a full `tusb_enable(off)`/`tusb_enable(on)` **only if gpio142 is high** (`phy-tusb.c:152-165`).
- So the PHY is power-cycled on every connect.

**Disconnect:** the PHY is fully gpio-powered-down and the clock released. `set_suspend` is a no-op, and there are no ULPI SuspendM writes.

**Mapping to what you need to implement:**
- `vbus_present()` = gpio142 level.
- Plug/unplug event: gpio142 both-edge interrupt, with GPIO5 wakeup enabled. For OFF mode, use the pad wakeup bit, which is already set in the pinmux.
- PHY low-power: the gpio-off sequence above.
- Bring-up: the gpio-on sequence, then about 10 ms (my margin, not from the kernel) before ULPI access or SOFTCONN.
- If you want ULPI status anyway (standard ULPI 1.1, not used by the vendor): USB Interrupt Status 0x13 (bit1 VbusValid, bit2 SessValid, bit3 SessEnd), Debug 0x15 (LineState [1:0]), Function Control 0x04/0x05 set/0x06 clear (bit5 Reset, bit6 SuspendM). This only works while the PHY is powered and clocked.

## 3. MUSB core init (vendor)

Register offsets (`musb_regs.h:45-81`, `223-270`):
- POWER 0x01: ISOUPDATE 0x80, SOFTCONN 0x40, HSENAB 0x20, HSMODE 0x10, RESET 0x08, RESUME 0x04, SUSPENDM 0x02, ENSUSPEND 0x01.
- INTRTX 0x02, INTRRX 0x04, INTRTXE 0x06, INTRRXE 0x08, INTRUSB 0x0A, INTRUSBE 0x0B, INDEX 0x0E, TESTMODE 0x0F.
- DEVCTL 0x60: SESSION 0x01, VBUS [4:3], BDEVICE 0x80.
- TXFIFOSZ 0x62, RXFIFOSZ 0x63, TXFIFOADD 0x64, RXFIFOADD 0x66 (in units of 8 bytes).
- HWVERS 0x6C.
- ULPI: BUSCONTROL 0x70 (bit0 USEEXTVBUS, bit1 EXTVBUSIND; not set, since `extvbus` = 0), INT_MASK 0x72, INT_SRC 0x73, **REG_DATA 0x74, REG_ADDR 0x75, REG_CONTROL 0x76** (bit0 REQ, bit1 CMPLT, bit2 RDnWR), RAW 0x77.
- EPINFO 0x78, RAMINFO 0x79.
- CONFIGDATA is 0x1F with INDEX = 0 (`DYNFIFO` = 0x04).

**ULPI viewport protocol** (`musb_core.c:136-216`):
- Clear POWER.SUSPENDM first.
- Read: ADDR = reg; CONTROL = REQ|RDnWR; poll CMPLT (10000 loops); write CONTROL & ~CMPLT; read DATA.
- Write: ADDR, DATA, CONTROL = REQ; poll; clear CMPLT.

**Start** (`musb_start`, `musb_core.c:915-955`):
- INTRTXE = epmask, INTRRXE = epmask & 0xfffe, **INTRUSBE = 0xf7**, TESTMODE = 0.
- **POWER = ISOUPDATE | HSENAB** (the comment says "ENSUSPEND wedges tusb").
- If DEVCTL.VBUS != 3, set DEVCTL.SESSION.
- SOFTCONN is set later, in pullup.

**Stop** (`:957-977`): all interrupt enables = 0, DEVCTL = 0, then read INTRUSB/TX/RX to flush.

**Unplug** (`omap2430_musb_set_vbus(0)`, `omap2430.c:184-197`): clear DEVCTL.SESSION.

**FIFO** (`:1045`, `:1101-1130`, `fifo_setup` around `:1165-1240`):
- `fifo_mode = 4` for OMAP2PLUS.
- EP0 is 64 bytes. EP1–9 are TX and RX, 512 each, single-buffered. EP10–12 TX 256 / RX 64. EP13 shared 4096. EP14–15 shared 1024.
- Encoding: SZ = log2(size) − 3 (+0x10 for double-buffered); ADD = offset >> 3.
- From `omap3.dtsi:546-555`: `ram-bits = 12` gives **16 KB FIFO RAM**, `num-eps = 16`, multipoint.
- The core uses dynamic FIFO only if CONFIGDATA.DYNFIFO is set.
- Register layout is **indexed** (`MUSB_FLAT_REG` is not defined; `musb_core.h:170-173`), CSRs at 0x10. FIFOs are at 0x20 + 4·ep.

## 4. TinyUSB `dcd_musb.c`

**Port selection** (`dcd_musb.c:41-47`): it includes `musb_ti.h` if `TUP_USBIP_MUSB_TI`, `musb_max32.h` if `_ADI`, otherwise `#error`. `musb_ti.h:34-46` itself errors unless the MCU is TM4C/MSP432E4. Your `tusb_config.h` uses `OPT_MCU_NONE` and defines the IP macro by hand, so you need **a new `#elif defined(TUP_USBIP_MUSB_OMAP)` include line in `dcd_musb.c`** plus your own header. You also need to define `TUP_USBIP_MUSB` so that `dcd_musb.c:30` and the hwfifo setup in `tusb_option.h:369-375` (32-bit stride with odd 16/8-bit tail, fixed address) are enabled.

**What the port header must provide** (from `musb_ti.h` and `musb_max32.h`):
- `MUSB_CFG_SHARED_FIFO`: 0 for OMAP (separate TX and RX FIFOs).
- `MUSB_CFG_DYNAMIC_FIFO`: 1.
- `MUSB_CFG_DYNAMIC_FIFO_SIZE`: use **16384**, not TI's 4096.
- `static const uintptr_t MUSB_BASES[] = {0x480ab000}`.
- `void musb_dcd_phy_init(uint8_t)`: called from `dcd_init`.
- `void musb_dcd_int_enable/disable(uint8_t)`: map to INTC unmask/mask of irq 92.
- `unsigned musb_dcd_get_int_enable(uint8_t)`: must return the current mask state; it is used to save/restore around critical sections.
- `void musb_dcd_int_clear(uint8_t)`: pending-clear; can be a no-op on INTC.
- `void musb_dcd_int_handler_enter(uint8_t)`: hook at the top of the ISR. MAX32 uses it to post `DCD_EVENT_UNPLUGGED`.

**Register layout** (`musb_type.h`): packed `musb_regs_t` that matches OMAP3. Common registers at 0x00–0x0F, indexed CSR at 0x10 (selected through INDEX by `get_ep_csr`), FIFOs at 0x20 + 4·ep, DEVCTL 0x60, FIFO size/address 0x62–0x66, HWVERS 0x6C, EPINFO/RAMINFO 0x78/0x79. It also maps flat CSRs at 0x100 (unused), DMA at 0x200, and **0x340/0x342 RX/TX double-packet-disable**.

**Behaviour:**
- **PIO only** (DMA unused), so no cache or alignment requirements.
- Dynamic FIFO: `hwfifo_config` (`:208-231`) allocates from 64 bytes upward, rounds sizes to a power of two, and **double-buffers all bulk endpoints** (2 × 512 each). It also writes 0x340/0x342. **Uncertain:** those registers may not exist on the OMAP3 MUSB revision. The kernel never touches them; check HWVERS and consider guarding the writes.
- `dcd_init` (`:675-688`): only `INTRUSBE |= SUSPEND`. It relies on the reset default (RESET|RESUME), then calls `musb_dcd_phy_init` and `dcd_connect`. It never touches DEVCTL.SESSION or INDEX. **Write INTRUSBE yourself, and set SESSION like the kernel does,** because MBM may have left other values.
- `dcd_connect` (`:728-733`) sets HSENAB if `TUD_OPT_HIGH_SPEED`, then SOFTCONN. `dcd_disconnect` clears SOFTCONN. Speed comes from POWER.HSMODE at bus reset (`:647`). With `CFG_TUD_MAX_SPEED = HIGH`, bulk max packet is 512.
- **No `dcd_deinit`.** The weak default is at `usbd.c:87`, and your `usb.c` calls `tud_deinit`, so provide one. Your `usb.c` also needs `dcd_stuck()` (`asteroid.h:239`), which `dcd_ci_hs_msm.c:46` currently provides.
- ISR (`:959-1020`): saves/restores INDEX and reads INTRUSB/INTRTX/INTRRX, which clear on read. **DISCON is ignored** (`:972`), and nothing posts UNPLUGGED; do that from gpio142 or from the enter hook. Suspend/resume map to `DCD_EVENT_SUSPEND/RESUME`. SOF is handled; `dcd_sof_enable` is a TODO.
- **Bug (likely):** `intr_tx`/`intr_rx` are `uint_fast8_t` (`:966-968`, `:1000`, `:1013`). That type is probably 8-bit on ARM GCC, which would drop interrupts for EP 8–15. Set `TUP_DCD_ENDPOINT_MAX` to 8, not 16. That value also sizes `pipe[]` and the loops in `close_all` and bus reset.

**Cortex-M-specific code:**
- `dcd_remote_wakeup` uses `SystemCoreClock` and `__NOP` (`:721-722`). Replace it with a delay of about 10 ms, or define those two symbols in your header.
- The NVIC calls exist only in the vendor headers.
- `musb_regs_t` is a packed struct. That is fine with your `-mcpu=cortex-a8` build, which allows unaligned access so GCC emits `ldrh`. Check the disassembly: `-mno-unaligned-access` would split the clear-on-read 16-bit registers into byte accesses.

**Edits needed:** the include selector, the remote-wakeup delay, and `uint_fast8_t` → `uint16_t` if you want EP ≥ 8. Optionally guard 0x340/0x342.

## 5. Proposed bare-metal sequences

**From scratch:**
1. Pinmux pads 0x140 (0x4104), 0x5ae/0x5b0/0x5c6 (0x0004). Enable GPIO1 and GPIO5 clocks. Set gpio15/16 out low and gpio27 out high.
2. Enable `CM_ICLKEN1_CORE` bit4 and wait for `CM_IDLEST1_CORE` bit5 = 0.
3. If gpio142 is high: take a reference on gpio177 (26 MHz), then drive resetn=1, cs=1, csn=0, and wait about 10 ms.
4. SYSCONFIG = 0x0002 (SOFTRST), poll SYSSTATUS bit0 with a timeout. Then SYSCONFIG = 0x0008 and INTERFSEL = 0x1. Set FORCESTDBY to your choice (see section 1).
5. Core: interrupt enables 0, DEVCTL 0, read the interrupt registers to flush. Read HWVERS/CONFIGDATA and check DYNFIFO.
6. `tusb_init`. In `musb_dcd_phy_init`: INTRUSBE = 0x27 (SUSPEND|RESUME|RESET|DISCON), TESTMODE = 0, POWER = HSENAB, DEVCTL |= SESSION.
7. Before `tud_connect`, mirror the vendor quirk: PHY off, 10 ms, PHY on, then SOFTCONN.

Since MBM ran fastboot first, the core is probably already clocked. Still do step 4 and clear SOFTCONN first, so the host sees a clean disconnect.

**Rest (gpio142 falls, after your 2 s debounce):**
1. `tud_disconnect`/`deinit`: SOFTCONN = 0, interrupt enables = 0, DEVCTL = 0, flush interrupts.
2. Mask irq 92.
3. Save INTERFSEL. Saving the full context isn't needed because you re-init.
4. PHY off: resetn=0, cs=0, csn=1, then release the 26 MHz clock (only drive gpio177 low if the display isn't using it).
5. SYSCONFIG = 0x0000, clear ICLKEN bit4, wait for IDLEST bit5 = 1.
6. Keep the gpio142 both-edge interrupt and GPIO5 wakeup armed. Pad 0x140 WAKEUPENABLE covers CORE/PER OFF.

**Restore (gpio142 rises):** steps 2–7 of the from-scratch sequence.

**What I couldn't settle:** the PHY part number, what csn does, the FORCESTDBY reset value, whether SOFTRST needs the PHY clock, whether 0x340/0x342 exist on this core, and whether the wireless dock raises gpio142.

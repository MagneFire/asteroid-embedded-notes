<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

I've worked out every register value from the vendor sources. All calculated values that the blanked dump also contains match it. A few things need verifying against the TRM and are marked **[UNVERIFIED]**.

Paths are relative to `/Users/darrel/Downloads/AsteroidOS/minnow/minnow-kernel/drivers/video/omap2/dss/` unless they say otherwise.

## Facts that change the recipe

1. **3630 feature flags** (`dss_features.c:523-540`):
   - Present: `DSI_PLL_PWR_BUG`, `DSI_PLL_FREQSEL`, `FUNCGATED`, `PCKFREEENABLE`, `OMAP3_DSI_FIFO_BUG`, `ALPHA_FIXED_ZORDER`.
   - Absent: `LCD_CLK_SRC`, `DSI_DCS_CMD_CONFIG_VC`, `DSI_GNQ`, `DSI_VC_OCP_WIDTH`, `DSI_PHY_DCC`, `DSI_PLL_REFSEL`, `DSI_REVERSE_TXCLKESC` (only 3430 and AM35xx have that one).
   - Consequences: 3 lanes are supported. The line buffer is 1023×3 = 3069 bytes. TXCLKESC reset bits are CFG5[24/25/26]. DCS_CMD_ENABLE lives in DSI_CTRL[24], not in VC_CTRL.
2. **DSI PLL reference.** It is the "sys_clk" optional clock = dss2_alwon_fck = 26 MHz. `periph_26mhz` (`omap3-minnow.dtsi:96`) is only the SSD2848 bridge's own clock input. The panel driver turns it on 6 ms before VIO (`panel-minnow.c:3058`).
3. **Lane pins.** The DT `pins` property is commented out (`omap3-minnow.dtsi:99`), so the defaults 0,1,2,3 apply (`panel-minnow.c:2411`). That gives clock on lane 0 and data1 on lane 1, both polarity 0. ndl = 1.
4. **Pad mux.** DSS_DATA0..3 are set to MODE1 (DSI DX0/DY0/DX1/DY1), value 0x0001, at padconf 0x480020DC/DE/E0/E2 (`omap3-minnow.dtsi:718-721`).
5. **No pad or CONTROL-module setup.** `omap_dsi_enable_pads()` does nothing on OMAP3 (`arch/arm/mach-omap2/display.c:177`).
6. **vdds_dsi.** No supply is mapped in the minnow board file or DT, and `CONFIG_REGULATOR_DUMMY=y`, so Linux gets a dummy regulator. **[UNVERIFIED]** Which PMIC LDO feeds VDDS_DSI is not in the sources; assume it is always on.
7. **Clock calculation** (`dsi.c:4861` dsi_cm_calc, `5201` set_config):
   - pixel_clock = ceil(320·290·45/1000) = 4176 kHz. pck_min = 6.264 MHz, pck_max = 9.396 MHz. txbyteclk = 18.79 MHz.
   - PLL range: pll_min = max(104 MHz×4, 18.79 MHz×16) = 416 MHz; pll_max = 600 MHz.
   - regn = ceil(26/2.1) = 13, so fint = 2 MHz. regm = 104, so CLKIN4DDR = 416 MHz.
   - regm_dispc = ceil(416/173) = 3, giving 138.67 MHz. DISPC lck_div = 1, pck_div = ceil(138.67/9.396) = 15, giving pck 9.244 MHz.
   - regm_dsi = 3, so DSI_FCLK = 138.67 MHz. LP divider = ceil(138.67/18) = 8, giving LP clock 8.667 MHz. DDR clock = 104 MHz, TxByteClkHS = 26 MHz.
8. **Clock sources when the panel is on.** DSS_CONTROL = **0x00000003**:
   - bit 1 DSI_CLK_SWITCH = 1 is set in `dsi_display_init_dsi` (`dsi.c:4551`).
   - bit 0 DISPC_CLK_SWITCH = 1 is set via `dss_select_lcd_clk_source`, which falls through to `dss_select_dispc_clk_source` because 3630 has no `LCD_CLK_SRC` (`dss.c:394`, `dsi.c:4450`).
   - So the whole DISPC functional clock runs at 138.67 MHz while video output is enabled. Your blanked dump shows 0 because blanking switches back to DSS_FCK (`dsi.c:4512`), which is why it reports pck 11.52 MHz.
   - Kernel quirk: after ULPS entry, bit 1 is cleared and the PLL is off, but bit 0 stays 1.

## 1. Clocks and power

The TRM-only bit positions below are **[UNVERIFIED]**.

1. Power domain:
   - PM_PWSTCTRL_DSS (0x48306EE0) [1:0] = 3 (ON). The dump has 0x30104, i.e. target OFF.
   - CM_CLKSTCTRL_DSS (0x48004E48) [1:0] = 2 (SW_WKUP). The dump has 3 (HW_AUTO).
   - Poll PM_PWSTST_DSS (0x48306EE4) [1:0] == 3.
2. DPLL4 M4: CM_CLKSEL_DSS (0x48004E40) [5:0] CLKSEL_DSS1 = **10**, giving 1728/10 = 172.8 MHz. [13:8] CLKSEL_TV = 0x20. The dump value is 0x200A.
   - The kernel computes this as fck_div = ceil(1728 MHz × multiplier 1 / 173 MHz) (`dss.c:559`, `dss.c:776`).
   - **[UNVERIFIED]** You probably also need to clear CM_CLKEN_PLL (0x48004D00) bit 29 PWRDN_DSS1. The blanked dump has 0x38610077, which has bits 27-29 set.
3. Clock enables:
   - CM_ICLKEN_DSS (0x48004E10) bit 0 = 1.
   - CM_FCLKEN_DSS (0x48004E00): bit 0 DSS1 (main fck), bit 1 DSS2 (DSI PLL reference), bit 2 TV. Linux enables TV only during reset (`display.c:577-629`, `CONFIG_OMAP2_DSS_RESET=y`). Use **0x7** during reset, then **0x3**.
   - Poll CM_IDLEST_DSS (0x48004E20) bit 1 (ST_DSS_IDLE) == 0.
4. DSS reset, mirroring `reset_omap_dss` (`display.c:577`):
   - DSS_CONTROL (0x48050040) = 0, SDI_CONTROL (+0x44) = 0, PLL_CONTROL (+0x48) = 0.
   - DSS_SYSCONFIG (+0x10) = 0x2, then poll DSS_SYSSTATUS (+0x14) bit 0 == 1.
   - Linux also clears DISPC LCDENABLE/DIGITENABLE first.
5. DISPC initial config (`dispc.c:3480`):
   - DISPC_CONFIG (0x48050444): bit 9 FUNCGATED = 1, [2:1] LOADMODE = 2 (frame only).
   - Burst size ×8 (= 2): GFX ATTRIBUTES [7:6], VID1/VID2 ATTRIBUTES [15:14].
   - DISPC_SYSCONFIG (0x48050410) = 0x2015 (hwmod: smart-idle/smart-standby, ENWAKEUP, AUTOIDLE).

## 2. DSI PLL (DSI base 0x4804FC00)

Waits marked "wfb" use `wait_for_bit_change` (`dsi.c:459`): 100 busy polls, then up to 500 ms in 1 ms steps.

1. DSI soft reset (`dsi.c:4612`):
   - DSS_CONTROL bit 1 = 0.
   - DSI_SYSCONFIG (0x010) bit 1 = 1.
   - Poll DSI_SYSSTATUS (0x014) bit 0 == 1, 10 × 1 µs.
2. IRQ setup (`dsi.c:889`). Clearing status is write-1-to-clear.
   - DSI_IRQENABLE (0x01C) = **0x0015C000** (errors plus TE_TRIGGER bit 16).
   - VC_IRQENABLE(n) (0x11C + 0x20·n) = **0xDB**.
   - COMPLEXIO_IRQ_ENABLE (0x050) = **0x3FF07FFF**.
3. `dsi_pll_init` (`dsi.c:1590`):
   - Make sure the DSS2 fclk is on.
   - DSI_CLK_CTRL (0x054) bit 14 CIO_CLK_ICG = 1.
   - Turn on vdds_dsi.
   - Quirk: set DISPC_CONTROL (0x48050440) bit 27 PCKFREEENABLE = 1, wfb DSI_PLL_STATUS (0x304) bit 0 RESETDONE == 1, then set bit 27 = 0.
   - DSI_CLK_CTRL [31:30] PLL_PWR_CMD = **2** (ON_ALL). The 3630 `PLL_PWR_BUG` turns 3 into 2. Poll [29:28] == 2, 1000 × 1 µs.
4. `dsi_pll_set_clock_div` (`dsi.c:1453`):
   - DSI_PLL_CONTROL (0x300) bit 0 = 0 (manual mode).
   - DSI_PLL_CONFIGURATION1 (0x30C) = **0x01106819**: [0] STOPMODE = 1, [7:1] REGN−1 = 12, [18:8] REGM = 104, [22:19] REGM_DISPC−1 = 2, [26:23] REGM_DSI−1 = 2.
   - DSI_PLL_CONFIGURATION2 (0x310) = **0x0010200E**: [4:1] FREQSEL = 7 (fint ≥ 1.75 MHz), [13] REFEN = 1, [14] = 0, [20] HSDIVBYPASS = 1.
   - DSI_PLL_GO (0x308) = 1. wfb bit 0 == 0, then wfb PLL_STATUS bit 1 (LOCK) == 1.
   - CONFIGURATION2 = **0x0005600E**: bit 13 REFEN, bit 14 DSIPHY_CLKINEN, bit 16 DSS_CLOCK_EN, bit 18 PROTO_CLOCK_EN; idle/LP/bypass bits and bit 20 cleared.
5. Switch the DSI fclk: wfb PLL_STATUS bit 8 == 1, then DSS_CONTROL bit 1 = 1.

## 3. Complex IO (`dsi_cio_init`, `dsi.c:2286`)

1. Dummy read of DSIPHY_CFG5 (0x214), then wfb CFG5 bit 30 == 1 (SCP clock domain out of reset).
2. COMPLEXIO_CFG1 (0x048), read-modify-write [11:0] = **0x021**: [2:0] clock position = 1, [3] pol 0, [6:4] data1 position = 2, [7] pol 0, [10:8] = 0 (data2 unused). Starting from reset 0x00200000 this gives 0x00200021.
3. DSI_TIMING1 (0x058) [15:0] = 0xFFFF: FORCE_TX_STOP, ×16, ×4, counter 0x1FFF.
4. Only if coming out of ULPS (manual exit), lane override:
   - DSIPHY_CFG10 (0x228) [22:17] = 0x0A (DX0 and DX1 high), then bit 27 ENLPTXSCPDAT = 1. Net effect |= 0x08140000.
5. COMPLEXIO_CFG1 [28:27] PWR_CMD = 1. Poll [26:25] == 1, 1000 × 1 µs. Then wfb CFG1 bit 29 RESETDONE == 1.
6. DSI_CTRL (0x040) bit 0 = 1 then 0, each followed by wfb.
7. DSI_CLK_CTRL bit 20 LP_CLK_ENABLE = 1.
8. Poll DSIPHY_CFG5 bits 24 and 25 == 1, up to 100000 tight reads with no delay.
9. ULPS case only: wait 1 ms, then CFG10 bit 27 = 0 and [22:17] = 0.
10. TIMING1 bit 15 = 0.
11. PHY timings (`dsi.c:2096`). ns2ddr(x) = (x·104 + 999)/1000.
    - DSIPHY_CFG0 (0x200) = **0x0A150C10**: THS_PREPARE 10, THS_PREPARE+ZERO 21, THS_TRAIL 12, THS_EXIT 16.
    - DSIPHY_CFG1 (0x204), read-modify-write [20:0]: TLPX/2 = 3, TCLK_TRAIL = 9, TCLK_ZERO = 28. From reset 0x420A1A6A this gives **0x4203091C**.
    - DSIPHY_CFG2 (0x208) [7:0] TCLK_PREPARE = 7, giving **0xB8000007**.
    - Your dump's CFG1/CFG2 are reset values, not values from this config, and CFG0 = 0.
12. DDR_CLK_ALWAYS_ON (CLK_CTRL bit 13) is left at 0, because it is only set in video mode.
13. **[UNVERIFIED]** LDO: the driver never waits on an LDO. DSI_IRQSTATUS bit 19 LDO_POWER_GOOD exists, and is set in your dump.

## 4. Protocol engine

1. `dsi_proto_timings` (`dsi.c:3956`), with ths_eot = 4:
   - DSI_CLK_TIMING (0x06C) = **0x00001010**: DDR_CLK_PRE = ceil((20+6+28+7)/4) = 16, DDR_CLK_POST = ceil((33+12)/4) + 4 = 16.
   - DSI_VM_TIMING7 (0x090) = **0x000A000C**: enter_hs = 10, exit_hs = 12. It is written even in command mode.
   - DSI_STOPCLK_TIMING is never written (reset value 0x80).
2. `dsi_set_lp_clk_divisor` (`dsi.c:1251`): CLK_CTRL [12:0] = 8, bit 21 LP_RX_SYNCHRO = 1 (fclk > 30 MHz). Final CLK_CTRL written = **0x80304008**; it reads back as 0xA0304008.
3. `dsi_proto_config` (`dsi.c:3886`):
   - TX_FIFO_VC_SIZE (0x070) = RX_FIFO_VC_SIZE (0x074) = **0x13121110** (32 words per VC).
   - DSI_TIMING1 = **0xFFFF9000**: stop counter 0x1000 with FORCE bit 15 set; TA_TO 0x1FFF ×8 ×16 enabled.
   - DSI_TIMING2 (0x05C) = **0xFFFF7FFF**: HS_TX_TO 0x1FFF ×4 ×16 enabled; LP_RX_TO disabled because `DSI_DISABLE_LP_RX_TO` is defined.
   - DSI_CTRL = **0x0108609E**:
     - bit 1 CS_RX, bit 2 ECC_RX, bit 3 TX_FIFO_ARB
     - bit 4 VP_CLK_RATIO = 1 (errata)
     - [7:6] = 2 (24 bpp), bit 8 VP_CLK_POL = 0
     - [13:12] LINE_BUFFER = 2, bit 14 TRIGGER_RESET_MODE
     - bit 19 EOT_ENABLE
     - bit 24 DCS_CMD_ENABLE = 1, bit 25 DCS_CMD_CODE = 0. **[UNVERIFIED]** The meaning of DCS_CMD_CODE; the code comment says "1=start, 0=continue".
   - VC_CTRL(0..3) (0x100 + 0x20·n) = **0x20800180**: bit 7 CS_TX, bit 8 ECC_TX, [23:21] = 4, [29:27] = 4; SOURCE = L4, MODE = command, MODE_SPEED = LP.
4. Enable:
   - Set VC_CTRL(n) bit 0 for VCs 0-3, with wfb on each.
   - DSI_CTRL bit 0 IF_EN = 1, wfb.
   - Force stop: TIMING1 bit 15 = 1, wfb until it reads 0. TIMING1 then reads 0xFFFF1000.
5. Virtual channel: the panel gets channel 0 from `omap_dsi_request_vc`, and `set_vc_id(TCH = 0)` makes the vc_id 0 (`panel-minnow.c:54, 2743-2749`).

## 5. Sending commands

1. **Switching source (`dsi_vc_config_source`, `dsi.c:2672`).** Only done if the source changes:
   - Sync the VC (see item 7).
   - VC_CTRL bit 0 = 0, wfb. wfb bit 15 VC_BUSY == 0.
   - Set bit 1 SOURCE (0 = L4, 1 = video port).
   - VC_CTRL bit 0 = 1, wfb.
2. **Short packet (`dsi.c:2978`).**
   - Abort if VC_CTRL bit 16 (TX FIFO full) is set.
   - Write VC_SHORT_PACKET_HEADER (0x110) = DT | (vc<<6) | (data16<<8). ECC = 0; hardware generates it.
   - DCS data types: 0x05 (1 byte), 0x15 (2 bytes). Generic: 0x03, 0x13, 0x23.
   - Example: set_max_rx_packet_size(4) = 0x00000437.
3. **Long packet (`dsi.c:2914`).**
   - Requires len + 4 ≤ 128 bytes.
   - Header: VC_LONG_PACKET_HEADER (0x108) = DT (0x39 DCS / 0x29 generic) | (len<<8).
   - Payload: write words to VC_LONG_PACKET_PAYLOAD (0x10C) as b0 | b1<<8 | b2<<16 | b3<<24. The final partial word is zero-padded.
   - Writes of 0-2 bytes become short packets (`dsi.c:3017`).
4. **"Sync" = BTA plus wait (`dsi.c:2837`).**
   - Wait for the TX FIFO to drain (item 7).
   - If VC_CTRL bit 20 RX_NOT_EMPTY is set, flush the RX FIFO.
   - Set VC_CTRL bit 6 BTA_EN and read back.
   - Wait up to 50 ms for VC_IRQSTATUS(0) (0x118) bit 5 BTA, or any DSI_IRQSTATUS error in mask 0x0015C000 minus bit 16.
   - After a synced write, a non-empty RX FIFO means an error (`dsi.c:3082`).
5. **Generic read with 2 parameters** (SSD2848 register read, `panel-minnow.c:740`):
   - Short write 0x37 with length 4, no sync.
   - Short write 0x24 with data = p1 | p2<<8.
   - BTA sync.
   - Read VC_SHORT_PACKET_HEADER (0x110). [5:0] is the data type:
     - 0x02: ACK with error report, error bits in [23:8].
     - 0x11/0x12: short response, data in [15:8] / [23:8].
     - 0x1A: long response, len in [23:8]. Then read ceil((len+2)/4) more words from 0x110, bytes LSB first; the last 2 bytes are the checksum.
   - DCS read is the same with 0x06 / 0x21 / 0x22 / 0x1C.
   - Afterwards, set max rx size back to 1.
6. **HS/LP switch (`omapdss_dsi_vc_enable_hs`, `dsi.c:2708`).**
   - VC disable, IF disable (each wfb).
   - VC_CTRL bit 9 MODE_SPEED = 1 for HS.
   - VC enable, IF enable, force TX stop.
   - No NULL packet is sent, because ddr_clk_always_on = 0 in command mode.
7. **Syncing a VC (`dsi.c:2519/2568`).**
   - L4 source: wait for VC_CTRL bit 5 TX_FIFO_NOT_EMPTY == 0. Linux uses the PACKET_SENT IRQ, bit 2, with a 10 ms timeout.
   - VP source: wait for VC_TE bit 30 == 0.
   - **[UNVERIFIED]** Polling IRQSTATUS bits with the enables masked should work, but I haven't confirmed it.

## 6. Frame update

**Power-on order** (`panel-minnow.c:2876`):
1. DSI enable (sections 2-4), then LP mode.
2. Bridge/panel reset and the init command buffer. Writes use BTA sync.
3. TEAR_ON: DCS 0x35, 0x00.
4. `omapdss_dsi_enable_te(true)`.
5. DISPLAY_ON: 0x29.
6. Switch to HS.
7. `dsi_enable_video_output`. In command mode this only does init_dispc plus mgr_enable; no DSI register is touched (`dsi.c:4137`).

**TE path.** No `gpio_te` is defined, so `_minnow_panel_enable_te` calls `omapdss_dsi_enable_te` and `dsi->te_enabled` becomes true (`panel-minnow.c:3578`). The update therefore takes the **TE_EN + BTA** path, not TE_START.
- `minnow_panel_te_isr` exists only for the GPIO case and is never registered. So "TE ISR never fires; omap_dsi_update called directly" is correct.
- The DSI hardware gates each frame on the bridge's TE trigger message. ~22 ms back-to-back matches 1/45 Hz.
- ULPS entry sends TEAR_OFF and sets te_enabled = 0; ULPS exit sets it back to 1.

**DISPC side** (`dsi_display_init_dispc` at `dsi.c:4444`, then apply/`dispc_mgr_set_lcd_config`):
1. Wait for PLL_STATUS bit 7, then DSS_CONTROL bit 0 = 1.
2. DISPC_CONTROL (0x048050440) = **0x00018B08**: bit 3 STNTFT, [9:8] = 3 (24 lines), bit 11 STALLMODE, bit 15 GPOUT0, bit 16 GPOUT1; bits 27/28/29 = 0.
3. DISPC_CONFIG (+0x44) = **0x00010204**: bit 16 FIFOHANDCHECK, bit 9 FUNCGATED, LOADMODE = 2.
4. DIVISOR (+0x70) = **0x0001000F**.
5. Timings use hsw = hfp = hbp = vsw = 1 and vfp = vbp = 0 (`dsi.c:4829`):
   - TIMING_H (+0x64) = 0, TIMING_V (+0x68) = 0.
   - POL_FREQ (+0x6C) = 0. Linux ORs into this register; write 0 yourself.
   - SIZE_LCD (+0x7C) = **0x0121013F**.
6. DEFAULT_COLOR0 (+0x4C) = 0. TRANS_COLOR0 (+0x54) = 0.
7. GFX pipe:
   - BA0 (+0x80) and BA1 (+0x84) = framebuffer physical address. POSITION (+0x88) = 0. SIZE (+0x8C) = 0x0121013F.
   - ATTRIBUTES (+0xA0) = **0x91**: bit 0 enable, [4:1] = 8 RGB24U (xRGB8888, word 0x00RRGGBB, so in memory B is the lowest byte), [7:6] = 2 burst ×8, bit 8 = 0 LCD channel.
   - FIFO_THRESHOLD (+0xA4) = **0x03C00380**. The 3630 manual-update FIFO bug rule gives low = 1024 − 2·64 and high = 1024 − 64.
   - ROW_INC (+0xAC) = 1, PIXEL_INC (+0xB0) = 1.
   - GLOBAL_ALPHA (+0x74) [7:0] = 0xFF.

**Per-update sequence** (`dsi.c:4232`; `panel-minnow.c:3081`):
1. Long DCS writes in HS: 0x2A 00 00 01 3F, then 0x2B 00 00 01 21, then BTA sync.
2. Set VC0 source to VP. VC_CTRL becomes 0x20800383.
3. Packet sizes: 960 bytes per line, packet payload = 3069/960·960 = 2880, so packet_len = 2881. TE_SIZE = 96·2881 + 1921 = **278497 (0x43FE1)**.
4. VC_TE(0) (0x104) = 0x00043FE1.
5. VC_LONG_PACKET_HEADER(0) = **0x000B4139**.
6. VC_TE(0) = **0x40043FE1** (TE_EN).
7. DISPC_SYSCONFIG [4:3] = 1 (no-idle).
8. Write the DISPC timing and LCD config shown above, then DISPC_CONTROL bit 0 LCDENABLE = 1.
9. VC_CTRL(0) bit 6 BTA_EN = 1.
10. Wait for DISPC_IRQSTATUS (+0x18) bit 0 FRAMEDONE, with a 250 ms timeout. Write 1 to clear it, then set SIDLEMODE back to 2.
    - LCDENABLE clears itself in stall mode.
    - FRAMEDONE means DISPC has finished, not DSI. Before the next L4 command, wait for VC_TE bit 30 == 0.
    - DSI_IRQSTATUS bit 16 TE_TRIGGER only cancels a debug timer.

**Overlays on 3630.**
- GFX and VID2 support ARGB32 (0xC), RGBA32 (0xD) and RGBX32 (0xE). VID1 has no alpha formats.
- Pre-multiplied alpha (ATTRIBUTES bit 28) exists only on GFX and VID2. Global alpha: GFX in GLOBAL_ALPHA [7:0], VID2 in [23:16]. Your dump has VID2's set to 0, so set it to 0xFF.
- Per-pixel blending needs DISPC_CONFIG bit 18 LCDALPHABLENDERENABLE. Z-order is fixed in hardware.
- VID ATTRIBUTES: [4:1] format, [15:14] burst, bit 16 channel. VID1 base +0xBC, VID2 base +0x14C; size at base+0x0C, picture size at base+0x28.
- **[UNVERIFIED]** The z-order (GFX at the bottom, VID2 on top) comes from my reading of the TRM, not from the code.

## 7. Disable paths (`dsi.c:4679`)

1. **Fast path (true, true)**, used for errors and normal power-off:
   - soft reset, then `dsi_cio_uninit`: CLK_CTRL bit 13 = 0, CFG1 PWR_CMD = 0 with poll, CLK_CTRL bit 14 = 0.
   - `dsi_pll_uninit`: PLL_PWR_CMD = 0, vdds_dsi off.
   - No ULPS is entered.
2. **Panel ULPS (false, true)**, after 250 ms idle (`panel-minnow.c:1289`):
   - TEAR_OFF, then sync all VCs.
   - `dsi_enter_ulps` (`dsi.c:3433`):
     - force TX stop, disable VCs 0-3
     - check COMPLEXIO_CFG2 (0x078) bits 16/17 (HS/LP busy) == 0
     - set CFG2 [9:5] = 0x03, read back
     - wait up to 1 s for COMPLEXIO_IRQSTATUS bit 30
     - clear [9:5]
     - CFG1 PWR_CMD = 2 (ULPS)
     - IF disable
   - Then IF/VC disable, DSS_CONTROL bit 1 = 0, CIO power off, PLL off with vdds left on.
3. **ULPS exit.** Run the whole enable sequence again. The only state carried across is the "ulps_enabled" flag, which triggers the lane-override exit in section 3 step 4. Every DSI register is lost to the soft reset.
4. **Normal power-off.** `dsi_disable_video_output`: DSS_CONTROL bit 0 = 0. Then the panel-off commands, then the fast disable.

## 8. Workarounds in the code

- PCKFREEENABLE toggle to get the PLL out of reset (`dsi.c:1635`).
- PLL power command 3 is broken, so 2 is used.
- Dummy SCP read of CFG5 after reset.
- Manual ULPS exit via lane override.
- VP_CLK_RATIO = 1, and packet payload must be a whole number of lines (errata).
- Line buffer uses 1023 rather than 1024 entries.
- 3630 DSI FIFO bug thresholds.
- DISPC no-idle during each transfer.
- LP_RX timeout disabled.
- Error handling: FIFO underflow disables the overlay; SYNC_LOST (DISPC bit 14) restarts the output (`dispc-compat.c:361-379`).
- Vendor additions: a soft reset on every enable, and resending the first command after a DSI reset because the SSD2848 reports "false control" (`panel-minnow.c:1264`).

## Check against `aos-dispc.txt`

| Register | Dump | Calculated |
|---|---|---|
| DISPC_CONTROL | 0x00018B08 | 0x00018B08 (0x00018B09 while updating) |
| DISPC_CONFIG | 0x00010204 | 0x00010204 |
| SIZE_LCD | 0x0121013F | 0x0121013F |
| GFX ATTRIBUTES | 0x91 | 0x91 |
| GFX FIFO_THRESHOLD | 0x03C00380 | 0x03C00380 |
| DIVISOR | 0x0001000F | 0x0001000F |

Where the panel-on state differs from the dump:
- DSS_CONTROL is 0x3 when on, 0 in the dump.
- The DISPC fclk is 138.67 MHz rather than 172.8 MHz, so pck is 9.24 MHz rather than 11.52 MHz.
- DISPC_IRQENABLE gains bit 0 (FRAMEDONE) during updates. The dump has 0xD640.
- The dump's DSI and DSIPHY values are reset values, not live values.

**Not determined from the sources:** the exact meaning of DSI_CTRL bit 25; which PMIC rail is VDDS_DSI; the CM_CLKEN_PLL bit positions; and whether IRQSTATUS bits latch while their enable bit is off.

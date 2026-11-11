<!-- Research digest from the vendor kernel sources, 2026-11-10. Not verified on the watch. -->

I found the raw disk image at `/Users/darrel/Downloads/AsteroidOS/minnow/dump/mmcblk0` (3959422976 bytes, 7733248 sectors) and decoded its MBR and EBR chain directly (read-only). The real partition table is in C.4.

---

# A. Digest of `/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-minnow/src/storage/emmc.c`

Classes: (1) SoC/host specific, (2) generic SDHCI, (3) portable card logic, (4) partition/guard/crc.

| Lines | Item | Class | Notes |
|---|---|---|---|
| 15–40 | GCC/TLMM/CORE defines | 1 | `EMMC_IDLE_MS 3000` (15) is generic |
| 41–99 | HC_* offsets, CTRL/CLK/NINT/CAPS/XFER/CMD/ADMA bits | 2 | `HC_VENDOR_SPEC` 0x10c and `HC_VENDOR_CAPS0` 0x11c are MSM-only (1) |
| 101–122 | R1/R1B/R2/R3 encodings, OCR, STATUS, EXT_CSD indices | 3 | R* are built from SDHCI CMD-register bits |
| 124–137 | `MAX_XFER_BLOCKS 64`, `MAX_PARTS 64`, `MAX_GUARD 32`, statics | mixed | see below |
| 139–144 | `hc_rb/wb/rw/ww/rl/wl`: 8/16/32-bit MMIO at `HC+r` | 2 | |
| 146–156 | `crc32` | 4 | also used by `kv.c:31` |
| 158–165 | `wait_clear(addr,mask,us)` | generic helper | |
| 167–180 | `gcc_enable` (GPLL0 vote, AHB/APPS CBCR, RCGR) | 1 | |
| 182–188 | `pins_config` (TLMM SDC1 drive/pull) | 1 | |
| 190–196 | `hc_reset(mask)` (byte at 0x2f, polls up to 100 ms) | 2 | |
| 198–226 | `pwrctl_handshake`, `pwrctl_drain` | 1 | |
| 228–257 | `rates[]`, `set_clock(hz)` | 1+2 | Only two rates. The GCC M/N/D sets the frequency; SDHCI CLK only does INT_EN, then poll STABLE (20 ms), then SD_EN. Fails if CMD/DAT inhibit is set. Writes `card.clock_hz`. |
| 259–265 | `struct cmd` | 3 | |
| 267–276 | `cmd_fail` | 2 | Logs, W1C NINT/EINT, `hc_reset(CMD|DAT)`, returns `-(eint ?: 0x10000)` |
| 278–282 | `slow_clear` (40 µs at ≤400 kHz) | 1 (MSM quirk) | |
| 284–363 | `send()` | 2 | the command plus data engine |
| 365–376 | `cmd()` | 3 | wrapper; returns -2 if `resp & STATUS_ERRORS` when CMD_INDEX is set |
| 378–398 | `card_status` (CMD13), `wait_tran` (polls until READY and TRAN) | 3 | |
| 400–411 | `ext_csd_switch` (CMD6 R1B, then wait_tran, then CMD13 SWITCH_ERROR check, -4) | 3 | |
| 413–420 | `read_ext_csd` (CMD8, 1×512, copied from bounce) | 3 | |
| 422–428 | `rails_on` (RPM L17 2.95 V, L6 1.8 V) | 1 | |
| 430–467 | `host_init` | 1+2 | rails, GCC, pins, HC_MODE, core SW reset, VENDOR_SPEC 0xa1c, RESET_ALL, pwrctl, CAPS 1.8 V fixup, bus power from CAPS, handshake, CTRL1=ADMA32, CTRL2=0, NINT_EN 0x000b, EINT_EN 0xffff, SIG=0, 400 kHz, 1 ms |
| 469–488 | `card_ready` (CMD0, 1 ms, CMD1 `0x40ff8000` loop for 1.5 s) | 3 | |
| 490–517 | `card_identify` | 3 | CMD1 failure leads to CMD5 wake and retry, then CMD2 (CID), CMD3 RCA=2, CMD9 (CSD), CMD7, wait_tran |
| 519–540 | `card_speed_up` | 3+2 | HS_TIMING=1, then CTRL2 SDR25 (2), 50 MHz, wait_tran, BUS_WIDTH from `card.caps & CAPS_8BIT` (**SDHCI caps bit**), CTRL1 width bits (2) |
| 545–587 | `emmc_init(fast)` | 3 | generation++, guard clear, host_init, identify, EXT_CSD, PART_CONFIG→user, speed_up, re-read EXT_CSD, verify, sector-mode only |
| 589–592 | `emmc_card` | 3 | |
| 598–602 | `branch_on(cbcr)` | 1 | |
| 604–643 | `emmc_sleep(on)` | 3, with lines 621–623 and 626–631 being 1 | see power below |
| 646–658 | `emmc_idle`, `emmc_next_ms` | 3 | |
| 660–693 | `xfer` | 3 | 64-block chunks through bounce: CMD17/18/24/25, timeout 2 s, R1 status check, after a write `wait_tran(2000)`, wdt_feed |
| 695–719 | `emmc_read`, `emmc_write` | 3+4 | write is refused (-10) unless `guarded()` |
| 702–742 | `guarded`, `emmc_guard_clear`, `emmc_guard_set` | 4 | |
| 744–799 | `utf16_name`, `le32`, `gpt_load(lba)` | 4 | |
| 801–832 | `emmc_part_scan` (primary GPT at LBA1, then backup at `sectors-1`), `emmc_part_count/get/find` | 4 | |

**Key structures (verbatim):**
```c
struct cmd { uint32_t index, arg, flags; uint32_t resp[4]; uint32_t blocks, blksz; bool read; uint32_t timeout_us; };   // 259
static uint8_t bounce[MAX_XFER_BLOCKS * EMMC_BLOCK] __attribute__((aligned(64)));                         // 135
static struct { uint16_t attr, len; uint32_t addr; } adma[8] __attribute__((aligned(64)));               // 136
static uint8_t gpt_buf[32 * EMMC_BLOCK] __attribute__((aligned(64)));                                    // 137
static int send(struct cmd *c);  static int cmd(uint32_t index, uint32_t arg, uint32_t flags, uint32_t *resp);
```
`struct emmc_info` and `struct emmc_part` are in `emmc.h:9-20`. Note that `mci_version` and `caps` in `emmc_info` are host-specific fields.

**`send()` mechanics (284–363):**
1. Polls `PRESENT & (CMD|DAT inhibit)` for up to 100 ms. On timeout it resets CMD/DAT and returns -1.
2. W1C on NINT/EINT, then `slow_clear`, then TIMEOUT=0xe.
3. If there is data, it uses one ADMA descriptor (`len` is a u16, so the 64×512 = 32 KiB maximum fits) pointing at `bounce`.
4. Cache handling: clean `adma`; for reads invalidate the bounce buffer before the command and again after TC (359–360); for writes clean it.
5. Sets ADMA_ADDR, BLKSZ, BLKCNT and the mode (DMA, READ, and for multi-block MULTI|BLKCNT|AUTO_CMD12). Then ARG, XFER_MODE, `dsb`, and a 16-bit write to CMD `(index<<8)|flags`.
6. Polls NINT for CMD_DONE or ERROR (100 ms), clears CC, then `slow_clear`.
7. Response handling: R2 is shifted by 8 bits across the 4 words (the SDHCI drops the CRC byte), so `resp[3]` ends up holding the top bits. Other responses read `RESP[0]`.
8. For data or R1B it polls for XFER_DONE (default limit 1 s, or `timeout_us`) with wdt_feed. An error that is *only* a data timeout ends the wait and returns "data timeout" (fail).
9. There is no interrupt use anywhere: `NINT_SIG`/`EINT_SIG` are 0. Errors come back as negative ints. Codes from `send()`/`cmd_fail()` are `-(EINT bits)` or -0x10000; card-level code uses small negatives (-2 … -7, -10, -2x for GPT).

**Power behaviour:**
- `emmc_sleep(true)` (609–624): wait_tran, then a cache flush if `ext_csd[33]&1` (`SWITCH` byte 32 = 1), then CMD7(0) to deselect, then CMD5 with `RCA<<16|BIT(15)` to sleep. If that fails it reselects, and marks the card not ready if the reselect also fails. It then clears SD_EN and gates the APPS and AHB CBCRs.
- Wake (626–636): ungates the branches, sets SD_EN, then CMD5 awake, CMD7, wait_tran. Any failure sets `ready=false`.
- `xfer` wakes the card automatically (664).
- `emmc_idle` sleeps the card after 3 s without I/O. `main.c:152` calls `emmc_idle`; `app.c:442` uses `emmc_next_ms`.

**Partition names the code uses:**
- `"system"`: `firmware.c:27`
- `"userdata"`: `rootfs.c:31`
- `"cache"`: `EMMC_WRITE_PARTITION` (`emmc.h:7`). This is both the guard partition (`emmc.c:730`) and the store partition (`storage.h:8` `STORE_PARTITION`, `store.c:13`).
- `"nvdata"`: `sensors/hub.c:150`. This is qcom-only (hub.c is in `SRCS_qcom`).
- The console takes arbitrary names and prints `p->name` (`console.c:578-599`).

Today `emmc.c` is linked only for qcom (`Makefile:44`). The omap3 build has no emmc provider apart from `tests/stubs.c`.

---

# B. OMAP3630 HSMMC2 facts

Source: kernel `drivers/mmc/host/omap_hsmmc.c`, plus TRM recollection where marked (TRM).

**Basics**
- Base 0x480B4000. On OMAP3 there is no +0x100 offset; that offset is OMAP4 only (`omap_hsmmc.c:1701`).
- IRQ 86 and sDMA requests TX=47, RX=48 (`omap_hwmod_3xxx_data.c:1834-1843`, `omap3.dtsi:315`). These are the 1-based values written to CCR.SYNCHRO_CONTROL (TRM S_DMA_46/47).
- The 3630 uses `es3plus_mmc2_hwmod`, which has no BROKEN_MULTIBLOCK flag (1874–1891).
- Sysconfig class: rev 0x1fc, sysc 0x10, syss 0x14, with CLOCKACTIVITY, SIDLEMODE (force/no/smart), ENAWAKEUP, SOFTRESET, AUTOIDLE and RESETDONE (1749–1758).
- **All registers are 32-bit. Use only 32-bit accesses (TRM).** The `hc_wb`/`hc_ww` byte and halfword helpers must not be used here.

| Off | Reg | Fields (and how they differ from SDHCI) |
|---|---|---|
| 0x10 | SYSCONFIG | AUTOIDLE b0, SOFTRESET b1, ENAWAKEUP b2, SIDLEMODE b4:3, CLOCKACTIVITY b9:8 |
| 0x14 | SYSSTATUS | RESETDONE b0 |
| 0x24 | CSRE | Mask of R1 status bits that raise STAT.CERR. Write 0 because emmc.c checks status in software. |
| 0x28 | SYSTEST | Manual line drive/observe (debug) |
| 0x2C | CON | OD b0, INIT b1, HR b2, STR b3, MODE b4, **DW8 b5** (8-bit is here, not in HCTL), MIT b6, CDP b7, WPP b8, DVAL b10:9, CTPL b11, CEATA b12, OBIP b13, OBIE b14, PADEN b15, CLKEXTFREE b16. DDR b19 is OMAP4 only. |
| 0x30 | PWCNT | Power counter |
| 0x104 | BLK | BLEN b10:0 (CAPA.MBL caps it; the kernel uses 512), NBLK b31:16 (≤65535) |
| 0x108 | ARG | |
| 0x10C | CMD | One 32-bit register, written last: SDHCI XFER_MODE in b15:0 and SDHCI CMD in b31:16. DE b0, BCE b1, ACEN b2, DDIR b4, MSBS b5, RSP_TYPE b17:16, CCCE b19, CICE b20, DP b21, CMD_TYPE b23:22, INDX b29:24. So `CMD = (sdhci_cmd16 << 16) | sdhci_mode16` exactly; the emmc.c XFER_*/CMD_* encodings carry over unchanged (kernel 783–808). |
| 0x110–0x11C | RSP10/32/54/76 | **R2 differs**: the kernel reads RSP76 as R[127:96] with no shift (884–899). So emmc.c's `<<8` fixup (336–337) is SDHCI-only; for OMAP use `resp[i] = RSP[i]`. |
| 0x120 | DATA | 32-bit FIFO port |
| 0x124 | PSTATE | CMDI b0, DATI b1, DLA b2, WTA b8, RTA b9, BWE b10, BRE b11 (same as SDHCI) |
| 0x128 | HCTL | DTW b1 (4-bit), HSPE b2 (see below), SDBP b8, SDVS b11:9 (5=1.8, 6=3.0, 7=3.3), SBGR/CR/RWC/IBG b16–19, IWE b24. There are no DMA-select bits: no ADMA and no SDHCI SDMA. |
| 0x12C | SYSCTL | ICE b0, ICS b1, CEN b2, **CLKD b15:6 (10-bit linear, f = fclk/CLKD, 0/1 = bypass)**, DTO b19:16 (TCF·2^(13+DTO), 0xE max), SRA b24, SRC b25, SRD b26. The byte layout matches SDHCI 0x2c/2e/2f but the divider semantics differ. |
| 0x130 | STAT | CC b0, TC b1, BGE b2, BWR b4, BRR b5, CIRQ b8, ERRI b15, CTO b16, CCRC b17, CEB b18, CIE b19, DTO b20, DCRC b21, DEB b22, ACE b24, CERR b28, BADA b29. This is SDHCI NINT \| EINT<<16, W1C, 32-bit. |
| 0x134 / 0x138 | IE / ISE | **A STAT bit only latches if its IE bit is set.** ISE routes to the IRQ; set ISE=0 for polling. |
| 0x13C | AC12 | Auto-CMD12 error status |
| 0x140 | CAPA | TCF b5:0, TCU b7, MBL b17:16, HSS b21, DS b22, SRS b23, VS33/VS30/VS18 b24/25/26. The VS bits are software-writable. **There is no 8-bit capability bit**: take the width from the board. |
| 0x148 | CUR_CAPA | |
| 0x1FC | REV | |

**Init sequence as the kernel does it:**
1. Fclk/iclk on: CM_FCLKEN1/ICLKEN1_CORE bit 25. Wait for CM_IDLEST1_CORE bit 25 = 0.
2. SYSCONFIG is left to hwmod: AUTOIDLE=1, ENAWAKEUP, SIDLEMODE smart. For bare metal I suggest 0x30D (no-idle) or 0x315 (smart) **(uncertain)**. Soft reset: SYSCONFIG.SOFTRESET, then poll RESETDONE. The driver itself never writes SYSCONFIG.
3. Bus power (`conf_bus_power` 1578–1600): MMC2 has no `ti,dual-volt`, so **SDVS = 1.8 V (5<<9)** and CAPA |= VS18 only. Then set SDBP and poll until it reads 1. SDBP refuses to set if SDVS doesn't match a CAPA VS bit.
4. Clock (`set_clock` 504–551): clear CEN, then write CLKD (`DIV_ROUND_UP(96 MHz, f)`, capped at 250) with DTO=0xE, then ICE, poll ICS (20 ms), then CEN. From 96 MHz:
   - 400 kHz: CLKD 240 (exactly 400 kHz)
   - 26 MHz: 4, giving 24 MHz
   - 52 MHz: 2, giving 48 MHz
5. HSPE is only set when the DT has `ti,needs-special-hs-handling`, which minnow lacks. So the kernel runs 48 MHz with HSPE=0. Copy that **(whether HSPE even exists on OMAP3: uncertain)**.
6. Init stream (`send_init_stream` 698–724): IE=mask, CON |= INIT, write CMD=0, poll STAT.CC (20 ms), CON &= ~INIT, STAT=0xffffffff. Do this once after power, before CMD0.
7. Open drain: the core sets CON.OD during identification (CMD0–CMD3), then push-pull (`set_bus_mode` 580–590). emmc.c has no equivalent.
8. Bus width (553–578): 8-bit is `CON |= DW8`; 4-bit is HCTL.DTW with DW8 clear.
9. IRQ mask in the driver: CC, TC, BWR, BRR, ERR, CTO, CCRC, CEB, CIE, DTO, DCRC, DEB, CERR, BADA (102–118). For PIO polling use IE ≈ 0x317F8033 (also add ACE b24) **(uncertain on the exact value)**.

**Completion and errors:**
- CC means command done. TC means data done, and also the end of busy for an R1B (RSP_TYPE 3).
- Quirk: "TC before CC from CMD6" (857–861).
- Errors: CTO or CCRC end the command. CTO/DTO count as timeouts; CCRC/DCRC as CRC errors.
- Recovery (`reset_controller_fsm` 975–1004): SYSCTL |= SRC (command errors) and/or SRD (data), then poll until the bit clears (20 ms). The 0→1-first wait is OMAP4 ES2+ only (`ti,needs-special-reset`) and is not needed on the 3630.

**Data movement:**
- No ADMA.
- PIO works fine. For reads, wait for STAT.BRR, W1C it, then read BLEN/4 words from DATA, once per block; for writes, BWR then write the words. Then wait for TC. The FIFO is 1 KiB, ping-pong **(TRM)**. `blksz % 4 == 0` is required (1305).
- sDMA alternative: CSDP 32-bit, constant address 0x480B4120, element count blksz/4, frame count = blocks, frame sync on request 47 (TX) or 48 (RX), plus CMD.DE. Cache maintenance would stay as it is now.
- Limits: BLEN 512, NBLK 65535 (kernel `max_blk_count 0xFFFF`). ACEN (auto-CMD12) exists, but the kernel sends CMD12 manually instead.

**DEVCONF1.MMCSDIO2ADPCLKISEL** (`CONTROL_DEVCONF1` = control base + 0x2D8, i.e. 0x480022D8, bit 6, "MMC2 loop back clock"): it is only written by `hsmmc2_before_set_reg` (`hsmmc.c:175-197`), and that is installed only on the legacy non-DT path when `HSMMC_HAS_PBIAS` is set. Minnow boots from DT (`board-minnow.c` has no mmc code), so **the kernel never touches it**; whatever the bootloader set is what is in use. Read it at runtime and log it, but don't write it **(uncertain which value mbm leaves)**.

**Pads:** the minnow DT has no `pinctrl` on `&mmc2` (`omap3-minnow.dtsi:946-951`), so the pads are left to the bootloader. Padconf for sdmmc2_clk/cmd/dat0-7 is 0x48002158–0x4800216A (TRM).

**Supplies:** LDO5 2.8 V always-on and DCDC3 1.875 V boot-on/always-on (`dtsi:560-615`). `set_power` returns early for DT non-removable slots when powering off, so there is no rail work to do.

**Context:** MMC2 is in CORE_PD. CORE retention keeps the registers. CORE OFF loses all MMCHS context (CAPA VS bits, HCTL SDVS/SDBP, SYSCTL, CON). The kernel detects this through the context-loss count and restores HCTL/CAPA/SDBP, width, clock and OD (598–666). The card keeps its own state because its rails stay on.

---

# C. Split proposal

## C.1 Host interface: new file `src/storage/emmc_host.h`

```c
struct emmc_req { uint32_t index, arg, flags /*SDHCI CMD bits*/, mode /*SDHCI XFER bits*/;
                  uint32_t blocks, blksz; bool read; void *buf; uint32_t timeout_us; uint32_t resp[4]; };
int  host_init(struct emmc_info *card);   /* clocks, pins, rails, reset, bus power, 400 kHz, init stream */
int  host_send(struct emmc_req *r);       /* = today's send(); resp[] normalized (resp[3]=R[127:96]) */
int  host_set_clock(uint32_t hz);         /* writes card.clock_hz via return/ptr */
void host_set_width(unsigned bits);
void host_set_timing_hs(bool on);         /* MSM: CTRL2 SDR25; OMAP: nothing (HSPE off) */
void host_set_opendrain(bool on);         /* MSM: no-op; OMAP: CON.OD */
unsigned host_max_width(void);            /* MSM: CAPS_8BIT?8:4; OMAP: board (8) */
void host_card_clock(bool on);            /* SD_EN / CEN */
int  host_power(bool on);                 /* MSM: CBCR gate/branch_on; OMAP: CEN+FCLK/ICLK bit25, ret 1 if context lost */
void *host_bounce(void);                  /* keeps the 64-block aligned bounce in the host */
```

**`src/soc/qcom/emmc_msm.c`** takes the following, unchanged: lines 15–99, 135–144, 158–257, 267–363 (`send`, which becomes `host_send`), 422–467, 598–602, and 526 (CTRL2) and 537 (CTRL1 width) moved into the hooks. Keep `hc_wb(0xe,…)` and `slow_clear` in it. `card.mci_version` and `card.caps` stay as they are, filled through the pointer.

**`src/storage/emmc.c` (shared)** keeps lines 101–133, 146–156, 259–265 (struct), 365–420, 469–587 (calling hooks; add `host_set_opendrain(true)` around CMD0–3 as a no-op on MSM), 589–592, 604–658 (lines 621–623/631 become `host_card_clock` + `host_power`), and 660–832.

Byte-for-byte on Qualcomm: the register write order is the same as long as `host_send` is today's `send` verbatim and the hooks contain exactly the moved statements.

## C.2 OMAP host: `src/soc/omap3/hsmmc.c`

- `host_init`:
  1. FCLKEN1/ICLKEN1 bit 25, wait IDLEST.
  2. SOFTRESET and RESETDONE.
  3. SYSCONFIG.
  4. CON=0 (DW8 later), CSRE=0.
  5. HCTL SDVS18, CAPA |= VS18, SDBP and poll.
  6. IE=mask, ISE=0.
  7. 400 kHz (CLKD 240, DTO 0xE).
  8. Init stream.
  9. Log DEVCONF1 and padconf.
- `host_send`:
  1. Poll PSTATE CMDI|DATI.
  2. STAT=~0.
  3. BLK = `blocks<<16|blksz`, ARG, then a single 32-bit CMD = `(flags<<16) | (index<<24) | mode`, minus DE for PIO. Note that `index<<8` in 16-bit terms becomes bit 24.
  4. Poll CC/ERRI; R2 read straight.
  5. PIO loop on BRR/BWR, then TC.
  6. On an error: SRC/SRD per `reset_controller_fsm` and return `-(STAT>>16 ?: 0x10000)`, so existing error codes keep their shape.
- `host_set_clock`: CLKD 240 or 2 (or 4) with ICE/ICS/CEN.
- `host_set_width(8)`: CON.DW8.
- `host_power(false)`: CEN off, clear FCLK/ICLK bit 25. `host_power(true)`: re-enable, then if `HCTL.SDBP==0` (context lost) redo steps 5–7 at the stored clock and width, without the init stream.

## C.3 Partition lookup without names

In `emmc_part_scan` (801), after both GPT attempts fail (so the Qualcomm path is untouched), call `mbr_load()`. Name each partition from `board->emmc_part_names[pnum]` (add `const char *const *emmc_part_names; unsigned emmc_nparts;` to `struct board`, `src/board/board.h`), falling back to `"p<N>"`.

Minnow table:
```
1:"" 2:"mbm" 3:"" 4:"ebr" 5:"cdt" 6:"pds" 7:"utags" 8:"logo" 9:"boot" 10:"recovery"
11:"misc" 12:"" 13:"" 14:"system" 15:"cache" 16:"customize" 17:"userdata"
```
- p14 matches `firmware.c:27`, p15 matches the guard/store (`"cache"`), p17 matches `rootfs.c:31`. Note that the dump's file is named `p17_data`, but the code wants `"userdata"`.
- `"nvdata"` is qcom-only.
- Names for p1/p3/p12/p13 are unknown.
- Leave p4 out of `parts[]`, or keep it with count=1 so the guard can never cover it.

**Walking algorithm (all little-endian):**
1. Read LBA0 and require `0x55AA` at byte 510.
2. The 4 entries start at byte 446, 16 bytes each: +0 boot flag, +4 type, +8 start LBA (u32), +12 sector count (u32).
3. If any entry has type 0xEE, it's a protective MBR: stop.
4. p1–p4 are the primary entries; skip type 0 and keep the slot number.
5. For an extended entry (type 0x05, 0x0F or 0x85): `ext = start`, `cur = ext`, n = 5. Loop:
   - Read `cur` and require `0x55AA`.
   - Entry 0: `first = cur + start0`, `count = size0` (start is relative to this EBR). Record it as p`n`, n++.
   - Entry 1: if type is 0 or start is 0, stop. Otherwise `cur = ext + start1` (relative to the start of the extended partition).
   - Bound the loop at MAX_PARTS and reject `cur` outside `[ext, ext+size)`.
6. Range-check every `first+count ≤ card.sectors`, as `gpt_load` does (791).

## C.4 Decoded real table (from `mmcblk0`; LBA, 512-byte sectors)

MBR: p1 type 83 start 256 size 256 (bootable 0x80); p2 type 83 1024/1024; p3 type 83 2048/1024; p4 type 05 3072/7730176.

The EBRs sit in consecutive sectors 3072–3084, and each link entry is `rel = k`, `size = 1`.

| p | start | size | p | start | size |
|---|---|---|---|---|---|
| 5 | 4096 | 1024 | 12 | 84992 | 1024 |
| 6 | 5120 | 8192 | 13 | 86016 | 16384 |
| 7 | 13312 | 3072 | 14 system | 102400 | 524288 (256 MiB) |
| 8 | 16384 | 2048 | 15 cache | 626688 | 524288 (256 MiB) |
| 9 boot | 18432 | 32768 | 16 | 1150976 | 262144 |
| 10 | 51200 | 32768 | 17 data | 1413120 | 6320128 (ends 7733247, the last sector) |
| 11 | 83968 | 1024 | | | |

LBA1 is zeros, so there is no GPT. The disk is 7733248 sectors. The sizes match the files in `/Users/darrel/Downloads/AsteroidOS/minnow/dump/extracted_partitions/`. p4 (`ebr`) was not extracted; it is skipped by `/Users/darrel/Downloads/AsteroidOS/minnow/dump/extract`.

## C.5 Other portability points

- `card_speed_up`: replace `card.caps & CAPS_8BIT` (532) with `host_max_width()`.
- The verification at 573 already checks the width that was applied.
- OCR `0x40ff8000` is fine for the 2.8 V card.
- The `ext_csd[33]` cache flush and the CMD5/CMD7 sleep and wake are portable.
- The CMD1-fails-then-CMD5-wake fallback (496–499) also covers waking up after CORE OFF.
- `emmc_info.mci_version` is meaningless on OMAP; put the REV register there or leave it 0.
- The console prints names, so the `"pN"` fallback keeps it working.

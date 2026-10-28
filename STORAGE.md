# Persistent storage (eMMC)

Status 2026-10-28: code written offline in the worktree `asteroid-embedded-emmc`
(branch `emmc`, uncommitted), builds without warnings, **never run on the
watch**. The ext4 reader, the store resolution, the write guard logic and the
key/value format were exercised on the pc against real images (see "Host
test" below); the SDHCI driver itself is untested.

Tags as in BLUETOOTH.md: [V] verified (source or file named), [I] inferred,
[U] unknown / to check on the watch.

Why: M7 needs persistent BLE bond keys (Sync bonds with MITM) and a stable
BD_ADDR; settings, alarms and notifications later.

## 1. Code

| File | What |
|---|---|
| `src/storage/emmc.c/.h` | SDCC1 SDHCI driver, GPT, write guard, CRC-32 |
| `src/storage/ext4.c/.h` | read-only ext4, nested volumes (loop image inside userdata) |
| `src/storage/store.c` | finds the AsteroidOS root fs, resolves the store file, arms the guard |
| `src/storage/kv.c` | key/value records, two alternating slots |
| `src/storage/storage.h` | API |
| `src/console/console.c` | commands (below) |
| `tests/stubs.c` | stubs for the new console commands (`make test` still fails to link for the pre-existing `cpu_clock_*`, `pmic_read`, `power_request`, same as before this change) |

API: `emmc_init(fast)`, `emmc_read(lba, n, buf)`, `emmc_write(lba, n, buf)`
(guarded), `emmc_part_scan()`, `emmc_part_find(name, &first, &count)`,
`storage_mount()`, `ext4_lookup/read/list/map`, `store_open/read/write`,
`kv_get/set/del/each`.

Console (all over `adb shell <cmd>`; nothing in the boot path calls any of it):

| Command | Does |
|---|---|
| `emmc [safe]` | (re)init, print host caps/clock/width, CID, CSD, OCR, capacity, EXT_CSD basics. `safe` stays at 400 kHz, 1-bit, no CMD6 |
| `part` | GPT list: index, name, first LBA, sectors, KiB |
| `emmcrd <part> <sector> [1-8]` | hexdump sectors relative to a partition |
| `fs` | superblock summary of userdata and of the AsteroidOS root fs, where the root fs was found |
| `ls [userdata:]<path>` / `cat [userdata:]<path>` | read-only browsing; without the prefix paths are in the AsteroidOS root fs |
| `store` | resolve the store file, print its eMMC runs and whether it is writable (and why not) |
| `emmctest` | save / write pattern / read back / compare / restore on the **last 4 KiB of the store file only** |
| `kv`, `kv set <k> <text>`, `kv del <k>` | list / change records |
| `btinfo` | AsteroidOS BD_ADDR file and, per BlueZ peer, which key groups exist (never prints key values) |

There is no raw-LBA write anywhere in the console.

## 2. Hardware (sturgeon, APQ8026)

| Item | Value | Source |
|---|---|---|
| SDHCI (hc) | 0xf9824900 (0x11c bytes) | [V] downstream `qcom/msm8226.dtsi` sdhc_1, mainline dtsi, watch `/proc/iomem` (`f9824900-f9824a1b : mmc0`) |
| MSM core | 0xf9824000 (0x800): MCI_VERSION +0x50, HC_MODE +0x78 (bit 0 enable, bit 13 FF_CLK_SW_RST_DIS), PWRCTL_STATUS +0xDC, MASK +0xE0, CLEAR +0xE4, CTL +0xE8 | [V] lk2nd `sdhci_msm.h`, downstream `sdhci-msm.c` |
| hc vendor regs | VENDOR_SPEC hc+0x10C (lk writes 0xA1C), VENDOR_CAPS0 hc+0x11C | [V] lk2nd `sdhci_msm.c` |
| IRQs | hc SPI 123, pwr SPI 138 (driver polls, GIC lines not enabled) | [V] dtsi |
| Clocks | GCC SDCC1: BCR 0xfc4004c0, APPS_CBCR 0x4c4, AHB_CBCR 0x4c8, CMD_RCGR 0x4d0, CFG_RCGR 0x4d4, M/N/D 0x4d8-0x4e0; source GPLL0 (sel 1) 600 MHz; vote APCS_GPLL_ENA_VOTE 0xfc401480 bit 0, GPLL0_STATUS 0xfc40001c bit 17 | [V] lk2nd `platform/msm8226/include/platform/iomap.h`, `msm8226-clock.c` |
| Card clock | RCG = GPLL0/3 = 200 MHz (as lk's `max_clk_rate`), divided by the SDHCI clock divider: 400 kHz (div 250), 50 MHz (div 2) | [V] lk2nd `target/msm8226/init.c`, `sdhci.c` |
| Rails | vmmc L17 2.95 V, vqmmc L6 1.8 V (always on) | [V] downstream `msm8226-720p-mtp.dtsi` (included by `apq8026-sturgeon.dts`), mainline sturgeon dts |
| Pads | TLMM SDC1_HDRV_PULL_CTL 0xfd512044: clk 16 mA no pull, cmd 10 mA pull-up, data 6 mA pull-up | [V] lk2nd `target/msm8226/init.c set_sdc_power_ctrl` |
| Bus | 8-bit, non-removable; downstream allows HS200 1.8 V and DDR 1.8 V up to 200 MHz | [V] dtsi |
| Card | 3817472 KiB user area (7634944 sectors), RPMB 4 MiB, emmcid 16b8f028 | [V] `hw/sturgeon/partitions.txt`, `cmdline.txt` |

### Init sequence (`emmc_init`)

1. RPM: `ldoa` 17 = 2.95 V + enable, `ldoa` 6 = 1.8 V + enable (no-ops if
   already on; RPM aggregates votes) [I].
2. GCC: vote GPLL0, enable the AHB branch, RCG to GPLL0/3, enable the apps
   branch (wait for CLK_OFF to clear). TLMM pad drive/pull as lk.
3. VENDOR_SPEC = 0xA1C, HC_MODE |= enable | FF_CLK_SW_RST_DIS, SDHCI
   software reset (all), drain + ack any pending PWRCTL status, PWRCTL_MASK
   = 0xF. All in lk's order (`sdhci_msm_init`).
4. If MCI major >= 1 and minor not 0x11/0x12: VENDOR_CAPS0 = caps | 1.8 V
   (lk). Bus power: highest voltage in CAPS, written as lk does (value then
   value|1); wait for PWRCTL_STATUS, write it to CLEAR, ack BUS/IO success in
   PWRCTL_CTL. lk waits for the same handshake via SPI 138; we poll. The IO
   pad switch (VENDOR_SPEC bit 16) is left as lk leaves it (cleared) [I: lk
   and Linux both run this card in that state at HS speeds].
5. HOST_CTRL1 = ADMA2-32, 1-bit; interrupt status enables (signals off);
   400 kHz.
6. CMD0, CMD1 (OCR 0x40FF8000, sector mode) until ready (1.5 s); on failure
   CMD5 (awake, RCA 2 = lk's RCA) and retry, because lk2nd's
   `target_uninit()` deselects the card and sends **CMD5 sleep** and turns HC
   mode off before it jumps to a kernel [V: lk2nd `target/msm8226/init.c`,
   `mmc_put_card_to_sleep`]. Whether CMD0 alone wakes it from Sleep [U]
   (JEDEC says Sleep accepts CMD0; the CMD5 fallback is there in case).
7. CMD2 (CID), CMD3 (RCA 2), CMD9 (CSD), CMD7 select, CMD13 until TRAN.
8. CMD8 EXT_CSD. If PARTITION_CONFIG access bits != 0, CMD6 clear-bits on
   bits 2:0 only (back to the user area) [I: lk leaves the user area selected].
9. `fast`: CMD6 HS_TIMING = 1, host UHS mode SDR25 (what lk does for HS,
   `mmc_set_hs_interface`), 50 MHz; CMD6 BUS_WIDTH = 2 (8-bit SDR) when CAPS
   has 8-bit, host 8-bit. Read EXT_CSD again in the final mode and check
   HS_TIMING/BUS_WIDTH/access bits agree (this is the first real data
   transfer at speed).

Not done, deliberately: HS200 (needs DLL init and tuning, `sdhci_msm.c`
~600 lines in lk; 50 MHz x 8 bit = ~50 MB/s is plenty for KiB-sized
records), DDR, RST_n_FUNCTION enable (lk sets it; it is a **one-time
programmable** EXT_CSD field, never touch it), cache/BKOPS/HPI, erase/trim.

"Reuse the bootloader state" fast path: **not implemented, not safe**: the
card is asleep and HC mode is off when lk2nd hands over (step 6), so there is
no live state to reuse. The stock Huawei aboot path is lk-derived [I] and
probably the same.

### Transfers

- ADMA2 (32-bit), one descriptor per command, up to 64 blocks (32 KiB),
  through a 64-byte aligned bounce buffer in .bss (first DRAM bank,
  cacheable). Why ADMA2 and not PIO: it is the only data path lk (and Linux
  sdhci-msm) use on this controller, so it is the proven one; PIO through the
  buffer data port would need BUFFER_READ/WRITE_READY handling that nothing
  on this SoC exercises. The bounce buffer keeps cache maintenance local:
  clean the descriptor and the buffer before a write, invalidate the buffer
  before and after a read (`dcache_*_range`, to PoC, so L2 included). Callers
  may pass unaligned buffers.
- Multi-block: CMD18/CMD25 with auto CMD12; single: CMD17/CMD24. After a write
  CMD13 until READY_FOR_DATA + TRAN. R1 error bits (0xFDF90000) fail the call.
- Errors: dump NINT/EINT/PRESENT/ADMA_ERR to the log, clear, reset CMD+DAT
  lines. Timeouts: 100 ms per command, 1-2 s per transfer; loops feed the
  watchdog.
- Not interrupt-driven; console use only for now.

### Write guard

`emmc_write()` refuses (log line, -10) unless the whole range lies inside
**one** range of the guard table. `emmc_guard_set()` only accepts ranges
lying entirely inside the GPT partition named by the compile-time
`EMMC_WRITE_PARTITION` (default `"userdata"`), and only `store.c` calls it,
with the eMMC runs of the store file (section 4). `emmc_init()` clears the
guard; a re-init invalidates the mount and the store (generation counter).

## 3. Partition table (sturgeon)

From Linux `/proc/partitions` (KiB) and the by-name list
(`hw/sturgeon/partitions.txt`, `partnames.txt`, sizes there in 512-byte
sectors). LBAs: run `part` on the watch [U].

| # | Name | Size | What it is | Used by AsteroidOS / boot chain |
|---|---|---|---|---|
| 1, 2 | sbl1, sbl1bak | 512 KiB each | secondary bootloader (+backup) [I] | boot ROM; **never** |
| 3 | dbi | 512 KiB | Qualcomm SDI/debug image [I] | boot chain; never |
| 4, 5 | rpm, rpmbak | 512 KiB | RPM firmware | boot chain; never |
| 6, 7 | tz, tzbak | 512 KiB | TrustZone | boot chain; never |
| 8, 9 | aboot, abootbak | 5 MiB | Huawei lk (STURGEONV3.4) | boot chain; never |
| 10 | nvdata | 10 MiB | Huawei factory data, ext4 | **mounted rw by AsteroidOS** at `/nvdata` (`init.machine.sh`, `MACWLAN` read from it) [V: meta-sturgeon] |
| 11 | nvbin | 5 MiB | Huawei NV binary [I] | unknown [U]; never |
| 12, 13 | modemst1, modemst2 | 1.5 MiB | modem EFS copies | never |
| 14 | fsc | 1 KiB | EFS cookie | never |
| 15 | ssd | 8 KiB | secure software download / QSEE secure storage [I] | never |
| 16 | misc | 1 MiB | Android bootloader control block | **read by aboot/lk** (`app/aboot/recovery.c` finds `"misc"`) [V lk2nd]; never |
| 17 | reserved | 31.5 MiB | unknown Huawei area [U] | never (content unknown) |
| 18 | DDR | 32 KiB | DDR training data written by SBL [I] | never |
| 19 | fsg | 1.5 MiB | modem golden EFS | never |
| 20 | oem | 150 MiB | Android Wear `/oem` (Huawei customisation) [I] | not mounted by AsteroidOS [I: meta-sturgeon] |
| 21 | boot | 20 MiB | lk2nd | boot chain; never |
| 22 | recovery | 20 MiB | lk2nd (this unit boots recovery) | boot chain; never |
| 23 | modem | 64 MiB | firmware (ADSP etc.) | read by AsteroidOS for firmware [I]; never |
| 24 | system | 512 MiB | Android system | AsteroidOS's sturgeon `machine.conf` sets only `sdcard_partition` [V], read-only at most; never |
| 25 | cache | 512 MiB | Android cache (OTA/recovery scratch) | not mounted by AsteroidOS [I: no reference in meta-sturgeon/meta-asteroid]; lk2nd's recovery path does not use it [I] |
| 26 | userdata | 2.33 GiB | ext4; holds AsteroidOS (loop image) | **AsteroidOS root fs**; writes only into the store file's data blocks |
| - | rpmb | 4 MiB | replay-protected area | not addressed by this driver |

`backup/sturgeon/` has boot and recovery images only.

## 4. Where our data goes

Filesystem support (Darrel, 2026-10-28): sturgeon only for now, so the own
read-only ext4 reader stays. Other watches (f2fs, btrfs) can later move to
GRUB's `grub-core/fs/` drivers (GPL-3.0-or-later, read-only) behind the same
interface; the in-place store file needs no filesystem write support.
lwext4 (BSD + GPL-2.0-or-later) is the option if real ext4 writes are ever
needed.

### Preferred (Darrel, 2026-10-28): a file in the AsteroidOS root fs

**Store file:** `/var/lib/asteroid-embedded/store.bin` in the AsteroidOS root
fs (`STORE_PATH`), fixed size, 36 KiB to 1 MiB, multiple of the fs block
size. Recommended: 64 KiB.

**Where the root fs is on sturgeon.** The initramfs (meta-asteroid
`initramfs-scripts-android/init.sh`) mounts `mmcblk0p26` (userdata,
`sdcard_partition` in meta-sturgeon `machine.conf`) at `/sdcard`, then uses
`/sdcard/asteroidos.ext4` if present, else `<media>/asteroidos.ext4` with
`<media>` = `/sdcard/media/0` if that directory exists, else
`/sdcard/media/`, as a loop-mounted root (`-o noatime,nodiratime,sync,rw,loop`);
otherwise userdata itself is the root [V]. The asteroidos.org sturgeon install
pushes the image to `/sdcard/asteroidos.ext4` under Wear OS, i.e.
`userdata:/media/0/asteroidos.ext4` [V: `install-full-adb-push-ext4.hbs`], and
this watch's `/proc/partitions` has a ~1 GB `loop0` [V]. `store.c` repeats
the initramfs logic; `fs` prints which one it found.

**ext4 features.** The AsteroidOS image is built with `-O ^metadata_csum`
[V: meta-asteroid `classes/asteroid-image.bbclass`]. The copy in
`~/Downloads/AsteroidOS/sturgeon/asteroidos.ext4` (taken from a live watch:
it has needs_recovery set and Darrel's phone bond) has: 4 KiB blocks,
256-byte inodes, has_journal ext_attr resize_inode dir_index orphan_file
filetype extent 64bit flex_bg sparse_super large_file huge_file dir_nlink
extra_isize, default mount options user_xattr acl, half_md4 hash [V:
dumpe2fs on pc]. The outer userdata fs was created by Wear OS / Android
(make_ext4fs or e2fsprogs, features [U]: check with `fs`). The reader
handles 32- and 64-byte group descriptors, flex_bg, extents (depth <= 5),
htree directories (read linearly), fast and slow symlinks; it refuses
compression, journal devices, meta_bg, MMP, dirdata, block-mapped inodes,
inline data and encrypted inodes (cleanly, with an error string).

**Write rules (enforced in `store.c` + `emmc.c`):**

- Only the data blocks of that pre-existing regular file are written; its
  extents are resolved at runtime through the root fs and, for a loop image,
  through `asteroidos.ext4`'s extents in userdata, down to eMMC sector runs.
  Those runs are the guard. No inode, bitmap, extent, directory, journal or
  superblock block is ever written, so `metadata_csum` (if present) is
  irrelevant.
- Any hole or unwritten (fallocate'd) extent at either level → no store.
- Read-only store (reads still work) if: the root fs has `needs_recovery`
  (its unreplayed journal may change the file's mapping), the file or either
  fs defaults to data=journal (`EXT4_JOURNAL_DATA_FL`, `s_default_mount_opts`;
  a mount option `data=journal` in fstab cannot be seen [U]: AsteroidOS mounts
  the loop root with `sync`, not data=journal [V init.sh]), or the runs fall
  outside `userdata`. A `needs_recovery` on the **outer** userdata fs is only
  logged: the image file's data blocks are not journalled in data=ordered,
  and its mapping cannot move under us (a loop image is overwritten in place;
  a region allocated in an unreplayed transaction would show up as a hole,
  which is refused).
- Risk to check early [U]: whether userdata is ever cleanly unmounted (it is
  mounted in the initramfs, the root is switched away from it); if the root
  fs (loop image) also shows needs_recovery after every AsteroidOS session,
  the store will be read-only in practice.

**Caveats.**

- mtime/ctime are not updated; Linux sees the new content (verified on the
  host test with debugfs), but tools comparing timestamps will not notice.
- Linux must not hold the file open across the switch (it does not: nothing
  in AsteroidOS uses it). Never edit it from Linux while relying on the
  firmware's copy.
- Reflashing or replacing `asteroidos.ext4` (a new image push), `e4defrag`,
  `resize2fs` shrinking, or a restore from backup deletes or moves the file.
  Moves between boots are fine (resolved at every `store_open`); deletion
  means an empty store (bonds lost, re-pair).
- If the file is missing: `store` says why, `kv` reads as empty, writes
  fail; the firmware keeps working. BT then needs either the raw fallback or
  pairing every boot.

**Creating it (once, from AsteroidOS over ssh/adb):**

```
mkdir -p /var/lib/asteroid-embedded
dd if=/dev/zero of=/var/lib/asteroid-embedded/store.bin bs=4096 count=16 conv=fsync
sync
```

`dd` writes real zeros, so the blocks are allocated and written. Do **not**
use `fallocate` (unwritten extents, refused) or `truncate` (holes, refused).

### Fallback: a raw partition

Build with `-DSTORE_PARTITION='"cache"' -DEMMC_WRITE_PARTITION='"cache"'`:
the store becomes the first 1 MiB of that partition, one run, same guard.

Recommendation for the fallback: **cache** (mmcblk0p25, 512 MiB). Reasons:
Android-only scratch (OTA packages, recovery command files), not mounted by
AsteroidOS, not read by the lk2nd boot chain [I], large, and nothing breaks
if it is overwritten. Risks: a return to Wear OS reformats it (data lost, no
harm); stock recovery tooling could read `/cache/recovery/command` [I] (we
would overwrite the fs superblock area, so Android would see an unformatted
cache and format it). Second choice **oem** (150 MiB, Android Wear only).
Avoid: misc (aboot reads the BCB from it), nvdata (mounted by AsteroidOS),
reserved/nvbin (unknown content), ssd/fsc/fsg/modemst*/DDR (firmware state),
anything in the boot chain, system, userdata as raw.

## 5. Record format (`kv.c`)

Store layout: slot A = bytes 0-16 KiB, slot B = 16-32 KiB, the rest
reserved (`emmctest` uses the last 4 KiB as scratch, restoring it).

Slot = 32-byte header + records, little-endian:

| Off | Size | Field |
|---|---|---|
| 0 | 4 | magic `AEKV` (0x564b4541) |
| 4 | 2 | version 1 |
| 6 | 2 | header size 32 |
| 8 | 4 | sequence number |
| 12 | 4 | payload length |
| 16 | 4 | reserved 0 |
| 20 | 4 | CRC-32 (IEEE) over the header with this field 0, then the payload |
| 24 | 8 | reserved 0 |

Record: key length (1-32), 0, value length (le16, <= 1024), key bytes, value
bytes. Keys are unique.

Load: validate both slots (magic, version, length, CRC, record walk); the
valid one with the newer sequence (serial-number compare) wins; none = empty.
Change: rebuild in RAM, write the whole image (rounded to 512 bytes) to the
**other** slot with sequence + 1, read it back and compare; only then switch.
Power loss mid-write: the slot being written fails its CRC, the previous one
is still valid and newest. Not covered: eMMC firmware corrupting the *other*
slot during a power cut (both slots share an erase block). If that matters,
use eMMC reliable write (CMD23 bit 31, EXT_CSD WR_REL_PARAM/WR_REL_SET are
printed by `emmc`) for kv commits, or put the slots >= 1 erase group apart
in a bigger file.

Suggested keys for M7: `bt.addr` (6 bytes), `bt.irk` (local, if privacy is
ever used), `bt.peer.<n>` (packed NimBLE `ble_store_value_sec` for our_sec +
peer_sec), `bt.cccd.<n>`.

## 6. Bonus: reading AsteroidOS's own Bluetooth state (read-only)

- **BD_ADDR**: `/var/lib/bluetooth-rfkill-event/bluetooth_address`, 17 ASCII
  characters, lower case, no newline, e.g. `68:67:8f:5c:8d:55`; written once
  by bluetooth-rfkill-event (random if missing, meta-asteroid patch 0002) and
  passed to brcm_patchram_plus as the controller's public address [V: image,
  patch]. Using the same value via 0xFC01 keeps the phone's view of the
  watch identical in both OSes.
- **BlueZ storage**: `/var/lib/bluetooth/<ADAPTER>/` (adapter address upper
  case) with `settings`, `attributes`, and per peer `<PEER>/info` (GKeyFile)
  [V: image, BlueZ 5.79 `src/adapter.c`]. Groups seen in the image for
  Darrel's S23 Ultra: `IdentityResolvingKey`, `LongTermKey`,
  `PeripheralLongTermKey`, `SlaveLongTermKey` (duplicate of Peripheral for
  old BlueZ), `General` (Name, `AddressType=public`, SupportedTechnologies=LE,
  Trusted, Blocked, Services), `LocalSignatureKey`, `RemoteSignatureKey`
  (Key, Counter, Authenticated), `ServiceChanged` (`CCC_LE`).
  - LTK groups: `Key` = 32 hex digits, `Authenticated` = mgmt key type (0
    unauthenticated legacy, 1 authenticated legacy, 2 unauthenticated P-256,
    3 authenticated P-256), `EncSize`, `EDiv` (decimal), `Rand` (decimal
    uint64). `LongTermKey` is the key used when the local side is central,
    `PeripheralLongTermKey` the one used when it is peripheral (BlueZ
    `store_longtermkey`) [V]. This bond: Authenticated=1 with nonzero
    EDiv/Rand in both, i.e. **LE legacy pairing with MITM**, not Secure
    Connections [V: values inspected, not copied].
  - `IdentityResolvingKey/Key`: the phone's IRK (resolves its private
    address). The watch's own IRK (`<ADAPTER>/identity`) only matters with
    `Privacy` on; AsteroidOS's main.conf sets only `ControllerMode = le` [V].
  - Key byte order: BlueZ prints the mgmt key buffer in order
    (`%2.2X` per byte), mgmt keys are little-endian as on HCI [I: verify with
    one reconnect before trusting].
- **Seeding NimBLE** (`nimble_1_10_0`, `host/include/host/ble_store.h`): as
  peripheral, an LE legacy reconnect is answered from
  `ble_store_read_our_sec()` keyed by the peer identity address and matched
  on EDiv/Rand (`ble_sm_retrieve_ltk`) [V]. Mapping: our_sec = {peer_addr =
  dir name + AddressType, ltk/ediv/rand/key_size from
  `PeripheralLongTermKey`, authenticated = (Authenticated & 1), sc =
  (Authenticated >= 2)}; peer_sec = {same address, ltk/ediv/rand from
  `LongTermKey`, irk from `IdentityResolvingKey` (irk_present)}; the peer IRK
  must also reach the controller's resolving list or NimBLE's host-side
  resolution [U: check how NimBLE 1.10 restores IRKs at start]. So yes, the
  store can be seeded read-only from BlueZ at first boot; then the phone
  reconnects without re-pairing in either OS.
- Limit: if the phone ever re-pairs with the bare-metal side, AsteroidOS's
  BlueZ copy goes stale (the phone keeps one bond per address); we cannot
  write BlueZ's file back without metadata writes. Re-pairing in AsteroidOS
  then fixes Linux, and a re-seed fixes ours.
- `btinfo` lists adapters, peers, key group names and AddressType only.

## 7. Host test (2026-10-28, pc)

`src/storage/{ext4,store,kv}.c` built for x86 with ASan/UBSan against a fake
`emmc.c` (file-backed, same guard semantics), on disk images built with
mkfs.ext4 + debugfs: outer userdata either "modern" (64bit, metadata_csum,
flex_bg) or "android-like" (no 64bit/metadata_csum/flex_bg), containing
`/media/0/asteroidos.ext4` or `/asteroidos.ext4` = the real sturgeon image
plus a 64 KiB store.bin. Results: nested lookup, directory listings, symlink
following (`/etc/os-release` → `../usr/lib/os-release`) and reads correct;
store resolved to 2 runs (8 + 120 sectors) through both levels; 6 kv commits,
reload picks the newest slot, a corrupted slot is ignored; raw write at LBA 0
refused; afterwards `e2fsck -fn` clean on both levels and the store content
visible from Linux via debugfs; the image with needs_recovery gave a
read-only store as designed. Test files were deleted from the pc afterwards.

## 8. First watch session: test plan

Read-only first; logs via `adb shell log 60`. Stop at the first surprise.

1. `emmc safe`: 400 kHz, 1-bit, no CMD6. Expect CID with the emmcid prefix
   (`androidboot.emmcid=16b8f028`, compare the serial), ~7634944 sectors,
   part_config access 0. If CMD1 never completes, note whether the CMD5
   fallback ran.
2. `part`: 26 entries matching section 3 (names, sizes); note the LBAs here.
3. `emmcrd boot 0`: `ANDROID!` magic (lk2nd boot image). `emmcrd userdata 2`:
   ext4 superblock (0xEF53 at offset 0x38 of sector 2).
4. `emmc` (HS 50 MHz, 8-bit): same CID, EXT_CSD shows hs_timing 1, bus_width
   2; repeat 2 and 3, same bytes.
5. `fs`: userdata features (record them here), root fs found at
   `userdata:/media/0/asteroidos.ext4` [expected], needs_recovery state.
6. `ls /`, `ls /var/lib`, `cat /etc/os-release`, `btinfo`: compare with the
   same files read under AsteroidOS.
7. Boot AsteroidOS, create store.bin (section 4), reboot cleanly into the
   firmware. `store`: runs, writable. Cross-check the runs: under AsteroidOS
   `filefrag -v` (if available) for the inner offsets, or skip.
8. **Only after Darrel confirms the store location**: `emmctest` (writes the
   last 4 KiB of store.bin and restores it), then `kv set test hello`,
   `kv`, reboot the firmware, `kv` again.
9. Boot AsteroidOS: `fsck` clean in the initramfs log, `hexdump -C
   store.bin | head` shows the `AEKV` slot.
10. Timing: note `emmctest` microseconds and `emmc` init ms in the log.

## 9. Open questions / unverified

- Whole SDHCI driver [U]: power handshake by polling, CMD0 from Sleep, ADMA
  on this core with our bounce buffer, HS 8-bit at 50 MHz with the pad
  switch cleared.
- RPM `uv` requests for L17/L6 accepted [U] (log shows the RPM ack).
- Outer userdata features and its clean/unclean state after AsteroidOS
  sessions [U] (affects writability, section 4).
- Data written under the loop image's `sync` mount option is irrelevant to us
  (we never write through Linux) [I].
- NimBLE IRK restore path, key byte order [U].

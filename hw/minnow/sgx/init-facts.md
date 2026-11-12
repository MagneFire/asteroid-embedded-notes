# SGX530 init: what `libsrv_init.so` does (verified by disassembly, 2026-11-11)

Read from the dump (`minnow/dump/extracted_data/system`), sha256 of `lib/libsrv_init.so`
fa890b45c4f59500ebe9f6873057b7df2226d6b32e84928dc2f523ec6f8af480. Nothing here has run on a watch.
In `.rodata` the virtual address equals the file offset. Background: `minnow/sgx-study/REPORT.md` and
`structures.md` (kernel side); this file corrects the study where marked.

## Microkernel programs

Loader at 0x958: `PVRSRVAllocDeviceMem` in the KernelCode heap (id 2, base 0x0E400000), flags 9,
alignment 0x8000, then a verbatim `PVRSRVMemCopy`.

| Program | Call site | Source offset | Copy size | Meminfo slot |
|---|---|---|---|---|
| SGX ukernel | 0xfba | 0x2898 | 0x6890 | +0x68 |
| SGX TA | 0x11ca | 0x9120 | 0x6790 | +0x6c |
| SGX SPM | 0x11f8 | 0xf8a8 | 0x5990 | +0x70 |
| SGX 3D | 0x123e | 0x15230 | 0x7130 | +0x74 |

Each copy is 8 bytes longer than the distance to the next program. Each is loaded once.

**Patched after the copy** (study said verbatim). Helper 0x8f8 writes a 32-bit immediate `v` into a
64-bit USE instruction: word0 = (w0 & 0xFFE00000) | (v & 0x1FFFFF); word1 bits 4-8 = v[25:21],
bits 12-17 = v[31:26] (mask 0x3F1F0). The 15 sites hold placeholders ending 0xBEEF:

| Program | Offset | Value |
|---|---|---|
| ukernel | +0x2260 | 0x41801000 |
| ukernel | +0x2270 | (PDS program 2 address - PDS base) >> 4 |
| ukernel | +0x2278 | TA/3D control device address |
| ukernel | +0x22b0 | 0x41800900 |
| ukernel | +0x22c0 | (PDS program 3 address - PDS base) >> 4 |
| ukernel | +0x2310 | (PDS program 4 address - PDS base) & ~15 |
| ukernel | +0x2320 | 7 |
| ukernel | +0x5328 | 0x42000900 |
| ukernel | +0x5340 | (PDS program 5 address - PDS base) >> 4 |
| TA | +0x5228 / +0x5240 | 0x42000900 / PDS program 5 offset >> 4 |
| SPM | +0x4428 / +0x4440 | same pair |
| 3D | +0x6728 / +0x6740 | same pair |

"PDS base" = PDSPixel heap base 0x0DC00000. PDS programs enter the USE programs at: ukernel +0x2260,
+0x22e0, +0x22f0, +0x80; TA +0, +0x2c0; SPM +0, +0x130; 3D +0, +0x540.

## PDS init programs

Five templates in `.rodata`, copied into the KernelCode heap (alignment 16, flags 9) and patched in
their data words only (DOUTU words, constants 0x04000000, 1, 0x100, 0x200, 0x01E0003F, 0x0004000F,
0x00120080; program 2 gets the TA/3D control address):

| # | Offset | Size | Role (from error strings) |
|---|---|---|---|
| 1 | 0x1C358 | 0x38 | primary program 1 for ukernel initialisation |
| 2 | 0x1C390 | 0x48 | secondary program |
| 3 | 0x1C3D8 | 0x38 | primary program 2 |
| 4 | 0x1C410 | 0x110 | EDM other events (to ukernel +0x80, TA, SPM, 3D) |
| 5 | 0x1C520 | 0x78 | ukernel loopback events |

Exact patched words: not listed here; the host lab's dump is the reference.

## Allocations, in order

Flags 0x4F = R|W|CACHE_CONSISTENT|NO_SYNCOBJ|EDM_PROTECT; 0x2004F adds MULTI_PROCESS.

| # | Item | Heap | Size | Align | Flags |
|---|---|---|---|---|---|
| 1 | Kernel CCB | KernelData | 0x2000 | 4 KiB | 0x4F |
| 2 | CCB control | KernelData | 8 | 4 KiB | 0x4F |
| 3 | Event kicker | KernelData | 4 | 16 | 0x4F |
| 4 | TA/3D control | KernelData | 0x120 | 32 | 0x2004F |
| 5 | HOST_CTL | KernelData | 0x4C | 32 | 0x2004F |
| 6 | Misc info | KernelData | 0x54 | 32 | 0x2004F |
| 7 | Microkernel trace buffer | KernelData | 0x2008 (zeroed) | 16 | 0x4F |
| 8 | HWPerf buffer | KernelData | 0x640C | 32 | 0x4F |
| 9 | TA signature buffer | KernelData | 0x314 | 32 | 0x4F |
| 10 | 3D signature buffer | KernelData | 0x724 | 32 | 0x4F |
| 11-14 | ukernel, TA, SPM, 3D | KernelCode | above | 32 KiB | 9 |
| 15-19 | PDS programs 1-5 | KernelCode | above | 16 | 9 |
| 20, 21 | Dummy stencil load / store | KernelData | 0x40000 each | 4 KiB | 0x0800002B |

## TA/3D control block as written by init

| Offset | Value |
|---|---|
| +0x0 | its own device address |
| +0x4 | HOST_CTL device address |
| +0x8 | CCB control device address |
| +0x18 | 2 |
| +0x80 | trace buffer device address |
| +0x88 | MKTraceProfile apphint |
| +0x8C | HWPerfFlags apphint |
| +0x98 | kernel CCB device address |
| +0x9C | **kernel page-directory physical address** |
| +0xDC | KernelData heap base |
| +0xE0, +0xE4 | stencil load/store offset from KernelData base, \| 0x80000000 |
| +0xE8, +0xEC, +0xF0 | HWPerf, TA signature, 3D signature buffer addresses |

## Init scripts (12-byte entries `{op, offset, value}`, op 1 = write, 4 = halt)

Part 1: 0xA58 = 0; `EVENT_TIMER` 0xACC = 0; halt.

Part 2:

| # | Register | Value |
|---|---|---|
| 0 | `EVENT_HOST_ENABLE` 0x130 | 0x4000 |
| 1 | `EVENT_HOST_ENABLE2` 0x110 | 0 |
| 2 | 0x13C | 0 |
| 3 | 0xA7C | 0 |
| 4 | 0xA80 | 0 |
| 5 | 0xA74 | (MaxEDMTasks << 16) \| 0x8200, default 0x003F8200 |
| 6 | 0x4E8 | 0 |
| 7 | 0xA78 | 0 |
| 8 | 0xABC | 0x40 |
| 9 | 0x804 | CacheCtrl apphint, default 0xFFFF |
| 10 | 0xA00 | 0x7C000 (0xFC000 with RegBoundReturnZero) |
| 11-20 | `USE_CODE_BASE(0..9)` 0xA0C.. | ((PixelUSSE base + n * 512 KiB) >> 8) \| 0x01000000 |
| 21-24 | `USE_CODE_BASE(10..13)` | (VertexUSSE base + n * 512 KiB) >> 8 |
| 25 | `USE_CODE_BASE(15)` 0xA48 | (KernelCode base >> 8) \| 0x03000000 |
| 26 | `PDS_EXEC_BASE` 0xAB8 | PDSPixel heap base |
| 27 | 0xB30 | 0x100 |
| 28 | `EVENT_KICKER` 0xAC4 | device address of the kicker word |
| 29 | 0xA68 | (PDS program 1 address - PDS base) & ~15 |
| 30 | 0xA6C | 3 |
| 31 | 0xA70 | 0x00013D01 |
| 32 | 0xA58 | 0x2204F00F |

The BIF requestor bases are not written by any script (study guessed they were).
Deinit: 0 to 0xA58, 0xA68, 0xA6C, 0xA70, 0xA48, 0x130, 0x110, 0x000; halt.

## Values handed to the kernel

- `ui32EDMTaskReg0` 0xB10, `ui32EDMTaskReg1` 0xB1C; `ui32ClkGateCtl` 0x00222220;
  `ui32ClkGateStatusReg` 0x004, mask 0xFFFFFFFF; `ui32CacheControl` 2.
- `asInitDevData`: [4] = 2, [6] = 0x180, [7] = 0x640, [8] = PDS heap base, [9] = PixelUSSE heap base,
  [10], [11] = stencil buffers.
- Host kick addresses (constants, not relocated, so the ukernel must be first in the KernelCode
  heap): TA 0x1EC, TRANSFER 0x1CD, POWER 0x18D, CONTEXTSUSPEND 0x1AB, CLEANUP 0x21D, GETMISCINFO 0x40E,
  PROCESS_QUEUES 0x3B1, SETHWPERFSTATUS 0x3B7.
- Struct sizes (build options 0x0016801C): CMDTA 1304, CMDTA_SHARED 1128, TRANSFERCMD 1204,
  TRANSFERCMD_SHARED 268, 3DREGISTERS 136, HWPBDESC 68, HWRENDERCONTEXT 64, HWRENDERDETAILS 1040,
  HWRTDATA 52, HWRTDATASET 76, HWTRANSFERCONTEXT 228, HOST_CTL 76, COMMAND 32.

## Other facts

- `CM_CLKSEL_SGX` under AsteroidOS reads 4: 192 MHz (`aos-prcm.txt`). The driver assumes 200 MHz.
- All 201 files of the vendor kernel driver are dual MIT/GPLv2.
- The blobs import about 130 libc functions and no thread creation; softfp ABI (firmware is hard).
- Active power: the microkernel sets `HOST_CTL.InterruptFlags` bit 1 or 2 and raises SW_EVENT; the
  host answers in `InterruptClearFlags`, and for bit 1 sends POWER/POWEROFF, polls `PowerStatus`
  bit 3, runs the deinit script and cuts power. A new command also counts as an answer.
- Completion of work: the microkernel writes the ops-complete words at the addresses given in the
  command's shared header, and raises SW_EVENT (bit 14 of 0x12C).

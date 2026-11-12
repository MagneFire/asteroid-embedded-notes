<!-- Static study by gpt-6.1-sol, 2026-11-12. Read from the dump and the vendor kernel; nothing run. -->
# SGX530 triangle submission path

This report establishes the host-side allocation and submission path, with explicit unresolved fields. It is not an exhaustive private-ABI reconstruction or a validated emulator recipe; the final unread list defines the remaining work.

## Scope and evidence notation

This is a static study of the owner's dump, with the local dual MIT/GPL kernel driver as the only source reference. No vendor CPU code was executed; no watch connection or web access was used. The previous `ta-path.md` did not exist when this study began. Existing Ghidra output was available in `/private/var/folders/xt/461q2g0d1xsbxpg8rrl7qmv80000gn/T/sgxta/out/`; addresses below are ELF virtual addresses, with the Thumb bit cleared. `S` means `libsrv_um.so`, `G` means `libGLESv2_POWERVR_SGX530_125.so`, `E` means `libIMGegl.so`, and `W` means `libpvrANDROID_WSEGL.so`. Kernel paths are relative to `minnow/minnow-kernel/drivers/gpu/pvr`.

**VERIFIED** means the cited code or stores were read. A role inferred from those stores is separately labelled **INFERRED**. Ghidra variable names are not ABI definitions: byte offsets, copy lengths and literal masks are the evidence. **UNREAD** identifies work not completed; it must not be interpreted as a zero field or a constant. Classification: **S** setup image, **F** submission/frame, **D** draw, **H** device/microkernel runtime state, **K** kernel patch. An area can have several owners over its lifetime.

The supplied verified size reference is `init-facts.md`: CMDTA 1304 (`0x518`), CMDTA_SHARED 1128 (`0x468`), 3DREGISTERS 136 (`0x88`), HWPBDESC 68 (`0x44`), HWRENDERCONTEXT 64 (`0x40`), HWRENDERDETAILS 1040 (`0x410`), HWRTDATA 52 (`0x34`), HWRTDATASET 76 (`0x4c`). These are checked against stores/allocation lengths below. Public kernel headers expose only the shared part of several structures.

## Render context and parameter buffer

**VERIFIED — S:0xd144 `SGXCreateRenderContext`.** It queries heap information, selects heap IDs 8 (sync), 10 (per-context parameters) and 3 (kernel data), allocates a 0x50-byte CPU context, 0x10-byte client PB descriptor and a temporary 0x40-byte CPU HW context image. These CPU allocations are not GPU allocations. It passes that image to registration with size 0x40 and PD-address patch offset 8. The temporary image is freed after registration.

**VERIFIED — S:0xd144.** Requested PB usable size comes from create-input +0x10, minimum 0x40000, rounded to 4 KiB. `PBSize`, if explicitly supplied, replaces it in units of pages (`<<12`). Limit comes from input +0x14: zero remains zero; nonzero values below 0x40000 become 0x40000; others round up to 4 KiB. `CreatePerContextPB` rejects a nonzero limit below usable size. The caller's default is discussed with GLES context creation below.

**VERIFIED — S:0xcd7c, 0xca10.** PB-related device allocations, in creation order:

| Area | Heap | Bytes | Alignment | Literal flags | Class |
|---|---:|---:|---:|---:|---|
| HWPBDESC | 3 | 0x44 | 0x20 | 0xf | S,H |
| HWPBBlock | 3 | 0x10 | 4 | 0xf | S; growth links F/H |
| Parameter pages | 10 | usable PB size + 0x1dd000 | 0x1000 | 0xb; optional `EDMProtectTATest` adds 0x40 | H after setup |
| Page links/table | 10 | 0x10000 | 0x10 | 0xb | S,H |

**VERIFIED — S:0xca10.** A page ID is `(GPU_address - parameter_heap_base) & 0x0fffffff`, shifted right 12. The block image is `{u32 page_count; u16 first; u16 last; u32 HWPBDESC_address; u32 next=0}`. Page count is the returned allocation size (`meminfo+0x14`) >>12. **VERIFIED — S:0xcd7c.** Each table entry is `next_id | previous_id<<16`; first previous and final next are 0xffff. Only entries for allocated pages are initialised. Do not treat the rest of this allocation as defined constants.

**VERIFIED — S:0xc910.** With N allocated pages, usable size is `(N-0x1dd)*4096`. Default threshold values are TA=N+16, ZLS=(N-0x1dd)&0xfffff, global=N+16, PDS=max(ZLS-0x1d9,0). `TAThreshold`, `ZLSThreshold`, `GlobalThreshold`, `PDSThreshold` override them and set host descriptor bits 1..4. Default growth increment is 0x200000; `PBGrowSize` is rounded to pages and replaces it only under the comparisons in 0xcd7c (greater than default, and initial usable size plus increment below limit). Zero limit is not a finite maximum.

**VERIFIED — S:0xcd7c, initial HWPBDESC image.** Entire 0x44 bytes are first zeroed.

| Offset | Initial value | Classification |
|---|---|---|
| 00 | 0 | H; exact flags semantics unread |
| 04 | N pages | S, changes with PB growth |
| 08 | first page in low 16, last page in high 16 | S,H |
| 0c | `(last-1)<<16` | S,H |
| 10 | page-link table GPU address | S address |
| 14 | 0 | H / precise role unread |
| 18 | copy of +08 | S,H |
| 1c | copy of +0c | S,H |
| 20,24 | 0 | H / precise role unread |
| 28,2c,30,34 | TA, ZLS, global, PDS thresholds | S; growth updates F |
| 38 | first HWPBBlock GPU address | S address; growth |
| 3c,40 | 0 | runtime linkage/role not decoded |

**VERIFIED — S:0xcb90, 0xcfcc, 0xd038.** Growth allocates another block, creates its page links, recomputes thresholds, marks host flag 0x40, and finalises CPU block-list links after successful kick. Growth is requested through `HandlePBGrowShrink`, not a separate PB kernel registration operation in this per-context path. **INFERRED:** replay must preserve or deliberately rebuild device PB state after completion; copying only initial list heads each frame without resetting all associated DPM state is unsafe.

## Context image, CCB and RT evidence

**VERIFIED — S:0xd144, S:0x187a8, kernel `sgxutils.c:1072` `SGXRegisterHWRenderContextKM`.** Additional context allocations:

| Area | Heap | Bytes | Align | Flags | Owner |
|---|---:|---:|---:|---:|---|
| TA client CCB | 3 | 0x10000 + 0x688 = 0x10688 | 0x1000 | 0x4f | CPU produces; MK consumes |
| TA CCB control | 3 | 8 | 0x20 | 0x4f | CPU write offset at +0; MK read offset at +4 |
| TA/3D dependency allocation | 8 | 4 | 0x10 | 3 | associated sync object; K/H counters |
| Visibility results, if input +0x18 nonzero | 8 | count*4 | 0x20 | 0x4b | CPU clears; H results |
| Registered HW context (kernel allocates it) | KernelData | 0x40 | 0x20 | R/W, NO_SYNCOBJ, EDM_PROTECT, CACHE_CONSISTENT (=0x4f) | copied setup image, K patch, H state |

**VERIFIED — S:0xd144; all 16 words of registration image:**

| Offset | Initial value | Class |
|---|---|---|
| 00 | 0x21 (1 plus per-context-PB flag 0x20) | S/H flags |
| 04 | 1 | S/H; exact scheduler meaning not decoded |
| 08 | zero in CPU image; kernel patches PD physical address in directory-register format | K, S |
| 0c | TA CCB GPU address | S address |
| 10 | TA CCB control GPU address | S address |
| 14 | 0 | S/H |
| 18 | HWPBDESC GPU address | S address |
| 1c,20,24,28,2c,30,34,38 | 0 | initial zero, H/precise field roles unresolved |
| 3c | process ID | S bookkeeping |

**VERIFIED — S:0x836c.** Registration bridge request is `0xc01c6769` (number 105), input includes CPU pointer, 64-byte size, patch offset 8, memory-context handle; output includes cleanup handle and GPU VA. **VERIFIED — kernel `sgxutils.c:1110–1179`.** Kernel copies image and patches PD address. **INFERRED:** list/scheduler zeros are mutable MK state, not safe frame-reset constants. No vendor definition of these fields was consulted.

**VERIFIED — S:0x18970 and 0xb940.** CCB ring capacity is 64 KiB, with extra contiguous overrun storage. Submission size rounds up to 64 bytes; CPU copies actual command bytes, writes rounded size at command +0, advances control +0 modulo 0x10000, and passes command-start +100 as the bridge's shared-header offset. Space acquisition compares against control +4 and can event-wait. Preserve the producer/consumer cursors; the init kernel CCB is a separate ring.

**VERIFIED — S:0xe354.** HWRTDATA count is `2 * create_input[1]`, or 2 if that input is zero. This is distinct from array render targets: the function requires exactly one array member (`u16` at input +0x2c). Single-sample and 2x2 sample modes are accepted. The decompiler's comparison against string `"OPY_TEST_FAILED"` is a mis-typed numeric constant: do not use that text as an API value. Width and height limit is 2048 each. Tile counts are ceil(width/16), ceil(height/16).

**VERIFIED — S:0xe354, single-sample default non-macrotile-mode branch.** Let tx=ceil(w/16), ty=ceil(h/16), ax=align4(ceil(tx/2)), ay=align4(ceil(ty/2)). Host dataset fields +34,+38,+3c=ax; +40,+44,+48=ay; +4c=tx-1; +50=ty-1; +54=ax*ay. Default `MTModePixelThreshold=0xffffffff`; alternative mode also requires the create flags to permit it. At 320x320: tx=ty=20, ax=ay=12, padded coverage=24x24. **VERIFIED:** the allocation path uses this padded coverage, not just 400 tiles.

**VERIFIED — S:0xd7e8 `SetupRTDataSet`.** Allocations for N HWRTDATAs; all addresses below are GPU VAs:

| Area | Heap | Size | Align | Flags | Initialisation/class |
|---|---:|---:|---:|---:|---|
| HWRENDERDETAILS pool | 3 | (N/2)*3 allocations of 0x410 | 0x20 | 0xf | zeroed; F/H |
| Each details access resource | 8 | 8 | 4 | 0xf | first word zero; CPU reserves=1, H releases |
| HW device sync-list pool | 3 | (N/2)*3 allocations of 0x38 | 0x20 | 0xf | zeroed, K/F/H |
| Each sync-list access resource | 8 | 8 | 4 | 0xf | first word zero; CPU reserves=1, H releases |
| Dataset pending counter | 3 | 4 | 0x20 | 0x4f | zero; CPU increments every submission, H completion |
| Dataset + inline RTDATA array | 3 | 0x18 + N*0x34 | 0x20 | 0x4f | zero then setup writes; H |
| Tail pointers | 1 TAData | 4*P*P | 0x40 | 0xb | zero; H after setup |
| Context control | 1 | 0x40 | 0x10 | 0xb | zero; H |
| Context OTPM | 1 | 0x50 | 0x80 | 0xb | zero; H |
| Special objects | 10 parameters | 0x200 | 0x1000 | 0x4b | CPU creates background/geometry words; S/F |
| Region headers, each RTDATA | 1 | 12*padded_x*padded_y | 0x40 | 0xb | allocation not explicitly cleared here; H |
| Context state, each RTDATA | 1 | 0x88 | 0x10 | 0xb | zero; H |

**VERIFIED — S:0xd7e8.** P is next power of two of max(padded_x,padded_y). For default 320x320, P=32, tail pointers=4096 bytes, region headers=6912 bytes each, N normally 2, dataset allocation=128 bytes. **Important size distinction:** 76 bytes is a one-element flexible-array view (24+52); this binary allocates 128 bytes for two. Do not allocate only 76 bytes for a normal set.

**VERIFIED — S:0xd7e8, dataset header:** +00=pending-counter address; +04=0; +08=padded_x; +0c,+10 remain zero; +14=N. RTDATA[i] starts at dataset+0x18+i*0x34:

| RTDATA offset | Creation value | Class |
|---|---|---|
| 00 | HW render-context GPU address | S address |
| 04 | 0 | H |
| 08 | `(ax*ay*sample_x*sample_y)>>4` | S geometry |
| 0c | `ax*ay*sample_x*sample_y*12` | S geometry |
| 10 | special-objects GPU address | S address |
| 14 | this RT's 0x88 context-state address | S address/H contents |
| 18 | context-control address | S address/H contents |
| 1c | OTPM address | S address/H contents |
| 20 | tail-pointer address | S address/H contents |
| 24 | tail-pointer allocation size | S |
| 28 | address of this RTDATA+0x30 | S self-address |
| 2c | 0 | H |
| 30 | 0x10 | initial flags, H |

**VERIFIED — S:0xb940.** On new scene (`kick.flags &4`) the client reserves a free details resource and advances host RT index `(old+1)%N`; stores dataset GPU VA into details+90 and selected RTDATA address into details+94. It does not choose RTDATA solely by reading a completed flag: resource pooling, modulo selection and MK state cooperate. RTDATA flags (dataset+0x48+i*0x34, i.e. RTDATA+0x30) bit 0x80 cause PB-growth handling on later kicks. **INFERRED:** reset/rotation must be captured across at least two frames and an out-of-space case, not inferred from a single initial frame.

## CMDTA layout: corrected shared-header location

**VERIFIED — S:0xb940, command local starts at stack `-0x6a8`; SGXDoKick bridge receives CCB start+100.** The 1304-byte base command is **100-byte prefix + 1128-byte shared block + 76-byte suffix**. Thus “176 bytes after the shared header” is not this binary's layout. Shared header is +0x64..+0x4cb. Suffix starts +0x4cc. The following covers all 44 non-shared words. K[n] denotes u32 at byte offset 4*n in the GLES-filled `SGX_KICKTA` input, not a kernel structure. Unless marked S, values are F; shader/state choices can also be D across submissions.

| CMDTA offset | Value/source | Role/class |
|---|---|---|
| 000 | command length rounded to 64 | F; 0x540 for base 0x518 |
| 004 | derived flags A (see below) | F |
| 008,00c,010 | K[0x25], K[0x26], K[0x27] | caller-provided TA state words; exact register names unresolved |
| 014 | default 0x08000000, else context NumVertexPartitions<<25 | partition state, S |
| 018 | 0x08000000 | constant |
| 01c | derived flags B | F |
| 020 | K[0] | frame number |
| 024 | HWPBDESC GPU VA | S address |
| 028,02c,030,034 | TA,ZLS,global,PDS thresholds on PB grow/shrink; otherwise zero | F |
| 038,03c,040 | pages, packed first/last, packed previous-last on PB grow/shrink; otherwise zero | F/H snapshots |
| 044 | old last HWPBBlock address when grow/shrink pending, else zero | F address |
| 048 | new HWPBBlock address on growth, else zero | F address |
| 04c | selected HWRENDERDETAILS GPU VA | F address |
| 050 | selected HW device sync-list GPU VA, or zero | F address |
| 054 | dataset GPU VA | S/F address |
| 058 | selected inline RTDATA GPU VA | F address |
| 05c | K[2] if K.flags bit 0x20, else zero | optional caller field |
| 060 | number of render-detail address/value updates | F |
| 4cc | 0x80000000 if x samples=2, OR 0x40000000 if y samples=2 | S sample mode |
| 4d0 | host RT +34<<22 OR +30<<31 OR +3c OR +38<<12 | S macrotile x partition |
| 4d4 | host RT +44<<12 OR +40<<22 OR +48 | S macrotile y partition |
| 4d8 | host RT +4c OR +50<<12 | S tile extent |
| 4dc | host RT +54 | S macrotile area |
| 4e0 | if flags&0xa00: flags&1 ? 0x400000 : 0x800000; else 0; context internal flags bit2 adds 0x80000 | F |
| 4e4 | K[0x22] | TA control stream pointer supplied by GLES |
| 4e8 | K[0x24] | caller state (exact role unresolved) |
| 4ec | selected region-header GPU address | F address |
| 4f0 | tail-pointer GPU address | S address |
| 4f4,4f8 | 0x358637bd each | constant |
| 4fc | (width-1) OR (height-1)<<12 | S extent |
| 500 | K[0x21] | GLES caller state |
| 504 | K[0x20] | GLES caller state |
| 508 | parameter heap base &0xfff00000 | S, BIF TA requestor-base role inferred |
| 50c | host RT +14 | S sample pattern |
| 510,514 | first update address/value, or zero when none | F addresses/data |

**VERIFIED — S:0xb940.** Middle kicks compare CPU-cached 3D register values with new inputs and emit `{absolute GPU destination address, replacement word}` pairs starting at command+0x510. Count at +0x60; nominal copy length `0x518+8*count` (there are eight bytes beyond the used pairs). The decompiled bounds assertion permits 0x178 bytes of updates. A new scene initialises the whole 3D-register image and uses the base length, with count zero. The 64-byte rounding is the ring consumption, not the count of meaningful bytes. This distinction matters to the fake kernel and native command writer.

**VERIFIED — S:0xb940.** With f=K[1], A starts at 1 on new scene, else 0. If `(f&0x90)==0x10`, A ORs 4 when f&0x100, otherwise 0xc. Additional direct mappings `f-bit -> A-bit`: 0x10000->0x40, 0x20000->0x20, 0x40000->0x10, 0x02000000->0x80, 0x20000000->0x1000, 0x00800000->0x400. f&0xa00 adds 2. PB growth adds 0x4000 at submit.

**VERIFIED — S:0xb940.** B starts 0; maps f&0x80000->0x80, f&0x100000->0x100; adds 1 if !(f&2), 2 if f&0x800, 8 if f&0x2000, 0x10 if `(f&0x4008)!=8`, 0x1000 if f&0x400, 0x4000 if f&0x20000000. f&0xa00 adds 0x400 and `frame<<15`, also 4 if f&0x8000. f&0x20 adds 0x60; f&0x1000000 adds 0x200. These are literal transformations, not names borrowed from unavailable headers.

## Shared header, 3D registers and scene transitions

**VERIFIED — kernel `sgx_mkif_km.h:158`, `servicesint.h:243`, `sgxapi_km.h:106`; S:0xb940.** Shared-header offsets relative to CMDTA+0x64:

| Relative offset | Field | Owner |
|---|---|---|
| 000 | ready/control flags | K sets READY=1 last; H consumes |
| 004,008 | TA / 3D status counts | K from kick |
| 00c..018 | TA-TQ write pending/address, read pending/address | K snapshots; H completion at pointed words |
| 01c..028 | 3D-TQ equivalent | K/H |
| 02c..043 | TA/3D dependency, 24-byte device sync | K/H |
| 044 | source-sync count | K |
| 048..347 | 32 source syncs, each 24 bytes | K/H |
| 348..447 | 32 TA status pairs `{address,value}` | K; H writes values to addresses |
| 448..467 | 4 3D status pairs | K/H |

**VERIFIED:** each device sync is `{read_pending,read_complete_GPU_address,write_pending,write_complete_GPU_address,read2_pending,read2_complete_GPU_address}`. Source-sync population has an Android native-fence build branch in `sgxkick.c`; never assume all source handles are ordinary services syncs. Generalised sync objects are not this build's layout.

**VERIFIED — S:0xb940.** The 0x88-byte 3D-register block lives at HWRENDERDETAILS+0, not at a separate allocation. CPU cache is the host details object+0x10, copied on new scene. Define Zbase as the minimum nonzero K[9],K[0xa],K[0xb],K[0xc], masked 0xfff00000; when `(K[0xe]&0x30000)==0x30000` use parameter-heap base instead. Table is the complete 34-word image. All caller state is F/state-dependent; allocation addresses and geometry are S unless buffers rotate.

| 3D block offset | Source written by services |
|---|---|
| 00 | parameter heap base &0xfff00000 (BIF_3D_REQ_BASE role inferred) |
| 04 | Zbase (BIF_ZLS_REQ_BASE role inferred) |
| 08 | K[0x15] OR 0x80 |
| 0c | K[6] OR K[0xf] |
| 10 | host RT +0x10 (sample mode) |
| 14 | K[0x10] |
| 18 | selected region-header address |
| 1c | host RT flags &1 |
| 20,24 | K[7], K[8] |
| 28 | K[0xe] (ZLS control from GLES) |
| 2c,30 | (K[9]-Zbase)&0x03fffff0, (K[0xb]-Zbase)&0x03fffff0 (depth load/store roles) |
| 34,38 | (K[0xa/0xc]-Zbase)&0x03fffff0 OR 0x80000000 when K[0xd]!=0 (stencil load/store roles) |
| 3c | K[4] |
| 40 | K[5] OR K[0x11] |
| 44 | ((special-object address - parameter-heap base)&0x03ffffff)>>4 OR 0x02000000 |
| 48 | host RT sample-pattern +0x18 |
| 4c | 2 if context internal-info word nonzero, else 0 |
| 50 | 0 |
| 54,58,5c | K[0x12],K[0x13],K[0x14] |
| 60,64,68,6c,70,74,78,7c,80,84 | K[0x16]..K[0x1f] respectively |

**VERIFIED — G:0x1f1fc `DoKickTA`.** K begins at GLES-context+0x160 (u32 index 0x58). K[4..0x15] is populated from render-surface fields +0x150,+0x148,+0x100,+0x108,+0x110,+0x128,+0x138,+0x128,+0x138, constant 1, +0x120, constant 0, +0x118,+0x148,+0x158,+0x160,+0x168,+0xf8, respectively. These are caller byte offsets, useful when recording even where register names remain unknown. K[0x22] is the VDM control-stream kick base (G CBUF type 0 +0x28). K[0x24] comes from surface+0xf0. K[0x25..0x27] come from surface+0xac..0xb4. **UNREAD:** a full semantic naming of K[0x16..0x21], K[0x23], and the background-colour preparation before this caller.

**VERIFIED — S:0xd7e8 and 0xb940.** Remaining known HWRENDERDETAILS stores: +88=access-resource address at setup; +90=dataset VA, +94=RTDATA VA, +c8=0 on new scene; +cc,+d0 zeroed at setup; +e0 default 0x01800000 for single-sample, 0x01000000 for multisample, or NumPixelPartitions<<22. All 1040 bytes are zeroed at allocation. **INFERRED:** +8c, +98..+c4, +d4..+dc, +e4..+40f are reserved or MK runtime save/list/state areas; their exact ownership and meanings were not established by reading the microkernel. They are explicitly **not classified constant merely because allocation clears them**. This is the largest unresolved part of the requested every-field classification.

**VERIFIED — S:0xb940 and `sgxinfo.h:178`.** `SGX_CCB_KICK` is 0x298 bytes in this blob. sCommand is zeroed except data[1]=HW-context VA (offset +0xc). hCCBKernelMemInfo is the TA CCB allocation handle. ui32CCBOffset is command-start+0x64. Status counts and triples come from K[0x28]/K[0x4f...] (TA) and K[0x29]/K[0xaf...] (3D); each triple is `{GPU status address,value,allocation handle}`. bFirstKickOrResume is `(A&5)!=0`; bLastInScene is `(A&3)>>1`. Source count is K[0x2a] only at terminate/abort path, with source client pointers K[0x2f...] converted to sync handles. hTA3DSyncInfo and bTADependency are selected by f bits 0x1800000; hTASyncInfo/h3DSyncInfo from optional TQ context K[0xbb], controlled by f bits 0x200000/0x400000. Memory context, dataset VA, RTDATA VA and frame number are also passed separately for kernel bookkeeping. No release-build `bTerminateOrAbort` member is present in the kernel bridge structure.

| Submission | Caller behaviour, VERIFIED at G:0x1f1fc and S:0xb940 |
|---|---|
| First | surface first-scene state contributes f=4; reserve details, advance RT index; A bit0=1, first/resume=true |
| Middle | no f&4, normally first/resume=false, last=false; reuse details and RTDATA; emit changes as update pairs; TA ring status advances |
| Last | GLES schedule bit1 contributes services f=0x200, abort/special path contributes 0x800; f&0xa00 makes A bit1=1, last=true; first may also be true for a one-kick scene |

**VERIFIED — kernel `sgxkick.c:440` and following schedule call.** Kernel fills sync/status fields, sets shared READY last and schedules a TA microkernel command. **VERIFIED — G:0x3b404.** Normal end-of-scene emits terminate-related PDS blocks and a final `0xc0000000` VDM word. **INFERRED:** scene-end flags plus terminate state cause MK to put completed TA work on its render queue and kick ISP/3D; no separate user-space 3D kick is needed. The permitted trace header explicitly names `MKTC_KICKTA_VDM_START=0xad000803`, `MKTC_KICKRENDER_CONFIG_REGION_HDRS=0xad000404`, `MKTC_KICKRENDER_ISP_START=0xad000402`, `MKTC_EHEVENT_PIXELENDRENDER=0xad000002`, and render-finished steps. Trace names corroborate stages, but do not prove private structure offsets.

## Draw storage and control stream

**VERIFIED — G:0x4458, context initialiser around 0x12fb6, G:0x1b164; labels read directly from G .data table 0x6d868.** Types and initial allocations:

| CBUF type | Label | Heap | Default bytes / rule | Align / flags |
|---:|---|---|---|---|
| 0 | VDM_CTRL | General 0 | 0x5000, DefaultVDMBufferSize | 64, 1 |
| 1 | VERTEX_DATA | General 0 | 0x32000, DefaultVertexBufferSize; MaxVertexBufferSize 0xc8000 | 32, 1 |
| 2 | INDEX_DATA | General 0 | 0x32000, DefaultIndexBufferSize | 64, 1 |
| 3 | PDS_VERT | PDSVertex 7 | 0xc800, DefaultPDSVertBufferSize | 32, 1 |
| 4 | PDS_VERT_SEC_PREGEN | 7 | 4 at creation | 32, 1 |
| 5 | PDS_MTE_COPY_PREGEN | 7 | DefaultPregenMTECopyBufferSize=0xc800, rounded down 32; 4 if EnableStaticMTECopy false | 32, 1 |
| 6 | PDS_AUX_PREGEN | — | not created in this context path | — |
| 7 | PDS_FRAG | PDSPixel 6 | render-surface/EGL managed, see below | 32 |
| 8 | USSE_FRAG | PixelUSSE 4 | render-surface managed; shader-variant code also uses code heaps | at least 16 |

**VERIFIED — G:0x4458.** Each created type 0..5 additionally gets a 4-byte status allocation in CacheCoherent heap 8, alignment 4, flags 0xf, zeroed. Data meminfos have sync objects because flags=1 does not include NO_SYNCOBJ. **VERIFIED — E:0x3918.** EGL supplies PDS fragment ring entries from heap 6, size `PDSFragBufferSize` (default 0x19000 from E:0x7140 `_TlsInit`), alignment32, flags1, and another 4-byte heap8 status word flags0xf. Pool min2/max50 apphints. Type8 and code-heap sizes are established in the additional-checks section. **UNREAD:** any lazy enlargement of type4.

**VERIFIED — G:0x3fdc.** CBUF calls take word counts, multiply by4; CPU emits at ring producer offset. Types3..7 align each reservation to32 bytes. Type8 aligns to16 and pads to avoid crossing a 0x8000-byte boundary. Type0 has a specialised space/link routine. Waiting for free space repeatedly reads the buffer's mapped status word and can wait on services events. These status words are F/H, not template constants.

**VERIFIED — G:0xe638, 0xe7a4, 0x3cca4.** Draws obtain vertex/index storage before generating PDS/VDM. GPU buffer objects can be referenced directly as meminfo GPU VA plus API offset; client arrays are copied to CBUF vertex storage. Non-indexed APIs also reach the index-list emitter using generated indices; “non-indexed triangle” does not imply a different hardware command with no index address. Indexed buffer path passes index type 2 or4 bytes, pointer and count to the same PDS/VDM routine. **UNREAD:** all index-generation/rebasing branches in 0xe8cc/0xf2c0/0x10c68, including byte-index conversion; replay should record the final index image.

**VERIFIED — G:0x3cca4 tail.** Every emitted index-list block is six words:

| Word | Emitted value | Embedded address / varying field |
|---:|---|---|
| 0 | `count | 0x81c00000 | primitive_bits` | count D; triangle list primitive_bits=0 from table G:0x64dc8[4] |
| 1 | index GPU address &~1 (16-bit) or &~3 (32-bit) | D absolute address |
| 2 | hardware-resource word from G:0x7490 OR vertex base/index offset; 32-bit indices add 0x01000000 | D layout; helper semantic bits partly unread |
| 3 | 0x003fffff | constant |
| 4 | helper word OR `(PDS_vertex_GPU_address - PDS_exec_base)>>4` | D/S address |
| 5 | helper word OR `PDS_vertex_data_bytes>>4` | D/S size |

**VERIFIED — G:0x3cca4 state builder.** MTE/ISP state is a separate block in CBUF3, first word a presence mask. Packed payload order follows mask bits: 0x1 ISP word A (with optional words B/C flagged by A bits0x200/0x100), 0x38 back-face A/B/C, 0x40 three pixel-PDS/secondary words, 0x80 two surface words, 0x100 six viewport words, 0x200 zero, 0x400 vertex-output word, 0x800 constant0x3727c5ac, 0x1000 other ISP state, 0xc000 two vertex-output words. Three pixel-PDS words include `(pixel_secondary_PDS_offset>>4) | (data_bytes>>4)<<26`, shader state, `(pixel_primary_PDS_offset>>4) | (data_bytes>>4)<<26`. Offsets are relative to PDS execution base. Source ISP words are context+0xb40..+0xb58, built in `SetupRenderState` 0x3c098. **UNREAD:** a complete bit-by-bit naming of ISP A/B/C; the binary constructs depth, cull, stencil, colour-mask and blend-related variants, so these words cannot be assumed invariant across blending/state changes. The presence mask is a word in the separate state image, not the high bits of a VDM index-list header.

**VERIFIED — G:0x3bfa0.** State/PDS launch packets are two VDM words: `(PDS_offset>>4)|0x40000000`, then `(data_bytes>>4)<<26` plus resource/attribute controls. Vertex-secondary launch adds 0x16100 and rounded attribute count. MTE-copy launch uses 0x28200, toggles a two-state counter and includes state-block word count. **VERIFIED — G:0x3b404.** Scene termination uses two such launches, then `(terminate_PDS_offset>>4)|0x60000000`, associated controls `(data_bytes>>4)<<26|0x2a201`, then `0xc0000000`. The type0 wrap/link encoding is decoded in the additional-checks section; it differs from termination.

## PDS data, uniforms and code addresses

**VERIFIED — G:0x3f5c4, 0x3fc6c, 0x3e6d4.** Vertex PDS data uses two banks interleaved in groups of eight words. Logical bank0 word n is output word `(n&7)+16*(n>>3)`; bank1 adds8. Two-word reservations round logical n up to even. Per stream, generator input record is 0x37 words: +0x2c stream base address, +0x30 byte stride, +0x38 element count; elements beginning +0x3c carry byte offset, byte size, destination attribute offset. Generator emits:

- bank1: stride (and optional divisor/multiplier fields for instancing).
- bank0 pairs: `stream_GPU_base + element_byte_offset`, then `(ceil(element_bytes/4)-1) | destination_attribute_offset<<8`.
- final bank0 pair + bank1 word: three DOUTU task words that launch vertex USSE.

**VERIFIED — G:0x3cca4, 0x3f5c4.** The host generator also records the *actual output word indices* of address words, element offsets and task words in a patch map. G:0x3fc6c subsequently rewrites precisely those words when streams or tasks move. This patch map is a better replay artifact than assuming stream addresses are at fixed template offsets. Interleaved position+colour can coalesce adjacent fetches subject to stride/size/destination constraints; a different shader attribute allocation can change the emitted data layout even with identical vertex bytes. The PDS data size rounds to16 bytes before instructions, and the complete code/data image goes to CBUF3 or a cached VAO allocation in heap7, flags1, align32.

**VERIFIED — G:0x3cca4, 0x39fac, 0x3a880.** First USSE address is packed into DOUTU word0, not represented as a raw pointer. For address A, heap base B and segment size 0x80000: delta=A-B; segment=delta>>19; within=delta&0x7ffff. Address contribution is `segment_index | ((within>>15)&15)<<4 | ((within<<4)&0x7ff00)`. Pixel segment_index=segment, vertex=segment+10. A must be 16-byte aligned. Resource/task flags are ORed into these same words. Second/third task addresses, when present, have additional pieces in word1 (`(within>>3)&0xffe`, and `(within<<9)&0xffe000`) and multi-task flags. **INFERRED:** freeze the complete one-task DOUTU triplet for an opaque shader at fixed VA; do not relocate it by adding the address delta to the word.

**VERIFIED — G:0x39fac and 0x3ec78.** Pixel PDS generator first emits three task words, then iterator words and, for texture lookups, three texture-state words. Data indices are allocated by 0x3e700, balancing two logical banks by half-word-pair occupancy; not simply contiguous triples. `0x3ec78` may merge an iterator into a preceding iterator whose low nibble is0xf, replacing bits with `old&0xfffff400 | new&0xbff`. Therefore the compiled shader's iterator list determines offsets. The instruction part consumes the resulting data and ends with 0xaf000000. Record both data size and each texture word's actual output location.

**VERIFIED — G:0x3901c.** Ordinary iterators include `0x0100000f`, coordinate selection<<12, input component count minus1<<22, format flags 0x10000000/0x20000000, and 0x0c000000. Texture iterators use coordinate selector plus 0xf100/0xf200/0xf300 depending on lookup/cube state. The exact emitted iterator is shader-interface-dependent. **UNREAD:** exhaustive semantic decoding of each iterator bit and all interpolation modes.

**VERIFIED — G:0x33d6c, 0x32764, 0x3297c, 0x2c268.** A normal texture contributes `{sampling_control,format_and_size,texture_GPU_base&~3}`; resident allocation address enters texture-object+0x38, then context texture triple, then PDS data or shader constant image. Multi-plane images have additional addresses; restrict initial replay to one uncompressed plane. For explicit dimensions, size word includes `(height-1)|((width-1)<<12)` and layout bits 0x60000000 or0x80000000; power-of-two/twiddled case uses log dimensions with x<<16. Format word table begins G:0x650cc, entries 0x6c bytes apart. **VERIFIED — G:0x2c268:** sampler values stored in texture +48/+4c are: min NEAREST=0x1e0000, LINEAR=0x1e0400; nearest mip nearest=0x180000, linear mip nearest=0x180400, nearest mip linear=0x180200, linear mip linear=0x180600; mag NEAREST=0, LINEAR=0x1000. S wrap clamp=0x80, mirror=0x40, repeat=0 in mask0x1c0; T clamp=0x10, mirror=8, repeat=0 in mask0x38. Validation can add mip-range and format flags, so use the final triple, not these API controls alone. **UNREAD:** all format-table entries and stride/NPOT combinations; the table-index-to-GL-format conversion is not fully decoded.

**VERIFIED — G:0x35304, 0x3a880, 0x3a7cc.** Uniforms do not need USSE instruction decoding. Compiler metadata maps user/builtin constants to a CPU constant array; 0x35304 emits a memory constant block into CBUF3 for vertex or CBUF7 for pixel, including compiler-requested full-word/half/packed conversions and texture triples. It stores its GPU address in program stage state+0x80 and word count+0x84. `LoadSecondaryAttributes` combines this with literals, texture state, scratch/indexable-temporary addresses when requested, and emits PDS DMA uploads plus optional secondary USSE task. A DMA pair contains raw source GPU VA and a packed burst/line/destination word; 0x3a7cc emits at most four pairs, advances source by transfer_bytes and destination attribute index by transferred words. Limits asserted are 1..512 words. Primary/pixel secondary PDS addresses enter the MTE state, vertex secondary enters a VDM launch. Uniforms are **D**, metadata/literal layout **S per shader variant**. Scratch and indexable temporary allocations are General heap, flags0xb, align4, sizes from compiler metadata +0x70/+0x6c; these are optional, not necessary for every simple shader.

## Shader replay artifacts

**VERIFIED — G:0x38598, 0x3901c, 0x37b40.** Hardware code is finalised by UniPatch at shader validation, then copied into driver-managed USSE allocations. Vertex code has generated attribute-unpack/prologue work in addition to compiled body; fragment code has generated feedback/colour-mask/blend epilogues. 0x3901c keys variants on colour mask, alpha-test-related state, MSAA/feedback state and texture formats; calls `PVRUniPatchSetTextureFormat` before finalisation. Blend generator 0x37f98 is invoked when the blend condition at 0x39570 requires it; its output is appended/combined with body. The driver also patches task exits and appends END/emit instructions at validation. Thus an API program is not one immutable USSE binary across blend-on/off or texture-format variants. **UNREAD:** complete blend instruction patch map and UniPatch's internal relocations; no USSE instruction decoder is claimed here.

**VERIFIED — G:0x3901c.** Fragment code allocator returns GPU VA at code-block+8 and CPU pointer+0xc. Main entry is allocation GPU VA plus compiler entry instruction index*8 (`u16` in finaliser output word5); secondary entries may point elsewhere in the same block. The code is addressed through 512 KiB code bases, matching the DOUTU calculation above. **VERIFIED — G:0x38598 and 0x37b40.** Vertex body and optional secondary-upload code are separately managed allocations. The additional-checks section identifies code-heap creation and chunk sizes; heap roles follow the selected pixel/vertex handles and task-base arithmetic.

**VERIFIED — G:0x23e38 `glGetProgramBinaryOES` implementation, 0x8288 binary reader.** Binary export serialises UniPatch shader input/state using the UniPatch packer and compiler binary writer, format0x9130. Import reconstructs UniPatch shaders (`UnpackUniPatchInput`) and later still finalises them. It is an intermediate/patchable driver program representation, **not a dump of the final draw-ready hardware image**.

**INFERRED — minimal replay artifact set for one fixed supported variant:** final vertex USSE including unpack code and entry offsets; final fragment USSE including blend/output epilogue and all entries; optional secondary USSE; vertex PDS template plus its patch map; pixel PDS template plus iterator/texture patch map; vertex/pixel secondary PDS upload templates; uniform destination/conversion metadata and literal images; MTE/ISP state image; VDM packet resource fields; surface pixel-event/end-of-tile/end-of-render templates. Keep separate variants for blend off/on and each texture/layout/format choice that changes finalisation. Recording merely vertex-USSE+fragment-USSE misses several required executable programs and address-bearing data images.

## Pixel back end and framebuffer relocation

**VERIFIED — G:0x1e908 -> 0x3b82c -> 0x404c8 -> 0x38380 -> 0x402c0.** At frame preparation the driver builds PBE words from surface pixel format, rotation/layout, destination GPU VA, byte stride converted to pixels, dimensions minus1, scaling and multisampling. It then emits a 56-byte USSE tile-store program in CBUF8, and a 160-byte PDS pixel-event template in CBUF7 (G:0x3e748 copies G rodata 0x64f48). Rebuild/repatch is needed when surface parameters change; these programs are not part of the user's fragment shader binary.

**VERIFIED — G:0x404c8.** Let input S={format,address,layout,stride_pixels,scaling,msaa,special}, R={rotation,min_x,max_x,min_y,max_y,extra}. For normal nonrotated, nonspecial surface, six output words are:

| PBE word | Value/role |
|---:|---|
| 0 | min_x OR min_y<<12; twiddled layout2 also adds calculated dimension powers in high byte |
| 1 | max_x OR max_y<<12 |
| 2 | 0x8000 OR format_table_high_nibble OR layout_bits; special path changes0x8000 to0x100 |
| 3 | adjusted_destination_GPU_VA&~3 OR rotation_bits |
| 4 | (stride_pixels-1)>>1 |
| 5 | scaling_bits OR (msaa?8:0) OR4; special clears4; certain formats add R.extra<<6 |

**VERIFIED:** layout table G:0x65090 = {0,0,0x08000000,0x04000000}; rotation G:0x650a0 = {1,2,3}; scale G:0x650b0 supplies {1,2,3} for requests1..3 (32-bit table; confirmed by Thumb load at0x405c8). Rotation can subtract a format/stride/extent-dependent adjustment from destination before encoding; do not apply a nonrotated address patch to a rotated recorded template.

**VERIFIED — direct ELF table read, G:0x65128 + pixel_format*0x6c; kernel `servicesext.h:386`.** ARGB8888 enum20 and XRGB8888 enum26 both have PBE format nibble0; ABGR8888 enum21 has0x10000000. All have32 bpp. For a 320x320 linear nonrotated surface with stride1280 bytes: stride_pixels320, PBE4=159, extent PBE1=319|(319<<12)=0x13f13f. **INFERRED:** byte-ordered RGBA on little-endian CPU corresponds to an ABGR word representation; record enum21 and verify channel order with asymmetric colour values rather than conflating API `GL_RGBA` and native framebuffer enum names. XRGB8888's alpha semantics still require a pixel test.

**VERIFIED — G:0x402c0.** PBE0..4 are encoded as immediates into five 64-bit instructions at program+0,+8,+16,+24,+32. For pair j and value v: word0 contains v&0x1fffff (plus register selector j<<21); word1 contains `(v>>17)&0x1f0 | (v>>26)<<12 | 0xfca00000`. **Framebuffer address lives in pair3 at program+0x18/+0x1c.** To repatch, replace low21 bits of word0 and mask0x3f1f0 in word1, preserving instruction bits. PBE5 contributes to final emit words at program+0x30 and +0x34: `(v&0x3f)<<22 |0x208184`, `(v&0x3000)<<10 | (v>>3)&0x1f8 |0xfb240000`. This is the limited immediate patch needed for replay; shaders can otherwise remain opaque.

**VERIFIED — G:0x3e748.** Pixel-event PDS template data patches output word indices {10,11,5} from input task triplet2..4; {0,1,8} from triplet5..7; {2,3,9} from triplet8..10. Data segment size0x40; total template0xa0. G:0x3b82c packs generated tile-store entry and other event entries into these task words, then exports surface register/value pairs for offsets0xa5c,0xa60,0xa64, with PDS program offset relative to execution base, data size>>4 and control0x4ffe. Those values eventually reach 3D-register offsets54/58/5c through K[0x12..0x14]. **INFERRED:** capture all three event branches even for an empty/simple frame; an unobserved branch may still be used on final tile or partial-render termination.

## Fake kernel: startup, draw, completion

**VERIFIED — E:0x7998, 0xf5b0; S:0x5e74, 0x8f94, 0xd144.** The following is the static partial order for the no-native-window path. Repeated allocation/mapping calls are loops, not a claim that every EGL configuration issues one identical flat ioctl list. Both pbuffer and FBO require an initialised services connection and EGL/GLES contexts. Texture upload can introduce transfer submissions; avoiding native windows does not itself disable transfer code.

| Order | Bridge/service operation | Number, where verified | Meaningful fake result |
|---:|---|---|---|
| 1 | open services; CONNECT_SERVICES | 13, S:0xa2e4 | service handle; fd wrapper and connection flags |
| 2 | ENUM_DEVICES; ACQUIRE_DEVICEINFO | 1,2; S:0x5dd0/0x5df8 | one SGX type7/class3D with index and cookie |
| 3 | SGX_GETMISCINFO driver revision/build check | 99, S:0x8ea8/0x8f94 | request3: build options0x0016801c; valid feature/revision structure |
| 4 | EGL explicitly enumerates/acquires again | E:0xf5b0 | same identity/handles |
| 5 | CREATE_DEVMEMCONTEXT | 4, S:0x6260 | memcontext handle and 11 heap descriptors |
| 6 | SGX_GETCLIENTINFO | 85, S:0x8c78 | process ID and asDevData, matching init's heap-base/resource values |
| 7 | GET_MISC_INFO | 37, S:0x6a9c | request9: mapped timer information and global event object |
| 8 | MHANDLE_TO_MMAP_DATA; mmap2; EVENT_OBJECT_OPEN as misc result requires | 12, syscall192,72 | usable guest mappings and event handle |
| 9 | GET_DEVMEM_HEAPINFO; PB/context allocations | 6,7; S:0xd144 | consistent heap handles, GPU addresses and CPU mappings |
| 10 | Each ALLOC_DEVICEMEM normally followed by MHANDLE_TO_MMAP_DATA/mmap2 for buffer, and for sync data unless NO_SYNCOBJ | 7,12; S:0x579c/0xa980 | meminfo + sync layout, not just success |
| 11 | SGX_GETINTERNALDEVINFO, REGISTER_HW_RENDER_CONTEXT | 87,105; S:0x8df8/0x836c | flags, bForcePTOff, hostctl handle; registered-context GPU VA and handle |
| 12 | Android gralloc load/open/get-transfer-context callbacks in EGL services init | E:0xf5b0 | valid callback ABI even with synthetic WSEGL (see next section) |
| 13 | GLES context: sync-word, CBUFs, special shader/code allocations | G initialiser around0x12600..0x13084 | allocation+mapping handling; CPU mutex/TLS/libc support |
| 14 | pbuffer/FBO render-surface creation: heap query, RT pool allocations and terminate buffers | E:0xfc58; S:0xe354/0xd7e8 | allocations shown above; no separate RT registration ioctl here |
| 15 | First draw: lazily allocate resident vertex/index/texture and shader/PDS variants; frame setup | G:0x1e908/0x3c098/0x3cca4 | addressable memory; feature queries if reached |
| 16 | SGX_DOKICK | 88 (`0xc01c6758`), S:0x87b0 | read/capture 0x298-byte kick and CCB memory, emulate shared-header updates; return0 |
| 17 | finish/pool-reuse waits | event wait71; G:0x1b4c4/0x1f1fc; S:0x9a74 | change completion memory before returning success/waking |

**VERIFIED — S:0xa2a8.** ioctl's third argument points to a 28-byte bridge package `{bridge_id,size=28,input_ptr,input_size,output_ptr,output_size,kernel_services_handle}`. The ioctls above use `0xc01c6700 | number`; pointers in the package refer to guest ARM addresses. Errors are not uniformly at output+0: GETCLIENTINFO and INTERNALDEVINFO place error after their payload, EVENT_OPEN returns handle then error. Implement from the permitted bridge structs, not a blanket output-zero shortcut.

**VERIFIED — S:0x579c, kernel `servicesext.h:739`.** Returned client meminfo is0x38 bytes: CPU VA +0, kernel CPU mapping placeholder+4, GPU VA+8, flags+0x10, actual allocation size+0x14, sync-info CPU pointer+0x18, mapping info+0x1c, kernel mem handle+0x20 (later fields also copied from bridge). With sync enabled, a separate0x18-byte client sync-info has mapped sync-data pointer+0, write-complete GPU VA+4, read-complete VA+8, read2-complete VA+0xc, mapping handle+0x10, kernel sync handle+0x14. Sync data begins `{write_pending,write_complete,read_pending,read_complete,read2_pending,read2_complete}` at offsets0,4,8,c,10,14; later dump/last-write fields exist. Allocate enough for the full kernel structure, not only six words.

**VERIFIED — S:0xa980.** Mapping bridge can return an existing user VA; if zero, the client performs mmap2 using returned size/offset, then adds returned byte offset to obtain the final mapping. CPU and GPU views must alias the same data. A fake GPU allocator can use arbitrary handles, but heap bases must match the client/init address arithmetic. Device addresses are not host pointers. **INFERRED:** preserve allocation identity and guest-VA↔GPU-VA mapping in the capture manifest, including hidden kernel-allocated context and sync data.

**VERIFIED — E:0x7140.** EGL defaults: PDSFragBufferSize0x19000, ParamBufferSize0x200000, MaxParamBufferSize0x1000000. E:0xf5b0 passes the last two as usable/limit into SGXCreateRenderContext. Thus initial parameter-page allocation is0x3dd000 (2MiB usable plus0x1dd000 reserve); physical pages/heap capacity still bound growth before a nominal16MiB usable limit could necessarily be satisfied. **INFERRED:** fake allocation policy should enforce heap bounds and log failure; a 16MiB apphint is not evidence that 16MiB of usable PB actually fits heap10.

**VERIFIED — kernel `sgxutils.c:813`, `sgxinit.c:2579`.** Internal info returns flags, force-page-table-off state and hostctl allocation handle. Client info returns PID and `asSGXDevData` set at init. It is not sufficient to invent just a core version number: resource limits and shader/PDS base values feed GLES arithmetic. Use init's recorded asDevData and permitted kernel heap table. The connection check rejects build-option mismatch; request3 can be answered without executing MK in a capture harness. **UNREAD:** all later SGXGetMiscInfo feature queries reachable for every shader/configuration and compiler-loader constructor dependencies; the table is a viable minimal design, not an executed full trace.

**VERIFIED — G:0x1b4c4/0x1f1fc.** `glFinish` routes to Schedule/DoKick with end-scene+wait when work exists (common flags5), or wait-only4. Hardware completion blockers actually read:

| Poll / wait site | Memory condition to satisfy |
|---|---|
| S:0x18970 TA CCB free space | control read offset+4 catches up to committed producer+0 |
| S:0xb940 details pool | first word of selected heap8 access resource becomes0 after being reserved1 |
| S:0xb940 sync-list pool | first access word becomes0 after reserved1 |
| G:0x3fdc CBUF space | mapped 4-byte status word reaches submitted buffer offset; refreshes host cached read cursor |
| G:0x1e848 WaitForTA | VDM CBUF status equals last committed offset, mask0xffffffff |
| G:0x1f1fc render sync path | sync-data write_complete at+4 >= write_pending at+0 |
| G:0x1f1fc render status path | mapped surface completion word >= surface sequence-1 |
| E:0x3918 PDS fragment pool | previous surface's mapped completion word >= its recorded sequence |

**VERIFIED — kernel `sgxkick.c:134–214, 316–440`.** Before fake completion, emulate pending-count bookkeeping and shared-header/status population. For a capture-only harness, apply each TA/3D status pair's supplied value to its pointed guest allocation, advance relevant sync completions consistently with pending counters, release details/list locks and consume CCB. Apply CMDTA address/value update pairs to details memory if capturing middle kicks; those updates are intended for MK execution, not done by the CPU when queued. **INFERRED:** do this as an explicit fake-completion step *after capturing pre-execution memory*. Record both pre-kick and post-fake-completion snapshots; otherwise completion stubs can erase the exact flags that bare metal must submit. Merely making event waits return success leaves infinite loops that re-read unchanged words. No actual triangle pixels are needed to reach the TA ioctl, but CPU readback paths should be avoided or tagged synthetic.

**VERIFIED — G:0x1f1fc, S:0x87b0.** DOKICK retries error0x18; render waits count timeouts and may issue GET_MISC_INFO0x200 (force-flip workaround); timeout diagnostics may call gralloc and SGX misc/debug requests. These are not required for a successful fake first kick if completions are coherent. Source native fences can be kept empty for a no-window, no-native-fence test. **UNREAD:** full sync-token/free/cleanup ioctl sequence after destroying all objects; task endpoint is glFinish, not teardown.

## Minimal WSEGL / Android boundary

**VERIFIED — W:0x1f14, ELF table at0x3e50; E:0x5c68.** Getter returns this table; E requires version4 at+0. Thumb addresses below omit bit0. Names marked INFERRED are assigned from call roles; others appear in module debug strings. Display validation at0x878 is a two-instruction stub returning success0.

| Byte offset | Function address | Role and rough signature |
|---:|---:|---|
| 00 | literal4 | ABI version |
| 04 | 0x878 | **INFERRED** display validation: `(native_display)->status` |
| 08 | 0x1d5c | InitialiseDisplay `(native_display,&display,&caps,&configs)->status` |
| 0c | 0x1cf8 | CloseDisplay `(display)->status` |
| 10 | 0x1a98 | **INFERRED** CreateWindowDrawable `(display,config,&drawable,native_window,&rotation)->status` |
| 14 | 0x1714 | **INFERRED** CreatePixmapDrawable with analogous args; validates Android buffer magic |
| 18 | 0x1c00 | DeleteDrawable `(drawable)->status` |
| 1c | 0x1bbc | SwapDrawable `(drawable,...)` |
| 20 | 0x19e4 | SwapControlInterval `(drawable,interval)` |
| 24 | 0x174c | WaitNative `(drawable,engine)` |
| 28 | 0x918 | CopyFromDrawable, returns4/unimplemented |
| 2c | 0x8e8 | CopyFromPBuffer, returns4/unimplemented |
| 30 | 0xe6c | GetDrawableParameters `(drawable,&source,&render,optional_extra)` |
| 34 | 0x1910 | ConnectDrawable `(drawable,...)` |
| 38 | 0x1874 | DisconnectDrawable `(drawable,...)` |
| 3c | 0x17bc | FlagStartFrame `(drawable)` |

**VERIFIED — W:0x1d5c, E:0x7998.** InitialiseDisplay sets display output0 (which is permitted for this module), calls `hw_get_module("gralloc")`, invokes module callback+0xb8 to enumerate a linked list of formats, filters nodes by flag0x200, builds 36-byte configuration entries plus a zero terminator, queries module+0xec with0x1000 for a preferred format, creates a mutex and opens gralloc device `"gpu0"` via module methods. It returns capabilities pointer W:0x4004 and config pointer. EGL walks configs in nine-word steps until first word0, and capability pairs until terminator. A harness must return at least one compatible configuration and a valid terminated capability list; copying table layout without contents is insufficient.

**VERIFIED — E:0x68b8 and 0x10850 caller; `IMGeglCreatePbufferSurface` 0x9778.** Pbuffer allocation is internal `GWS_CreatePBufferDrawable` -> device-memory allocator, not WSEGL CreatePixmapDrawable. It stores width/height and allocation in a CPU pbuffer object. Thus a pbuffer-only fake WSEGL needs display validation/init/close and compatible config/capability tables; most drawable callbacks can fail explicitly if unexpectedly called. **INFERRED:** use this path before a native window to avoid dequeue/queue/fence/gralloc-buffer conversion work.

**VERIFIED — E:0xf5b0.** EGL services init separately calls `hw_get_module("gralloc")`, module methods open, then callback+0x10c to obtain a transfer-context pointer. It does this even before a pbuffer draw. Replacing WSEGL alone does **not** remove this dependency. **INFERRED:** supply a small synthetic HAL module for these callbacks, or hook this specific EGL services boundary to furnish a well-formed optional transfer context; logging and failing unexpected HAL calls will expose additional paths. Returning a random nonzero TQ pointer is unsafe because DoKickTA dereferences +0x18/+0x20 sync members. A fully normal vendor-HAL initialisation and its additional bridge operations were outside this read; no proprietary HAL header was used.

## Additional checks and address-bearing areas

**VERIFIED — G:0x46d0/0x4870, G:0x12650 shared-state creation.** Code heaps initially allocate 0x8000 bytes, alignment0x8000, flags1, in VertexUSSE5, PixelUSSE4, PDSPixel6 and General0 respectively. Their host code-heap types are1,1,2,3. Allocation requests are <=0x8000 and cannot cross a 0x8000 boundary. Suballocations round to16 bytes for USSE,32 for PDS,64 for General-type codeheap. A new0x8000 allocation is added when no free block fits. This closes the code-heap size question left open earlier; shader bodies themselves are variable-sized suballocations, not one full chunk each.

**VERIFIED — E:0xfc58.** The surface's USSE_FRAG CBUF is a 0x400-byte PixelUSSE4 allocation, align32, flags1, with its own heap8 4-byte status allocation flags0xf/align4. Its inline CBUF control begins at surface+0x30; GLES uses it as type8. Termination setup also allocates a VertexUSSE5 0x10-byte code block (align0x100,flags9), PDSVertex7 0x80 and0x40-byte blocks (align0x20,flags9). Optional depth/stencil external storage is `align32(width)*align32(height)*5`, or20 bytes per padded pixel for multisample; General heap,flags0xb,align2. **VERIFIED — E:0x10850.** Pbuffer colour storage uses stride `bytes_per_pixel*align8(width)` and size stride*height in General heap, flags0xb. At 320x320x4 that is409600 bytes.

**VERIFIED — G:0x3f64.** VDM wrap is a single link word `VDM_ring_GPU_base>>2`, written at old producer position, followed by resetting producer to0. It reserves requested bytes plus0x5c of emergency termination space. This closes the link encoding left open above: low-type link packet with address in four-byte units, distinct from0xc0000000 terminate.

**VERIFIED — G:0x1dff0.** Whole-surface tile clip is `{0x80000000 | (ceil(width/16)-1), ceil(height/16)-1}` in surface+e4/e8; explicit clip adds x/y tile origins in bits starting12. At 320x320 whole-surface words are0x80000013 and0x13. **VERIFIED — G:0x7a64.** Background accumulation state can itself sample the previous colour surface: it builds a texture triple with colour-buffer address&~3, size/layout/stride bits and a PDS fragment task, then three background pixel-state words in surface+ac/b0/b4. Those three become CMDTA+8/c/10. The same colour target therefore appears both as a PBE immediate and, when preserving background, as a texture address. **UNREAD:** all clear-vs-load decision branches and packing of clear colour; a recording with glClear and a recording preserving prior pixels are both needed.

**VERIFIED — kernel `sgxinfo.h:178`, S:0xb940, release build.** Exact `SGX_CCB_KICK` byte offsets (separate from CMDTA and from outer bridge flags/cookie):

| Offset | Field |
|---|---|
| 000..01f | sCommand |
| 020 | hCCBKernelMemInfo |
| 024,028,02c | destination count, HW sync-list allocation handle, pointer to destination sync handles |
| 030,034 | TA/3D status counts |
| 038..1b7 | 32 TA status triples |
| 1b8..1e7 | 4 3D status triples |
| 1e8,1ec | first-or-resume, last-in-scene |
| 1f0 | shared-header CCB offset |
| 1f4,1f8..277 | source count,32 source handles/fence values |
| 278,27c | TA dependency bool, TA/3D sync handle |
| 280,284 | TA-TQ sync handle,3D-TQ sync handle |
| 288,28c,290,294 | memory context, dataset VA, selected RTDATA VA, frame |

**INFERRED — relocation checklist, based on the verified stores above; not an exhaustive proof of all possible GLES paths.** Capture allocation images plus explicit relocations in: HW context PD/CCB/control/PB pointers; HWPBDESC and block/page links; dataset pending/context/tail/OTPM/self pointers; render details and update destinations; shared-header completion/status addresses; destination sync-list addresses; VDM link/index/PDS pointers; MTE pixel-PDS pointers; PDS stream/constant DMA addresses and all DOUTU tasks; texture triples in PDS *and constants*; end-tile USSE PBE immediate pair; pixel-event DOUTU tasks; background accumulation texture/PDS state; optional scratch/indexable/temp and ZLS load/store pointers. Holding VAs fixed eliminates most relocation work, but not changing stream offsets or completion values.

## Replay verdict

**INFERRED — feasible for a deliberately bounded renderer, not yet a verified replay implementation.** Fixed GPU VAs and a fixed 320x320 surface let setup geometry, HW context pointers, PB block descriptors, RT geometry, shader/vertex-layout variants and most PDS instructions be retained as setup artifacts. Native per-frame work can be small once captures exist: select a free RT/detail slot, fill dynamic vertices/indices/constants, patch PDS source addresses if they move, emit state/launch/index/terminate blocks, set frame/end-scene/status values, place CMDTA into the ring, perform cache maintenance and kick. Destination changes require patching PBE address immediates and any background-load texture address. This is a credible alternative to reimplementing the compiler or decoding general USSE instructions.

**INFERRED — main implementation-plan changes from this read:**

1. The command's public shared block starts100 bytes into the command; 176 private bytes are split before/after it. Base size0x518, ring size consumption0x540, middle-kick variable update list are three distinct quantities.
2. A normal RT set needs128 bytes for two records, not the nominal76-byte one-record structure. At 320x320, default storage covers24x24 tiles, not20x20. Details/sync-list pools add three of each for a normal set.
3. A 2 MiB usable PB allocates0x3dd000 parameter bytes plus descriptors/table; PB state is not a throwaway per-frame constant image. The fixed16MiB parameter heap and reserve overhead can constrain growth below the advertised usable limit.
4. Blend mode and texture format can change final USSE code; freeze hardware variants after draw validation. ProgramBinaryOES is not the replay asset.
5. Framebuffer address patches include USSE immediates and background texture state. Native RGBA byte order and PVRSRV format enum names must be distinguished.
6. WSEGL replacement still leaves an unconditional gralloc boundary in EGL services init. Fake hardware completion must write ring/status/resource words, not merely return from event waits.

**INFERRED — mutation/lifetime policy:** initialise PB pages/link table, DPM context/tail/OTPM/state and RT records once; then preserve device-written state until all work completes. For deterministic first experiments, serialize one scene at a time, avoid PB OOM/growth and freeze all shader/surface variants. Do not reset unknown MK fields to their allocation-time zeros between frames. A full reset/reinitialisation could theoretically replay a first-frame image repeatedly, but that has not been proven to restore *all* GPU/firmware state and is not a substitute for completion handling.

**INFERRED — principal risks:** PB free-list/head/tail mutation and partial-render/OOM recovery; shared tail/context state across rotating RT records; dynamic render-detail patches and resource-lock release; CPU/GPU cache visibility and ordering before READY/kicker; asynchronous TA/3D/status completion; microkernel active-power/timer handshakes from init; shader variants with scratch/secondary tasks; source native-fence translation. The one explicitly verified physical address in this path is the HW context PD field patched by the kernel; parameter page IDs, ordinary command pointers and PBE target are GPU virtual addresses. That does not prove absence of physical addresses in unread branches or opaque executable templates.

**INFERRED — code-size estimate, explicitly not measured:** with fixed templates, serialized scenes, fixed layouts, precompiled shader variants, no OOM and no dynamic resource allocator, expect roughly1–3k lines of native C for TA/3D submission, small packet builders, patching, counters and completions, *in addition to* already-working MMU/init/cache/interrupt code and captured binary assets. General vertex formats, arbitrary uniforms/textures/blending, allocation reclamation, PB growth/OOM and concurrency would plausibly make this5–15k+ lines and much more validation work. A tens-of-words patch loop alone is not the whole driver. Capture harness effort is additional and the gralloc/libc/TLS/compiler interfaces may dominate getting the first draw.

**UNREAD / unsettled, in priority order:**

- Exact semantics and lifetime ownership of every zero-initialised HW-context/PB/render-detail word, especially HWRENDERDETAILS+0x98..0x40f. Host writes are mapped; MK save/restore writes have not been decoded. Consequently this report does **not** claim the requested exhaustive per-field S/F/D/H classification.
- Full semantic names for private TA/3D register words (including K[0x16..0x21],K[0x23]) and full ISP/TSP bit layouts. `sgx530defs.h` in the permitted kernel is only542 lines and lacks most TA/ISP/PBE register definitions; no disallowed headers were used to fill the gap.
- Clear colour and clear/background load/save program choices; all simple-draw index-generation branches; complete texture format/NPOT/stride table and iterator semantics. Final known address sites are listed, but an exhaustive “every embedded address” guarantee requires the recorded artifacts and differential relocation runs.
- Full literal1..3 sample/macrotile alternate geometries and all render-target creation flags; the 320x320 single-sample default path is decoded. Cross-frame post-hardware values, OOM/free-list recovery and “resume” scene cases need actual GPU evidence later.
- Entire EGL/GLES/GLSL compiler constructor/import closure and exact executed bridge ordering for the selected pbuffer and FBO tests. The static minimal partial order and observed wait words are established; no emulator was run, so successful eglInitialize-to-glFinish is unproven.
- Exact arbitrary Android native-window callback signatures and HAL internals beyond the directly read boundary. The pbuffer path avoids most of them.

**INFERRED — highest-value recordings:** a first one-kick cleared triangle; a second frame on the same context/RT set; an intentionally split first/middle/final scene; a target-address-only move; vertex-buffer-address-only and uniform-only moves; opaque-colour vs textured variants; blend off/on with identical shader; preserved-background vs clear; and eventually controlled PB exhaustion. Capture pre-bridge, post-kernel-shared-header, and post-completion images separately. The first capture will settle exact artifact placement and unused bytes; only later hardware execution can settle true device mutations and handshake correctness.

## Evidence identity and static checks

**VERIFIED — original ELF files read directly for identity, table data and selected Thumb instruction cross-checks.** Existing Ghidra output was reused as analysis, not treated as vendor source. SIMD-heavy decompiler output contains type artefacts; tables and simple explicit stores are preferred. No vendor source/header beyond the permitted kernel was opened.

| Library | SHA-256 |
|---|---|
| S | `e16b7534f18b4598fb66cf140d031910c766ba64d4664870a9f5ac6dd49483a8` |
| G | `3d0bdddcd745d1293922186969ed634b3d41493f971622e95bda234187e06695` |
| E | `6c5fb9578d4f5b63c437cc4cdfa942dcfeda59118a6ccb46108b9bdb72df4910` |
| W | `55b528f0f7c71f18d28596f6200206cb91bd0a5126b6eddc1a0b18d24e58c518` |

**VERIFIED — arithmetic cross-checks:** 100+1128+76=1304; shared layout ends exactly at0x468; kick layout ends at0x298; default RT set24+2*52=128; TA ring base command rounds to0x540. Original Thumb loads confirm W table targets, PBE32-bit scaling lookup, CCB64-byte alignment and copy lengths. These checks validate layout consistency, not rendering correctness.

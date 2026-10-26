# ir3 shader toolchain for Adreno 305B (minnow)

How to compile GLSL ES shaders into Adreno A3xx ir3 machine code and
disassemble shaders and command streams, for the bare-metal GPU driver.
Everything runs on `pc`. The Mac only runs `tools/ir3c`.

## What works

| Tool | Path on pc (`/media/Data/mesa-ir3/mesa-25.2.8/build/...`) | Purpose |
|---|---|---|
| `ir3_compiler` (patched) | `src/gallium/drivers/freedreno/ir3_compiler` | GLSL (ES 1.00/3.x), SPIR-V or TGSI to ir3 binary, plus disassembly and metadata |
| `ir3-disasm` | `src/freedreno/isa/ir3-disasm` | Disassembles a raw shader binary (`FILE`) or one 64-bit instruction (`-x HEX`) |
| `cffdump` | `src/freedreno/decode/cffdump` | Decodes `.rd` command-stream dumps, including the shaders inside `CP_LOAD_STATE` |
| `pgmdump`, `pgmdump2` | `src/freedreno/decode/` | Decode the blob driver's program binaries. Built, but not tested. |
| `tools/mkrd.py` | Mac: `tools/`; pc: `/media/Data/mesa-ir3/tools/mkrd.py` | Wraps a raw command-stream dump (and the buffers it points to) into an `.rd` file for `cffdump` |
| `tools/ir3c` | Mac | Uploads GLSL to pc, runs `ir3_compiler`, prints the output and emits C arrays |

`ir3_disasm` (`src/freedreno/ir3/ir3_disasm`) is only a unit test with a
built-in table. Use `ir3-disasm` instead.

## Mesa version and why it is not the newest

- Built tree: tag **mesa-25.2.8**, commit `f97d7dcca0e51d7e20ed4342bb5ea8afea7db7fa`
  (2025-12-04), at `/media/Data/mesa-ir3/mesa-25.2.8`.
- The standalone compiler `src/gallium/drivers/freedreno/ir3/ir3_cmdline.c` was
  **removed in Mesa 25.3**. It exists in 25.2.8 but not in 25.3.6, 26.0.6,
  26.1.5 or 26.2.5. So 25.2.8 is the newest release that has it.
- `/media/Data/mesa-ir3/mesa` is a shallow clone of mesa-26.2.5
  (`ddaf85e353442d9d7f192fdcf1823e652e3f2ee3`). It is not built.
  `mesa-25.2.8` is a `git worktree` of that clone.
- Upstream, the 25.2.8 `ir3_cmdline.c` had bit-rotted. Unpatched, it segfaults
  or asserts on every GLSL input:
  - It ignores the link failure, then dereferences NULL.
  - The GLSL linker already lowers I/O, and `load_glsl()` lowers it a second
    time. The output stores then write undefined temporaries.
  - The NIR is created with all-zero standalone options instead of the ir3
    options, which trips the `nir_lower_amul` assertion.
  - Plain uniforms become `load_uniform`, which ir3 no longer handles.
  - It compiles only the stage of the last file on the command line.

  The local patch is in `tools/ir3_compiler-mesa-25.2.8.patch`. The same
  file is at `/media/Data/mesa-ir3/patches/0001-ir3_compiler-revive-standalone-GLSL-path.patch`.
  It is already applied to the pc tree as uncommitted changes. The patch:
  - Adds `nir_options` and `point_size_fixed` to `standalone_options`. The
    GLSL linker then runs with ir3's NIR options, exactly as the gallium
    driver does. `GLSLTessLevelsAsInputs` is set as freedreno sets it.
    `PointSizeFixed` is set so that the linker does **not** add a
    `gl_PointSize = 1.0` output.
  - Mirrors the GL state tracker's uniform path: uniforms go to vec4 slots
    (samplers do not count), then `nir_lower_io` and
    `nir_lower_uniforms_to_ubo`. ir3's UBO analysis then pushes UBO0 into
    the const file, as it does in the real driver.
  - Compiles every linked stage. When a VS and an FS are given together, it
    prints the VS->FS linkage computed by `ir3_link_shaders()`, the function
    `fd3_program.c` uses.
  - Builds variants through `ir3_shader_from_nir()` and
    `ir3_shader_create_variant()`, the gallium path. This also yields the VS
    **binning variant**.
  - Prints a `SUMMARY` block of the fields `fd3_program.c` and `fd3_emit.c`
    program from, and a `BEGIN/END DWORDS` block with the raw binary.
  - Adds `-c/--chip HEX`.
  - Never lowers mediump to fp16. The GL driver enables fp16 only on a5xx
    and later. Forcing it on a3xx produced wrong uniform reads (it treated
    the uniforms as packed 16-bit data).

## GPU id

Use `-c 03000520` (the default in `ir3c`). Mesa's table has no exact entry
for 0x03000520. Its "FD305B" entry is chip 0x03000512. 0x03000520 matches
the wildcard entry `GPUId(305)` (chip `0x030005ff`). Every a3xx id (305, 307,
320, 330, 305B, 306A) shares a single `GPUInfo`, and the compiler only
depends on `gen == 3`. So `-g 305`, `-g 320` or `-c 03000520` produce
identical code. `ir3-disasm` accepts `-c 3000520` as well.

## Build steps (on pc)

Run from the Mac:

```sh
ssh pc bash -s <<'EOF'
mkdir -p /media/Data/mesa-ir3 && cd /media/Data/mesa-ir3
git clone --depth 1 --branch mesa-26.2.5 https://gitlab.freedesktop.org/mesa/mesa.git
cd mesa
git fetch --depth 1 origin tag mesa-25.2.8
git worktree add --detach ../mesa-25.2.8 mesa-25.2.8
cd ../mesa-25.2.8
git apply ../patches/0001-ir3_compiler-revive-standalone-GLSL-path.patch
meson setup build -Dbuildtype=debugoptimized \
  -Dgallium-drivers=freedreno -Dvulkan-drivers= -Dtools=freedreno \
  -Dplatforms= -Dglx=disabled -Degl=disabled -Dgbm=disabled \
  -Dgles1=disabled -Dgles2=enabled -Dllvm=disabled -Dfreedreno-kmds=msm \
  -Dvalgrind=disabled -Dlibunwind=disabled -Dzstd=enabled -Dshader-cache=disabled
ninja -C build src/gallium/drivers/freedreno/ir3_compiler \
  src/freedreno/isa/ir3-disasm src/freedreno/decode/cffdump \
  src/freedreno/decode/pgmdump src/freedreno/decode/pgmdump2
mkdir -p /media/Data/mesa-ir3/tmp /media/Data/mesa-ir3/tools
EOF
scp tools/mkrd.py pc:/media/Data/mesa-ir3/tools/
```

(On a fresh setup, first copy `tools/ir3_compiler-mesa-25.2.8.patch` to
`/media/Data/mesa-ir3/patches/0001-ir3_compiler-revive-standalone-GLSL-path.patch`.)

- `-Dgles2=enabled` is required. The GLSL front end accepts `#version 100`
  only when `HAVE_OPENGL_ES_2` is set. Without it, every ES shader fails
  with "GLSL ES 1.00 is not supported".
- `ir3_compiler` is built only when the gallium freedreno driver is enabled,
  so `-Dgallium-drivers=freedreno` is needed. That needs libdrm, which is
  already on pc.
- No packages were installed. pc already had meson, ninja, bison, flex,
  python-mako, python-yaml, python-packaging, libdrm, zstd, expat, libelf,
  lua and glslang.
- Building only the listed targets compiles about 880 objects (a few
  minutes). LLVM and libclc are not needed.

## Usage

### `tools/ir3c` (Mac)

```sh
tools/ir3c vs pos.vert                         # one stage
tools/ir3c fs color.frag
tools/ir3c -p tri vs tri.vert fs tri.frag      # linked pair, plus linkage table
tools/ir3c -C -p tri vs tri.vert fs tri.frag   # C arrays only
tools/ir3c -q ...                              # compiler output only
tools/ir3c -v ...                              # also NIR and ir3 pass dumps
tools/ir3c -g 320 ...                          # other gpu id (default -c 03000520)
```

- File extensions don't matter. The stage word decides.
- A file without a `#version` line gets `#version 100` prepended, so
  error line numbers are off by one for such files.
- A single stage prints `error: program lacks a fragment/vertex shader` from
  the ES linker. This is expected: the stage is still compiled. To get
  matching varying locations, always compile real pipelines as a VS/FS
  pair.
- `IR3C_HOST` and `IR3C_ROOT` override `pc` and `/media/Data/mesa-ir3`.

The C output contains, per stage (`vs`, `vs_binning`, `fs`), `#define`s for
`INSTRLEN`, `CONSTLEN`, `FULLREGFOOTPRINT`, `HALFREGFOOTPRINT`, `TOTAL_IN`,
`SYSVAL_IN` and `VARYING_IN`, plus `static const uint32_t <prefix>_<stage>[]`.
The register ids (pos, color, inputs, linkage) are in the text output
above the C output.

### Directly on pc

```sh
B=/media/Data/mesa-ir3/mesa-25.2.8/build
$B/src/gallium/drivers/freedreno/ir3_compiler -c 03000520 x.vert x.frag   # needs .vert/.frag extensions
$B/src/freedreno/isa/ir3-disasm -c 3000520 shader.bin                      # raw LE binary
$B/src/freedreno/isa/ir3-disasm -c 3000520 -x 0x202cc00000000003           # one instr (hi_lo)
python3 /media/Data/mesa-ir3/tools/mkrd.py [-c 03000520] [-a 0x10000000] [-b ADDR:FILE ...] ring.bin out.rd
$B/src/freedreno/decode/cffdump --no-pager --no-color out.rd
```

`mkrd.py` writes an `RD_CHIP_ID` section, then `RD_GPUADDR` +
`RD_BUFFER_CONTENTS` for each `-b` buffer and for the command stream, then
`RD_CMDSTREAM_ADDR`. Indirect buffers and `CP_LOAD_STATE` with
`SS_INDIRECT` decode only if the referenced memory is passed with `-b` at
its GPU address. Tested with a hand-built stream (a `SP_FS_LENGTH_REG`
write, then `CP_LOAD_STATE` SB_FRAG_SHADER with test c's FS inline).
cffdump decoded the registers and disassembled the shader.

## How the metadata maps to A3xx registers

This mapping comes from `fd3_program.c` and `fd3_emit.c` in the same Mesa
tree. The terms are:

- **regid** = `(reg << 2) | comp`. Bit 8 (`0x100`, `HALF_REG_ID`) marks a
  half register. `0xfc` = `r63.x` = unused.
- **instrlen** is in units of 4 instructions (8 dwords). The binary is
  padded to `max(instrlen*4, ninstr+4)` instructions (trailing `nop`s after
  `end`), so upload all `sizedwords`.
- **Shader upload** (direct): `CP_LOAD_STATE` with
  `DST_OFF=0`, `STATE_SRC=SS_DIRECT`,
  `STATE_BLOCK=SB_VERT_SHADER(4)/SB_FRAG_SHADER(6)`, `NUM_UNIT=instrlen`,
  `STATE_TYPE=ST_SHADER`, followed by `sizedwords` dwords.
- **Constants**: each stage has its own const space. Uniform vec4 slot `i`
  is in `c(range[0].offset + i)` (`range[0].offset` is `c0` in all the cases
  below). Upload with `CP_LOAD_STATE` and `ST_CONSTANTS`: the const block of
  the stage, `DST_OFF = 2*N` for `cN`, `NUM_UNIT = 2` per vec4 (units of 64
  bits). The shader needs `constlen` vec4s. Immediates, if any, show as
  `@const(cN.x)` lines in the disassembly and must be uploaded too.
  Other registers:
  - `HLSQ_VS_CONTROL_REG.CONSTLENGTH` and `SP_VS_CTRL_REG1.CONSTLENGTH` =
    `vs constlen`. `CONSTFOOTPRINT = max(constlen-1, 0)`.
  - FS: the same fields with the FS constlen.
    `HLSQ_FS_CONTROL_REG.CONSTSTARTOFFSET = 128`.
    `SP_FS_OBJ_OFFSET_REG.CONSTOBJECTOFFSET = max(128, vs constlen)`.
  - `CONSTMODE = (vs.constlen + fs.constlen > 256)`.
- **Register footprint**: `SP_xS_CTRL_REG0.FULLREGFOOTPRINT = max_reg+1`
  and `HALFREGFOOTPRINT = max_half_reg+1`.
- **VS inputs**: `VFD_DECODE_INSTR[j].REGID = input regid`,
  `WRITEMASK = compmask`. Attributes are numbered in declaration order
  (`VERT_ATTRIB_GENERIC0` = first used attribute).
  `SP_VS_CTRL_REG1.INITIALOUTSTANDING = total_in`.
- **VS outputs**: `SP_VS_PARAM_REG.POSREGID` and `PSIZEREGID`.
  `TOTALVSOUTVAR = fs.varying_in`. For each linkage entry `k`:
  `SP_VS_OUT_REG[k/2].A/B_REGID` = VS regid and `COMPMASK` = compmask.
  `SP_VS_VPC_DST_REG[k/4].OUTLOCn = loc + 8`.
- **FS inputs**: varyings are read with `bary.f dst, inloc, r0.x`, where
  `inloc` is **without** the `+8`. The barycentrics are preloaded into the
  `IJPERSPCENTERREGID` register (`r0.x` in test c).
  `SP_FS_CTRL_REG1.INITIALOUTSTANDING = sysval_in`.
  `VPC_ATTR.TOTALATTR = VPC_PACK.NUMFPNONPOSVAR = NUMNONPOSVSVAR = fs.total_in`.
  For flat inputs, set bits in `VPC_VARYING_INTERP` and
  `SP_FS_FLAT_SHAD_MODE`, indexed by inloc (with no `+8`).
- **FS outputs**: `SP_FS_MRT_REG[i].REGID` = color regid. Set
  `HALF_PRECISION` if regid bit 8 is set (none here).
  `SP_FS_OUTPUT_REG.DEPTH_REGID` for depth.
- **Binning pass**: for GMEM/binning, `fd3` uses the VS binning variant
  (position only). Its input regids and constlen differ from the main VS,
  so it needs its own VFD decode setup. A sysmem-only renderer can ignore
  it.

## Test results (`-c 03000520`, Mesa 25.2.8 + patch)

Everything is full precision: mediump stays 32-bit on a3xx, and every
`HALFREGFOOTPRINT` is 0.

Summary:

| | a: VS pos | b: FS uniform | c: VS (pair) | c: FS (pair) |
|---|---|---|---|---|
| instrs (incl. `end`) / sizedwords / instrlen | 1 / 10 / 1 | 5 / 18 / 2 | 1 / 10 / 1 | 5 / 18 / 2 |
| full regs (max_reg+1) / half | 1 / 0 | 1 / 0 | 2 / 0 | 2 / 0 |
| constlen (vec4) | 0 | 1 (`color` = c0) | 0 | 0 |
| inputs | `pos` = r0.xyzw (regid 0x00) | none | `pos` = r1 (0x04), `col` = r0 (0x00) | `v`: inloc 0..3, compmask 0xf; ij in r0.xy |
| outputs | POS r0 (0x00) | color r0 (0x00) | POS r1 (0x04), VAR0 r0 (0x00) | color r0.z (0x02), i.e. r0.zw r1.xy |
| total_in / sysval_in / varying_in | 4 / 0 / 0 | 0 / 2 / 0 | 8 / 0 / 0 | 4 / 2 / 1 |
| linkage | | | VAR0: VS r0.x, cm 0xf, loc 0, OUTLOC 8 | |

In a and c, the VS is only `end`: the attribute registers are reused as
the output registers.

In c, the FS color output regid is 0x02 (r0.z). The four components are
consecutive registers: r0.z, r0.w, r1.x, r1.y.

### a. Vertex shader `attribute vec4 pos; void main(){ gl_Position = pos; }`

`tools/ir3c -p a vs a_pos.vert`

```
; gpu_id=0 chip_id=0x03000520 gen=3

Info log for linking:
error: program lacks a fragment shader

; VS: uniforms (vec4 slot in UBO0 = default uniform block; see ubo_state range[] for where ir3 pushes UBO0 into the const file):
; VERT: NIR compiler
Native code for unnamed VERT shader (null) with sha1 11336efa5b56d9d728d0465d609f64755ea9e290:
; num_ubos:           0
; num_driver_params:  0
; offsets:
;   primitive_param            c0.x (1 vec4)
; ubo_state:
;   num_enabled:      0
@in(r0.x)	in0 (wrmask=0xf)
end
nop
nop
nop
nop
; VERT: outputs: r0.x (VARYING_SLOT_POS)
; VERT: inputs: r0.x (VERT_ATTRIB_GENERIC0 slot=15 cm=f,il=0,b=0)
; VERT prog 1/1: 1 instr, 0 nops, 1 non-nops, 0 mov, 0 cov, 10 dwords
; VERT prog 1/1: 0 last-baryf, 0 last-helper, 0 half, 1 full, 0 constlen
; VERT prog 1/1: 1 cat0, 0 cat1, 0 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; VERT prog 1/1: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; VERT prog 1/1: 16 max_waves, 0 double_threadsize
; pos: r0.x

; VERT: SUMMARY
;   instrlen:              1 (units of 4 instrs = 8 dwords)
;   sizedwords:            10
;   constlen (vec4):       0
;   max_reg:               0 -> FULLREGFOOTPRINT 1
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              4
;   sysval_in:             0
;   varying_in:            0
;   num_sampler_prefetch:  0
;   input[0]: slot=15 (VERT_ATTRIB_GENERIC0) regid=0x00 compmask=0xf inloc=0 sysval=0 bary=0 flat=1 rasterflat=0
;   output[0]: slot=0 (VARYING_SLOT_POS) regid=0x00 half=0
;   POSREGID               r0.x (regid 0x00)
;   PSIZEREGID             r63.x (unused, regid 0xfc)
;   writes_psize:          0
; VERT: BEGIN DWORDS (10 dwords, 5 instrs, instrlen=1)
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
; VERT: END DWORDS

; VERT: BINNING VARIANT (VS used for the binning pass; position only)
Native code for unnamed BVERT shader (null) with sha1 11336efa5b56d9d728d0465d609f64755ea9e290:
; num_ubos:           0
; num_driver_params:  0
; offsets:
;   primitive_param            c0.x (1 vec4)
; ubo_state:
;   num_enabled:      0
@in(r0.x)	in0 (wrmask=0xf)
end
nop
nop
nop
nop
; BVERT: outputs: r0.x (VARYING_SLOT_POS)
; BVERT: inputs: r0.x (VERT_ATTRIB_GENERIC0 slot=15 cm=f,il=0,b=0)
; BVERT prog 1/2: 1 instr, 0 nops, 1 non-nops, 0 mov, 0 cov, 10 dwords
; BVERT prog 1/2: 0 last-baryf, 0 last-helper, 0 half, 1 full, 0 constlen
; BVERT prog 1/2: 1 cat0, 0 cat1, 0 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; BVERT prog 1/2: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; BVERT prog 1/2: 16 max_waves, 0 double_threadsize
; pos: r0.x

; BVERT: SUMMARY
;   instrlen:              1 (units of 4 instrs = 8 dwords)
;   sizedwords:            10
;   constlen (vec4):       0
;   max_reg:               0 -> FULLREGFOOTPRINT 1
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              4
;   sysval_in:             0
;   varying_in:            0
;   num_sampler_prefetch:  0
;   input[0]: slot=15 (VERT_ATTRIB_GENERIC0) regid=0x00 compmask=0xf inloc=0 sysval=0 bary=0 flat=1 rasterflat=0
;   output[0]: slot=0 (VARYING_SLOT_POS) regid=0x00 half=0
;   POSREGID               r0.x (regid 0x00)
;   PSIZEREGID             r63.x (unused, regid 0xfc)
;   writes_psize:          0
; BVERT: BEGIN DWORDS (10 dwords, 5 instrs, instrlen=1)
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
; BVERT: END DWORDS

ir3_compiler: GLSL link failed, continuing with the unlinked stage(s)

/* ---------------- C ---------------- */
#define A_VS_INSTRLEN 1
#define A_VS_CONSTLEN 0
#define A_VS_FULLREGFOOTPRINT 1
#define A_VS_HALFREGFOOTPRINT 0
#define A_VS_TOTAL_IN 4
#define A_VS_SYSVAL_IN 0
#define A_VS_VARYING_IN 0
static const uint32_t a_vs[] = {
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
};

#define A_VS_BINNING_INSTRLEN 1
#define A_VS_BINNING_CONSTLEN 0
#define A_VS_BINNING_FULLREGFOOTPRINT 1
#define A_VS_BINNING_HALFREGFOOTPRINT 0
#define A_VS_BINNING_TOTAL_IN 4
#define A_VS_BINNING_SYSVAL_IN 0
#define A_VS_BINNING_VARYING_IN 0
static const uint32_t a_vs_binning[] = {
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
};

```

### b. Fragment shader `precision mediump float; uniform vec4 color; void main(){ gl_FragColor = color; }`

`tools/ir3c -p b fs b_color.frag`

```
; gpu_id=0 chip_id=0x03000520 gen=3

Info log for linking:
error: program lacks a vertex shader

; FS: uniforms (vec4 slot in UBO0 = default uniform block; see ubo_state range[] for where ir3 pushes UBO0 into the const file):
;   color                vec4         mediump vec4 slot 0..0 = UBO0 bytes 0..15
; FRAG: NIR compiler
Native code for unnamed FRAG shader (null) with sha1 f99fb943e2b734b2b9403088f4bdb512980ecfb4:
; num_ubos:           0
; num_driver_params:  0
; offsets:
;   ubo_ranges                 c0.x (8 vec4)
; ubo_state:
;   num_enabled:      1
;   range[0]:
;     block:          0
;     offset:         c0.x
;     size:           8 vec4 (0b -> 128b)
mov.u32u32 r0.x, c0.x
mov.u32u32 r0.y, c0.y
mov.u32u32 r0.z, c0.z
mov.u32u32 r0.w, c0.w
end
nop
nop
nop
nop
; FRAG: outputs: r0.x (FRAG_RESULT_COLOR)
; FRAG: inputs: r63.x (SYSTEM_VALUE_BARYCENTRIC_PERSP_PIXEL slot=58 cm=3,il=0,b=0)
; FRAG prog 1/1: 5 instr, 0 nops, 5 non-nops, 4 mov, 0 cov, 18 dwords
; FRAG prog 1/1: 0 last-baryf, 0 last-helper, 0 half, 1 full, 1 constlen
; FRAG prog 1/1: 1 cat0, 4 cat1, 0 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; FRAG prog 1/1: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; FRAG prog 1/1: 16 max_waves, 1 double_threadsize
; color: r0.x

; FRAG: SUMMARY
;   instrlen:              2 (units of 4 instrs = 8 dwords)
;   sizedwords:            18
;   constlen (vec4):       1
;   max_reg:               0 -> FULLREGFOOTPRINT 1
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              0
;   sysval_in:             2
;   varying_in:            0
;   num_sampler_prefetch:  0
;   input[0]: slot=58 (SYSTEM_VALUE_BARYCENTRIC_PERSP_PIXEL) regid=0xfc compmask=0x3 inloc=0 sysval=1 bary=0 flat=0 rasterflat=0
;   output[0]: slot=2 (FRAG_RESULT_COLOR) regid=0x00 half=0
;   MRT color (all)        r0.x (regid 0x00)
;   DEPTH_REGID            r63.x (unused, regid 0xfc)
;   FRAGCOORDXYREGID       r63.x (unused, regid 0xfc)
;   FACENESSREGID          r63.x (unused, regid 0xfc)
;   IJPERSPCENTERREGID     r63.x (unused, regid 0xfc)
;   IJNONPERSPCENTERREGID  r63.x (unused, regid 0xfc)
;   IJPERSPCENTROIDREGID   r63.x (unused, regid 0xfc)
;   IJNONPERSPCENTROIDREGID r63.x (unused, regid 0xfc)
;   writes_pos (depth):    0
;   need_pixlod:           0
;   color0_mrt:            1
; FRAG: BEGIN DWORDS (18 dwords, 9 instrs, instrlen=2)
  0x00000000, 0x202cc000, /* 000 */
  0x00000001, 0x202cc001, /* 001 */
  0x00000002, 0x202cc002, /* 002 */
  0x00000003, 0x202cc003, /* 003 */
  0x00000000, 0x03000000, /* 004 */
  0x00000000, 0x00000000, /* 005 */
  0x00000000, 0x00000000, /* 006 */
  0x00000000, 0x00000000, /* 007 */
  0x00000000, 0x00000000, /* 008 */
; FRAG: END DWORDS

ir3_compiler: GLSL link failed, continuing with the unlinked stage(s)

/* ---------------- C ---------------- */
#define B_FS_INSTRLEN 2
#define B_FS_CONSTLEN 1
#define B_FS_FULLREGFOOTPRINT 1
#define B_FS_HALFREGFOOTPRINT 0
#define B_FS_TOTAL_IN 0
#define B_FS_SYSVAL_IN 2
#define B_FS_VARYING_IN 0
static const uint32_t b_fs[] = {
  0x00000000, 0x202cc000, /* 000 */
  0x00000001, 0x202cc001, /* 001 */
  0x00000002, 0x202cc002, /* 002 */
  0x00000003, 0x202cc003, /* 003 */
  0x00000000, 0x03000000, /* 004 */
  0x00000000, 0x00000000, /* 005 */
  0x00000000, 0x00000000, /* 006 */
  0x00000000, 0x00000000, /* 007 */
  0x00000000, 0x00000000, /* 008 */
};

```

### c. Varying color, linked pair

VS `attribute vec4 pos; attribute vec4 col; varying vec4 v; void main(){ v = col; gl_Position = pos; }`

FS `precision mediump float; varying vec4 v; void main(){ gl_FragColor = v; }`

`tools/ir3c -p c vs c_varying.vert fs c_varying.frag`

```
; gpu_id=0 chip_id=0x03000520 gen=3
; VS: uniforms (vec4 slot in UBO0 = default uniform block; see ubo_state range[] for where ir3 pushes UBO0 into the const file):
; VERT: NIR compiler
Native code for unnamed VERT shader (null) with sha1 11336efa5b56d9d728d0465d609f64755ea9e290:
; num_ubos:           0
; num_driver_params:  0
; offsets:
;   primitive_param            c0.x (1 vec4)
; ubo_state:
;   num_enabled:      0
@in(r0.x)	in0 (wrmask=0xf)
@in(r1.x)	in1 (wrmask=0xf)
end
nop
nop
nop
nop
; VERT: outputs: r1.x (VARYING_SLOT_POS) r0.x (VARYING_SLOT_VAR0)
; VERT: inputs: r1.x (VERT_ATTRIB_GENERIC0 slot=15 cm=f,il=0,b=0) r0.x (VERT_ATTRIB_GENERIC1 slot=16 cm=f,il=0,b=0)
; VERT prog 1/1: 1 instr, 0 nops, 1 non-nops, 0 mov, 0 cov, 10 dwords
; VERT prog 1/1: 0 last-baryf, 0 last-helper, 0 half, 2 full, 0 constlen
; VERT prog 1/1: 1 cat0, 0 cat1, 0 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; VERT prog 1/1: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; VERT prog 1/1: 16 max_waves, 0 double_threadsize
; pos: r1.x

; VERT: SUMMARY
;   instrlen:              1 (units of 4 instrs = 8 dwords)
;   sizedwords:            10
;   constlen (vec4):       0
;   max_reg:               1 -> FULLREGFOOTPRINT 2
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              8
;   sysval_in:             0
;   varying_in:            0
;   num_sampler_prefetch:  0
;   input[0]: slot=15 (VERT_ATTRIB_GENERIC0) regid=0x04 compmask=0xf inloc=0 sysval=0 bary=0 flat=1 rasterflat=0
;   input[1]: slot=16 (VERT_ATTRIB_GENERIC1) regid=0x00 compmask=0xf inloc=0 sysval=0 bary=0 flat=1 rasterflat=0
;   output[0]: slot=0 (VARYING_SLOT_POS) regid=0x04 half=0
;   output[1]: slot=32 (VARYING_SLOT_VAR0) regid=0x00 half=0
;   POSREGID               r1.x (regid 0x04)
;   PSIZEREGID             r63.x (unused, regid 0xfc)
;   writes_psize:          0
; VERT: BEGIN DWORDS (10 dwords, 5 instrs, instrlen=1)
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
; VERT: END DWORDS

; VERT: BINNING VARIANT (VS used for the binning pass; position only)
Native code for unnamed BVERT shader (null) with sha1 11336efa5b56d9d728d0465d609f64755ea9e290:
; num_ubos:           0
; num_driver_params:  0
; offsets:
;   primitive_param            c0.x (1 vec4)
; ubo_state:
;   num_enabled:      0
@in(r0.x)	in0 (wrmask=0xf)
end
nop
nop
nop
nop
; BVERT: outputs: r0.x (VARYING_SLOT_POS)
; BVERT: inputs: r0.x (VERT_ATTRIB_GENERIC0 slot=15 cm=f,il=0,b=0) r63.x (VERT_ATTRIB_POS slot=0 cm=0,il=0,b=0)
; BVERT prog 1/2: 1 instr, 0 nops, 1 non-nops, 0 mov, 0 cov, 10 dwords
; BVERT prog 1/2: 0 last-baryf, 0 last-helper, 0 half, 1 full, 0 constlen
; BVERT prog 1/2: 1 cat0, 0 cat1, 0 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; BVERT prog 1/2: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; BVERT prog 1/2: 16 max_waves, 0 double_threadsize
; pos: r0.x

; BVERT: SUMMARY
;   instrlen:              1 (units of 4 instrs = 8 dwords)
;   sizedwords:            10
;   constlen (vec4):       0
;   max_reg:               0 -> FULLREGFOOTPRINT 1
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              4
;   sysval_in:             0
;   varying_in:            0
;   num_sampler_prefetch:  0
;   input[0]: slot=15 (VERT_ATTRIB_GENERIC0) regid=0x00 compmask=0xf inloc=0 sysval=0 bary=0 flat=1 rasterflat=0
;   input[1]: slot=0 (VERT_ATTRIB_POS) regid=0xfc compmask=0x0 inloc=0 sysval=0 bary=0 flat=0 rasterflat=0
;   output[0]: slot=0 (VARYING_SLOT_POS) regid=0x00 half=0
;   POSREGID               r0.x (regid 0x00)
;   PSIZEREGID             r63.x (unused, regid 0xfc)
;   writes_psize:          0
; BVERT: BEGIN DWORDS (10 dwords, 5 instrs, instrlen=1)
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
; BVERT: END DWORDS

; FS: uniforms (vec4 slot in UBO0 = default uniform block; see ubo_state range[] for where ir3 pushes UBO0 into the const file):
; FRAG: NIR compiler
Native code for unnamed FRAG shader (null) with sha1 03915fa59dcb9935e49d8a3d5e533f44f0d9282d:
; num_ubos:           0
; num_driver_params:  0
; offsets:
; ubo_state:
;   num_enabled:      0
@in(r0.x)	in0 (wrmask=0x3)
bary.f r0.z, 0, r0.x
bary.f r0.w, 1, r0.x
bary.f r1.x, 2, r0.x
bary.f (ei)r1.y, 3, r0.x
end
nop
nop
nop
nop
; FRAG: outputs: r0.z (FRAG_RESULT_COLOR)
; FRAG: inputs: r0.z (VARYING_SLOT_VAR0 slot=32 cm=f,il=0,b=1) r0.x (SYSTEM_VALUE_BARYCENTRIC_PERSP_PIXEL slot=58 cm=3,il=4,b=0)
; FRAG prog 2/1: 5 instr, 0 nops, 5 non-nops, 0 mov, 0 cov, 18 dwords
; FRAG prog 2/1: 3 last-baryf, 0 last-helper, 0 half, 2 full, 0 constlen
; FRAG prog 2/1: 1 cat0, 0 cat1, 4 cat2, 0 cat3, 0 cat4, 0 cat5, 0 cat6, 0 cat7
; FRAG prog 2/1: 0 sstall, 0 (ss), 0 systall, 0 (sy), 0 loops
; FRAG prog 2/1: 16 max_waves, 1 double_threadsize
; pos (ij_pixel): r0.x
; color: r0.z

; FRAG: SUMMARY
;   instrlen:              2 (units of 4 instrs = 8 dwords)
;   sizedwords:            18
;   constlen (vec4):       0
;   max_reg:               1 -> FULLREGFOOTPRINT 2
;   max_half_reg:          -1 -> HALFREGFOOTPRINT 0
;   total_in:              4
;   sysval_in:             2
;   varying_in:            1
;   num_sampler_prefetch:  0
;   input[0]: slot=32 (VARYING_SLOT_VAR0) regid=0xfc compmask=0xf inloc=0 sysval=0 bary=1 flat=0 rasterflat=0
;   input[1]: slot=58 (SYSTEM_VALUE_BARYCENTRIC_PERSP_PIXEL) regid=0x00 compmask=0x3 inloc=4 sysval=1 bary=0 flat=0 rasterflat=0
;   output[0]: slot=2 (FRAG_RESULT_COLOR) regid=0x02 half=0
;   MRT color (all)        r0.z (regid 0x02)
;   DEPTH_REGID            r63.x (unused, regid 0xfc)
;   FRAGCOORDXYREGID       r63.x (unused, regid 0xfc)
;   FACENESSREGID          r63.x (unused, regid 0xfc)
;   IJPERSPCENTERREGID     r0.x (regid 0x00)
;   IJNONPERSPCENTERREGID  r63.x (unused, regid 0xfc)
;   IJPERSPCENTROIDREGID   r63.x (unused, regid 0xfc)
;   IJNONPERSPCENTROIDREGID r63.x (unused, regid 0xfc)
;   writes_pos (depth):    0
;   need_pixlod:           0
;   color0_mrt:            1
; FRAG: BEGIN DWORDS (18 dwords, 9 instrs, instrlen=2)
  0x00002000, 0x47300002, /* 000 */
  0x00002001, 0x47300003, /* 001 */
  0x00002002, 0x47300004, /* 002 */
  0x00002003, 0x47308005, /* 003 */
  0x00000000, 0x03000000, /* 004 */
  0x00000000, 0x00000000, /* 005 */
  0x00000000, 0x00000000, /* 006 */
  0x00000000, 0x00000000, /* 007 */
  0x00000000, 0x00000000, /* 008 */
; FRAG: END DWORDS

; LINKAGE (ir3_link_shaders(vs, fs, pack_vs_out=false), as fd3_program.c uses it)
;   cnt=1 max_loc=4
;   var[0]: slot=32 (VARYING_SLOT_VAR0) vs regid=0x00 (r0.x) compmask=0xf loc=0 -> SP_VS_VPC_DST OUTLOC=8
;   SP_VS_PARAM_REG.TOTALVSOUTVAR = fs->varying_in = 1
;   VPC_ATTR.TOTALATTR = VPC_PACK.NUMFPNONPOSVAR = NUMNONPOSVSVAR = fs->total_in = 4
;   HLSQ CONSTMODE = 0 (vs->constlen + fs->constlen > 256)

/* ---------------- C ---------------- */
#define C_VS_INSTRLEN 1
#define C_VS_CONSTLEN 0
#define C_VS_FULLREGFOOTPRINT 2
#define C_VS_HALFREGFOOTPRINT 0
#define C_VS_TOTAL_IN 8
#define C_VS_SYSVAL_IN 0
#define C_VS_VARYING_IN 0
static const uint32_t c_vs[] = {
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
};

#define C_VS_BINNING_INSTRLEN 1
#define C_VS_BINNING_CONSTLEN 0
#define C_VS_BINNING_FULLREGFOOTPRINT 1
#define C_VS_BINNING_HALFREGFOOTPRINT 0
#define C_VS_BINNING_TOTAL_IN 4
#define C_VS_BINNING_SYSVAL_IN 0
#define C_VS_BINNING_VARYING_IN 0
static const uint32_t c_vs_binning[] = {
  0x00000000, 0x03000000, /* 000 */
  0x00000000, 0x00000000, /* 001 */
  0x00000000, 0x00000000, /* 002 */
  0x00000000, 0x00000000, /* 003 */
  0x00000000, 0x00000000, /* 004 */
};

#define C_FS_INSTRLEN 2
#define C_FS_CONSTLEN 0
#define C_FS_FULLREGFOOTPRINT 2
#define C_FS_HALFREGFOOTPRINT 0
#define C_FS_TOTAL_IN 4
#define C_FS_SYSVAL_IN 2
#define C_FS_VARYING_IN 1
static const uint32_t c_fs[] = {
  0x00002000, 0x47300002, /* 000 */
  0x00002001, 0x47300003, /* 001 */
  0x00002002, 0x47300004, /* 002 */
  0x00002003, 0x47308005, /* 003 */
  0x00000000, 0x03000000, /* 004 */
  0x00000000, 0x00000000, /* 005 */
  0x00000000, 0x00000000, /* 006 */
  0x00000000, 0x00000000, /* 007 */
  0x00000000, 0x00000000, /* 008 */
};

```

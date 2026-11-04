# Codex (gpt-6-astra) power round 7, 2026-11-04: the AsteroidOS day run

**1. The equal-trim arithmetic is sound; a physical 2.5–3 mA gap remains conditional.** I reproduced **3.072 mA** over 125 settled intervals and **3.087 mA** endpoint-integrated. Firmware’s 23 baseline arms average **4.702 mA**, with time-weighted trim approximately **bbd7.3**. At that trim, your Linux slope gives approximately **2.0 mA**, hence a **2.7 mA apparent gap**. POWER.md’s “held bbd2–bbd4” is contradicted by the [raw firmware log](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/logs-floor2-2026-11-04-sturgeon.txt:2218).

Both write the same hardware offset; choosing different calibration channels does not invalidate normalization by the **actual written value**. However, equal trim cancels programmed offset, not differences in the underlying analogue zero with temperature/state. Linux also applies gain/temperature corrections. Thus this is stronger evidence than the earlier short run, but not yet proof of a physical 2.7 mA saving. Record **PMIC die temperature**, calibration channel/gain and running DT; battery temperature and capacity are not independent validation. [Firmware trim](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded/src/soc/pmic.c:658), [Linux calibration](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/hwmon/qpnp-adc-current.c:954), [counter conversion](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/power/qpnp-bms.c:1441).

**2. Capture these before switching.** Proposed commands only; nothing was edited, committed or accessed on-device. Below, `D=/sys/kernel/debug`.

| Capture at unplugged timer wakes | Concrete reads / purpose |
|---|---|
| Rails | `/sys/class/regulator/regulator*/{name,state,num_users,opmode,microvolts}`; preserve names beside values. `num_users` is an enable reference count, not current. Disabled handles do not establish physical rail shutdown. |
| Sleep history | `cat $D/wakeup_sources /proc/interrupts $D/rpm_stats $D/rpm_master_stats`; compare deltas, including accumulated residency, not just entry counts. |
| Clocks / pins | `cat $D/clk/enabled_clocks $D/gpio`; inspect `$D/clk/*/{enable,rate}` and available `$D/pinctrl/*/{pins,pinmux-pins,pinconf-pins}`. GPIO output alone is not a complete TLMM configuration dump. |
| eMMC / USB | `cat $D/mmc0/ios $D/msm_otg/otg_state`; read `power/{control,runtime_status,runtime_active_time,runtime_suspended_time}` under `/sys/bus/mmc/devices/*`, `/sys/class/mmc_host/mmc0/device`, and `/sys/bus/platform/devices/*f9a55000*`. Discover actual names first. Avoid `ext_csd`/card-status reads during measurement: they issue commands. |

For **physical regulator registers**, use the logger’s SPMI selector interface:
`echo ADDRESS > $D/spmi/spmi-0/address; echo 2 > $D/spmi/spmi-0/count; cat $D/spmi/spmi-0/data`.
For L*n*, `ADDRESS=0x14045+0x100*(n−1)` reads mode/enable; cover L3/4/6/8/10/15/17/19/20. LVS1 enable is `0x18046`. Decode HPM/enable bit 7 **and hardware-follow bits**. These selector writes do not write PMIC registers. [Register definitions](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/qpnp-regulator.c:120).

**Timer wakes sample after resume, not while asleep.** Use RAM output, screen off, USB absent; serialize snapshots and stop the duplicate polling logger. Its timer mode holds a five-second wakelock, so retain identical overhead between arms. [Logger](/Users/darrel/Downloads/AsteroidOS/asteroid-embedded-notes/tools/aos-powerlog.sh:33).

For a separate short diagnostic capture, save/restore these settings:

- `/sys/module/rpm_smd/parameters/debug_mask=1`
- `/sys/module/rpm_smd_regulator/parameters/debug_mask=2`
- `$D/clk/debug_suspend=1`; collect `dmesg`.

The regulator logger distinguishes active/sleep and cached/sent requests. **RPM debug_mask alone misses buffered sleep-request flush details**; this kernel passes `print=0`. Physical asleep PMIC/TLMM values require suspend-side instrumentation; resumed dumps cannot recover them. [Request logging](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/regulator/rpm-smd-regulator.c:295), [sleep entry](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/cpuidle/lpm-levels.c:486).

**3. Best short experiments:** compare `wake_gesture=1` versus `0` at the existing Synaptics attribute, cycling the screen after each change; the store only updates a flag. Use 30–60 minutes per arm, ideally ABBA, identical timer cadence, settled temperature and trim logged. This separates gesture-doze from sensor sleep; any saving would **increase** Linux’s advantage over firmware T. [Touch suspend](/Users/darrel/Downloads/AsteroidOS/minnow/sturgeon-kernel/drivers/input/touchscreen/synaptics_dsx/synaptics_dsx_core.c:3851). Separately compare 302-second versus 602-second logging to quantify wake overhead. **My leading hardware guess is panel/full-off or shared-rail policy**, but neither is established by the plugged-in snapshot.
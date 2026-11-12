# `adb reboot bootloader` froze minnow (fixed in 7de93d6)

Since 2ccbde4 (2026-11-11) DCDC1, the CPU supply, is taken off the SoC's voltage bus (TPS65912
I2C_SPI_CFG 0x26 = 0x48 instead of the vendor's 0x49) and set to 0.975 V (DCDC1_OP sel 38) whenever the
CPU clock is slow, which is also the case awake after 300 ms without drawing.

The reset is the PRCM's DPLL3 global reset, which does not touch the PMIC. A reboot while slow left
DCDC1 at 0.975 V and out of reach of the bootloader's voltage controller; the bootloader then runs the
CPU at full speed, and the watch hung until forced off (it then came up in AsteroidOS, the default).
Cause inferred from the code; the fix was confirmed by Darrel the same evening.

The vendor kernel (minnow-kernel `drivers/cpufreq/cpufreq-cpu0.c:180`, `cpu0_cpufreq_reboot_notify`)
sets the highest OPP before every reboot and power-off, and SmartReflex shutdown stops autocomp; its
`omap3xxx_restart` itself only writes the boot mode and resets DPLL3.

Fix: `reset_now` calls `cpu_supply_reset()`, which writes back the DCDC1_OP value and the 0x26 value
read at `tps65912_init` (the bootloader's), with the ramp time between.

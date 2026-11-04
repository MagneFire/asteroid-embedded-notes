#!/bin/sh
# One power-state snapshot on AsteroidOS (sturgeon), for comparing what Linux
# leaves configured in sleep with the firmware. Meant to run from a systemd
# timer with WakeSystem=true while unplugged, so it sees the state right after
# a resume from suspend (not the live asleep state):
#   systemd-run --unit=aossnap --on-active=600 --on-unit-active=600 \
#     --timer-property=WakeSystem=true sh /tmp/aos-snapshot.sh
# Output: /tmp/aos-snap-<epoch>.txt (RAM). Reads only; the debugfs SPMI
# address/count writes select what is read and write no PMIC register.
echo "aossnap 10000000000" > /sys/power/wake_lock
D=/sys/kernel/debug
OUT=/tmp/aos-snap-$(date +%s).txt
SPMI=$D/spmi/spmi-0

spmi() {
	echo "$1" > $SPMI/address
	echo "$2" > $SPMI/count
	cat $SPMI/data
}

{
	B=/sys/class/power_supply/bms
	echo "== time $(date +%s) uptime $(cut -d' ' -f1 /proc/uptime) usb $(cat /sys/class/power_supply/usb/present) cap $(cat $B/capacity) volt $(cat $B/voltage_now) cur $(cat $B/current_now) temp $(cat /sys/class/power_supply/battery/temp)"
	echo "== regulators (name state users opmode uV)"
	for r in /sys/class/regulator/regulator.*; do
		echo "$(cat $r/name 2>/dev/null) $(cat $r/state 2>/dev/null) $(cat $r/num_users 2>/dev/null) $(cat $r/opmode 2>/dev/null) $(cat $r/microvolts 2>/dev/null)"
	done
	echo "== PMIC LDO mode/enable registers (+0x45 mode, +0x46 enable), L1-L28"
	n=1
	while [ $n -le 28 ]; do
		printf "L%d " $n
		spmi $(printf "0x%x" $((0x14045 + 0x100 * (n - 1)))) 2
		n=$((n + 1))
	done
	echo "== LVS1 (+0x46)"
	spmi 0x18046 1
	echo "== SMPS S1-S5 mode/enable (+0x45/+0x46 of each control block)"
	for b in 0x11445 0x11745 0x11a45 0x11d45 0x12045; do spmi $b 2; done
	echo "== IADC trim / BMS"
	spmi 0x36f2 2
	echo "== rpm_stats"; cat $D/rpm_stats
	echo "== rpm_master_stats"; cat $D/rpm_master_stats
	echo "== wakeup_sources"; cat $D/wakeup_sources
	echo "== suspend_stats"; cat $D/suspend_stats
	echo "== interrupts"; cat /proc/interrupts
	echo "== enabled clocks"; cat $D/clk/enabled_clocks 2>/dev/null
	echo "== gpio"; cat $D/gpio
	echo "== mmc0 ios"; cat $D/mmc0/ios 2>/dev/null
	echo "== otg_state"; cat $D/msm_otg/otg_state 2>/dev/null
	echo "== runtime pm"
	for p in /sys/bus/mmc/devices/*/power /sys/class/mmc_host/mmc0/device/power /sys/bus/platform/devices/*f9a55000*/power; do
		[ -d "$p" ] && echo "$p $(cat $p/control 2>/dev/null) $(cat $p/runtime_status 2>/dev/null) active $(cat $p/runtime_active_time 2>/dev/null) suspended $(cat $p/runtime_suspended_time 2>/dev/null)"
	done
	echo "== touch"; cat /sys/class/input/input0/doze_cycle /sys/class/input/input0/wake_gesture
} > $OUT 2>&1

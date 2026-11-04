#!/bin/sh
# Battery logger for AsteroidOS on sturgeon, for comparing its sleep current
# with the firmware's by the same counter. Run it detached from adb so it
# survives the unplug:
#   systemd-run --unit=aoslog sh /tmp/aos-powerlog.sh 300
# It polls once a second while the system is awake and logs on every change
# of USB presence and every <interval> seconds of awake wall-clock time. This
# kernel's RTC has no wakealarm, so it cannot wake the system itself: with the
# screen and BT off the unplug and the replug are the samples, and the BMS
# accumulated shadow charge counter (uAh; Linux keeps it across its own resets
# of the raw register) integrates everything between them. Each line also has
# current, voltage, capacity, temperature, the IADC offset trim and the RPM
# low-power mode counts. Output: /tmp/aos-power.log (RAM).
INTERVAL=${1:-300}
LOG=/tmp/aos-power.log
BMS=/sys/class/power_supply/bms
SPMI=/sys/kernel/debug/spmi/spmi-0

spmi16() {
	echo "$1" > $SPMI/address
	echo 2 > $SPMI/count
	cat $SPMI/data | sed -n 1p
}

rpm() {
	awk '/RPM Mode/ {m=$2} /count:/ {split($1, a, ":"); c[m]=a[2]} /time in last mode/ {split($0, a, ":"); t[m]=a[2]} END {printf "xosd %s vmin %s vmin_last_ms %s", c["Mode:xosd"], c["Mode:vmin"], t["Mode:vmin"]}' /sys/kernel/debug/rpm_stats
}

echo "start $(date +%s) interval $INTERVAL" >> $LOG
prev=x
last=0
while true; do
	usb=$(cat /sys/class/power_supply/usb/present)
	now=$(date +%s)
	if [ "$usb" != "$prev" ] || [ $((now - last)) -ge "$INTERVAL" ]; then
		echo "t $now uptime $(cut -d' ' -f1 /proc/uptime) shadow $(cat $BMS/charge_counter_shadow) cc $(cat $BMS/charge_counter) cur $(cat $BMS/current_now) volt $(cat $BMS/voltage_now) cap $(cat $BMS/capacity) temp $(cat /sys/class/power_supply/battery/temp) usb $usb trim [$(spmi16 0x36f2)] rpm $(rpm)" >> $LOG
		prev=$usb
		last=$now
	fi
	sleep 1
done

# Codex (gpt-6-astra) power round 8, 2026-11-04: AsteroidOS snapshots

**1. The snapshots strengthen the panel/domain investigation; they do not locate the ~2.7 mA gap.**

- Your physical LDO list is correct in both snapshots. L8/L10 being on despite disabled ordinary handles demonstrates why regulator sysfs alone is insufficient. L17 is also on: **these dumps do not establish eMMC VCC-off during sleep**. S1–S4 and LVS1 are enabled; S5 is off.
- Only the **second** snapshot has 25 enabled clocks and 100 kHz non-active-only bus votes. The first has 28, 100 MHz votes, and three additional SDCC clock entries. These are resumed software votes, not measured asleep frequencies. Firmware R already requests zero; lowering those votes further is not the next experiment. LPASS AXI and hub UART appearing enabled likewise does not establish sustained sleep consumption.
- Over 536 seconds: RTC alarms **+3**, successful suspends **+3**, freeze failures **+5**, VDD-min entries **+35**, accumulated VDD-min **+515 seconds (~96%)**. Three alarms are not the total low-power transition count; diagnostic overhead is visible.
- GPIO25/78 read **input-high**, not reset/enable driven low. All listed GDSCs report disabled, but GX is absent. Physical domain/TLMM reads remain useful. Trim changes **bbcb→bbd7**: these snapshots do not independently validate equal-trim current.

**2. Before switching, capture physical domains/pins and one short regulator trace.** Proposed commands only. Run memory reads through the existing unplugged timer, to RAM, if `devmem` is available:

```sh
G="fd8c1024 fd8c2304 fd8c35a4 fd8c36a4 fd8c4024 fd8c4034 fc400404 fc401488 fc4011c0 fc400684 fc4004ac"
for a in $G; do echo "$a"; devmem "0x$a" 32; done
n=0; while [ "$n" -le 116 ]; do
  for o in 0 4; do
    a=$(printf '0x%x' $((0xfd511000+16*n+o)))
    echo "$n $a"; devmem "$a" 32
  done
  n=$((n+1))
done
```

Order: Venus, MDSS, JPEG, VFE, GX, CX, HSIC; GCC sleep vote, LPASS AXI, hub UART, USB PHY sleep clock. **VFE is `fd8c36a4`, correcting the inventory’s `3664`.** GDSCR bit31 indicates powered-on; bit0 requests collapse.

```sh
p=/sys/module/rpm_smd_regulator/parameters/debug_mask
old=$(cat "$p"); echo 2 > "$p"
# Cycle screen on/off; allow two unplugged timer wakes, then collect:
dmesg > /tmp/aos-rpm-regulators.txt
echo "$old" > "$p"
```

Inspect `rpm_regulator_req` lines for `s=slp`, especially `smpa 1` and `ldoa 3/8`; distinguish `sent`, `prev`, `cached`. **Mask 2 does not dump unchanged existing votes**, so missing lines prove nothing. Also retain a matching **plugged, screen-off** snapshot for the console comparison.

**3. Firmware reads and first experiment.** Generate the exact console lines in a host shell using the same `G` above; send each line separately:

```sh
for a in $G; do printf 'mem %s 1\n' "$a"; done
n=0; while [ "$n" -le 116 ]; do
  printf 'mem %x 2\n' $((0xfd511000+16*n)); n=$((n+1))
done
n=0; while [ "$n" -lt 28 ]; do
  printf 'pmic %x 2\n' $((0x14045+256*n)); n=$((n+1))
done
for a in 11445 11745 11a45 11d45 12045; do printf 'pmic %s 2\n' "$a"; done
printf 'pmic 18046 1\npmic 36f2 2\n'
```

USB-console reads are **plugged comparisons**; replug restores USB and undoes harness measures. A genuinely comparable unplugged firmware dump needs deferred RAM capture, absent from this harness.

First rehearse `powertest 1 1 night`, then run **`powertest 15 30 night`**, screen/AOD off. Its order is **B–P–P–B–B–S–S–B**, masks **01f/21f/41b**; verify `want=have`, trim and residency. P is the best first existing arm, but tests **panel deep-standby commands only**—it does not remove L4/L8/L15 supplies. A null P result leaves that rail difference unresolved; S then tests sleeping MCU versus reset-held sensors.

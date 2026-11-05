#!/usr/bin/env python3
"""Sums up a firmware log for the on-watch checklist (WATCH-TESTS.md): counts
what should appear, lists what should not, and totals the `passes:` lines.
Reads a file, or stdin: `adb shell log 20000 | tools/watch-check.py`."""
import fileinput, re, sys

GOOD = ["usb: up again", "phy in low power mode", "display: clamped", "display: clamps released",
        "power: always-on on", "power: always-on off", "controller stuck", "bringing up failed"]
BAD = ["!!!", "previous boot ended with", "secure config not restored", "power domain stays",
       "lanes not in ULPS", "frame not done on DSI", "DSI PLL not locked", "dsi: command", "ulpi write",
       "phy did not enter", "did not stick", "woke "]

good = dict.fromkeys(GOOD, 0)
bad = []
passes = slow = 0
steps = []
for line in fileinput.input():
    for g in GOOD:
        good[g] += g in line
    if any(b in line for b in BAD):
        bad.append(line.rstrip())
    m = re.search(r"passes: (\d+), (\d+) on the slow clock; us total/max per step: (.*)", line)
    if m:
        passes += int(m[1])
        slow += int(m[2])
        vals = [tuple(map(int, v.split("/"))) for v in m[3].split()]
        steps = steps or [[0, 0] for _ in vals]
        for s, (total, top) in zip(steps, vals):
            s[0] += total
            s[1] = max(s[1], top)

for g in GOOD:
    print("%6d  %s" % (good[g], g))
if good["display: clamped"] != good["display: clamps released"]:
    print("clamps not balanced: a difference of one is a rest still open, more is not")
print("\n%d lines to look at" % len(bad))
for l in bad[:40]:
    print("  " + l)
if passes:
    print("\n%d passes asleep, %d on the slow clock" % (passes, slow))
    print("step 1 usb to weather, 2 start to bms, 3 sensors to settings, 4 power to clock")
    for i, (total, top) in enumerate(steps):
        if i:
            print("  step %d: %d us per pass, worst %d us" % (i, total // passes, top))
sys.exit(1 if bad else 0)

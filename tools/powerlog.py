#!/usr/bin/env python3
"""Per-arm battery current from a firmware powertest log.

Reads the console log (`[t] ...` lines), splits it at `powertest: arm N <label>`
lines and, for each arm, reports:
  - the coulomb counter slope from the `bms: ... cc X uAh` lines (cc restarts at
    every new OCV, so only deltas within one OCV segment are used),
  - the mean and median of the `power: asleep ... N mA average` lines,
  - the hardware OCV slope (mV/h) from `bms: new ocv` lines, as a check.
The first --trim minutes of every arm are dropped. Arms are then grouped by
label and the paired difference is printed with a standard error taken from
the spread of the per-arm values.

usage: powerlog.py LOG [--trim MIN]
"""
import argparse
import re
import statistics as st

LINE = re.compile(r"^\[(\d+\.\d+)\] (.*)$")
ARM = re.compile(r"powertest: arm (\d+) (.*)$")
BMS = re.compile(r"bms: .*ocv (\d+) uV, cc (-?\d+) uAh")
NEWOCV = re.compile(r"bms: new ocv (\d+) uV")
AVG = re.compile(r"power: asleep, .* (-?\d+) mA average")
END = re.compile(r"powertest: plugged in")
SHADOW = re.compile(r"power: cc (-?\d+) uA over (\d+) ms, xo (\d+) x (\d+) ms, vmin (\d+) x (\d+) ms, slept (\d+) ms")
MEASURES = re.compile(r"powertest: measures want ([0-9a-f]+) have ([0-9a-f]+)")
ARMEND = re.compile(r"powertest: arm (\d+) end")


def parse(path):
    arms, cur = [], None
    for raw in open(path, errors="replace"):
        m = LINE.match(raw.strip())
        if not m:
            continue
        t, text = float(m.group(1)), m.group(2)
        if ARMEND.search(text):
            cur = None
        elif (a := ARM.search(text)):
            label = re.sub(r" have [0-9a-f]+$", "", a.group(2).strip())
            cur = {"n": int(a.group(1)), "label": label, "t0": t, "bms": [], "avg": [], "ocv": [], "reset": [],
                   "shadow": [], "mismatch": []}
            arms.append(cur)
        elif END.search(text) or ARMEND.search(text):
            cur = None
        elif cur is None:
            continue
        elif (b := NEWOCV.search(text)):
            cur["ocv"].append((t, int(b.group(1))))
            cur["reset"].append(t)
        elif (b := BMS.search(text)):
            cur["bms"].append((t, int(b.group(1)), int(b.group(2))))
        elif (b := SHADOW.search(text)):
            cur["shadow"].append((t,) + tuple(int(x) for x in b.groups()))
        elif (b := MEASURES.search(text)):
            if b.group(1) != b.group(2):
                cur["mismatch"].append(t)
        elif (b := AVG.search(text)):
            cur["avg"].append((t, int(b.group(1))))
    return arms


def arm_stats(arm, trim_s):
    start = arm["t0"] + trim_s
    bms = [x for x in arm["bms"] if x[0] >= start]
    charge = dur = 0.0
    for (t0, ocv0, cc0), (t1, ocv1, cc1) in zip(bms, bms[1:]):
        if ocv0 != ocv1 or any(t0 < r <= t1 for r in arm["reset"]):
            continue
        charge += cc1 - cc0
        dur += t1 - t0
    cc_ma = charge / dur * 3.6 if dur else None  # uAh/s -> mA
    avg = [v for t, v in arm["avg"] if t >= start]
    ocv = [(t, v) for t, v in arm["ocv"] if t >= start]
    slope = None
    if len(ocv) >= 3:
        ts = [t for t, _ in ocv]
        vs = [v / 1000 for _, v in ocv]
        mt, mv = st.mean(ts), st.mean(vs)
        den = sum((t - mt) ** 2 for t in ts)
        slope = sum((t - mt) * (v - mv) for t, v in zip(ts, vs)) / den * 3600 if den else None
    sh = [x for x in arm["shadow"] if x[0] >= start]
    sh_ms = sum(x[2] for x in sh)
    shadow_ma = sum(x[1] * x[2] for x in sh) / sh_ms / 1000 if sh_ms else None
    slept = sum(x[7] for x in sh)
    vmin = 100 * sum(x[6] for x in sh) / slept if slept else None
    xo = 100 * sum(x[4] for x in sh) / slept if slept else None
    late = [t for t in arm["mismatch"] if t >= start]
    return {"min": dur / 60, "cc_ma": cc_ma, "shadow_ma": shadow_ma, "shadow_min": sh_ms / 60000, "vmin": vmin, "xo": xo,
            "mismatch": len(late), "avg_mean": st.mean(avg) if avg else None,
            "avg_median": st.median(avg) if avg else None, "ocv_n": len(ocv), "ocv_mv_h": slope}


def fmt(v, f="{:7.2f}"):
    return f.format(v) if v is not None else "      -"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--trim", type=float, default=2.0, help="minutes dropped at the start of each arm")
    ap.add_argument("--min-shadow", type=float, default=8.0, help="minimum shadow-counter minutes for an arm to count")
    args = ap.parse_args()
    arms = parse(args.log)
    if not arms:
        raise SystemExit("no powertest arms in the log")
    print(f"{'arm':>3} {'label':<28} {'min':>5} {'cc mA':>7} {'sh min':>6} {'sh mA':>7} {'vmin%':>6} {'xo%':>6} "
          f"{'ocv':>4} {'mV/h':>7} bad")
    by_label = {}
    stats = {}
    for a in arms:
        s = arm_stats(a, args.trim * 60)
        stats[a["n"]] = (a["label"], s)
        print(f"{a['n']:>3} {a['label']:<28} {s['min']:5.1f} {fmt(s['cc_ma'])} {s['shadow_min']:6.1f} {fmt(s['shadow_ma'])} "
              f"{fmt(s['vmin'], '{:6.1f}')} {fmt(s['xo'], '{:6.1f}')} {s['ocv_n']:>4} {fmt(s['ocv_mv_h'])} {s['mismatch'] or ''}")
        if s["cc_ma"] is not None and s["min"] >= 10:
            by_label.setdefault(a["label"], []).append(s["cc_ma"])
    print()
    for label, v in by_label.items():
        se = st.stdev(v) / len(v) ** 0.5 if len(v) > 1 else float("nan")
        print(f"{label:<16} n={len(v):<3} cc {st.mean(v):7.2f} mA  se {se:5.2f}")
    leave_one_out(stats, args.min_shadow)
    if len(by_label) == 2:
        (la, va), (lb, vb) = by_label.items()
        d = st.mean(va) - st.mean(vb)
        se = (st.variance(va) / len(va) + st.variance(vb) / len(vb)) ** 0.5 if len(va) > 1 and len(vb) > 1 else float("nan")
        print(f"\n{la} - {lb}: {d:+.2f} mA  (2 se {2 * se:.2f})")


LOO = ["URHET", "-RHET", "U-HET", "UR-ET", "URH-T", "URHE-", "-----"]
NAMES = ["U usb phy lpm", "R rpm/gcc sleep votes", "H hub reset", "E emmc sleep", "T touch sleep"]


def leave_one_out(stats, trim_ok):
    """Per complete 14-arm cycle of `powertest ... sleep`: A = mean of the
    two all-on arms, S_j = mean of the two arms without measure j minus A
    (the saving of j with the other four on), N - A the whole bundle."""
    cycles = {}
    for n, (label, s) in stats.items():
        m = re.search(r"sleep=([-URHET]{5})", label)
        if m and s["shadow_ma"] is not None and s["shadow_min"] >= trim_ok and not s["mismatch"]:
            cycles.setdefault(n // 14, {})[n % 14] = s["shadow_ma"]
    rows = {k: [] for k in NAMES + ["bundle (none - all)"]}
    for c, v in sorted(cycles.items()):
        if len(v) != 14:
            print(f"cycle {c}: incomplete ({len(v)} usable arms), skipped")
            continue
        A = (v[0] + v[13]) / 2
        for j, name in enumerate(NAMES, 1):
            rows[name].append((v[j] + v[13 - j]) / 2 - A)
        rows["bundle (none - all)"].append((v[6] + v[7]) / 2 - A)
    if not any(rows.values()):
        return
    print("\nleave-one-out, shadow counter, saving with the other measures on (positive = saves):")
    for k, d in rows.items():
        if not d:
            continue
        se = st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else float("nan")
        print(f"  {k:<24} {st.mean(d):+6.2f} mA  2 SE {2 * se:5.2f}  cycles {len(d)}  per cycle "
              + " ".join(f"{x:+.2f}" for x in d))


if __name__ == "__main__":
    main()

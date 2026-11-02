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


def parse(path):
    arms, cur = [], None
    for raw in open(path, errors="replace"):
        m = LINE.match(raw.strip())
        if not m:
            continue
        t, text = float(m.group(1)), m.group(2)
        if (a := ARM.search(text)):
            cur = {"n": int(a.group(1)), "label": a.group(2).strip(), "t0": t, "bms": [], "avg": [], "ocv": [], "reset": []}
            arms.append(cur)
        elif END.search(text):
            cur = None
        elif cur is None:
            continue
        elif (b := NEWOCV.search(text)):
            cur["ocv"].append((t, int(b.group(1))))
            cur["reset"].append(t)
        elif (b := BMS.search(text)):
            cur["bms"].append((t, int(b.group(1)), int(b.group(2))))
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
    return {"min": dur / 60, "cc_ma": cc_ma, "avg_mean": st.mean(avg) if avg else None,
            "avg_median": st.median(avg) if avg else None, "ocv_n": len(ocv), "ocv_mv_h": slope}


def fmt(v, f="{:7.2f}"):
    return f.format(v) if v is not None else "      -"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--trim", type=float, default=2.0, help="minutes dropped at the start of each arm")
    args = ap.parse_args()
    arms = parse(args.log)
    if not arms:
        raise SystemExit("no powertest arms in the log")
    print(f"{'arm':>3} {'label':<16} {'min':>5} {'cc mA':>7} {'avg mA':>7} {'median':>7} {'ocv':>4} {'mV/h':>7}")
    by_label = {}
    for a in arms:
        s = arm_stats(a, args.trim * 60)
        print(f"{a['n']:>3} {a['label']:<16} {s['min']:5.1f} {fmt(s['cc_ma'])} {fmt(s['avg_mean'])} "
              f"{fmt(s['avg_median'])} {s['ocv_n']:>4} {fmt(s['ocv_mv_h'])}")
        if s["cc_ma"] is not None and s["min"] >= 10:
            by_label.setdefault(a["label"], []).append(s["cc_ma"])
    print()
    for label, v in by_label.items():
        se = st.stdev(v) / len(v) ** 0.5 if len(v) > 1 else float("nan")
        print(f"{label:<16} n={len(v):<3} cc {st.mean(v):7.2f} mA  se {se:5.2f}")
    if len(by_label) == 2:
        (la, va), (lb, vb) = by_label.items()
        d = st.mean(va) - st.mean(vb)
        se = (st.variance(va) / len(va) + st.variance(vb) / len(vb)) ** 0.5 if len(va) > 1 and len(vb) > 1 else float("nan")
        print(f"\n{la} - {lb}: {d:+.2f} mA  (2 se {2 * se:.2f})")


if __name__ == "__main__":
    main()

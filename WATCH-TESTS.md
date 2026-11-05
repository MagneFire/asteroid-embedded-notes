# On-watch tests for aod-review, app-core and sched

Sparrow first (G3NZCJ015551123, PR3), then sturgeon, after asking Darrel: it was left on
AsteroidOS. Build in the worktree named, after `make clean` when switching `TEST=`. Boot with
`make run`, with `ANDROID_SERIAL` set only for adb calls: it also filters fastboot, which hangs
with both watches attached. Sum up every log with `adb shell log 20000 | tools/watch-check.py`.
Afterwards release console holds: `awake off`, `rotate auto`.

## 0. Baseline: the plugged-in reset on sparrow

Main checkout at 84fbbe3 with the harness, plus the `exceptions.c` aid and the two clamp log
lines from `patches/power-harness-aod-review.patch`.

| Run | Cable | Always-on on the charger | `rest` | Note |
|---|---|---|---|---|
| a | USB host | on | 2 | the suspect path |
| b | wall charger | on | 2 | host or not |
| c | USB host | on | 1 | clamps out, same AOD |
| d | USB host | on | 0 | |
| e | USB host | off | 2 | changes much more than the clamps |

Long enough to reset in run a, then the same length for the others. A reset with `display:
clamped` last in the log implicates the path; no reset clears nothing.

## 1. aod-review on sparrow, per commit area

- [ ] Boots, UI, touch, adb. `make test` first.
- [ ] Unplug and re-plug 20 times, some under 2 s apart: `usb: up again`, adb back each time.
- [ ] Screen off 30 min, `phy in low power mode`, no `woke`, current as before.
- [ ] Always-on face 30 min on and off the charger: minutes change, clamps balanced.
- [ ] Console with a host that stops reading (open port, `help`, stop reading): no watchdog.
- [ ] Fault builds, each expecting the log line:

| `TEST=` | Do | Expect |
|---|---|---|
| `usb_stuck` | after 30 s, unplug and re-plug fast | `controller stuck`, then `usb: up again` |
| `usb_fail` | unplug, re-plug | `failed at test`, retry after 5 s works |
| `usb_no_lpm` | unplug | `clocks left on` once at most, rest on the second try |
| `usb_clock` | unplug, re-plug | `failed at clocks`, clocks off, retry works |
| `scm_fail` | AOD face past 60 s | fault record `display: no secure config`, reset, next boot prints it |
| `scm_slow` | AOD face past 60 s | no reset, frame late by 20 ms |
| `scm_hang` | AOD face past 60 s | fault record, reset |

## 2. app-core on sparrow

- [ ] As section 1, boot to UI, then every app, settings, notifications, media, weather.
- [ ] Log before and after the split match in order: boot lines, `tick`, `power:`.
- [ ] GPU suspend and resume across 20 sleeps, flatmesh and app backgrounds unchanged.
- [ ] Setting matrix, unplug while asleep, nightstand on, delay 5 s:

| Nightstand AOD | Normal AOD | On charger | After the delay |
|---|---|---|---|
| off | off | dark | dark |
| off | on | dark | face, no old screen flash, `always-on on` |
| on | off | face | dark, `always-on off` |
| on | on | face | face |

- [ ] Unplug asleep, nightstand AOD off, wake an hour later: no nightstand face.
- [ ] The picture really stays off until the face is drawn, on both panels.

## 3. Sturgeon

Sections 1 and 2 again, then a 1-minute-arm `powertest 1 1 night` rehearsal before any long run.
Harness measures U, R, E only on sparrow; the rest are sturgeon's.

## 4. Scheduler gate

`app-core` with `patches/power-harness-app-core.patch`, BT connected, AOD on, 1 h, sparrow:
`watch-check.py` totals give passes, slow-clock share, time per step and worst step. Compare the
active time to the current budget. This decides whether `sched` gets wired in.

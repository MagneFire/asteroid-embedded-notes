# asteroid-embedded apps vs their AsteroidOS originals

Research only (2026-10-30). Nothing was modified. Screen is 400x400, so every AsteroidOS
dimension below is converted with Dims.l(x) = Dims.w(x) = Dims.h(x) = 4x px,
Dims.defaultFontSize = 28 px, Dims.iconButtonMargin = 12 px. "Ours" paths are under
`~/Downloads/AsteroidOS/asteroid-embedded/ui/ui/`; AsteroidOS paths are under `~/Downloads/AsteroidOS/`.

Sources compared:

| Ours | AsteroidOS | Version used |
|---|---|---|
| settings.slint | asteroid-settings/src/qml/*.qml | newest, f/revert-language-animation 0e17fa5 (2026-10-26); 2.1 (2a29830) only differs by the WiFi row, `depth`/`pop` props and spacer placement |
| clock.slint TimerApp | 2.1/asteroid-timer/src/main.qml | f04baa1 (2026-02-20) |
| clock.slint StopwatchApp | 2.1/asteroid-stopwatch/src/{main,LapPage}.qml | 6f366ee (2026-03-21, lap page) |
| music.slint | asteroid-music/src/main.qml | 3a95e5f (2026-09-21); 2.1 only differs in the MPRIS binding, not in layout |
| weather.slint | 2.1/asteroid-weather/src/main.qml + icons.js | 32f886f (2026-02-27) |
| notes.slint | asteroid-launcher/src/qml/notifications/{NotificationsPanel,NotificationView,NotificationActions,NotificationButton}.qml | 39639e8 (2026-10-26) |
| overlay.slint (popup) | asteroid-launcher/src/qml/notifications/NotificationPreview.qml | same |
| today.slint | asteroid-launcher/src/qml/today/Today.qml | same |
| shared controls | qml-asteroid/src/controls/qml/*.qml | c190548 (2026-10-10); the 2.1 copies are the same apart from the Qt5 imports and the inline spinner-fade shader |

## 0. Shared control reference (pixel values at 400 px)

These are the values a faithful port must reproduce. Several already exist in `alarm.slint`
(PageHeader, IconButton, Spinner) and should be lifted into a shared file instead of being
copied again.

- **Label** (Label.qml:29-33): white, 28 px, elide right. The system font is Noto Sans
  (asteroid-launcher/src/main.cpp:59 `QGuiApplication::setFont(QFont("Noto Sans"))`); the
  `styleName`s used by apps ("SemiCondensed Light", "SemiCondensed ExtraLight",
  "ExtraCondensed ExtraLight", "Medium", "Bold") are Noto Sans variants. We embed only Noto Sans
  Light, Roboto Medium/Light and Raleway Light (ui/fonts), so condensed/bold/extralight styles can
  only be approximated (bold -> Roboto Medium, light/extralight -> Noto Sans Light; condensed
  widths cannot be matched without embedding NotoSans-SemiCondensedLight.ttf etc.).
- **PageHeader** (PageHeader.qml:30-58): 80 px tall band, gradient #000000dd at 20 % ->
  #00000055 at 80 % -> transparent at 100 %; title 28 px "SemiCondensed Light", centred, 100 px
  padding each side on round screens, word wrap, max 2 lines. alarm.slint:27-51 already matches.
- **IconButton** (IconButton.qml:39-46): 80 x 80, icon 0.7 opacity while pressed. alarm.slint:54-76 matches.
- **ListItem** (ListItem.qml:50-86, used by the Settings main list): row 84 px (h(21)); icon
  60 px (84 - h(6)) at x = 72 (w(18)), vertically centred; label at x = 72 + 60 + 24 = 156 px, 36 px
  (l(9)) "SemiCondensed Light"; a HighlightBar over the whole row: #33ffffff while pressed,
  150 ms OutQuad colour animation (HighlightBar.qml:48-62).
- **ListRow** (ListRow.qml:76-120, base of LabeledSwitch / LabeledActionButton / IntSelector /
  OptionCycler): rowMargin 60 px (w(15)); iconSize 80 px; label 24 px (l(6)) white, word wrap,
  vertically centred, spanning x = 60 .. 236; action slot 128 px wide (80 + 2 x 24 padding),
  80 px tall, right margin 36 px, so the action widget is centred at x = 300; whole row is a
  HighlightBar (#33ffffff on press). Opacity animates over 200 ms.
- **Switch** (Switch.qml:39-59): 80 px ios-checkmark-circle-outline / ios-circle-outline
  cross-faded over 100 ms, 0.6 opacity when disabled.
- **IntSelector** (IntSelector.qml:79-166), inside a 100 px row (Dims.h(25)): pill track
  x = 7.2 .. 332.8 (left margin l(1.8), right margin rowMargin + l(1.8)), height 80 - 14.4 =
  65.6 px, radius 32.8, transparent with a 2.56 px white border, fill (value - min)/(max - min) of
  the width in black 0.4 (0.6 while scrubbing, 120 ms OutQuad width animation); "ios-remove"
  IconButton 80 px at x = -6 of the track, "ios-add" at the right edge + 6, each 0.3 opacity at the
  limit; value label "N%" centred, Noto Sans SemiCondensed bold, 26.4 px (33.6 px while scrubbing).
  Press-and-hold or horizontal swipe scrubs.
- **RowSeparator** (RowSeparator.qml:61-75): 1 px, #40ffffff, full width.
- **OptionCycler** (OptionCycler.qml:50-78): a ListRow whose action slot shows the current value,
  28 px Noto Sans SemiCondensed bold, centred, wrap; tap cycles.
- **StatusPage** (StatusPage.qml:36-70): 100 px black disc (0.25 x height) centred at (200, 148)
  (vertical offset -52), opacity 0.2 (0.4 when `activeBackground`); icon fills the disc minus
  12 px margins (76 px); label 20 px (l(5)), centred, wrap, x = 16 .. 384, vertical centre at
  y = 260 (offset +60). Text is rich: `<h3>First line</h3>\nSecond line`.
- **Spinner** (Spinner.qml:28-50 + SpinnerDelegate.qml:62-81): vertical ListView, delegate 40 px
  (h(10)) with 8 px spacing (48 px pitch), current item scale 1.4 (39.2 px) opaque, others 0.8
  (22.4 px) at 0.6, 200 ms scale/opacity animations, top and bottom 20 % fade to transparent
  (spinnerfade.frag), optional 1 px #88ffffff separator at the right over 80 % of the height.
  Does not wrap. **CircularSpinner** (CircularSpinner.qml:39-70) is the wrapping PathView
  variant with the same delegate and pitch (2 x h(6) = 48 px per item). alarm.slint:81-127
  implements both (wrap on/off) with 22 -> 39 px sizes; reuse it.
- **PageDot** (PageDot.qml:41-70): dots of diameter = height, spacing height/4, white, 0.5 when
  not current; total width = height x 5/4 x n.
- **Marquee** (Marquee.qml:29-107): text centred when it fits; otherwise holds 2000 ms, scrolls
  left (InOutQuad, 1000 ms x textWidth/boxWidth), holds 400 ms, scrolls back, loops.
- **NotificationButton** (NotificationButton.qml:3-15): pill, radius height/2, #BB222222
  (#99222222 pressed), label 32 px (l(8)) centred.
- **LayerStack** (LayerStack.qml:112-146, 147-220): a pushed page slides in from the right over
  200 ms OutQuint; a swipe from the left edge drags it back and pops when past 15 % of the width
  (200 ms OutQuint), otherwise snaps back. Our `Face.app-depth`/`Face.back-count` mechanism
  (used by alarm.slint:160-168) gives the pop; the slide-in animation is not emulated anywhere yet.
- **Application** (Application.qml:33-96): FlatMesh background with the app's centerColor /
  outerColor. All six app colours in `Apps.list` (launcher.slint:18-25) match the QML
  (`centerColor`/`outerColor` of each main.qml).

Rendering constraints that apply throughout: the Slint software renderer has no shaders, so the
spinner fade is emulated per item (alarm.slint:103-104 `fade`), masks are emulated by strips
(launcher.slint:612-643, the speed dial), rounded clipping works on the GPU path, and no bold
weights are embedded, so `font-weight: 700` in alarm.slint:143 is a synthetic/fallback bold.

---

## 1. Settings — verdict: needs rework

### Matches
- App colours #0044A6 / #00010C (main.qml:8-9 vs launcher.slint:21).
- The functional subset (brightness, Bluetooth on/off, always-on, watchface, launcher,
  nightstand enable, 12/24 h, build) exists on both sides.

### Differences, most visible first

1. **Main list paradigm.** AsteroidOS (main.qml:44-160) is a vertical Flickable of
   `ListItem` rows — icon + title, each pushing a page on a LayerStack — with no title and
   no inline values: 24 px top spacer (h(6)), then rows of 84 px (icon 60 px at x = 72, title 36 px
   "SemiCondensed Light" at x = 156, full-row #33ffffff press highlight), 24 px bottom spacer.
   Ours (settings.slint:206-331) shows a "Settings" title (24 px at y = 24 .. 64), a 304 px wide
   Flickable at x = 48, y = 68 of 56 px rows with a 20 px label left and a 20 px value right in
   #ffffffb0, 12 px-radius #ffffff30 press highlight, plus inline −/+ brightness discs. To match:
   drop the title and the values, use full-width 84 px icon rows and navigate into pages.
   Row order and icons in AsteroidOS: Display (ios-display-outline), Nightstand (ios-moon-outline),
   Quick Panel (ios-quickpanel-batterybottom / -batterytop), Sound (ios-sound-outline, only with a
   speaker), Wallpaper (ios-wallpaper-outline), Watchface (ios-watchface-outline), Launcher
   (ios-launcher-outline), Time (ios-clock-outline), Date (ios-date-outline), Units
   (ios-units-outline), Language (ios-earth-outline), Time zone (ios-globe-outline), Bluetooth
   (ios-bluetooth-outline), WiFi (ios-wifi-outline, only with WLAN), USB (ios-usb), Power
   (ios-power-outline), About (ios-help-circle-outline). All exist in
   third_party/asteroid-icons-ion/src; none are in ui/icons yet.
2. **Brightness / Always on -> DisplayPage** (DisplayPage.qml:44-135). AsteroidOS: PageHeader
   "Display" (80 px band) over a Flickable column: 60 px spacer (l(15)); "Brightness" label 24 px,
   48 px tall, bottom-aligned, centred; IntSelector row 100 px (min 10, step 10, "N%"); 1 px
   separator; LabeledSwitch "Automatic brightness" 100 px; separator; LabeledSwitch "Always on
   Display" 100 px; separator; OptionCycler "Burn-in Protection" (Off/High/Medium/Low, only when
   DeviceSpecs.needsBurnInProtection); separator; LabeledSwitch "Tilt-to-wake" (0.6 opacity when
   unavailable); separator; LabeledSwitch "Tap-to-wake"; 60 px spacer.
   Ours: a 64 px HorizontalLayout with two 56 px #ffffff28 discs "−"/"+" (28 px glyphs) around
   "Brightness N%" 20 px (settings.slint:230-251), and an "Always on  On/Off" row
   (settings.slint:277-283). The firmware already steps brightness by 10 (UI_BRIGHTNESS_UP/DOWN,
   src/main.c:242) so an IntSelector with − / + works as is; scrubbing to an arbitrary value would
   need a "set brightness to N" event (SETTING_BRIGHTNESS currently cycles by 25, main.c:239).
3. **Bluetooth -> BluetoothPage** (BluetoothPage.qml:8-22): a StatusPage — 100 px disc at
   (200, 148), 0.4 opacity when powered else 0.2, icon ios-bluetooth-outline / ios-bluetooth-off-outline
   76 px, tap on the disc toggles; label at y ≈ 260: "<h3>Bluetooth on|off</h3>\nConnected|Not
   connected" at 20 px (the h3 renders bigger/bold). Ours: a list row "Bluetooth  On/Off"
   (settings.slint:254-260). Needs ios-bluetooth-outline.svg (we have ios-bluetooth.svg, the
   filled one, and ios-bluetooth-off-outline.svg).
4. **Watchface picker -> WatchfacePage / WatchfaceSelector** (WatchfaceSelector.qml:24-168).
   AsteroidOS: a 2-column GridView, cells 200 x 160 (w(50) x h(40)), scrolled to centre the
   current one, no title, no names. Each cell: a 160 px circle (round screen) clipped preview;
   the selected one shows the wallpaper behind it (100 ms fade) and a 60 px filled
   ios-checkmark-circle with a 2 px drop shadow, anchored to the cell bottom overhanging by
   4.8 px, offset ±72 px horizontally (towards the screen centre: +72 for even index, −72 for odd).
   Staying on the page after a tap. Ours (settings.slint:91-145): "Watchface" title 24 px,
   two 160 px circles at x = 30 / 210, y = 112, #00000060 background, 3 px white border when
   selected, 18 px name below, and the page pops back to the list on tap. Change: remove the
   title, names and border; add the checkmark badge (ios-checkmark-circle.svg, available) and a
   wallpaper/mesh background behind the selected one; keep the page open after selecting.
   With only two faces the AsteroidOS grid would sit at y = 0 .. 160 (it cannot scroll to centre);
   centring the single row vertically is the sensible deviation.
5. **Launcher picker -> LauncherPage** (LauncherPage.qml:27-170): same 200 x 160 grid, preview
   is the launcher QML at 160 x 160 (square, not circle-clipped), no title, no names; the selected
   cell gets a black 0.4 overlay over the whole cell and a 60 px ios-checkmark-circle in its
   bottom-right corner; the selected preview flips between first and last page every 5 s. Ours
   (settings.slint:148-204): "Launcher" title 24 px, 140 px circles with 3 px border and 16 px
   names in 2 columns at x = 50 / 210, rows 176 px apart from y = 90, pops on tap.
6. **Nightstand -> NightstandPage** (NightstandPage.qml:43-151): PageHeader "Nightstand";
   60 px spacer; LabeledSwitch "Enable" 100 px; a sub-column at 0.4 opacity while disabled
   (200 ms): "Brightness" 24 px label (48 px tall) + IntSelector (step 10, "%"), "Delay" label +
   IntSelector (step 5, max 30, "s"), LabeledSwitch "Always on Display"; 24 px spacer;
   LabeledSwitch "Custom watchface"; LabeledActionButton "Select watchface" with
   ios-arrow-dropright (0.4 opacity unless enabled + custom); 60 px spacer. Ours: one row
   "Nightstand  On/Off" (settings.slint:301-307).
7. **Clock 12/24 h -> UnitsPage** (UnitsPage.qml:19-42): PageHeader "Units"; 100 px spacer
   (l(25)); LabeledSwitch "Use 12H format:" 100 px; LabeledSwitch "Use Fahrenheit:" 100 px.
   Ours: row "Clock  12 hour/24 hour" (settings.slint:309-315).
8. **About / Build -> AboutPage** (AboutPage.qml:35-111): no header; 40 px spacer; logo-asteroidos
   160 px centred; "AsteroidOS" 28 px; version 28 px at 0.8; then per item 20 px spacer, bold
   28 px label, 28 px value: Build ID, Codename, Host name, WLAN MAC, IMEI, Serial number,
   Display size ("400W x 400H"), Kernel version, Qt version, Uptime ("N days hh:mm:ss"), Threads,
   loads, Total/Free memory; 40 px bottom spacer. Ours: disabled rows "Build" and "Battery"
   (settings.slint:317-327). logo-asteroidos.svg exists in asteroid-icons-ion.
9. **Rows AsteroidOS does not have:** "Forget phone" (settings.slint:262-267), "Vibration"
   (settings.slint:269-275 — in AsteroidOS haptics is a Quick Panel toggle,
   QuickPanelPage.qml:116-117, not a settings row) and "Battery". If kept, style them as
   LabeledSwitch / LabeledActionButton rows inside a page (e.g. Bluetooth page for forget, Sound
   page for vibration) rather than as main-list rows.
10. **Page transitions.** AsteroidOS pushes pages with a 200 ms OutQuint slide from the right and
    pops with an edge swipe (LayerStack.qml:79-89, 147-220); ours switches `page` instantly
    (settings.slint:81-86).

### Behaviour gaps
- Brightness: scrub-to-value needs a value-carrying setting event (firmware has only ±10 steps).
- Nightstand brightness / delay / nightstand AOD / custom watchface: no firmware settings.
- Automatic brightness, tilt-to-wake, tap-to-wake, burn-in protection: no firmware support.
- Bluetooth "Connected / Not connected": firmware knows (bt_host) but `Face` only has
  `bluetooth-on` (face.slint:48) — needs a `bluetooth-connected` property.
- About values: only `build` exists (face.slint:52). Codename ("sturgeon"), display size and the
  OS name are constants; uptime would need a firmware property.
- Fahrenheit: no firmware setting (and weather.slint/today.slint always show °C).

### Lower priority: pages we do not have at all
Quick Panel (toggle order/battery options), Sound (volume IntSelector + mute disc,
SoundPage.qml:14-68), Wallpaper, Time (CircularSpinner hour/minute[/AM-PM] + check button,
TimePage.qml:17-79 — our alarm Spinner page is this layout already), Date, Language, Time zone,
WiFi, USB, Power (ListItem list Power Off / Reboot / Bootloader with a RemorseTimer,
PowerPage.qml:17-72). Time/Date would need set-clock events in the firmware; Power would need a
reboot/poweroff hook; the others have no firmware backing.

---

## 2. Timer — verdict: needs rework

### Matches
- Colours #A6005F / #0C0003 (asteroid-timer main.qml:7-8 vs launcher.slint:23).
- The timer keeps running while the app is closed on both sides; default 5 min (main.qml:12,
  face.slint:56-57).

### Differences
1. **Layout** (main.qml:40-117): a Row of three non-wrapping `Spinner`s (h / m / s), 280 px tall
   (h(70)), vertically centred (y ≈ 59 .. 339), left margin 63.6 px (w(15.9)), right margin 6.4 px:
   hours 52.8 px wide (0.16 x 330) at x = 63.6 .. 116.4, model 24; minutes 166.7 px (0.505 x 330)
   at x = 116.4 .. 283, model 60; seconds 52.8 px at x = 283 .. 336, model 60. Delegates are the
   standard 48 px pitch (39.2 px current, 22.4 px others at 0.6, top/bottom 20 % fade). Unit
   letters "h", "m", "s" (main.qml:82-117): 25.6 px (l(6.4)), style "Medium" (Roboto Medium is the
   closest we embed), 0.9 opacity, centred at y = 177.6 (−22.4 from centre) and x = 120.4, 233.6,
   337.2 — i.e. just right of each number, raised like a superscript.
   Ours (clock.slint:44-118): "MM:SS" 72 px at y = 120 .. 200, four 56 px #ffffff30 discs
   "+1m"/"+10s" at y = 52 and "−1m"/"−10s" at y = 208 (x centres 120 / 280), a 64 px play/pause
   disc at y = 288 and a "Reset" disc beside it while running.
2. **Button** (main.qml:118-143): one IconButton 80 px at bottom centre (x = 160 .. 240,
   y = 308 .. 388): "ios-timer-outline" when idle, "ios-pause" when running; hidden when the
   selected time is 0. There is no reset button and no digital readout; while running the three
   spinners are disabled and scroll to the remaining time every 500 ms (main.qml:144-161).
3. **Stop semantics**: tapping while running deletes the countdown and leaves the spinners at the
   remaining time, so the next tap restarts from there (effectively pause/resume) and the user may
   re-spin first. The last duration is persisted (main.qml:16-20).

### Behaviour gaps
- The firmware only offers UI_TIMER_MINUTE_UP/DOWN and UI_TIMER_SECONDS_UP/DOWN (±1 min / ±10 s,
  src/ui/ui.h:56-65); a spinner needs a "set duration to N seconds" clock event (one new
  enum value carrying the seconds in `ui_event.value`) — small firmware change. Hours up to 23
  need `timer-set-ms` to accept 86 340 000 ms (it is an int, fine).
- Spinner for the running state: `Face.timer-ms` is already updated continuously, so the
  spinners can be bound to it when running.

### Data we lack
- Nothing beyond the set-duration event; the ringing screen is a separate matter (see §7).

---

## 3. Stopwatch — verdict: needs rework

### Matches
- Colours #9800A6 / #0C0009 (asteroid-stopwatch main.qml:6-7 vs launcher.slint:22).
- Tenths resolution; runs while closed.

### Differences
1. **Main page** (main.qml:48-63): a single rich-text label centred on the screen, base size
   100 px (h(25)). Format (main.qml:13-27): under a minute `SS` + superscript `s` in white at
   size 3 (= 100 px) followed by the tenth in #CCCCF3 at HTML size 1 (≈ 0.7 x, ~70 px); from a
   minute, line 1 `MM`+sup `m` white 100 px, line 2 `SS`+sup `s` + tenth in #CCCCF3 ~70 px; from an
   hour, line 1 `H`+sup `h`, line 2 `MMmSSs` in #CCCCF3. Ours (clock.slint:126-136): one
   "MM:SS.t" line at 64 px, y = 120 .. 200.
2. **Controls**: no buttons. A tap anywhere on the page starts/stops (main.qml:64-77). While
   paused the label blinks (opacity 1 -> 0 -> 1, 500 ms each, main.qml:56-62) and a 96 px
   (l(24)) "ios-refresh" icon appears centred between the label's bottom and the screen bottom;
   tapping it resets (main.qml:78-96). Ours: 64 px play/pause disc and a "Reset" disc at
   y = 248 (clock.slint:138-156).
3. **Lap page** (LapPage.qml), reached by swiping left (ListView, SnapOneItem, main.qml:32-41),
   with a PageDot (2 dots, 8 px, 8 px above the bottom, hidden while paused on page 0,
   main.qml:108-118). Top 160 px: black -> transparent gradient (LapPage.qml:120-131) and a 48 px
   (h(12)) label centred in it — the current split, or the delta to the previous lap in #AAEE44
   (faster) / #FF6644 (slower), #CCCCF3 otherwise — tapping it records a lap (LapPage.qml:133-169).
   Below, a list from y = 160: rows 80 px (l(20)), "L n" 24 px #CCCCF3 at 0.6 at x = 60, split
   time 32 px 12 px further right ("MM:SS.t" or "SS.ts"), delta 24 px right-aligned 60 px from the
   right edge in the same green/red, 1 px RowSeparator at the row bottom; the first row is the live
   current lap ("SSs" / "MMmSSs" / "HHhMMmSSs"); 80 px footer.

### Behaviour gaps
- Laps: the firmware has no lap store (ui.h:63-64 only START/RESET). Laps can be kept in Slint
  state from `Face.stopwatch-ms`, but they would be lost when the UI panel is recreated and are
  not persisted as AsteroidOS does (StopwatchController save()); persisting needs firmware work.
- Hours: our readout is minutes-based; the AsteroidOS format switches at 1 h.

---

## 4. Music — verdict: needs rework (layout is simple, but everything moves)

### Matches
- Colours #2577B3 / #000619 (asteroid-music main.qml:7-8 vs launcher.slint:20).
- Play/pause, previous, next and volume ± buttons exist on both sides; ios-play/ios-pause,
  ios-volume-down/up icons are already in ui/icons.

### Differences (main.qml:23-140)
1. **Button geometry.** AsteroidOS: previous = IconButton "ios-arrow-dropleft" 80 px at
   x = 12 .. 92, y = 160 .. 240; play/pause = IconButton 160 px (w(40)) centred (120 .. 280);
   next = "ios-arrow-dropright" at x = 308 .. 388. Ours (music.slint:70-103): 72 px skip icons
   (ios-skip-backward/forward) at x = 50 / 278, y = 176, and a 104 px outlined circle (2 px
   #ffffffa0 border, 56 px icon) at (148, 160). Need ios-arrow-dropleft.svg (available;
   ios-arrow-dropright.svg is already in ui/icons). No outline circle, no press background —
   only the 0.7 opacity dim.
2. **Volume row.** AsteroidOS: "ios-volume-down" 80 px at x = 64 (w(16)), bottom margin 48
   (y = 272 .. 352); "ios-volume-up" at x = 256 .. 336; between them a slider: 112 px wide
   (w(28)), 8 px tall, radius 12, white 0.6 at y = 308 .. 316, with a white fill of width
   112 x volume. Ours: 64 px buttons at x = 80 / 256, y = 268, and a "N%" text 20 px #ffffffa0
   (music.slint:105-137).
3. **Titles.** AsteroidOS: song title Marquee, bold 28 px, 240 px wide (w(60)), y = 28 .. 68;
   artist Marquee 28 px, 280 px wide, y = 64 .. 104 (overlapping by 4 px); both centred; a
   Marquee scrolls instead of eliding. No album. Ours: title 28 px bottom-aligned in y = 40 .. 124
   with wrap+elide, "Nothing playing" placeholder, and "artist – album" 20 px #ffffffa0 at
   y = 124 .. 152 (music.slint:42-68). Marquee needs an animated x in Slint (feasible: hold 2 s,
   scroll, hold 0.4 s, back).
4. **No-connection state**: StatusPage "<h3>No data</h3>Sync AsteroidOS with your phone." with
   "ios-sync" (76 px in the 100 px disc at (200,148), text at y ≈ 260), shown whenever Bluetooth
   is not connected. Ours has no such state (shows "Nothing playing").
5. **Cover art**: full-screen `artUrl` image at 0.7 with a black 0.5 band from the top to the
   artist's bottom (+2 px) when art is loaded (main.qml:32-49).

### Behaviour gaps
- Volume: AsteroidOS steps 5 % (0.05) and debounces 500 ms; ours sends UI_MEDIA_VOLUME_UP/DOWN
  and shows `Face.media-volume` (0..100, −1 unknown) — fine for the slider fill (width = 112 x
  volume / 100; hide the fill when unknown).
- `canGoNext/canGoPrevious/canPlay/canPause` gating: not available; harmless.

### Data we lack
- Bluetooth connection state for the StatusPage (firmware knows; not in `Face`).
- Cover art (no art transfer in the firmware; skip).

---

## 5. Weather — verdict: needs rework

### Matches
- Colours #990019 / #0C0200 (asteroid-weather main.qml:7-8 vs launcher.slint:24).
- Icon mapping: Face.weather-icon (face.slint:96-98) matches icons.js (2xx thunderstorm,
  3xx drizzle, 5xx rainy except 511 snow, 6xx snow, 7xx cloudy, 800 sunny, 801 partly-sunny,
  802-804 cloudy, else alert). Note the launcher's today/weathericons.js maps 3xx to
  ios-rainy-outline instead — a tiny inconsistency inside AsteroidOS itself.
- Up to 5 days from today, °C (src/main.c:317-320 converts from kelvin).

### Differences (main.qml:67-273)
1. **Paging, not a summary.** AsteroidOS shows one day per page in a horizontal ListView
   (SnapOneItem) with a PageDot (12 px dots, 15.2 px above the bottom, one per available day,
   main.qml:263-272). Ours is a single page with today on top and a 5-column forecast strip
   (weather.slint:76-122).
2. **Day page layout** (main.qml:117-251): day name in a 168 px tall label (h(42)) at the top,
   40 px (l(10)) "SemiCondensed ExtraLight", centred ("Today", "Tomorrow", then the full weekday
   name); icon 96 px (w(24)) centred at (200, 200); min temperature in a 120 px (w(30)) circle
   centred at (80, 200): "N°C" at 60 px "ExtraCondensed ExtraLight", with "Min:" bold 20 px
   #99ffffff 40 px above the centre and "▼" light 24 px #88ffffff 40 px below; max in a circle at
   (320, 200): "Max:" 40 px below, "▲" 24 px above (main.qml:132-233). City name at the bottom
   (main.qml:76-96): 176 px tall label (h(44)) anchored to the bottom, 248 px wide, centred, wrap,
   40 px (36 px if > 14 chars, 33.6 px if > 16) "SemiCondensed ExtraLight", letter spacing −0.2 px.
   Ours: city 22 px #ffffffa0 at y = 32, icon 88 px at y = 68, a condition word ("Cloudy") 22 px at
   y = 160 that AsteroidOS never shows, "max° min°" 36 px at y = 188, then the strip.
3. **No-data state**: StatusPage "<h3>No data</h3>Sync AsteroidOS with your phone." with
   "ios-sync" (main.qml:67-72). Ours: "No weather data" 24 px #ffffffa0 centred (weather.slint:10-18).
4. The ExtraCondensed/ExtraLight styles cannot be matched with the embedded fonts (Noto Sans Light
   is the nearest); temperature at 60 px in a 120 px circle will need a slightly smaller size or a
   condensed Noto Sans face added to ui/fonts.

### Behaviour gaps
- The number of pages is `availableDays` (days since the data's day0, main.qml:9-15); our
  firmware passes "days starting today" already (ui.h:15), so pages = 1 + forecast length.
- Fahrenheit: no setting in the firmware — always °C.

### Data we lack
- Nothing for the layout; the weekday names come from `Face.weekday`.

---

## 6. Notifications list — verdict: needs rework (different paradigm)

AsteroidOS has no list. Each notification is a full-screen panel to the left of the watchface
(newest nearest, older ones further left, NotificationsPanel.qml:11-23), each with an actions
panel in the row above it (swipe down to reach: Snooze / Dismiss all / Dismiss,
NotificationActions.qml:62-100). Ours (notes.slint) is one panel with a title and a scrolling
list of 76 px rounded rows.

### Matches
- The empty state content: "No notifications" (NotificationsPanel.qml:117-138 vs notes.slint:14),
  though not its geometry (see below).
- Dismiss per notification exists (`Face.notification-dismissed`).

### Differences
1. **NotificationView** (NotificationView.qml:55-123): a 280 px wide (0.7) centred column that
   can be dragged vertically when taller than the screen: 60 px spacer; a 40 px row with the app
   name 24 px (l(6)) in 224 px (w(56)), elided, and a right-aligned timestamp 24 px in 56 px
   (w(14)) — "Now", "Nm", "Nh", "Nd"; 12 px spacer; summary bold 28 px, elided single line; 4 px
   spacer; body 28 px, wrapped; 40 px spacer; "Dismiss" NotificationButton 220 x 80 px (w(55) x
   h(20)) pill #BB222222 with 32 px text; 40 px spacer. No icon on this view (the icon only appears
   with the timestamp at the bottom of the actions panel, NotificationActions.qml:159-191, 24 px
   icon + #b0b0b0 24 px text, 12 px above the bottom). Ours: 32 px icon, 20 px app, 22 px summary,
   no body, an "x" button (notes.slint:28-98).
2. **Empty state geometry** (NotificationsPanel.qml:117-138): "ios-mail-outline" 108 px (w(27)) at
   0.8 opacity centred with a −36 px vertical offset (y = 110 .. 218), and "No notifications" 24 px
   at 0.8, 16 px below the icon, centred. Ours shows only text at the top (notes.slint:10-19).
   ios-mail-outline.svg is available in asteroid-icons-ion but not yet in ui/icons.
3. **Navigation**: one notification per horizontal page. The screen stack (src/ui/stack.h) has a
   single "left" panel, so paging must be done inside notes.slint with a horizontal Pager (as
   alarm.slint:174-195 does) and the launcher-style edge reporting so the stack only takes over the
   swipe back on the last/first page (`Face.launcher-edges` mechanism, face.slint:44-46).
4. **Actions panel** (NotificationActions.qml:62-158): three 220 x 80 px pills stacked with 32 px
   spacing, centred; "Snooze" pushes a page with a PageHeader "Snooze" and a 2 x 2 grid of 104 px
   (l(26)) round pills "10m", "30m", "1h", "3h" (80 px margins, 32 px spacing).

### Behaviour gaps
- Timestamp: `struct notification` has `time` (src/notify/notify.h:9) but `ui_add_notification`
  does not pass it (src/main.c:489-490) and the `Note` struct has no field (face.slint:4-10) —
  needs plumbing plus a clock to compute "Now/Nm/Nh/Nd".
- Snooze: no firmware support (would need a re-post timer); "Dismiss all" can loop in the UI.
- Our popup tap dismisses (removes) the notification (overlay.slint:65-70); in AsteroidOS a tap
  only hides the preview and the notification stays (NotificationPreview.qml:12).

---

## 7. Notification popup (overlay.slint) — verdict: small fixes

Reference: NotificationPreview.qml:8-134.

### Matches
- Full-screen overlay with icon on top, summary, body; tap closes it.

### Differences
1. **Background**: black at 0.8 opacity (0.85 while pressed) over the current screen; fades in and
   out over 300 ms; auto-hides after 5 s (NotificationPreview.qml:13-17, 108-129). Ours: opaque
   black (overlay.slint:11-12), 150 ms stack fade, no timeout (hidden only on sleep, src/main.c:640).
   Our layers are premultiplied RGBA, so `background: #000000cc` gives the translucency directly.
2. **Content block** is vertically centred as a group (NotificationPreview.qml:18-77): icon 80 px
   (w(20)) with a 12 px top margin; summary bold 24 px (l(6)), 360 px wide (w(90)), centred,
   single line elided, 12 px below the icon (0 px and 0 height when empty); body 24 px (h(6)),
   320 px wide (w(80)), centred, wrapped, max 4 lines, elided, 12 px below the summary, bold when
   there is no summary. No app name. Ours: 36 px icon at y = 16, app name 20 px at y = 56,
   summary 28 px at y = 92 .. 156, body 22 px at y = 164 .. 332 top-aligned (overlay.slint:14-63).
3. **Icon fallback**: "ios-mail-outline" when the notification has none
   (NotificationPreview.qml:30-44); ours uses ios-alert-outline (overlay.slint:19, notes.slint:40).
4. **Tap** should only hide (see §6 behaviour gaps).

### Behaviour gaps
- 5 s auto-hide needs a timer (Slint `Timer` or the firmware's main loop calling
  `ui_hide_notification`).

### Related overlays (not in the brief, noted for completeness)
- Pairing code vs BluetoothAgent.qml:12-112 (ReqConfirmation/DispPasskey): a #f4f4f4 disc 280 px
  with a drop shadow, grey (#666666) ios-bluetooth 80 px at centre −80 px, "Confirm:"/"Pass Key:"
  20 px grey, the 6-digit key bold 28 px grey, and grey ios-close-circle-outline /
  ios-checkmark-circle-outline IconButtons at x = 200 ∓ 48, 84 px above the bottom. Ours is
  white-on-black text (overlay.slint:73-97).
- Ringing alarm/timer vs 2.1/asteroid-alarmclock/alarmpresenter/main.qml:38-122: mesh #333333 /
  #000000, StatusPage disc with ios-alarm-outline or ios-timer-outline, the time at 60 px (l(15))
  — or the countdown title "HH:MM:SS" at 32 px — in the bottom 176 px, dismiss
  (ios-checkmark-circle-outline) IconButton at the left middle and snooze
  (ios-sleep-circle-outline / ios-refresh-circle-outline for a timer) at the right middle; auto
  snooze after 30 s. Ours: "Alarm"/"Timer" caption, 80 px time, Snooze/Dismiss pills
  (overlay.slint:99-150). All icons exist in asteroid-icons-ion.

---

## 8. Today — verdict: matches

Reference: Today.qml:65-160.

### Matches
- Header weather: icon 60 px (h(15)) right-aligned to the horizontal centre (x = 140 .. 200),
  vertically centred in the 140 px header (y = 40 .. 100), 0.8 opacity (Today.qml:69-77 vs
  today.slint:10-18); temperatures "min°C\nmax°C" 20 px (l(5)) at 0.8, 180 px wide (w(45)) from
  x = 220, vertically centred over the header height, left-aligned (Today.qml:78-89 vs
  today.slint:20-30).
- Empty state: ios-calendar-outline 108 px (w(27)) at 0.8 centred with a +4 px offset when there is
  weather and −36 px otherwise, "No events today" 24 px at 0.8, 16 px below (Today.qml:139-160 vs
  today.slint:32-51).

### Differences
- None visible. (Icon mapping: the launcher's weathericons.js uses ios-rainy-outline for 3xx
  where our shared Face.weather-icon uses ios-drizzle-outline; negligible.)

### Behaviour / data gaps
- Agenda rows (Today.qml:113-137: 60 px rows, time 20 px right-aligned in the left 30 %, title
  28 px at x = 136) and the small-caps "Today" caption are impossible without calendar data; the
  firmware has none.
- Fahrenheit: n/a.

---

## Summary of firmware work implied (for the gaps above)

| Needed by | Change |
|---|---|
| Timer spinners | a clock event "set duration to N s" (new `ui_clock_action`, value in `ui_event.value`) |
| Brightness scrubbing | a setting event carrying an absolute brightness |
| Bluetooth page, Music no-data page | expose `bluetooth-connected` in `Face` |
| Notification timestamp | pass `notification.time` through `ui_add_notification` into `Note`, plus a now-clock |
| Notification popup | 5 s auto-hide (UI timer or main loop) |
| Stopwatch laps | optional persistence of a lap list |
| Nightstand/Display/Units/About extras | new settings (nightstand brightness/delay/AOD, auto brightness, tap/tilt wake, Fahrenheit) and about values (uptime) |

## Icons to copy from third_party/asteroid-icons-ion/src into ui/icons
ios-arrow-dropleft, ios-sync, ios-mail-outline, ios-refresh, ios-remove, ios-bluetooth-outline,
ios-checkmark-circle, logo-asteroidos, and the settings list icons: ios-display-outline,
ios-moon-outline, ios-quickpanel-batterybottom, ios-sound-outline, ios-wallpaper-outline,
ios-watchface-outline, ios-launcher-outline, ios-clock-outline, ios-date-outline,
ios-units-outline, ios-earth-outline, ios-globe-outline, ios-wifi-outline, ios-usb,
ios-power-outline, ios-help-circle-outline (all present in the Ionicons set). For the ringing
overlay also ios-sleep-circle-outline, ios-refresh-circle-outline, ios-close-circle-outline.

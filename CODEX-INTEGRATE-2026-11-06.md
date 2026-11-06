The changes introduce incorrect maXTouch report-ID assignment and delayed USB detection on sleeping smelt devices. Existing host-test binaries and the boot-image test passed, but they do not cover these failures.

Full review comments:

- [P1] Preserve object-table order when assigning report IDs — /Users/darrel/Downloads/AsteroidOS/asteroid-embedded-integrate/src/input/mxt.c:23-29
  When reporting objects are not in address order, this sort changes their report IDs. maXTouch assigns IDs in object-table order, not register-address order. For example, the unsorted table in `mxt_test.c` should give T9 first ID 1, but this implementation assigns 2. Consequently, `mxt_decode()` rejects the first finger's reports, and `message_done()` can mistake another object's messages for touches. Assign IDs before sorting, or remove the sort, and update the test expectation.

- [P2] Retain a USB polling deadline on smelt — /Users/darrel/Downloads/AsteroidOS/asteroid-embedded-integrate/src/app.c:140-145
  On smelt, the battery driver only installs the wireless-dock interrupt; USB insertion through the pogo pins is detected by polling. Making `cable_task` lazy removes that polling deadline from `sched_next_ms()`. Once USB has collapsed, `usb_next_ms()` also returns no deadline, so an asleep watch with Bluetooth disabled can take up to the next 60-second stats wake to detect USB and enumerate. Keep a non-lazy cable polling deadline for boards without a USB-insertion interrupt.
Triage (Claude):
- P1 disagree: Motorola atmxt.c sorts the object table by address before assigning report ids (minnow-kernel atmxt.c ~1590), which is what mxt.c follows. Only upstream atmel_mxt_ts uses table order. Check on a real smelt.
- P2 smelt only, not a regression: before sched the check also ran only on a pass, so asleep it waited for the next wake. Follow-up if smelt gets tested.

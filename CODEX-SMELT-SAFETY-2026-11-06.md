The charging timeout can terminate charging prematurely, and tilt configuration can remain out of sync with the hub. Existing host test binaries pass, but they do not cover these scenarios.

Full review comments:

- [P2] Initialize the full-charge timer on the first full reading — /Users/darrel/Downloads/AsteroidOS/asteroid-embedded-smelt2/src/soc/charge_policy.c:53-59
  If the first valid reading is already 100%, `full_ms` remains zero. Because `time_ms()` reads the hardware counter rather than elapsed firmware runtime, booting after more than 30 minutes in fastboot immediately marks charging complete, even with substantial charging current. Initialize the timer when first observing 100%, including when no earlier below-full sample exists.

- [P2] Cache tilt configuration only after the hub applies it — /Users/darrel/Downloads/AsteroidOS/asteroid-embedded-smelt2/src/app.c:157-161
  On the first awake pass, this caches `false`, but `m4_tilt_on(false)` returns without applying it while the M4 is booting. `started()` subsequently enables gestures, and the cached value prevents disabling them until another sleep/wake cycle. Likewise, an I²C failure when enabling tilt for sleep leaves tilt-to-wake disabled without retries. Keep the desired configuration pending until it is successfully applied.

- [P3] Add the included backlight driver to the test prerequisites — /Users/darrel/Downloads/AsteroidOS/asteroid-embedded-smelt2/tests/backlight_test.c:3-3
  The test now includes the driver implementation, but its Makefile target still depends only on the test source and headers. Editing `backlight_lm3535.c` alone therefore leaves the test executable unchanged, so `make test` runs stale driver code and can miss regressions. Add the included implementation as a prerequisite.
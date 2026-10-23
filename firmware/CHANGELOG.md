# Changelog

All notable changes to the `firmware/` tree are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are dated rather than versioned — no releases have been cut yet,
and the firmware is sim-verified, **not** hardware-validated.

## [Unreleased]

### Fixed

- Fleet sweep #4 2026-10-23: dev-only `pillow` pin bumped
  12.3.0 -> 13.0.0 in `requirements-dev.txt` and
  `firmware/requirements-dev.txt` — pip-audit flagged 20 known
  vulnerabilities in 12.3.0, all fixed in 13.0.0; re-audit is clean
  and the 46-test sim suite passes on the new pin. (Dev/simulator
  dependency only — the pod firmware itself is dependency-free
  MicroPython and is untouched.)
- Bug hunt sweep #3 2026-10-21 (2 new tests in `sim/test_sweep3.py`,
  suite 44 -> 46):
  - `pod/main.py`: `go_to_sleep()` cut the PMU rails (camera, GPS
    antenna, modem) unguarded, so any exception from a rail cut —
    e.g. `camera_power_off()` calling a PMU method the bench has not
    proven exists in XPowersLib — escaped and left the pod awake at
    full draw instead of parked in deep sleep. Rail cuts are now
    best-effort (each failure logged), matching main()'s standing
    rule that PMU failures must never veto sleep. Whether
    `disableALDO` exists in XPowersLib remains a bench question —
    the pod now survives either answer.

- Bug hunt #2 2026-10-19 (4 new tests in `sim/test_sim.py`, suite 40 -> 44):
  - `pod/main.py`: `run_alert_loop()` documents NEVER raises, but its
    setup phase sat outside the crash guard — a `PanicButton`
    construction failure (e.g. a bad hold tunable reaching
    `int(hold_s * 1000)`) escaped `main()` with no bare SMS, and a
    `build_lilygo_pod()` failure in `run_alert()` (UART/Pin
    construction on a sick board) did the same. Both now take the
    shared crash path: best-effort bare SMS when a HAL exists, then
    `pod-error`, so `main()` logs the failure and parks the pod.
  - `pod/esp32_hal.py`: a failure anywhere after `AT+CMMSINIT` in
    `send_mms()` left the modem holding an open MMS session, so the
    alert's own retry started `CMMSINIT` against stale state.
    `send_mms()` now best-effort sends `AT+CMMSTERM` (the same command
    the success path uses) on the way out and re-raises the original
    error for the fallback ladder.

- All-repo sweep 2026-10-19 (7 new tests in `sim/test_sim.py`, suite 33 -> 40):
  - `pod/config.py`: `validate()` itself raised `TypeError` on a
    string/None typo in the comparison-only tunables
    (`BUTTON_HOLD_SECONDS`, `BUTTON_DEBOUNCE_MS`, `GPS_FIX_TIMEOUT_S`,
    `GPS_MODEM_SETTLE_MS`, `MODEM_CMD_TIMEOUT_S`) — and `main()` calls
    it unguarded at boot, so the never-block check became a boot crash.
    All tunables are now type-guarded before comparison (bool and NaN
    flag too); `validate()` reports, never raises.
  - `pod/esp32_hal.py`: `LilyGoModem.get_fix()` accepted any
    `float()`-parseable coordinates — out-of-range or NaN values from a
    marginal fix would have handed the parent a maps link to nowhere.
    Coordinates are now range-checked (-90..90, -180..180; NaN fails
    the check) and a bad parse is just "no fix yet".
  - `pod/esp32_hal.py`: `_Uart.cmd()` sent the AT line with a bare
    `write()` — a partial UART write truncated the command mid-line.
    It (and `write_raw()`) now go through the stall-bounded
    `write_all()`, like the JPEG payloads already did.
  - `pod/button.py`: `hold_progress()` divided by `_hold_ms` and
    raised `ZeroDivisionError` for `hold_s=0` (config error, flagged
    by `validate()`; reachable from the sim GUI). A zero hold now
    reports as fully met instead of crashing the display helper.

- Security audit pass 2 (concurrency / edge cases):
  - `pod/main.py`: an uncaught exception mid-alert (e.g. GPS power-on
    against a dead modem) used to escape `run_alert()` and kill the
    alert silently — on the board the reboot lands in the power-on
    branch and the pod sleeps without ever sending. The wake-cycle loop
    (`run_alert_loop()`, now unit-testable on the PC) catches any
    exception, attempts a best-effort bare SMS first, sets the LED red,
    and returns `pod-error` so the boot log shows the failure.
  - `pod/esp32_hal.py`: `send_sms()`/`send_mms()` validated the dial
    string *after* the modem attach, and `_attach()` sent the APN
    unchecked — a misconfigured pod burned a PWRKEY pulse plus 60 s of
    attach timeouts before failing closed. Number and APN are now
    validated before the modem wakes up.
  - `pod/alert.py`: with the camera dead, the SMS claimed "PHOTOS
    PENDING - MMS failed" when there were no photos at all. It now says
    "NO PHOTOS - camera failed" in that case; "PHOTOS PENDING" is only
    used when photos exist but MMS failed.
  - `sim/mock_hal.py`: outbox filenames used `int(time.time())` alone,
    so same-second sends overwrote each other, and repeated runs grew
    `sim/outbox/` without bound. Filenames now carry a sequence
    counter (`mms_<ts>_<seq>.txt` etc.) and the outbox is pruned to the
    newest 50 files on init.
- `pod/config.py`: new `validate()` fail-fast check (dialable parent
  number, no `REPLACE_WITH_` placeholders left, sane tunables);
  `pod/main.py` prints a WARNING per problem at boot. Warnings only —
  the pod still arms the button; a misconfigured pod stays silent
  rather than dialing something odd.

### Added

- `sim/test_sim.py`: 10 new edge-case tests (28 total) — modem dies
  mid-MMS (OSError retry + SMS fallback), camera dies mid-capture
  (partial photos still send), button mashed during alert phases (no
  crash, no double alert), alert-crash bare-SMS path, config.validate()
  (placeholders / filled / bad number), outbox pruning cap, and
  same-second filename uniqueness.

- Security audit pass 1: AT-command parameter sanitizers in
  `pod/esp32_hal.py` — dial strings restricted to digits and a leading
  `+`, quoted-string params (APN, MMSC URL, proxy) reject quotes and
  control characters, SMS/MMS bodies are stripped of CR/LF/Ctrl-Z, and
  unsafe values fail closed (`ValueError`, alert stays silent) instead of
  injecting extra modem commands. 4 new pytest cases in
  `sim/test_sim.py`; behavior documented under Security in
  `firmware/README.md`.
- `pod/pmu.py`: setup note now says to keep `XPowersLib.py`'s MIT license
  header intact when copying it from LilyGo's repo (the MIT grant
  requires it).
- `sim/test_sim.py`: original 14-test pytest suite covering the golden
  path, every rung of the fallback ladder (no-MMS, no-GPS, camera
  failure), the hold-to-trigger button (tap never fires, hold fires
  exactly once, 2-second hold timing, hold-progress ramp), the HAL
  contract, carrier config placeholders, DRAFT markers on unvalidated AT
  sequences, and wrap-safe timing regression tests (full alert + 90 s
  GPS timeout driven across a simulated `ticks_ms()` wrap).
- `.github/workflows/sim-ci.yml`: CI on push/PR — pytest, `ruff check`,
  `black --check` for `pod/` and `sim/`.
- `firmware/pyproject.toml`: ruff + black config, with documented
  MicroPython-portable style choices (`%`-formatting, catch-all
  degradation in the alert path, REPL asserts in `bringup.py`).
- `firmware/CHANGELOG.md`: this file.
- Issue + PR templates under `.github/`.
- `firmware/README.md`: full technical rewrite — feature rundown, module
  map, fallback ladder, deep-sleep design and the GPIO45 wake-pin risk,
  verification status, business contact, donations.

## 2026-10-11

### Fixed

- Bug hunt 3: wrap-safe timing throughout (`diff_ms` instead of raw
  `now + deadline`), the carrier APN is now actually sent to the modem
  (`AT+CGDCONT`) before attach, GPIO45 wake-pin bench check documented
  as mandatory (`pod/lilygo_board.py`, `BRINGUP.md`).

## 2026-10-10

### Fixed

- Bug hunt 2: power-on REPL window (deep sleep was eating Ctrl+C),
  UART write-all surviving partial writes, AT response drain after match.
- Bug hunt: power sequencing, `ticks_ms()` wrap safety, MMS AT sequence
  fixes.

### Added

- Board-specific firmware for the LILYGO T-SIM7080G-S3: `pod/` MicroPython
  modules (config, HAL contract, button, alert orchestrator, board pins,
  AXP2101 PMU, ESP32-S3 peripherals, bench bring-up, deep-sleep main),
  `sim/` PC proof model (mocks, CLI runner, tkinter demo), `BRINGUP.md`,
  `HARDWARE.md`.

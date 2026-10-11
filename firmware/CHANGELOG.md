# Changelog

All notable changes to the `firmware/` tree are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are dated rather than versioned — no releases have been cut yet,
and the firmware is sim-verified, **not** hardware-validated.

## [Unreleased]

### Added

- `sim/test_sim.py`: 14-test pytest suite covering the golden path, every
  rung of the fallback ladder (no-MMS, no-GPS, camera failure), the
  hold-to-trigger button (tap never fires, hold fires exactly once,
  2-second hold timing, hold-progress ramp), the HAL contract, carrier
  config placeholders, DRAFT markers on unvalidated AT sequences, and
  wrap-safe timing regression tests (full alert + 90 s GPS timeout driven
  across a simulated `ticks_ms()` wrap).
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

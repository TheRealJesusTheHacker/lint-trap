# lint-trap — Hoodie Pod Firmware

MicroPython firmware for a child-safety wearable — the **hoodie pod**.

A kid in trouble holds a hidden sleeve button for 2 seconds; the pod wakes from deep sleep, gets a GPS fix, captures 3 photos, and fires an MMS + SMS with a Google Maps link straight to the parent's phone. No servers, no accounts, no company database — carrier MMS/SMS direct, photo-only (no microphone, by design).

The full technical documentation lives in [`firmware/README.md`](firmware/README.md). This page is the repository overview.

## Status

In development. The firmware is **sim-verified, NOT hardware-validated**: the pytest suite and the PC simulator scenarios prove the logic against mocks, and no releases have been cut yet. The SIM7080G AT command sequences in `firmware/pod/esp32_hal.py` are marked **DRAFT** until proven against the SIMCom AT manual on the bench, and the deep-sleep wake pin (GPIO45) is expected to fail bench validation — see "Known hardware risk" below and `firmware/BRINGUP.md`.

## Who it's for

Parents who want a panic button their kid will actually carry: sewn into a hoodie, one deliberate 2-second hold, and the parent gets location + photos within a couple of minutes. Phase 1 is the dev-board proof on the LILYGO T-SIM7080G-S3; Phase 2 lays out a custom single motherboard from the proven circuit (see `firmware/HARDWARE.md`).

## What it does

- **Hold-to-trigger panic button:** a 2.0-second deliberate hold (50 ms debounce) fires exactly one alert; taps and bumps never fire.
- **GNSS positioning:** up to 90 seconds for a fix; on timeout the alert still goes out, flagged "no GPS fix".
- **Camera capture:** 3 VGA JPEGs per alert from the OV2640 camera; camera failure degrades to a location-only alert.
- **MMS + SMS alerts:** MMS carries the photos and location (one retry), and an SMS with the coordinates and a Google Maps link is always sent. If MMS fails after photos were captured, the SMS says photos are pending; if the camera failed, it says so instead.
- **Fallback ladder:** every phase degrades rather than dying silently — no GPS, failed MMS, dead camera, mid-alert crash, and low battery each have a defined outcome, documented in `firmware/README.md`.
- **Deep-sleep power design:** the pod spends its life in deep sleep with the modem, GPS-antenna, and camera rails cut, waking only on the button. A 2000 mAh LiPo is sized for months, not hours (design target, not yet measured).
- **Hardware abstraction:** the alert logic in `firmware/pod/` only talks to the contracts in `firmware/pod/hal.py`, never to pin numbers — which is why the same code runs on a PC in the simulator and can port unchanged to the Phase 2 custom board.
- **Bench bring-up:** five ordered steps (power, camera, SMS, GPS, golden path) in `firmware/pod/bringup.py` and `firmware/BRINGUP.md`, each proving a subsystem before the next depends on it.

## Repository layout

```
firmware/
  pod/             the real firmware (MicroPython, runs on the board)
    config.py        parent number, carrier APN/MMSC/proxy, all tunables
    hal.py           hardware contracts: Button/Gps/Camera/Modem/Led/Clock
    button.py        debounced hold-to-trigger; fires exactly once per hold
    alert.py         orchestrator: IDLE -> GPS -> CAPTURE -> SEND, with fallbacks
    lilygo_board.py  pin map and power rails for the T-SIM7080G-S3
    pmu.py           AXP2101 power management
    esp32_hal.py     real peripherals and SIM7080G AT sequences (DRAFT)
    bringup.py       bench bring-up steps
    main.py          deep-sleep entry point for the board
  sim/             the PC proof model: the same pod/ code against mocks
    mock_hal.py      mock peripherals; the mock modem writes sim/outbox/
    run.py           CLI scenarios (golden path and fallback cases)
    gui.py           interactive tkinter demo with a hold-to-trigger button
    test_sim.py      pytest suite (40 tests)
  BRINGUP.md       bench procedure: polarity, SIM, antennas, steps, fault table
  HARDWARE.md      product architecture: one motherboard + wired peripherals
  CHANGELOG.md     dated change history
SECURITY.md        security reporting policy
```

## Run it right now (no hardware needed)

```bash
cd firmware
pip install -r requirements-dev.txt   # pillow for the mock camera frames
python3 sim/run.py            # golden path: hold -> GPS -> photos -> MMS+SMS
python3 sim/run.py --no-mms   # MMS fails -> SMS fallback with "PHOTOS PENDING"
python3 sim/run.py --no-gps   # no GPS fix -> alert still goes out, flagged
python3 sim/gui.py            # interactive demo with a hold-to-trigger button
python3 -m pytest sim/ -v     # the full test suite
```

Sent "messages" land in `sim/outbox/` — the MMS text file, 3 JPEGs, and the SMS with the Google Maps link — plus the AT command log showing exactly what the real SIM7080G would see.

## Board setup (real hardware)

1. Flash LilyGo's MicroPython firmware for the T-SIM7080G-S3 (esptool).
2. Copy `firmware/pod/` to the board, plus LilyGo's `lib/XPowersLib.py` next to it — `pod/pmu.py` wraps it.
3. Fill in `firmware/pod/config.py` (parent number, carrier APN/MMSC/proxy). The shipped carrier values are `REPLACE_WITH_…` placeholders; `config.validate()` flags leftovers as boot warnings, and misconfigured values fail closed rather than dialing something odd.
4. Follow `firmware/BRINGUP.md`: `bringup.step1_power()` through `bringup.step5_golden()`, including the wake-pin check **before** installing `main.py`.

## Known hardware risk

ESP32-S3 deep-sleep EXT0/EXT1 wake requires an RTC GPIO (GPIO0–GPIO21 only). The panic button is on **GPIO45, which is not RTC-capable**, so waking from deep sleep on the button is *expected to fail* bench validation: the pod would sleep and never wake on a press. This is a mandatory bench check in `firmware/BRINGUP.md` — if it fails, the button moves to a free RTC pin or the design switches to light sleep. Details are in `firmware/README.md` and `firmware/pod/lilygo_board.py`.

## Tests and lint

```bash
cd firmware
python3 -m pytest sim/ -v   # scenarios, fallback ladder, button behavior,
                            # HAL contract, config validation, ticks-wrap safety
python3 -m ruff check pod/ sim/
python3 -m black --check pod/ sim/
```

Configuration lives in `firmware/pyproject.toml`, including the documented MicroPython-portable style choices (`%-formatting`, and broad `except Exception` in the alert path, which the fallback ladder requires).

## Safety and design constraints

These are baked in, not optional:

- **Photo-only, NO microphone** — the pod has no microphone or audio path, by design.
- **Serverless** — photos and location go carrier-direct to the parent's phone. No company servers, no accounts, no database.
- **Kid-proof triggering** — a 2-second deliberate hold; status progress is exposed so the wearer can see the hold registering.
- **Fail closed on bad configuration** — phone numbers, APN, MMSC URL, and proxy values are sanitized before they reach AT commands; unsafe values stop the alert instead of dialing something odd (see the security section of `firmware/README.md`).

## Security

See [SECURITY.md](SECURITY.md). Report security issues to **Sentinelsafeguard@outlook.com** — do not open a public issue.

## Business contact

**Sentinelsafeguard@outlook.com** — Sentinel Safeguard LLC.

## Donations

If this tool earned its keep, BTC is welcome:

```
bc1qvydns2fmyjzj55wzxq7ta28nxdhcmu9l9m6yg0
```

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE).

Copyright (c) 2026 JesusTheHacker.

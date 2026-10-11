# Hoodie Pod Firmware

[![Sim CI](https://github.com/TheRealJesusTheHacker/lint-trap/actions/workflows/sim-ci.yml/badge.svg)](https://github.com/TheRealJesusTheHacker/lint-trap/actions/workflows/sim-ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)

MicroPython firmware for a child-safety wearable — the **hoodie pod**. A kid
in trouble holds a hidden sleeve button for 2 seconds; the pod wakes from
deep sleep, gets a GPS fix, captures 3 photos, and fires an MMS + SMS with
a Google Maps link straight to the parent's phone. No servers, no accounts,
no company database — carrier MMS/SMS direct, photo-only (no microphone,
by design).

This tree holds **two halves that run the same logic**:

- **`pod/`** — the real firmware. Runs on the LILYGO T-SIM7080G-S3
  (ESP32-S3 + SIM7080G cellular/GNSS + OV2640 camera) for Phase 1 bench
  work, and ports unchanged to the custom single-motherboard design for
  Phase 2, because it only ever talks to the hardware through `hal.py`.
- **`sim/`** — the PC proof model. The *identical* `pod/` alert code runs
  against mocks on your laptop: no hardware needed to prove the
  architecture, exercise every fallback, and read the exact AT commands
  the real modem would see.

> **Verification status — read this first.** The firmware is
> **sim-verified, NOT hardware-validated.** The 28-test pytest suite and
> the three CLI scenarios below prove the logic against mocks. The
> SIM7080G AT sequences in `pod/esp32_hal.py` are marked **DRAFT** until
> proven against the SIMCom AT manual on the bench. The deep-sleep wake
> pin (GPIO45) is **expected to fail** bench validation — see
> [Deep-sleep power design](#deep-sleep-power-design). Nothing here has
> touched a live board yet.

## Who it's for

Parents who want a panic button their kid will actually carry: sewn into
a hoodie, one deliberate 2-second hold, and the parent gets location +
photos within a couple of minutes. Phase 1 is the dev-board proof on the
parts-list LILYGO board; Phase 2 lays out the custom motherboard from the
proven circuit (see `HARDWARE.md`).

## How an alert works

```
button held 2s → wake from deep sleep → GPS fix (≤90s)
  → 3 JPEGs → modem attach → MMS (photos + location)
  → SMS (location + maps link) → back to deep sleep
```

The orchestrator (`pod/alert.py`) is a non-blocking tick state machine:

| State | What happens |
|---|---|
| `IDLE` | LED green. Button debounced; a qualifying hold starts the alert. |
| `ACQUIRING` | GNSS powered on, fix hunt up to 90s. Timeout → send anyway, flagged. |
| `CAPTURING` | 3 JPEGs from the OV2640. Camera failure → location-only alert. |
| `SENDING` | 2s modem settle (GNSS fully off first — the SIM7080G can't do both), then MMS with one retry, then SMS. |
| `DONE` | Result string recorded (`mms=… sms=… photos=…`), LED green/red, back to sleep. |

All time math goes through `hal.Clock.diff_ms()` — MicroPython's
`ticks_ms()` wraps roughly every 12 days, so a raw `now + deadline`
comparison is not wrap-safe. The suite includes regression tests that
drive the whole pipeline across a simulated wrap.

## Feature rundown

- **Hold-to-trigger panic button** (`pod/button.py`) — 2.0 s deliberate
  hold (`BUTTON_HOLD_SECONDS`), 50 ms debounce, active-low on GPIO45
  with pull-up. A tap or bump *never* fires; each hold fires *exactly
  once*; `hold_progress()` returns 0.0–1.0 so the kid-facing UI can show
  the hold is registering (today it drives the demo GUI's progress bar;
  wiring it to a physical status LED is for the custom motherboard).
- **GNSS positioning** (`pod/esp32_hal.py`) — SIM7080G GNSS via
  `AT+CGNSPWR=1` / `AT+CGNSINF` parsing, up to 90 s for a cold fix
  (`GPS_FIX_TIMEOUT_S`), then the alert goes out anyway flagged
  "no GPS fix". Cellular and GNSS are mutually exclusive on this
  modem — the firmware powers GNSS fully off and lets the modem settle
  2 s (`GPS_MODEM_SETTLE_MS`) before attaching.
- **Camera capture** — OV2640, 3 still JPEGs per alert (`PHOTO_COUNT`),
  VGA framesize, init retried 5× with rail settle. On-device JPEG
  quality is the LilyGo driver's default (no per-capture knob —
  `PHOTO_JPEG_QUALITY` is advisory on hardware); step 2 of the bench
  bring-up checks the frame size against what MMS can carry.
- **MMS alert with photos** — SIM7080G `AT+CMMSINIT` → `AT+CMMSCFG`
  (carrier MMSC + proxy) → `AT+CMMSDOWN` TEXT + PICs → `AT+CMMSSEND` →
  `AT+CMMSTERM`. **DRAFT** — validate every line against the SIM7080G
  AT manual on the bench; MMSC/proxy/APN are carrier-specific and ship
  as `REPLACE_WITH_…` placeholders in `pod/config.py`. The APN is sent
  via `AT+CGDCONT` before attach. One retry (`MMS_RETRIES`), then the
  SMS fallback.
- **SMS alert with maps link** — `AT+CMGF=1` / `AT+CMGS`, always sent:
  `HOODIE ALERT from your child. LOCATION: <lat>, <lon>
  https://maps.google.com/?q=<lat>,<lon>`. If MMS failed after photos
  were captured, it appends `PHOTOS PENDING - MMS failed, call your
  child now`; if the camera failed too (no photos at all), it says
  `NO PHOTOS - camera failed` instead of claiming photos are pending.
- **The fallback ladder** — an alert that dies halfway is worse than no
  alert. Every phase degrades (see table below); a low battery
  (< 3400 mV) warns at boot but the alert *still sends*.
- **Deep-sleep power design** (`pod/main.py`) — the pod spends its life
  in deep sleep (microamps design target) and wakes *only* on the
  button (EXT0). Modem, GPS-antenna, and camera rails are cut in
  sleep; a 2000 mAh LiPo is sized for months, not hours (design target,
  not yet measured). Power-on boot gives a 5 s Ctrl+C REPL window so
  deep sleep never eats your bench session, and wake is never armed
  while the button is still held (that would reboot-loop/double-alert).
- **AXP2101 power management** (`pod/pmu.py`) — wraps LilyGo's MIT
  `XPowersLib`: DC3 3000 mV modem rail, BLDO2 3300 mV GPS-antenna rail,
  TS-pin detection disabled (no NTC on board — otherwise the LiPo
  never charges), battery/VBUS/system ADCs, camera ALDO1/2/4 rails
  (1800/2800/3000 mV) driven via raw registers. BLDO1 and DC1 are
  never touched.
- **Hardware abstraction** (`pod/hal.py`) — `Button` / `Gps` / `Camera` /
  `Modem` / `Led` / `Clock` contracts. The alert logic never sees a pin
  number; that's why `sim/` can run the real code on a laptop.
- **Bench bring-up** (`pod/bringup.py`, `BRINGUP.md`) — five ordered
  REPL steps: power → camera → SMS → GPS → golden path, each proving
  a subsystem before the next depends on it, plus a fault table and a
  carrier kill criterion (flaky MMS = switch carriers first).
- **PC proof model** (`sim/`) — mocks for all five peripherals;
  the mock modem writes `sim/outbox/` (`mms_<ts>_<seq>.txt`,
  `sms_<ts>_<seq>.txt`, `photo_<ts>_<seq>_1..3.jpg` — a sequence counter
  keeps same-second sends from overwriting each other) and logs the AT
  commands the real SIM7080G would see. The outbox is pruned to the
  newest 50 files on each run so repeated sim sessions can't fill the
  disk. CLI runner + an interactive tkinter demo
  with a hold-to-trigger mouse button and live progress bar.

### The fallback ladder

| Failure | What happens |
|---|---|
| No GPS fix in 90 s | Sends anyway, flagged "no GPS fix" (no maps link) |
| MMS rejected | Retries once, then SMS-only: "PHOTOS PENDING — call your child now" |
| MMS dies mid-send (modem OSError) | Retry once, then SMS-only fallback — same as rejected |
| Camera fails | Location-only alert still goes out (no MMS, SMS carries the fix); SMS says "NO PHOTOS — camera failed" |
| Camera dies mid-capture | MMS goes out with whatever frames were captured (partial evidence beats none) |
| Alert crashes mid-run (e.g. dead modem on GPS power-on) | Best-effort bare SMS, LED red, result `pod-error` — never dies silently |
| Misconfigured number/APN (empty PARENT_NUMBER, unsafe APN) | The dial-string/APN sanitizers fail closed *before* the modem attach (no wasted radio time): silent pod, LED red, `mms=False sms=False`. A leftover `REPLACE_WITH_` placeholder passes the sanitizer (no quotes/control chars) and fails closed only after a doomed attach — `config.validate()` flags it as a boot WARNING |
| Accidental bump / short press | 2-second hold requirement — taps never fire |
| Button pressed during alert phases | Ignored — the button is only polled in IDLE; each hold fires exactly once |
| Low battery | Warns at boot, but the alert still sends |
| Modem silent | PWRKEY pulse + rail checks (see `BRINGUP.md` fault table) |

## Module map

```
pod/
  config.py        parent number, carrier APN/MMSC/proxy, all tunables
                   (FILL IN the REPLACE_WITH_… placeholders before flashing;
                   main.py prints a WARNING at boot for each problem found
                   by config.validate() — misconfigurations fail closed,
                   never dial something odd)
  hal.py           the contract: Button/Gps/Camera/Modem/Led/Clock interfaces
  button.py        debounced hold-to-trigger; fires exactly once per hold
  alert.py         the orchestrator: IDLE → GPS → CAPTURE → SEND, with fallbacks
  lilygo_board.py  pin map + power rails + hardware limits for the T-SIM7080G-S3
  pmu.py           AXP2101 power-up: modem/GPS/camera rails, TS disable, battery
  esp32_hal.py     real peripherals: GPIO45 button, SIM7080G AT, OV2640, PWRKEY
                   (AT sequences DRAFT — bench-validate before trusting)
  bringup.py       bench bring-up in the buy list's order (step1..step5)
  main.py          copy to board as main.py — deep-sleeps between alerts
sim/
  mock_hal.py      mock button/GPS/camera/modem/LED/clock; modem writes sim/outbox/
  run.py           CLI: golden path + --no-mms / --no-gps fallback scenarios
  gui.py           tkinter demo: hold the big red button with your mouse
  test_sim.py      28-test pytest suite (CI) — scenarios, ladder, button, wraps
BRINGUP.md         bench procedure: polarity, SIM, antennas, steps, fault table
HARDWARE.md        product architecture: one motherboard + wired peripherals
CHANGELOG.md       what changed, by date (no releases cut yet)
```

## Run it right now (no hardware needed)

```bash
cd firmware
pip install -r requirements-dev.txt   # pillow for the mock camera frames
python3 sim/run.py            # golden path: hold → GPS → photos → MMS+SMS
python3 sim/run.py --no-mms   # MMS fails → SMS fallback with "PHOTOS PENDING"
python3 sim/run.py --no-gps   # no GPS fix → alert still goes out, flagged
python3 sim/gui.py            # interactive demo with a hold-to-trigger button
python3 -m pytest sim/ -v     # the full 28-test suite
```

Sent "messages" land in `sim/outbox/` — the MMS text file, 3 JPEGs, the SMS
with the Google Maps link — plus the AT command log showing exactly what
the real SIM7080G would do.

## Board setup (real hardware)

1. Flash LilyGo's MicroPython firmware for the T-SIM7080G-S3 (esptool).
2. Copy `pod/` to the board. Copy LilyGo's MIT `lib/XPowersLib.py`
   (from [LilyGo-T-SIM7080G-MicroPython](https://github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G-MicroPython))
   next to it — `pmu.py` wraps it.
3. Fill in `pod/config.py` (parent number, carrier APN/MMSC/proxy).
4. Follow `BRINGUP.md`: `bringup.step1_power()` … `step5_golden()`,
   including the wake-pin check **before** installing `main.py`.

## Deep-sleep power design

The pod is asleep ~always. `main.py` boots, reads the battery, and — unless
it's a button wake — drops into `machine.deepsleep()` with the modem rail
(DC3), GPS-antenna rail (BLDO2), and camera rails (ALDO1/2/4) all cut. A
press on the panic button fires EXT0, the board reboots into `main.py`,
runs the 2-second hold timer (a short press goes straight back to sleep),
fires the alert, and sleeps again.

> **Known hardware risk — do not skip.** `lilygo_board.py` documents that
> ESP32-S3 deep-sleep EXT0/EXT1 wake requires an RTC GPIO (GPIO0–GPIO21
> only). The panic button is on **GPIO45, which is not RTC-capable**, so
> `esp32.wake_on_ext0(pin=45)` is *expected to fail*: the pod would sleep
> and never wake on the button. This is a **mandatory bench check** in
> `BRINGUP.md` — if it fails, the button moves to a free RTC pin
> (GPIO0–GPIO21, with the camera connected only GPIO45/46 are free, so
> the sleep design may need rethinking) or the design switches to light
> sleep (~mA idle instead of microamps).

## Tests & lint

```bash
cd firmware
python3 -m pytest sim/ -v   # 28 tests: golden path, fallback ladder,
                            # edge cases (modem death, mid-capture camera
                            # failure, button mashing, alert-crash SMS),
                            # button behavior, HAL contract, config
                            # validation, outbox hygiene, ticks-wrap safety
python3 -m ruff check pod/ sim/
python3 -m black --check pod/ sim/
```

Config lives in `pyproject.toml`. Two deliberate style choices are
documented there: `%-formatting` (portable across MicroPython builds)
and broad `except Exception` in the alert path (the fallback ladder
*requires* catch-all degradation — a crashing alert helps no one).

## Standing constraints (baked in, not optional)

- **Photo-only, NO microphone** — audio recording is a wiretapping felony
  in ~13 states. The pod has no mic path, by design.
- **Serverless** — photos and location go carrier-direct to the parent's
  phone. No company servers, no accounts, no database to breach.
- **Kid-proof triggering** — 2-second deliberate hold; the LED shows
  progress so the kid knows it's working.

## Security

See [`../SECURITY.md`](../SECURITY.md). Report security issues to
**Sentinelsafeguard@outlook.com** — do not open a public issue.

### AT command safety (`pod/esp32_hal.py`)

Phone numbers, APN, MMSC URL, and proxy are interpolated into quoted AT
strings, so the modem HAL sanitizes them before sending: dial strings may
only carry digits and a leading `+`; quoted-string params may not contain
quotes or control characters; message bodies are stripped of CR/LF/Ctrl-Z
(the SMS/MMS body goes out as an AT line ended by Ctrl-Z, so an embedded
framing char would split it into extra AT commands). Anything unsafe
raises `ValueError` and the pod **fails closed** — no alert goes out, the
LED goes red, and the result records `mms=False sms=False` instead of
dialing something odd. Fill `config.py` placeholders carefully; a typo in
`PARENT_NUMBER` means a silent pod, not a wrong-number dial.

## Business contact

**Sentinelsafeguard@outlook.com** — Sentinel Safeguard LLC.

## Donations

If this tool earned its keep, BTC is welcome:

```
bc1qvydns2fmyjzj55wzxq7ta28nxdhcmu9l9m6yg0
```

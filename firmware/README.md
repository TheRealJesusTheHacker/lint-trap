# Hoodie Pod — Proof Model

Working proof of the tech inside the child safety hoodie: **hold the panic
button 2 seconds → GPS fix → 3 photos → MMS + SMS with maps link to the
parent's phone.** No servers anywhere — carrier MMS/SMS direct.

## What's here

```
firmware/
  pod/            MicroPython code — runs ON the ESP32-S3 board
    config.py     parent number, carrier APN/MMSC, timings (FILL IN before flashing)
    hal.py        hardware abstraction contract
    button.py     debounced hold-to-trigger (a bump never fires an alert)
    alert.py      the orchestrator: IDLE → GPS → CAPTURE → SEND, with fallbacks
    esp32_hal.py  real peripherals: GPIO button, SIM7080G AT commands, OV2640, RGB LED
    main.py       copy to board as main.py — runs the pod forever
  sim/            PC proof model — the SAME pod/ logic against mocks
    mock_hal.py   mock button/GPS/camera/modem/LED; modem writes sim/outbox/
    run.py        CLI: full golden path + --no-mms / --no-gps fallback tests
    gui.py        tkinter demo: hold the big red button with your mouse
```

## Run it right now (no hardware needed)

```bash
cd firmware
python3 sim/run.py            # golden path
python3 sim/run.py --no-mms   # MMS fails -> SMS fallback with "PHOTOS PENDING"
python3 sim/run.py --no-gps   # no GPS fix -> alert still goes out, flagged
python3 sim/gui.py            # interactive demo with a hold-to-trigger button
```

Sent "messages" land in `sim/outbox/` — the MMS text file, 3 JPEGs, the SMS
with the Google Maps link — plus the AT command log showing exactly what the
real SIM7080G would do.

## The fallback ladder (why this architecture matters)

An alert that dies halfway is worse than no alert. Every phase degrades
gracefully:

| Failure | What happens |
|---|---|
| No GPS fix in 90s | Sends anyway, flagged "no GPS fix" |
| MMS rejected | Retries once, then SMS-only: "PHOTOS PENDING — call your child now" |
| Camera fails | Location-only alert still goes out |
| Accidental bump | 2-second hold requirement — taps never fire |

## From proof model to board

1. Buy list approved → parts land (see `../files/safety-hoodie-phase1-buy-list-2026-10-05.md`).
2. Fill in `pod/config.py` (parent number, carrier APN/MMSC from the $10/mo line).
3. Validate the AT sequences in `pod/esp32_hal.py` against the SIMCom SIM7080G
   AT Command Manual — they're marked DRAFT until proven on hardware.
4. Copy `pod/` to the LILYGO T-SIM7080G-S3 as `main.py`, power it, run the
   bring-up order in the buy list.

## Standing constraints (baked in, not optional)

- **Photo-only, NO microphone** — audio recording is a wiretapping felony in
  ~13 states. The pod has no mic path, by design.
- **Serverless** — photos and location go carrier-direct to the parent's phone.
  No company servers, no accounts, no database to breach.
- **Kid-proof triggering** — 2-second deliberate hold; the LED shows progress
  so the kid knows it's working.

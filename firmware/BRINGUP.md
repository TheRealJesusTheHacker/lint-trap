# Bench bring-up — T-SIM7080G-S3 (parts-list board)

Do these in order. Each step proves a subsystem before the next depends on it.
Kill criterion (from the buy list): if MMS is flaky on carrier #1, switch
carriers before writing any more code.

## Before power

1. **JST polarity**: red/black on the MakerNova 2000mAh LiPo must match the
   board's JST 1.25 footprint. Reversed = dead board. Check twice.
2. **SIM in BEFORE power-on** — the SIM7080G won't detect a hot-swapped SIM.
   $10/mo consumer line (US Mobile Light / RedPocket / T-Mobile Connect).
   IoT data plans can't do MMS — don't bother.
3. Antennas on: LTE + GPS. Mechanical switch beside USB -> **ON**.
4. Flash MicroPython (LilyGo's `LilyGo-T-SIM7080G-MicroPython-firmware.bin`
   via esptool), copy `pod/` to the board, and copy LilyGo's MIT
   `lib/XPowersLib.py` next to it.
5. Fill in `pod/config.py`: `PARENT_NUMBER`, `CARRIER_APN`, `CARRIER_MMSC_URL`,
   `CARRIER_MMS_PROXY`.
6. Do NOT copy `pod/main.py` as the board's root `main.py` yet — do that
   after step5 passes. (The pod firmware deep-sleeps on boot; power-on
   gives a 5s Ctrl+C window for REPL, but bench work is easier without
   main.py in the way.)

## Steps (REPL over USB-C)

```python
from pod import bringup
bringup.step1_power()   # PMU, battery voltage, charging
bringup.step2_camera()  # OV2640 still -> photo_test.jpg on flash
                       # CHECK the file size: on-device JPEG quality is the
                       # driver default (no per-capture knob). If a VGA frame
                       # is too big for MMS, note it — driver fix needed.
bringup.step3_sms()     # Cat-M1 attach, "hoodie pod alive" SMS
bringup.step4_gps()     # GNSS fix — WRITE DOWN the time-to-fix
bringup.step5_golden()  # hold button 2s -> fix -> 3 JPEGs -> MMS + SMS
```

## Then

1. **Wake-pin check (do this before trusting deep sleep):** from the REPL,
   run:
   ```python
   from pod.esp32_hal import sleep_until_button
   from pod import lilygo_board as B
   sleep_until_button(B)   # board sleeps — press the panic button
   ```
   The board must reboot into the REPL within a second of the press. If it
   doesn't wake, GPIO45 is not RTC-wake-capable (expected — see the
   CRITICAL note on PIN_BUTTON in `pod/lilygo_board.py`): stop, move the
   button to a free RTC pin (GPIO0..21), and update PIN_BUTTON. Do NOT
   install main.py until the button wakes the board.
2. Copy `pod/main.py` as the board's `main.py`. The pod boots, arms the
   button, and deep-sleeps between alerts (wakes on button press). The
   modem only powers its radio during an alert — measure the actual deep
   sleep current on the bench to confirm the idle-life estimate.

## If something fails

| Symptom | Check |
|---|---|
| No AT response | PWRKEY pulse (41, low >1s); DC3 rail via PMU; BLDO1 never disabled |
| No network attach | SIM seated before power-on; Cat-M1 coverage; APN |
| No GPS fix | BLDO2 on (GPS antenna power); outdoors/window; up to 90s cold |
| MMS fails | Carrier MMSC path; then SWITCH CARRIERS (kill criterion) |
| Battery never charges | `disableTSPinMeasure()` ran? (no NTC on board) |
| Camera init fails | Reseat the camera FPC; ALDO1/2/4 rails on |

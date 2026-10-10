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
5. Fill in `pod/config.py`: `PARENT_NUMBER`, `CARRIER_APN`.

## Steps (REPL over USB-C)

```python
import bringup
bringup.step1_power()   # PMU, battery voltage, charging
bringup.step2_camera()  # OV2640 still -> photo_test.jpg on flash
bringup.step3_sms()     # Cat-M1 attach, "hoodie pod alive" SMS
bringup.step4_gps()     # GNSS fix — WRITE DOWN the time-to-fix
bringup.step5_golden()  # hold button 2s -> fix -> 3 JPEGs -> MMS + SMS
```

## Then

Copy `pod/main.py` as the board's `main.py`. The pod boots, arms the
button, and deep-sleeps between alerts (wakes on button press). The 2000mAh
LiPo idles for weeks; the modem only powers its radio during an alert.

## If something fails

| Symptom | Check |
|---|---|
| No AT response | PWRKEY pulse (41, low >1s); DC3 rail via PMU; BLDO1 never disabled |
| No network attach | SIM seated before power-on; Cat-M1 coverage; APN |
| No GPS fix | BLDO2 on (GPS antenna power); outdoors/window; up to 90s cold |
| MMS fails | Carrier MMSC path; then SWITCH CARRIERS (kill criterion) |
| Battery never charges | `disableTSPinMeasure()` ran? (no NTC on board) |
| Camera init fails | Reseat the camera FPC; ALDO1/2/4 rails on |

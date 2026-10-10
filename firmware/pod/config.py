# Hoodie Pod configuration — shared by the ESP32-S3 firmware and the PC simulator.
# MicroPython-compatible. Board pins live in lilygo_board.py (the parts-list
# board); behavior tunables live here.

# ---- parent / carrier (FILL THESE IN before flashing) ----
PARENT_NUMBER = "+18165558418"   # parent's mobile — receives the MMS + SMS
# NOTE: LilyGo's ATDebug example drives MMS via the carrier MMSC with
# AT+CMMSINIT/AT+CMMSDOWN/AT+CMMSSEND. The exact MMSC/proxy AT set is
# carrier-specific — fill from the $10/mo line's carrier and validate on
# the bench (buy list kill criterion: flaky MMS = switch carriers first).
CARRIER_APN = "REPLACE_WITH_CARRIER_APN"

# ---- behavior ----
BUTTON_HOLD_SECONDS = 2.0     # hold-to-trigger; kills accidental presses
BUTTON_DEBOUNCE_MS = 50
PHOTO_COUNT = 3               # JPEGs per alert
PHOTO_JPEG_QUALITY = 70       # small enough for MMS, clear enough to ID a face
GPS_FIX_TIMEOUT_S = 90        # then send anyway (see alert.py fallback)
GPS_MODEM_SETTLE_MS = 2000    # pause between GNSS-off and cellular-on
                              # (SIM7080G can't do both at once)
MODEM_CMD_TIMEOUT_S = 10
MMS_RETRIES = 1               # then fall back to SMS-only with "photos pending"

# ---- power ----
DEEP_SLEEP_BETWEEN_ALERTS = True  # wake on button press only; sips the 2000mAh LiPo

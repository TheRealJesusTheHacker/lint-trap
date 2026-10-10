# Hoodie Pod configuration — shared by the ESP32-S3 firmware and the PC simulator.
# MicroPython-compatible (no f-strings in hot paths, no stdlib-only modules).

# ---- parent / carrier (FILL THESE IN before flashing) ----
PARENT_NUMBER = "+18165558418"   # parent's mobile — receives the MMS + SMS
CARRIER_APN = "REPLACE_WITH_CARRIER_APN"
CARRIER_MMSC_URL = "REPLACE_WITH_CARRIER_MMSC_URL"   # e.g. http://mmsc.t-mobile.com
CARRIER_MMS_PROXY = "REPLACE_WITH_PROXY_IP"
CARRIER_MMS_PROXY_PORT = 8080

# ---- behavior ----
BUTTON_HOLD_SECONDS = 2.0     # hold-to-trigger; kills accidental presses
BUTTON_DEBOUNCE_MS = 50
PHOTO_COUNT = 3               # JPEGs per alert
PHOTO_JPEG_QUALITY = 70       # small enough for MMS, clear enough to ID a face
GPS_FIX_TIMEOUT_S = 90        # then send anyway (see alert.py fallback)
MODEM_CMD_TIMEOUT_S = 10
MMS_RETRIES = 1               # then fall back to SMS-only with "photos pending"

# ---- ESP32-S3 wiring (LILYGO T-SIM7080G-S3) ----
# Double-check against the board schematic before flashing.
PIN_BUTTON = 0        # panic button, active-low, internal pull-up
PIN_LED_R = 1
PIN_LED_G = 2
PIN_LED_B = 3
UART_MODEM_ID = 1
UART_MODEM_BAUD = 115200
# UART pins board-specific — set from schematic:
PIN_UART_TX = -1
PIN_UART_RX = -1

# Board support: LILYGO T-SIM7080G-S3 (the Phase 1 parts-list board).
#
# Pin map from LilyGo's "LILYGO_ESP32S3_CAM_SIM7080G" config, published in
# their MIT-licensed MicroPython repo (lib/utilities.py) and README pin
# table. Treat as "from the docs" — validate on the bench before trusting.
#
# HARDWARE LIMITS (LilyGo docs — these shape the firmware):
#  * Cellular and GNSS can NEVER run at the same time. alert.py already
#    sequences them: GPS fix -> GPS fully off -> modem attach -> send.
#  * BLDO1 must NEVER be disabled — it carries ESP32<->modem comms.
#  * TS pin detection must be disabled or the LiPo will never charge.
#  * SIM must be inserted BEFORE power-on. Mechanical switch -> ON, then
#    hold the board's PWR button ~2s when on battery.
#  * GPIO35/36/37 are unusable (octal PSRAM). With the camera connected,
#    the ONLY free GPIOs are 45 and 46.

# --- SIM7080G modem ---
MODEM_UART_ID = 1
MODEM_BAUD = 115200
MODEM_TX_PIN = 5    # ESP32 TX -> modem RXD
MODEM_RX_PIN = 4    # ESP32 RX <- modem TXD
MODEM_PWR_PIN = 41  # PWRKEY, active-low: pull LOW >1s to toggle modem power
MODEM_DTR_PIN = 42
MODEM_RI_PIN = 3

# --- OV2640 camera (board's camera connector) ---
# NOTE: on LilyGo's MicroPython build these pins are baked into the
# firmware — camera.init() takes no pin arguments. The constants below
# document the wiring and are used by the future custom motherboard.
CAM_PWDN = -1       # not routed
CAM_RESET = 18
CAM_XCLK = 8
CAM_SIOD = 2        # SDA
CAM_SIOC = 1        # SCL
CAM_VSYNC = 16
CAM_HREF = 17
CAM_PCLK = 12
CAM_Y2 = 14         # Y2..Y9 in order
CAM_Y3 = 47
CAM_Y4 = 48
CAM_Y5 = 21
CAM_Y6 = 13
CAM_Y7 = 11
CAM_Y8 = 10
CAM_Y9 = 9

# --- AXP2101 PMU ---
PMU_SDA_PIN = 15
PMU_SCL_PIN = 7
PMU_IRQ_PIN = 6

# --- panic button: GPIO45 (see note above — the only safe free pin) ---
# CRITICAL BENCH CHECK: ESP32-S3 deep-sleep EXT0/EXT1 wake requires an RTC
# GPIO — that's GPIO0..GPIO21 ONLY (TRM section 10.4.4; anything else gets
# ESP_ERR_INVALID_ARG). GPIO45 is NOT RTC-capable, so
# esp32.wake_on_ext0(pin=45) is expected to FAIL: the pod would sleep and
# never wake on the button. Probe this FIRST on the bench — if it fails,
# the button must move to a free RTC pin (0..21) or the sleep design must
# change (light sleep wakes on any GPIO but idles at ~mA, not microamps).
PIN_BUTTON = 45

# --- power rails (mV) ---
RAIL_MODEM_DC3_MV = 3000   # SIM7080G main power
RAIL_GPS_BLDO2_MV = 3300   # GPS antenna — must be on for any fix
RAIL_CAM_ALDO1_MV = 1800   # camera DVDD
RAIL_CAM_ALDO2_MV = 2800   # camera DVDD
RAIL_CAM_ALDO4_MV = 3000   # camera AVDD

# --- battery ---
# Buy list: MakerNova 2000mAh LiPo, JST 1.25. VERIFY POLARITY ON ARRIVAL —
# reversed JST = dead board. The board also has an 18650 holder; either works.
BATT_LOW_MV = 3400   # warn below this, but ALWAYS still send the alert
BATT_EMPTY_MV = 3200

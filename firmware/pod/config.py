# Hoodie Pod configuration — shared by the ESP32-S3 firmware and the PC simulator.
# MicroPython-compatible. Board pins live in lilygo_board.py (the parts-list
# board); behavior tunables live here.

# ---- parent / carrier (FILL THESE IN before flashing) ----
PARENT_NUMBER = "+18165558418"  # parent's mobile — receives the MMS + SMS
# DRAFT: the MMSC/proxy AT set is carrier-specific — fill from the $10/mo
# line's carrier and validate every line against the SIM7080G AT manual on
# the bench (buy list kill criterion: flaky MMS = switch carriers first).
CARRIER_APN = "REPLACE_WITH_CARRIER_APN"
CARRIER_MMSC_URL = "REPLACE_WITH_CARRIER_MMSC_URL"
CARRIER_MMS_PROXY = "REPLACE_WITH_PROXY_IP"
CARRIER_MMS_PROXY_PORT = 8080

# ---- behavior ----
BUTTON_HOLD_SECONDS = 2.0  # hold-to-trigger; kills accidental presses
BUTTON_DEBOUNCE_MS = 50
PHOTO_COUNT = 3  # JPEGs per alert
PHOTO_JPEG_QUALITY = 70  # small enough for MMS, clear enough to ID a face
GPS_FIX_TIMEOUT_S = 90  # then send anyway (see alert.py fallback)
GPS_MODEM_SETTLE_MS = 2000  # pause between GNSS-off and cellular-on
# (SIM7080G can't do both at once)
MODEM_CMD_TIMEOUT_S = 10
MMS_RETRIES = 1  # then fall back to SMS-only with "photos pending"


def _dial_ok(number):
    """Same dial-string rule the modem HAL enforces (see esp32_hal):
    digits plus an optional leading '+'."""
    s = str(number).strip()
    body = s[1:] if s[:1] == "+" else s
    return bool(body) and all("0" <= c <= "9" for c in body)


def validate():
    """Fail-fast config check. Returns a list of problem strings
    (empty = good to flash).

    Called at boot by main.py: problems print as WARNINGs but never block
    the pod — a misconfigured pod still arms the button, it just can't
    send. Catching a typo'd PARENT_NUMBER or a leftover REPLACE_WITH_
    placeholder at boot beats burning minutes of modem time on a doomed
    attach at 2am."""
    problems = []
    if not _dial_ok(PARENT_NUMBER):
        problems.append("PARENT_NUMBER %r is not a dialable number" % (PARENT_NUMBER,))
    for name, value in (
        ("CARRIER_APN", CARRIER_APN),
        ("CARRIER_MMSC_URL", CARRIER_MMSC_URL),
        ("CARRIER_MMS_PROXY", CARRIER_MMS_PROXY),
    ):
        if str(value).startswith("REPLACE_WITH"):
            problems.append("%s still has the REPLACE_WITH_ placeholder" % name)
    if not isinstance(CARRIER_MMS_PROXY_PORT, int) or not (
        1 <= CARRIER_MMS_PROXY_PORT <= 65535
    ):
        problems.append(
            "CARRIER_MMS_PROXY_PORT %r is not a valid port" % (CARRIER_MMS_PROXY_PORT,)
        )
    if BUTTON_HOLD_SECONDS <= 0:
        problems.append("BUTTON_HOLD_SECONDS must be > 0")
    if BUTTON_DEBOUNCE_MS < 0:
        problems.append("BUTTON_DEBOUNCE_MS must be >= 0")
    if not isinstance(PHOTO_COUNT, int) or not (1 <= PHOTO_COUNT <= 10):
        problems.append("PHOTO_COUNT must be an int 1-10 (got %r)" % (PHOTO_COUNT,))
    if not isinstance(PHOTO_JPEG_QUALITY, int) or not (1 <= PHOTO_JPEG_QUALITY <= 100):
        problems.append(
            "PHOTO_JPEG_QUALITY must be an int 1-100 (got %r)" % (PHOTO_JPEG_QUALITY,)
        )
    if GPS_FIX_TIMEOUT_S <= 0:
        problems.append("GPS_FIX_TIMEOUT_S must be > 0")
    if GPS_MODEM_SETTLE_MS < 0:
        problems.append("GPS_MODEM_SETTLE_MS must be >= 0")
    if MODEM_CMD_TIMEOUT_S <= 0:
        problems.append("MODEM_CMD_TIMEOUT_S must be > 0")
    if not isinstance(MMS_RETRIES, int) or MMS_RETRIES < 0:
        problems.append("MMS_RETRIES must be an int >= 0 (got %r)" % (MMS_RETRIES,))
    return problems

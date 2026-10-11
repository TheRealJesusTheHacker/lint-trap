# Alert orchestrator — the heart of the pod.
# Golden path: HOLD button 2s -> GPS fix -> 3 photos -> MMS -> SMS w/ maps link.
# Every step has a fallback. An alert that dies halfway is worse than no alert.
#
# Fallback ladder:
#   no GPS fix in time  -> send anyway, flag "NO GPS FIX"
#   MMS fails           -> retry once, then SMS-only with "PHOTOS PENDING"
#   camera fails        -> send location-only alert (a location beats nothing)

IDLE = 0
ACQUIRING = 1   # GPS fix
CAPTURING = 2   # photos
SENDING = 3     # MMS then SMS
DONE = 4

class AlertPod:
    def __init__(self, hal, cfg, clock):
        self._hal = hal
        self._cfg = cfg
        self._clock = clock
        self._button = None  # set via attach_button
        self.state = IDLE
        self._t0 = 0
        self._lat = None
        self._lon = None
        self._photos = []
        self._settle_t0 = 0
        self.last_result = ""

    def attach_button(self, button):
        self._button = button

    # -- main loop: call tick() as fast as the platform allows --
    def tick(self):
        now = self._clock.now_ms()
        if self.state == IDLE:
            self._hal.led.set("green")
            if self._button.update(now):
                self._begin_alert(now)
        elif self.state == ACQUIRING:
            self._tick_acquiring(now)
        elif self.state == CAPTURING:
            self._tick_capturing(now)
        elif self.state == SENDING:
            self._tick_sending(now)
        elif self.state == DONE:
            self._hal.led.set("blue")
            self.state = IDLE

    # -- phases --
    def _begin_alert(self, now):
        self.state = ACQUIRING
        self._t0 = now
        self._lat = self._lon = None
        self._photos = []
        self._hal.led.set("red")
        self._hal.gps.power_on()

    def _tick_acquiring(self, now):
        if self._clock.diff_ms(now, self._t0) > self._cfg.GPS_FIX_TIMEOUT_S * 1000:
            self._end_acquiring(now)  # give up on GPS, keep moving
            return
        fix = self._hal.gps.get_fix(timeout_s=5)
        if fix:
            self._lat, self._lon = fix
            self._end_acquiring(now)

    def _end_acquiring(self, now):
        self._hal.gps.power_off()
        # SIM7080G can't run GNSS and cellular together — let the
        # modem settle before it attaches. Stored as a start time and
        # compared with diff_ms: ticks_ms() wraps every ~12 days, so a
        # raw now+settle deadline is not wrap-safe (hal.py contract).
        self._settle_t0 = now
        self.state = CAPTURING

    def _tick_capturing(self, now):
        for _ in range(self._cfg.PHOTO_COUNT):
            try:
                self._photos.append(
                    self._hal.camera.capture_jpeg(self._cfg.PHOTO_JPEG_QUALITY))
            except Exception:
                break  # location-only alert still goes out
        self.state = SENDING

    def _tick_sending(self, now):
        if self._clock.diff_ms(now, self._settle_t0) \
                < self._cfg.GPS_MODEM_SETTLE_MS:
            return  # modem still settling after GNSS shutdown
        loc = self._location_text()
        maps = self._maps_link()
        sms_body = "HOODIE ALERT from your child. " + loc + " " + maps

        mms_ok = False
        if self._photos:
            for attempt in range(self._cfg.MMS_RETRIES + 1):
                try:
                    mms_ok = self._hal.modem.send_mms(
                        self._cfg.PARENT_NUMBER,
                        "HOODIE ALERT",
                        loc + " " + maps,
                        self._photos)
                    if mms_ok:
                        break
                except Exception:
                    mms_ok = False
        if not mms_ok:
            sms_body += " (PHOTOS PENDING - MMS failed, call your child now)"

        sms_ok = False
        try:
            sms_ok = self._hal.modem.send_sms(self._cfg.PARENT_NUMBER, sms_body)
        except Exception:
            sms_ok = False

        self.last_result = "mms=" + str(mms_ok) + " sms=" + str(sms_ok) \
            + " photos=" + str(len(self._photos))
        self._hal.led.set("green" if (mms_ok or sms_ok) else "red")
        self.state = DONE

    # -- helpers --
    def _location_text(self):
        if self._lat is None:
            return "LOCATION: no GPS fix."
        return "LOCATION: %.6f, %.6f" % (self._lat, self._lon)

    def _maps_link(self):
        if self._lat is None:
            return ""
        return "https://maps.google.com/?q=%.6f,%.6f" % (self._lat, self._lon)

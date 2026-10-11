# PC mocks of every peripheral. The SAME pod/alert.py logic runs here —
# this is the proof model: if the golden path works against mocks,
# the architecture is sound before a single part is soldered.
#
# Mock modem "sends" into sim/outbox/: mms_<ts>.txt + sms_<ts>.txt,
# and logs the exact AT commands the real SIM7080G would see.

import contextlib
import io
import os
import time

OUTBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox")

# Cap the sim outbox: repeated runs / long demo sessions must not grow it
# without bound. MockModem prunes to the newest OUTBOX_MAX_FILES on init.
OUTBOX_MAX_FILES = 50

# A test location (Liberty, MO). Override with HOODIE_TEST_LAT/LON env vars.
TEST_LAT = float(os.environ.get("HOODIE_TEST_LAT", "39.2462"))
TEST_LON = float(os.environ.get("HOODIE_TEST_LON", "-94.4102"))


class MockButton:
    def __init__(self):
        self.held = False

    def is_pressed(self):
        return self.held


class MockGps:
    def __init__(self, fix_delay_s=4, fail=False):
        self.fix_delay_s = fix_delay_s
        self.fail = fail
        self._t0 = None

    def power_on(self):
        self._t0 = time.monotonic()

    def power_off(self):
        pass

    def get_fix(self, timeout_s):
        if self.fail:
            time.sleep(min(timeout_s, 1))
            return None
        if time.monotonic() - self._t0 >= self.fix_delay_s:
            return (TEST_LAT, TEST_LON)
        time.sleep(0.5)
        return None


class MockCamera:
    def __init__(self):
        self.n = 0

    def capture_jpeg(self, quality):
        # Stand-in for the OV2640: timestamped test frame via PIL.
        from PIL import Image, ImageDraw

        self.n += 1
        img = Image.new("RGB", (640, 480), (20 + self.n * 30, 30, 60))
        d = ImageDraw.Draw(img)
        d.text((20, 20), "HOODIE POD CAM %d" % self.n, fill=(255, 255, 255))
        d.text((20, 50), time.strftime("%Y-%m-%d %H:%M:%S"), fill=(255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


class MockModem:
    # Process-wide send counter: filenames stay unique even when several
    # sends land in the same wall-clock second (int(time.time()) alone
    # would collide and silently overwrite the earlier message).
    _seq = 0

    def __init__(self, fail_mms=False):
        self.fail_mms = fail_mms
        os.makedirs(OUTBOX, exist_ok=True)
        self._prune_outbox()
        self.at_log = []

    @classmethod
    def _stamp(cls):
        cls._seq += 1
        return "%d_%03d" % (int(time.time()), cls._seq % 1000)

    @staticmethod
    def _prune_outbox():
        """Keep the newest OUTBOX_MAX_FILES so long sim sessions and
        repeated runs can't fill the disk."""
        try:
            files = [
                os.path.join(OUTBOX, f)
                for f in os.listdir(OUTBOX)
                if os.path.isfile(os.path.join(OUTBOX, f))
            ]
        except OSError:
            return
        if len(files) <= OUTBOX_MAX_FILES:
            return
        files.sort(key=lambda p: os.path.getmtime(p))
        for p in files[: len(files) - OUTBOX_MAX_FILES]:
            with contextlib.suppress(OSError):
                os.remove(p)

    def _log(self, s):
        self.at_log.append(s)

    def send_sms(self, number, text):
        self._log("AT+CMGF=1 -> OK")
        self._log('AT+CMGS="%s" -> > ' % number)
        self._log("<message>\\x1A -> +CMGS: 1 OK")
        ts = self._stamp()
        with open(os.path.join(OUTBOX, "sms_%s.txt" % ts), "w") as f:
            f.write("TO: %s\n\n%s\n" % (number, text))
        return True

    def send_mms(self, number, subject, text, images):
        if self.fail_mms:
            self._log("AT+CMMSINIT -> OK")
            self._log("AT+CMMSSEND -> ERROR (simulated carrier rejection)")
            return False
        self._log("AT+CMMSINIT -> OK")
        self._log("AT+CMMSDOWN PIC x%d -> CONNECT ... OK" % len(images))
        self._log('AT+CMMSSEND="%s" -> +CMMSSEND: OK' % number)
        ts = self._stamp()
        with open(os.path.join(OUTBOX, "mms_%s.txt" % ts), "w") as f:
            f.write(
                "TO: %s\nSUBJECT: %s\n\n%s\n\n[ATTACHED: %d JPEG photos]\n"
                % (number, subject, text, len(images))
            )
            for i, img in enumerate(images):
                p = os.path.join(OUTBOX, "photo_%s_%d.jpg" % (ts, i + 1))
                with open(p, "wb") as pf:
                    pf.write(img)
                f.write("  - %s (%d bytes)\n" % (os.path.basename(p), len(img)))
        return True


class MockLed:
    def __init__(self):
        self.color = "off"

    def set(self, color):
        self.color = color


class MockClock:
    def now_ms(self):
        return int(time.monotonic() * 1000)

    def diff_ms(self, newer, older):
        return newer - older


def build_mock_hal(fail_mms=False, gps_fail=False, gps_delay_s=4):
    from pod import hal as _hal

    btn, gps = MockButton(), MockGps(fix_delay_s=gps_delay_s, fail=gps_fail)
    return (
        _hal.PodHAL(btn, gps, MockCamera(), MockModem(fail_mms=fail_mms), MockLed()),
        MockClock(),
        btn,
    )

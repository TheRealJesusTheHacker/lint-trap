# Real ESP32-S3 peripherals for the LILYGO T-SIM7080G-S3.
# Built against the parts list: SIM7080G modem, OV2640 camera,
# MakerNova 2000mAh LiPo, 12mm metal panic button on GPIO45.
#
# DRAFT until bench-validated: AT sequences and the PWRKEY pulse come from
# LilyGo's docs/examples, not a live board.

try:
    import time

    import esp32
    import machine

    _ON_DEVICE = True
except ImportError:
    _ON_DEVICE = False

from . import config as _cfg
from . import hal as _hal

# -- AT command safety --
# Config values (parent number, APN, MMSC URL, proxy) are interpolated
# into quoted AT strings. A quote or control character in any of them
# would break out of the string and inject extra modem commands, so
# these helpers fail closed (ValueError) instead of sending. Legitimate
# values pass through byte-for-byte untouched; a misconfigured pod stays
# silent (LED red, alert DONE) rather than dialing something odd.


def _at_number(number):
    """Phone numbers may only carry digits and a leading '+'."""
    s = str(number).strip()
    body = s[1:] if s[:1] == "+" else s
    if not body or any(c < "0" or c > "9" for c in body):
        raise ValueError("refusing unsafe dial string in AT command")
    return s


def _at_param(value, name):
    """Quoted-string AT params may not contain quotes or control chars."""
    s = str(value)
    for c in s:
        if c == '"' or ord(c) < 32:
            raise ValueError("refusing unsafe %s in AT command" % name)
    return s


def _at_text(text):
    """Strip AT-framing chars from a message body.

    The SMS/MMS body goes out as an AT line ended by Ctrl-Z; an embedded
    CR/LF/Ctrl-Z would split it into extra AT commands. Legit bodies
    (fixed alert text + float coordinates) never contain these.
    """
    out = []
    for c in str(text):
        if c != "\r" and c != "\n" and c != "\x1a":
            out.append(c)
    return "".join(out)


class _Uart:
    def __init__(self, board):
        self._u = machine.UART(
            board.MODEM_UART_ID,
            baudrate=board.MODEM_BAUD,
            tx=machine.Pin(board.MODEM_TX_PIN),
            rx=machine.Pin(board.MODEM_RX_PIN),
            timeout=1000,
        )

    def cmd(self, at, expect="OK", timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _cfg.MODEM_CMD_TIMEOUT_S * 1000
        self._u.write((at + "\r\n").encode())
        # Wrap-safe deadline: ticks_ms() wraps every ~12 days, so compare
        # elapsed time with ticks_diff instead of adding to the clock.
        start = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            n = self._u.any()
            if n:
                buf += self._u.read(n)
                if expect.encode() in buf:
                    # Drain: the matched line (e.g. +CGNSINF coordinates)
                    # may still be arriving after the match.
                    for _ in range(6):
                        time.sleep_ms(50)
                        m = self._u.any()
                        if not m:
                            break
                        buf += self._u.read(m)
                    return buf.decode(errors="ignore")
            time.sleep_ms(50)
        raise OSError("AT timeout: " + at)

    def write_raw(self, data):
        """Write bytes outside AT framing (e.g. after a CONNECT prompt)."""
        self._u.write(data)

    def write_all(self, data):
        """Write every byte, surviving partial UART writes."""
        off = 0
        while off < len(data):
            chunk = data[off : off + 1024]
            n = self._u.write(chunk)
            if n is None:
                off += len(chunk)  # port took it all
            elif n == 0:
                time.sleep_ms(10)
            else:
                off += n


class GpioButton(_hal.ButtonHAL):
    def __init__(self, pin_num):
        self._pin = machine.Pin(pin_num, machine.Pin.IN, machine.Pin.PULL_UP)

    def is_pressed(self):
        return self._pin.value() == 0  # active-low, wired to GND

    @property
    def pin(self):
        return self._pin


class LilyGoModem(_hal.ModemHAL, _hal.GpsHAL):
    """SIM7080G: one object because cellular and GNSS share the modem —
    and LilyGo's docs are explicit they can NEVER run simultaneously."""

    def __init__(self, board, pmu):
        self._board = board
        self._pmu = pmu
        self._uart = _Uart(board)
        self._pwrkey = machine.Pin(board.MODEM_PWR_PIN, machine.Pin.OUT)
        self._pwrkey.value(1)
        self._attached = False
        self._gnss_on = False

    # -- power --
    def _pulse_pwrkey(self):
        # PWRKEY active-low, >1s per SIMCom manual
        self._pwrkey.value(0)
        time.sleep_ms(1200)
        self._pwrkey.value(1)
        time.sleep_ms(5000)  # modem boot time

    def _ensure_alive(self):
        for _ in range(3):
            try:
                self._uart.cmd("AT", timeout_ms=2000)
                return
            except OSError:
                pass
        self._pulse_pwrkey()
        self._uart.cmd("AT", timeout_ms=10000)  # raises if truly dead

    # -- cellular --
    def _attach(self):
        if self._attached:
            return
        self._ensure_alive()
        if self._gnss_on:
            self.power_off()  # hardware rule: GNSS fully off before cellular
        u = self._uart
        # The APN was configured in config.py but never sent — without it
        # the PDP context attach below uses a wrong/default APN.
        u.cmd('AT+CGDCONT=1,"IP","%s"' % _at_param(_cfg.CARRIER_APN, "carrier APN"))
        u.cmd("AT+CGATT=1", timeout_ms=30000)
        u.cmd("AT+CNACT=0,1", timeout_ms=30000)
        self._attached = True

    def send_sms(self, number, text):
        self._attach()
        number = _at_number(number)
        u = self._uart
        u.cmd("AT+CMGF=1")
        u.cmd('AT+CMGS="%s"' % number, expect=">")
        u.cmd(_at_text(text) + chr(26), expect="+CMGS:", timeout_ms=30000)
        return True

    def send_mms(self, number, subject, text, images):
        # DRAFT — validate every line against the SIM7080G AT manual on
        # the bench. The init -> down -> send -> term SHAPE matches SIMCom's
        # documented flow; the MMSC/proxy addressing is carrier-specific.
        self._attach()
        number = _at_number(number)
        u, c = self._uart, _cfg
        u.cmd("AT+CMMSINIT")
        u.cmd('AT+CMMSCFG="mmsc","%s"' % _at_param(c.CARRIER_MMSC_URL, "MMSC URL"))
        u.cmd(
            'AT+CMMSCFG="proxy","%s",%d'
            % (_at_param(c.CARRIER_MMS_PROXY, "MMS proxy"), c.CARRIER_MMS_PROXY_PORT)
        )
        tb = _at_text(text).encode()
        u.cmd('AT+CMMSDOWN="TEXT",%d,10000' % len(tb), expect="CONNECT")
        u.write_all(tb)
        for img in images:
            u.cmd('AT+CMMSDOWN="PIC",%d,20000' % len(img), expect="CONNECT")
            u.write_all(img)
        u.cmd('AT+CMMSSEND="%s"' % number, expect="+CMMSSEND:", timeout_ms=60000)
        u.cmd("AT+CMMSTERM")
        return True

    # -- GNSS (mutually exclusive with cellular — see _attach) --
    def power_on(self):
        self._ensure_alive()
        self._uart.cmd("AT+CGNSPWR=1")
        self._gnss_on = True

    def power_off(self):
        try:
            self._uart.cmd("AT+CGNSPWR=0", timeout_ms=5000)
        except OSError:
            pass
        self._gnss_on = False
        self._attached = False  # re-attach after GNSS; clean state

    def get_fix(self, timeout_s):
        try:
            resp = self._uart.cmd(
                "AT+CGNSINF", expect="+CGNSINF:", timeout_ms=int(timeout_s * 1000)
            )
        except OSError:
            return None
        for line in resp.splitlines():
            if "+CGNSINF:" in line:
                f = line.split(":")[1].strip().split(",")
                if len(f) > 4 and f[1] == "1":
                    try:
                        return (float(f[3]), float(f[4]))
                    except ValueError:
                        return None
        return None


class Ov2640(_hal.CameraHAL):
    def __init__(self, pmu):
        self._pmu = pmu
        self._ready = False

    def _init(self):
        if self._ready:
            return
        import camera

        self._pmu.camera_power_on()
        time.sleep_ms(500)  # rails settle
        for _ in range(5):
            try:
                camera.deinit()
            except Exception:
                pass
            if camera.init(0, format=camera.JPEG, framesize=camera.FRAME_VGA):
                self._ready = True
                return
            time.sleep_ms(2000)
        raise RuntimeError("OV2640 init failed — check camera connector")

    def capture_jpeg(self, quality):
        # NOTE: quality is advisory on-device — LilyGo's MicroPython
        # camera driver uses its own default JPEG quality; there is no
        # per-capture quality knob. Check photo_test.jpg size at
        # bringup step2: if frames are too big for MMS, the fix is in
        # the driver/firmware, not here.
        self._init()
        import camera

        return camera.capture()


class PrintLed(_hal.LedHAL):
    """Dev-board stand-in: the T-SIM7080G-S3 has no user RGB LED
    (only modem-status red + PMU charge blue). States go to serial;
    the custom motherboard gets a real status LED on this interface."""

    def __init__(self):
        self.color = "off"

    def set(self, color):
        if color != self.color:
            print("[LED] %s" % color)
            self.color = color


class DeviceClock(_hal.Clock):
    def now_ms(self):
        return time.ticks_ms()

    def diff_ms(self, newer, older):
        return time.ticks_diff(newer, older)


def build_lilygo_pod(board, pmu):
    """Wire the real T-SIM7080G-S3 peripherals. Returns (PodHAL, clock, button_pin)."""
    btn = GpioButton(board.PIN_BUTTON)
    modem = LilyGoModem(board, pmu)
    return (
        _hal.PodHAL(btn, modem, Ov2640(pmu), modem, PrintLed()),
        DeviceClock(),
        btn.pin,
    )


def sleep_until_button(board):
    """Deep sleep; wake when the panic button is pressed (active-low).
    On wake the board reboots into main.py and the hold-timer decides."""
    pin = machine.Pin(board.PIN_BUTTON, machine.Pin.IN, machine.Pin.PULL_UP)
    esp32.wake_on_ext0(pin=pin, level=esp32.WAKE_LOW)
    machine.deepsleep()

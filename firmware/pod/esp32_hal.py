# Real ESP32-S3 peripherals for the LILYGO T-SIM7080G-S3.
# Built against the parts list: SIM7080G modem, OV2640 camera,
# MakerNova 2000mAh LiPo, 12mm metal panic button on GPIO45.
#
# DRAFT until bench-validated: AT sequences and the PWRKEY pulse come from
# LilyGo's docs/examples, not a live board.

try:
    import machine
    import time
    import esp32
    _ON_DEVICE = True
except ImportError:
    _ON_DEVICE = False

from . import hal as _hal


class _Uart:
    def __init__(self, board):
        self._u = machine.UART(board.MODEM_UART_ID,
                               baudrate=board.MODEM_BAUD,
                               tx=machine.Pin(board.MODEM_TX_PIN),
                               rx=machine.Pin(board.MODEM_RX_PIN),
                               timeout=1000)

    def cmd(self, at, expect="OK", timeout_ms=10000):
        self._u.write((at + "\r\n").encode())
        deadline = time.ticks_ms() + timeout_ms
        buf = b""
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            n = self._u.any()
            if n:
                buf += self._u.read(n)
                if expect.encode() in buf:
                    return buf.decode(errors="ignore")
            time.sleep_ms(50)
        raise OSError("AT timeout: " + at)


class GpioButton(_hal.ButtonHAL):
    def __init__(self, pin_num):
        self._pin = machine.Pin(pin_num, machine.Pin.IN,
                                machine.Pin.PULL_UP)

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
        u.cmd("AT+CGATT=1", timeout_ms=30000)
        u.cmd("AT+CNACT=0,1", timeout_ms=30000)
        self._attached = True

    def send_sms(self, number, text):
        self._attach()
        u = self._uart
        u.cmd("AT+CMGF=1")
        u.cmd('AT+CMGS="%s"' % number, expect=">")
        u.cmd(text + chr(26), expect="+CMGS:", timeout_ms=30000)
        return True

    def send_mms(self, number, subject, text, images):
        self._attach()
        u = self._uart
        # DRAFT: validate against the SIM7080G AT manual on the bench.
        u.cmd("AT+CMMSINIT")
        u.cmd("AT+CMMSTERM")
        u.cmd('AT+CMMSDOWN="TEXT",%d,10000' % len(text.encode()),
              expect="CONNECT")
        self._uart._u.write(text.encode())
        u.cmd("", expect="OK")
        for img in images:
            u.cmd('AT+CMMSDOWN="PIC",%d,20000' % len(img), expect="CONNECT")
            for j in range(0, len(img), 1024):
                self._uart._u.write(img[j:j + 1024])
            u.cmd("", expect="OK")
        u.cmd('AT+CMMSSEND="%s"' % number, expect="+CMMSSEND:",
              timeout_ms=60000)
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
            resp = self._uart.cmd("AT+CGNSINF", expect="+CGNSINF:",
                                  timeout_ms=int(timeout_s * 1000))
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
            if camera.init(0, format=camera.JPEG,
                           framesize=camera.FRAME_VGA):
                self._ready = True
                return
            time.sleep_ms(2000)
        raise RuntimeError("OV2640 init failed — check camera connector")

    def capture_jpeg(self, quality):
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


def build_lilygo_pod(board, pmu):
    """Wire the real T-SIM7080G-S3 peripherals. Returns (PodHAL, clock, button_pin)."""
    btn = GpioButton(board.PIN_BUTTON)
    modem = LilyGoModem(board, pmu)
    return (_hal.PodHAL(btn, modem, Ov2640(pmu), modem, PrintLed()),
            DeviceClock(), btn.pin)


def sleep_until_button(board):
    """Deep sleep; wake when the panic button is pressed (active-low).
    On wake the board reboots into main.py and the hold-timer decides."""
    pin = machine.Pin(board.PIN_BUTTON, machine.Pin.IN,
                      machine.Pin.PULL_UP)
    esp32.wake_on_ext0(pin=pin, level=esp32.WAKE_LOW)
    machine.deepsleep()

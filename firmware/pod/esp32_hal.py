# ESP32-S3 hardware implementations for the LILYGO T-SIM7080G-S3.
# DRAFT — AT sequences must be validated against the SIMCom SIM7080G
# AT Command Manual on real hardware before trusting them.
# Copy this whole pod/ directory onto the board; main.py wires it up.

try:
    import machine
    import time
    _ON_DEVICE = True
except ImportError:
    _ON_DEVICE = False

from . import hal as _hal
from . import config as _cfg


class _Uart:
    def __init__(self, cfg):
        self._u = machine.UART(cfg.UART_MODEM_ID,
                               baudrate=cfg.UART_MODEM_BAUD,
                               tx=cfg.PIN_UART_TX, rx=cfg.PIN_UART_RX,
                               timeout=1000)

    def cmd(self, at, expect="OK", timeout_ms=10000):
        self._u.write((at + "\r\n").encode())
        deadline = time.ticks_ms() + timeout_ms
        buf = b""
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = self._u.read()
            if chunk:
                buf += chunk
                if expect.encode() in buf:
                    return buf.decode(errors="ignore")
            time.sleep_ms(50)
        raise OSError("AT timeout: " + at + " -> " + buf.decode(errors="ignore")[-120:])


class GpioButton(_hal.ButtonHAL):
    def __init__(self, cfg):
        self._pin = machine.Pin(cfg.PIN_BUTTON, machine.Pin.IN,
                                machine.Pin.PULL_UP)

    def is_pressed(self):
        return self._pin.value() == 0  # active-low


class Sim7080Gps(_hal.GpsHAL):
    def __init__(self, uart):
        self._u = uart

    def power_on(self):
        self._u.cmd("AT+CGNSPWR=1")

    def power_off(self):
        try:
            self._u.cmd("AT+CGNSPWR=0")
        except OSError:
            pass

    def get_fix(self, timeout_s):
        # DRAFT: validate +CGNSINF field layout against the manual.
        resp = self._u.cmd("AT+CGNSINF", expect="+CGNSINF:",
                           timeout_ms=int(timeout_s * 1000))
        for line in resp.splitlines():
            if "+CGNSINF:" in line:
                f = line.split(":")[1].strip().split(",")
                # f[0]=run status, f[1]=fix status, f[3]=lat, f[4]=lon
                if len(f) > 4 and f[1] == "1":
                    try:
                        return (float(f[3]), float(f[4]))
                    except ValueError:
                        return None
        return None


class Ov2640(_hal.CameraHAL):
    def __init__(self):
        import camera  # MicroPython camera driver for ESP32
        camera.init(0, format=camera.JPEG)
        self._cam = camera

    def capture_jpeg(self, quality):
        # quality tuning is driver-specific; kept simple for the proof model
        return self._cam.capture()


class Sim7080Modem(_hal.ModemHAL):
    """SIM7080G via AT. DRAFT sequences — validate on hardware."""

    def __init__(self, uart, cfg):
        self._u = uart
        self._cfg = cfg
        self._attached = False

    def _attach(self):
        if self._attached:
            return
        self._u.cmd("AT")
        self._u.cmd("AT+CGATT=1", timeout_ms=30000)
        # PDP context for the $10/mo consumer line's APN:
        self._u.cmd('AT+CGDCONT=1,"IP","%s"' % self._cfg.CARRIER_APN)
        self._u.cmd("AT+CNACT=0,1", timeout_ms=30000)
        self._attached = True

    def send_sms(self, number, text):
        self._attach()
        self._u.cmd("AT+CMGF=1")
        self._u.cmd('AT+CMGS="%s"' % number, expect=">")
        self._u.cmd(text + chr(26), expect="+CMGS:")
        return True

    def send_mms(self, number, subject, text, images):
        self._attach()
        u, c = self._u, self._cfg
        u.cmd("AT+CMMSINIT")
        u.cmd('AT+CMMSTERM="%s"' % c.CARRIER_MMSC_URL)
        u.cmd('AT+CMMSPROTO="%s",%d' % (c.CARRIER_MMS_PROXY,
                                       c.CARRIER_MMS_PROXY_PORT))
        # text part
        tb = text.encode()
        u.cmd('AT+CMMSDOWN="TEXT",%d,10000' % len(tb), expect="CONNECT")
        u._u.write(tb)
        u.cmd("", expect="OK")
        # photo parts
        for i, img in enumerate(images):
            u.cmd('AT+CMMSDOWN="PIC",%d,20000' % len(img), expect="CONNECT")
            # chunked write: UART buffers are small on the S3
            for j in range(0, len(img), 1024):
                u._u.write(img[j:j + 1024])
            u.cmd("", expect="OK")
        u.cmd('AT+CMMSSEND="%s"' % number, expect="+CMMSSEND:",
              timeout_ms=60000)
        u.cmd("AT+CMMSTERM")
        return True


class RgbLed(_hal.LedHAL):
    _MAP = {"off": (0, 0, 0), "red": (1, 0, 0), "green": (0, 1, 0),
            "blue": (0, 0, 1), "amber": (1, 1, 0)}

    def __init__(self, cfg):
        self._pins = {
            "r": machine.Pin(cfg.PIN_LED_R, machine.Pin.OUT),
            "g": machine.Pin(cfg.PIN_LED_G, machine.Pin.OUT),
            "b": machine.Pin(cfg.PIN_LED_B, machine.Pin.OUT),
        }

    def set(self, color):
        r, g, b = self._MAP.get(color, (0, 0, 0))
        self._pins["r"].value(r)
        self._pins["g"].value(g)
        self._pins["b"].value(b)


class DeviceClock(_hal.Clock):
    def now_ms(self):
        return time.ticks_ms()


def build_pod(cfg):
    """Wire the real peripherals and return (PodHAL, DeviceClock)."""
    uart = _Uart(cfg)
    return (_hal.PodHAL(GpioButton(cfg), Sim7080Gps(uart), Ov2640(),
                        Sim7080Modem(uart, cfg), RgbLed(cfg)),
            DeviceClock())

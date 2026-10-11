# Hardware Abstraction Layer — the contract every platform implements.
# pod/alert.py only talks to these interfaces, so the same alert logic runs
# on the ESP32-S3 (pod/esp32_hal.py) and in the PC simulator (sim/mock_hal.py).


class ButtonHAL:
    def is_pressed(self):
        """True while the panic button is physically held down."""
        raise NotImplementedError


class GpsHAL:
    def power_on(self):
        raise NotImplementedError

    def power_off(self):
        raise NotImplementedError

    def get_fix(self, timeout_s):
        """Block up to timeout_s. Returns (lat, lon) floats or None."""
        raise NotImplementedError


class CameraHAL:
    def capture_jpeg(self, quality):
        """Returns JPEG bytes of one still frame."""
        raise NotImplementedError


class ModemHAL:
    def send_sms(self, number, text):
        """Returns True on delivered-to-modem."""
        raise NotImplementedError

    def send_mms(self, number, subject, text, images):
        """images = list of JPEG bytes. Returns True on accepted."""
        raise NotImplementedError


class LedHAL:
    def set(self, color):
        """color: 'off', 'red', 'green', 'blue', 'amber'."""
        raise NotImplementedError


class PodHAL:
    """One object carrying all five peripherals."""

    def __init__(self, button, gps, camera, modem, led):
        self.button = button
        self.gps = gps
        self.camera = camera
        self.modem = modem
        self.led = led


class Clock:
    """Milliseconds clock — time.ticks_ms() on device, time.monotonic on PC."""

    def now_ms(self):
        raise NotImplementedError

    def diff_ms(self, newer, older):
        """Wrap-safe newer - older. MUST be used for all time math:
        MicroPython ticks_ms() wraps every ~12 days."""
        raise NotImplementedError

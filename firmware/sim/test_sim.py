# Pytest suite for the hoodie-pod proof model.
#
# Runs the SAME pod/ alert logic as sim/run.py against the PC mocks —
# pure Python, no hardware needed. Covers the golden path, every rung
# of the fallback ladder, the hold-to-trigger button, the HAL contract,
# and wrap-safe timing (MicroPython ticks_ms() wraps ~every 12 days,
# so all time math must go through Clock.diff_ms).
import glob
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pod import alert, button, config, esp32_hal, hal  # noqa: E402
from sim import mock_hal  # noqa: E402

FIRMWARE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- fixtures


@pytest.fixture()
def outbox(tmp_path, monkeypatch):
    """Redirect the mock modem's outbox into a temp dir per test."""
    box = tmp_path / "outbox"
    box.mkdir()
    monkeypatch.setattr(mock_hal, "OUTBOX", str(box))
    return box


@pytest.fixture()
def fast_cfg(monkeypatch):
    """Shrink the real-world timings so the suite stays quick.

    Values mirror config.py's ratios; one test below keeps the true
    2-second hold to prove the documented behavior.
    """
    monkeypatch.setattr(config, "BUTTON_HOLD_SECONDS", 0.3)
    monkeypatch.setattr(config, "GPS_FIX_TIMEOUT_S", 3)
    monkeypatch.setattr(config, "GPS_MODEM_SETTLE_MS", 100)
    return config


def drive_alert(pod, btn, hold_s=0.3, tick_ms=50, timeout_s=30):
    """Hold the mock button and tick the pod until it reaches DONE."""
    btn.held = True
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        pod.tick()
        if pod.state == alert.DONE:
            btn.held = False
            return pod.last_result
        time.sleep(tick_ms / 1000.0)
    raise TimeoutError("pod never reached DONE")


def outbox_files(outbox, pattern):
    return sorted(glob.glob(os.path.join(str(outbox), pattern)))


def read(path):
    with open(path) as f:
        return f.read()


# ------------------------------------------------------------- golden path


def test_golden_path(outbox, fast_cfg):
    """2s hold -> GPS fix -> 3 photos -> MMS + SMS with maps link."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=True sms=True photos=3"

    mms = outbox_files(outbox, "mms_*.txt")
    sms = outbox_files(outbox, "sms_*.txt")
    photos = outbox_files(outbox, "photo_*.jpg")
    assert len(mms) == 1 and len(sms) == 1 and len(photos) == 3

    sms_text = read(sms[0])
    assert "HOODIE ALERT" in sms_text
    assert "maps.google.com/?q=" in sms_text
    assert str(mock_hal.TEST_LAT)[:6] in sms_text
    assert "[ATTACHED: 3 JPEG photos]" in read(mms[0])


def test_real_two_second_hold(outbox, fast_cfg, monkeypatch):
    """The documented hold time really is 2 seconds on unpatched config."""
    monkeypatch.setattr(config, "BUTTON_HOLD_SECONDS", 2.0)
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.1)
    pod = alert.AlertPod(pod_hal, config, clock)
    pb = button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    pod.attach_button(pb)

    mock_btn.held = True
    t0 = time.monotonic()
    fired_after = None
    while time.monotonic() - t0 < 3.0:
        now = clock.now_ms()
        if pb.update(now) and fired_after is None:
            fired_after = time.monotonic() - t0
        pod.tick()
        time.sleep(0.02)
    mock_btn.held = False

    assert fired_after is not None, "2s hold never fired the alert"
    assert fired_after >= 2.0, "fired before the full hold elapsed"


# ------------------------------------------------------ fallback ladder


def test_no_mms_falls_back_to_sms(outbox, fast_cfg):
    """MMS rejected -> retry once -> SMS-only with PHOTOS PENDING."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(fail_mms=True, gps_delay_s=0.5)
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=False sms=True photos=3"

    assert outbox_files(outbox, "mms_*.txt") == []
    sms = outbox_files(outbox, "sms_*.txt")
    assert len(sms) == 1
    assert "PHOTOS PENDING" in read(sms[0])
    # photos=3 in the result above proves the 3 JPEGs were captured in
    # memory — only the MMS transport fell back, not the camera.


def test_no_gps_fix_still_sends_flagged(outbox, fast_cfg):
    """No fix in the timeout -> alert goes out anyway, flagged."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_fail=True)
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=True sms=True photos=3"

    sms = outbox_files(outbox, "sms_*.txt")
    assert len(sms) == 1
    sms_text = read(sms[0])
    assert "no GPS fix" in sms_text
    assert "maps.google.com" not in sms_text  # no coords, no link


def test_camera_failure_sends_location_only(outbox, fast_cfg):
    """Camera dies -> location-only alert still goes out (no MMS)."""

    class DeadCamera:
        def capture_jpeg(self, quality):
            raise RuntimeError("simulated OV2640 failure")

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod_hal.camera = DeadCamera()
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=False sms=True photos=0"

    sms = outbox_files(outbox, "sms_*.txt")
    assert len(sms) == 1
    assert "maps.google.com/?q=" in read(sms[0])  # location beats nothing


# ------------------------------------------------------------- the button


def test_tap_never_fires(fast_cfg):
    """A bump shorter than the hold time must never fire an alert."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal()
    pod = alert.AlertPod(pod_hal, config, clock)
    pb = button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    pod.attach_button(pb)

    fired = False
    mock_btn.held = True
    t0 = time.monotonic()
    while time.monotonic() - t0 < 0.1:  # tap: well under the 0.3s hold
        pod.tick()
        fired = fired or pb.update(clock.now_ms())
        time.sleep(0.02)
    mock_btn.held = False
    t0 = time.monotonic()
    while time.monotonic() - t0 < 0.5:
        pod.tick()
        time.sleep(0.02)

    assert not fired
    assert pod.state == alert.IDLE
    assert pod.last_result == ""


def test_hold_fires_exactly_once(outbox, fast_cfg):
    """One deliberate hold -> exactly one alert, even if held longer."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.1)
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    mock_btn.held = True
    completions = 0
    seen = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 8:  # long enough for two full cycles
        pod.tick()
        if pod.state == alert.DONE and pod.last_result != seen:
            completions += 1
            seen = pod.last_result
        time.sleep(0.02)
    mock_btn.held = False

    assert completions == 1
    assert seen == "mms=True sms=True photos=3"


def test_hold_progress_ramps(fast_cfg):
    """hold_progress() drives the kid-facing LED: 0.0 -> 1.0."""
    _hal, clock, mock_btn = mock_hal.build_mock_hal()
    pb = button.PanicButton(mock_btn, config.BUTTON_HOLD_SECONDS, clock)

    assert pb.hold_progress(clock.now_ms()) == 0.0
    mock_btn.held = True
    t0 = time.monotonic()
    peak = 0.0
    while time.monotonic() - t0 < 0.6:
        pb.update(clock.now_ms())
        peak = max(peak, pb.hold_progress(clock.now_ms()))
        time.sleep(0.02)
    mock_btn.held = False

    assert peak == pytest.approx(1.0)


# ------------------------------------------------------- wrap-safe timing


class WrapClock(hal.Clock):
    """Mimics MicroPython time.ticks_ms()/ticks_diff(): 30-bit wrap."""

    PERIOD = 2**30

    def __init__(self, start=0):
        self.t = start

    def now_ms(self):
        return self.t % self.PERIOD

    def diff_ms(self, newer, older):
        d = (newer - older) % self.PERIOD
        return d - self.PERIOD if d >= self.PERIOD // 2 else d

    def advance(self, ms):
        self.t += ms


class FakeButton(hal.ButtonHAL):
    def __init__(self):
        self.held = False

    def is_pressed(self):
        return self.held


class FakeGps(hal.GpsHAL):
    def __init__(self, fix=None):
        self.fix = fix

    def power_on(self):
        pass

    def power_off(self):
        pass

    def get_fix(self, timeout_s):
        return self.fix


class FakeCamera(hal.CameraHAL):
    def capture_jpeg(self, quality):
        return b"\xff\xd8fakejpeg\xff\xd9"


class FakeModem(hal.ModemHAL):
    def __init__(self):
        self.sms = []
        self.mms = []

    def send_sms(self, number, text):
        self.sms.append((number, text))
        return True

    def send_mms(self, number, subject, text, images):
        self.mms.append((number, subject, text, images))
        return True


class FakeLed(hal.LedHAL):
    def __init__(self):
        self.color = "off"

    def set(self, color):
        self.color = color


def wrap_pod(clk, fix=(39.2462, -94.4102)):
    btn = FakeButton()
    pod_hal = hal.PodHAL(btn, FakeGps(fix=fix), FakeCamera(), FakeModem(), FakeLed())
    pod = alert.AlertPod(pod_hal, config, clk)
    pod.attach_button(button.PanicButton(btn, 2.0, clk))
    return pod, btn


def test_button_hold_fires_across_ticks_wrap():
    """The 2s hold still measures correctly when ticks_ms() wraps mid-hold."""
    start = (WrapClock.PERIOD - 500) % WrapClock.PERIOD  # 500ms before wrap
    clk = WrapClock(start=start)
    btn_hal = FakeButton()
    pb = button.PanicButton(btn_hal, 2.0, clk)

    btn_hal.held = True
    fired_at = None
    for _ in range(100):  # 5s of pod time, crossing the wrap
        clk.advance(50)
        if pb.update(clk.now_ms()):
            fired_at = clk.now_ms()
            break

    assert fired_at is not None, "hold never fired across the wrap"
    assert clk.diff_ms(fired_at, start) >= 2000


def test_full_alert_across_ticks_wrap():
    """Golden path completes when ticks_ms() wraps mid-alert."""
    clk = WrapClock(start=WrapClock.PERIOD - 1000)  # 1s before wrap
    pod, btn = wrap_pod(clk)
    btn.held = True
    for _ in range(400):  # 20s of pod time
        clk.advance(50)
        pod.tick()
        if pod.state == alert.DONE:
            break
    else:
        pytest.fail("pod never finished across the wrap")

    assert pod.last_result == "mms=True sms=True photos=3"


def test_gps_timeout_across_ticks_wrap():
    """The 90s GPS give-up must also be wrap-safe (raw now+deadline is not)."""
    clk = WrapClock(start=WrapClock.PERIOD - 1000)
    pod, btn = wrap_pod(clk, fix=None)  # never fixes
    btn.held = True
    for _ in range(2400):  # 120s of pod time, crossing wrap + 90s timeout
        clk.advance(50)
        pod.tick()
        if pod.state == alert.DONE:
            break
    else:
        pytest.fail("pod stuck in ACQUIRING across the wrap")

    assert pod.last_result == "mms=True sms=True photos=3"
    assert "no GPS fix" in pod._hal.modem.sms[0][1]


# ------------------------------------------------- contracts and hygiene


def test_hal_contract():
    """Every platform HAL exposes the five peripherals + wrap-safe clock."""
    pod_hal, clock, _btn = mock_hal.build_mock_hal()
    assert isinstance(pod_hal, hal.PodHAL)
    for name in ("button", "gps", "camera", "modem", "led"):
        assert getattr(pod_hal, name) is not None, name
    assert callable(pod_hal.button.is_pressed)
    assert callable(pod_hal.gps.get_fix)
    assert callable(pod_hal.camera.capture_jpeg)
    assert callable(pod_hal.modem.send_sms)
    assert callable(pod_hal.modem.send_mms)
    assert callable(pod_hal.led.set)
    assert callable(clock.now_ms) and callable(clock.diff_ms)


def test_carrier_config_placeholders_present():
    """config.py ships FILL-IN placeholders so real carrier credentials
    never land in the repo; flashing requires filling them first."""
    assert config.CARRIER_APN.startswith("REPLACE_WITH")
    assert config.CARRIER_MMSC_URL.startswith("REPLACE_WITH")
    assert config.CARRIER_MMS_PROXY.startswith("REPLACE_WITH")
    assert config.PARENT_NUMBER  # non-empty so the sim has a recipient


def test_draft_markers_on_unvalidated_at_sequences():
    """The SIM7080G AT sequences stay marked DRAFT until bench-validated."""
    src = (FIRMWARE_DIR / "pod" / "esp32_hal.py").read_text()
    assert "DRAFT" in src


# ------------------------------------------------- AT command safety


def test_at_number_accepts_real_numbers():
    assert esp32_hal._at_number("+18165558418") == "+18165558418"
    assert esp32_hal._at_number("8165558418") == "8165558418"


def test_at_number_rejects_injection():
    """A quote or control char in the dial string would escape the quoted
    AT string and inject modem commands — refuse it instead."""
    for bad in ('+1";AT+CMGS="x', "1\rATZ", "", "+", "++1"):
        with pytest.raises(ValueError):
            esp32_hal._at_number(bad)


def test_at_param_rejects_quotes_and_control_chars():
    for bad in ('apn";ATZ', "apn\r\n", "apn\t"):
        with pytest.raises(ValueError):
            esp32_hal._at_param(bad, "carrier param")
    assert (
        esp32_hal._at_param("fast.t-mobile.com", "carrier param") == "fast.t-mobile.com"
    )


def test_at_text_strips_framing_chars():
    """The SMS/MMS body is an AT line ended by Ctrl-Z; embedded CR/LF/
    Ctrl-Z would split it into extra AT commands — strip them."""
    assert esp32_hal._at_text("HOODIE ALERT plain text") == "HOODIE ALERT plain text"
    assert esp32_hal._at_text("a\r\nb\x1ac") == "abc"


# -------------------------------------- pass 2: concurrency + edge cases


def test_modem_dies_mid_mms_still_sends_sms(outbox, fast_cfg):
    """Modem dies mid-MMS (OSError, not a polite False) -> retry once ->
    SMS-only fallback with PHOTOS PENDING. No crash, no silent drop."""

    class DyingModem(mock_hal.MockModem):
        def __init__(self):
            super().__init__(fail_mms=False)
            self.attempts = 0

        def send_mms(self, number, subject, text, images):
            self.attempts += 1
            raise OSError("simulated modem death mid-MMS")

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    dying = DyingModem()
    pod_hal.modem = dying
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=False sms=True photos=3"
    assert dying.attempts == config.MMS_RETRIES + 1  # initial + one retry
    sms = outbox_files(outbox, "sms_*.txt")
    assert len(sms) == 1
    assert "PHOTOS PENDING" in read(sms[0])


def test_camera_dies_mid_capture_sends_partial(outbox, fast_cfg):
    """Camera dies on the 2nd of 3 captures -> MMS goes out with the one
    good frame (evidence beats completeness), result records photos=1."""

    class FlakyCamera:
        def __init__(self):
            self.n = 0

        def capture_jpeg(self, quality):
            self.n += 1
            if self.n > 1:
                raise RuntimeError("simulated mid-capture death")
            return b"\xff\xd8fake\xff\xd9"

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod_hal.camera = FlakyCamera()
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=True sms=True photos=1"
    assert len(outbox_files(outbox, "photo_*.jpg")) == 1


def test_button_mashed_during_alert_phases_ignored(outbox, fast_cfg):
    """Button held/released/mashed during ACQUIRING/CAPTURING/SENDING
    can't crash the pod or queue a second alert: the button is only
    polled in IDLE, and a hold fires exactly once."""
    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    mock_btn.held = True
    results = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        pod.tick()
        if pod.state != alert.IDLE:
            mock_btn.held = not mock_btn.held  # mash during alert phases
        if pod.state == alert.DONE:
            results.append(pod.last_result)
            break
        time.sleep(0.02)

    assert results == ["mms=True sms=True photos=3"]
    assert len(outbox_files(outbox, "mms_*.txt")) == 1


def test_no_photos_sms_names_camera_failure(outbox, fast_cfg):
    """Camera dead -> the SMS says NO PHOTOS (camera failed), NOT
    PHOTOS PENDING: there is nothing pending."""

    class DeadCamera:
        def capture_jpeg(self, quality):
            raise RuntimeError("simulated OV2640 failure")

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod_hal.camera = DeadCamera()
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=False sms=True photos=0"
    sms_text = read(outbox_files(outbox, "sms_*.txt")[0])
    assert "NO PHOTOS" in sms_text
    assert "PHOTOS PENDING" not in sms_text


def test_alert_crash_still_tries_bare_sms(outbox, fast_cfg, monkeypatch):
    """GPS power_on blows up (dead modem, an exception the fallback
    ladder doesn't catch) -> run_alert_loop must NOT let it escape:
    best-effort bare SMS goes out and the loop returns 'pod-error'."""
    from pod import main as pod_main

    class DeadGps:
        def power_on(self):
            raise OSError("simulated dead modem on GPS power-on")

        def power_off(self):
            pass

        def get_fix(self, timeout_s):
            return None

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.1)
    pod_hal.gps = DeadGps()

    class SimTime:
        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    monkeypatch.setattr(pod_main, "time", SimTime)

    mock_btn.held = True  # trigger the alert so GPS power_on runs
    result = pod_main.run_alert_loop(pod_hal, clock)
    assert result == "pod-error"

    sms = outbox_files(outbox, "sms_*.txt")
    assert len(sms) == 1
    assert "Pod error mid-alert" in read(sms[0])


def test_config_validate_flags_placeholders():
    """Shipped config.py still has the carrier placeholders -> validate()
    flags exactly those three, and nothing else."""
    problems = config.validate()
    assert len(problems) == 3
    assert all("placeholder" in p for p in problems)


def test_config_validate_passes_when_filled(monkeypatch):
    monkeypatch.setattr(config, "CARRIER_APN", "fast.t-mobile.com")
    monkeypatch.setattr(config, "CARRIER_MMSC_URL", "http://mmsc.example")
    monkeypatch.setattr(config, "CARRIER_MMS_PROXY", "10.0.0.1")
    assert config.validate() == []


def test_config_validate_catches_bad_number(monkeypatch):
    monkeypatch.setattr(config, "PARENT_NUMBER", "")
    assert any("PARENT_NUMBER" in p for p in config.validate())


def test_outbox_pruned_to_cap(outbox):
    """60 stale files in the outbox -> creating a MockModem prunes to
    OUTBOX_MAX_FILES so repeated runs can't fill the disk."""
    for i in range(60):
        (Path(str(outbox)) / ("old_%02d.txt" % i)).write_text("x")
        time.sleep(0.001)  # distinct mtimes so pruning is deterministic
    mock_hal.MockModem()
    assert len(os.listdir(str(outbox))) <= mock_hal.OUTBOX_MAX_FILES


def test_same_second_sends_keep_distinct_files(outbox):
    """Two sends in the same wall-clock second must not overwrite each
    other (the old int(time.time()) names collided)."""
    m = mock_hal.MockModem()
    m.send_sms("+10000000000", "a")
    m.send_sms("+10000000000", "b")
    assert len(outbox_files(outbox, "sms_*.txt")) == 2


# -------------------------------------- pass 3: bug hunt round 2


def test_camera_none_frame_is_a_failure_not_a_photo(outbox, fast_cfg):
    """A camera driver can hand back None instead of raising on a failed
    capture. The None must not be counted as a photo: it used to poison
    the whole MMS (the modem send touches every frame), losing the good
    frames and reporting photos=3 for an alert that delivered none."""

    class NoneSecondCamera:
        def __init__(self):
            self.n = 0

        def capture_jpeg(self, quality):
            self.n += 1
            if self.n == 2:
                return None
            return b"\xff\xd8fake\xff\xd9"

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod_hal.camera = NoneSecondCamera()
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=True sms=True photos=1"
    assert len(outbox_files(outbox, "photo_*.jpg")) == 1
    sms_text = read(outbox_files(outbox, "sms_*.txt")[0])
    assert "PHOTOS PENDING" not in sms_text


def test_camera_empty_frames_send_location_only(outbox, fast_cfg):
    """Empty-byte frames are failed captures too: zero usable photos ->
    the location-only ladder rung, with the honest NO PHOTOS wording."""

    class EmptyCamera:
        def capture_jpeg(self, quality):
            return b""

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    pod_hal.camera = EmptyCamera()
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=False sms=True photos=0"
    sms_text = read(outbox_files(outbox, "sms_*.txt")[0])
    assert "NO PHOTOS" in sms_text


class ColdBootGps(hal.GpsHAL):
    """GPS whose power_on burns 12 s of clock (a cold modem waking from
    deep sleep: AT retries + PWRKEY pulse + boot) and whose fix becomes
    available 85 s after power-on completes."""

    def __init__(self, clock):
        self._clock = clock
        self._fix_at = None

    def power_on(self):
        self._clock.advance(12000)
        self._fix_at = self._clock.now_ms() + 85000

    def power_off(self):
        pass

    def get_fix(self, timeout_s):
        if self._fix_at is not None and self._clock.now_ms() >= self._fix_at:
            return (39.2462, -94.4102)
        return None


def test_fix_window_starts_when_gps_powers_on():
    """The 90 s fix window is for fix attempts. The ~12 s cold-boot inside
    power_on — during which a fix is impossible — must not be charged
    against it, or every deep-sleep wake (modem rail cut = always cold)
    silently shrinks the window. Fix lands 85 s after power-on: inside
    the window measured from power-on, outside it measured from the
    button trigger (85 + 12 = 97 s)."""
    clk = WrapClock()
    btn = FakeButton()
    modem = FakeModem()
    pod_hal = hal.PodHAL(btn, ColdBootGps(clk), FakeCamera(), modem, FakeLed())
    pod = alert.AlertPod(pod_hal, config, clk)
    pod.attach_button(button.PanicButton(btn, 0.3, clk))

    btn.held = True
    for _ in range(4000):  # 200 s of pod time
        clk.advance(50)
        pod.tick()
        if pod.state == alert.DONE:
            break
    else:
        pytest.fail("pod never finished")

    assert pod.last_result == "mms=True sms=True photos=3"
    assert len(modem.sms) == 1
    assert "no GPS fix" not in modem.sms[0][1]
    assert "39.246200" in modem.sms[0][1]


def test_mms_retry_recovers_from_transient_raise(outbox, fast_cfg):
    """Modem raises on the first MMS attempt, succeeds on the retry ->
    the alert is an MMS success and the SMS must NOT claim the photos
    are pending."""

    class FlakyModem(mock_hal.MockModem):
        def __init__(self):
            super().__init__(fail_mms=False)
            self.attempts = 0

        def send_mms(self, number, subject, text, images):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("simulated transient modem failure")
            return super().send_mms(number, subject, text, images)

    pod_hal, clock, mock_btn = mock_hal.build_mock_hal(gps_delay_s=0.5)
    flaky = FlakyModem()
    pod_hal.modem = flaky
    pod = alert.AlertPod(pod_hal, config, clock)
    pod.attach_button(
        button.PanicButton(pod_hal.button, config.BUTTON_HOLD_SECONDS, clock)
    )

    assert drive_alert(pod, mock_btn) == "mms=True sms=True photos=3"
    assert flaky.attempts == 2
    sms_text = read(outbox_files(outbox, "sms_*.txt")[0])
    assert "PHOTOS PENDING" not in sms_text


def test_config_validate_flags_non_int_tunables(monkeypatch):
    """PHOTO_COUNT / MMS_RETRIES feed range() and PHOTO_JPEG_QUALITY the
    JPEG encoder: a float typo (3.0) passes a pure range check but
    raises TypeError mid-alert. validate() exists to catch config typos
    at boot — it must flag the type, not just the range."""
    monkeypatch.setattr(config, "PHOTO_COUNT", 3.0)
    assert any("PHOTO_COUNT" in p for p in config.validate())
    monkeypatch.setattr(config, "PHOTO_COUNT", 3)

    monkeypatch.setattr(config, "MMS_RETRIES", 1.5)
    assert any("MMS_RETRIES" in p for p in config.validate())
    monkeypatch.setattr(config, "MMS_RETRIES", 1)

    monkeypatch.setattr(config, "PHOTO_JPEG_QUALITY", 70.5)
    assert any("PHOTO_JPEG_QUALITY" in p for p in config.validate())


# -------------------------------------- pass 4: sweep 2026-10-19


def test_config_validate_survives_non_numeric_tunables(monkeypatch):
    """validate() must REPORT a typo'd tunable, never raise on it: a
    string/None in a comparison field used to make validate() itself
    raise TypeError, and main() calls it unguarded at boot — the check
    designed to never block the pod became the thing that crashed it.
    (Same family as the non-int PHOTO_COUNT fix in pass 3, which only
    covered the three isinstance-checked fields.)"""
    for name, bad in (
        ("BUTTON_HOLD_SECONDS", "2"),
        ("BUTTON_HOLD_SECONDS", None),
        ("BUTTON_DEBOUNCE_MS", "50"),
        ("GPS_FIX_TIMEOUT_S", None),
        ("GPS_MODEM_SETTLE_MS", "2000"),
        ("MODEM_CMD_TIMEOUT_S", "10"),
    ):
        monkeypatch.setattr(config, name, bad)
        problems = config.validate()  # must not raise
        assert any(name in p for p in problems), (name, bad, problems)
        monkeypatch.undo()


def test_config_validate_flags_bool_and_nan_tunables(monkeypatch):
    """True is an int in Python (== 1) and NaN passes every <= check:
    neither is a sane tunable, and validate() must flag both."""
    monkeypatch.setattr(config, "PHOTO_COUNT", True)
    assert any("PHOTO_COUNT" in p for p in config.validate())
    monkeypatch.undo()
    monkeypatch.setattr(config, "BUTTON_HOLD_SECONDS", float("nan"))
    assert any("BUTTON_HOLD_SECONDS" in p for p in config.validate())


def test_hold_progress_with_zero_hold_does_not_divide_by_zero():
    """PanicButton(hold_s=0).hold_progress() divided by _hold_ms == 0.
    The firmware path never calls hold_progress (validate() flags the
    config), but the sim GUI does — a display helper must not crash."""
    _hal, clock, mock_btn = mock_hal.build_mock_hal()
    pb = button.PanicButton(mock_btn, 0, clock)
    assert pb.hold_progress(clock.now_ms()) == 0.0  # not pressed
    mock_btn.held = True
    pb.update(clock.now_ms())
    assert pb.hold_progress(clock.now_ms()) == 1.0  # zero hold is met


class _FakeModemUart:
    """UART stub for LilyGoModem.get_fix: cmd() replays one CGNSINF line."""

    def __init__(self, line):
        self._line = line

    def cmd(self, at, expect="OK", timeout_ms=None):
        return self._line


def _modem_with_cgnsinf(line):
    modem = object.__new__(esp32_hal.LilyGoModem)
    modem._uart = _FakeModemUart(line)
    return modem


def _cgnsinf(lat, lon):
    return "+CGNSINF: 1,1,20240101000000.000,%s,%s,0.00,0.0,0" % (lat, lon)


def test_get_fix_rejects_out_of_range_coordinates():
    """float() parses anything numeric — including a marginal-fix echo
    of lat=95 or lon=-181, which would hand the parent a maps link to
    nowhere. Out-of-range parses as no-fix, so polling continues."""
    modem = _modem_with_cgnsinf(_cgnsinf("95.000000", "-94.410200"))
    assert modem.get_fix(timeout_s=1) is None
    modem = _modem_with_cgnsinf(_cgnsinf("39.246200", "-181.000000"))
    assert modem.get_fix(timeout_s=1) is None


def test_get_fix_rejects_nan_coordinates():
    modem = _modem_with_cgnsinf(_cgnsinf("nan", "nan"))
    assert modem.get_fix(timeout_s=1) is None


def test_get_fix_accepts_valid_coordinates():
    modem = _modem_with_cgnsinf(_cgnsinf("39.246200", "-94.410200"))
    assert modem.get_fix(timeout_s=1) == (39.2462, -94.4102)


class _FakeTicks:
    """MicroPython-style ticks for esp32_hal.time on a CPython host."""

    def __init__(self):
        self.t = 0

    def ticks_ms(self):
        return self.t

    def ticks_diff(self, newer, older):
        return newer - older

    def sleep_ms(self, ms):
        self.t += ms


class _PartialUart:
    """UART whose write() accepts at most 3 bytes per call (a real
    MicroPython UART write may short-write) and which answers OK."""

    def __init__(self):
        self.written = bytearray()
        self._resp = b""

    def write(self, data):
        n = min(3, len(data))
        self.written += bytes(data[:n])
        if bytes(self.written).endswith(b"\r\n"):
            self._resp = b"\r\nOK\r\n"
        return n

    def any(self):
        return len(self._resp)

    def read(self, n):
        out, self._resp = self._resp[:n], self._resp[n:]
        return out


def test_uart_cmd_survives_partial_writes(monkeypatch):
    """_Uart.cmd used a bare write() for the AT line: a short write
    truncated the command mid-line and the modem waited in silence
    until the timeout. cmd() now goes through write_all."""
    monkeypatch.setattr(esp32_hal, "time", _FakeTicks())
    uart = object.__new__(esp32_hal._Uart)
    uart._u = _PartialUart()
    out = uart.cmd("AT+CMGF=1", timeout_ms=5000)
    assert bytes(uart._u.written) == b"AT+CMGF=1\r\n"
    assert "OK" in out
